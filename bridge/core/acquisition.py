"""Background acquisition runner.

Acquisitions run as a background task so the HTTP request can return promptly:
short acquisitions finish within a grace window and return their full result;
long ones return ``running`` and complete unattended (broadcasting progress and
the final preview over WebSocket). This is also what lets a second request be
rejected as *busy* while the first is still in flight.
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from typing import Any

import numpy as np

from bridge.core.instrument import InstrumentState, InstrumentStatus
from bridge.core.ws_hub import WebSocketHub
from bridge.protocol import commands
from bridge.protocol.client import NotConnectedError, ProtocolClient, ProtocolError
from bridge.protocol.decoder import (
    bytes_per_frame,
    decode_intensity,
    integration_time_unit,
)
from bridge.services.data_location import DataLocation
from bridge.services.file_writer import build_png_metadata, name_suffix, save_acquisition
from bridge.services.preview import make_preview
from bridge.services.reducer import reduce_folder
from bridge.services.sidecar import write_sidecar

# Acquisitions finishing within this window return their full result; longer
# ones return `running` (and finish in the background). Small enough that a
# large multi-frame acquisition is reliably still in flight, large enough that
# typical single/few-frame acquisitions return `done` synchronously.
RESULT_GRACE_S = 0.3

# Multi-iteration intensity acquisitions are sent in batches so the socket
# returns to idle between batches — a safe boundary where health polling can run
# and auto-protect can abort mid-acquisition (the single TCP socket can't be
# polled mid-stream).
BATCH_SIZE = 10


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class IntensityParams:
    def __init__(
        self,
        *,
        bit_depth: int,
        integration_time: float,
        iterations: int,
        roi_width: int,
        overlap: bool,
        pileup_correction: bool,
        timeout_s: float | None,
        sample_name: str | None = None,
        experiment_name: str | None = None,
        notes: str | None = None,
        run_reducer: bool = False,
    ) -> None:
        self.bit_depth = bit_depth
        self.integration_time = integration_time
        self.iterations = iterations
        self.roi_width = roi_width
        self.overlap = overlap
        self.pileup_correction = pileup_correction
        self.timeout_s = timeout_s
        self.sample_name = sample_name
        self.experiment_name = experiment_name
        self.notes = notes
        self.run_reducer = run_reducer

    def png_metadata_kwargs(self) -> dict[str, Any]:
        return {}

    def sidecar_params(self, unit: str) -> dict[str, Any]:
        return {
            "mode": "intensity",
            "bit_depth": self.bit_depth,
            "integration_time": self.integration_time,
            "integration_time_ms": self.integration_time if unit == "ms" else None,
            "integration_time_us": self.integration_time if unit == "us" else None,
            "integration_time_unit": unit,
            "iterations": self.iterations,
            "roi_width": self.roi_width,
            "overlap": self.overlap,
            "pileup_correction": self.pileup_correction,
            "sample_name": self.sample_name,
            "experiment_name": self.experiment_name,
            "notes": self.notes,
        }


class GatedParams:
    def __init__(
        self,
        *,
        bit_depth: int,
        integration_time: float,
        iterations: int,
        gate_steps: int,
        gate_step_size: float,
        gate_offset: int,
        gate_width: int,
        gate_direction: str,
        gate_trigger_source: str,
        overlap: bool,
        stream: bool,
        pileup_correction: bool,
        arbitrary_steps: list[float] | None,
        sample_name: str | None = None,
        experiment_name: str | None = None,
        notes: str | None = None,
        run_reducer: bool = False,
    ) -> None:
        self.bit_depth = bit_depth
        self.integration_time = integration_time
        self.iterations = iterations
        self.gate_steps = gate_steps
        self.gate_step_size = gate_step_size
        self.gate_offset = gate_offset
        self.gate_width = gate_width
        self.gate_direction = gate_direction
        self.gate_trigger_source = gate_trigger_source
        self.overlap = overlap
        self.stream = stream
        self.pileup_correction = pileup_correction
        self.arbitrary_steps = arbitrary_steps
        self.sample_name = sample_name
        self.experiment_name = experiment_name
        self.notes = notes
        self.run_reducer = run_reducer

    @property
    def effective_steps(self) -> int:
        if self.arbitrary_steps:
            return len(self.arbitrary_steps)
        return self.gate_steps

    def png_metadata_kwargs(self) -> dict[str, Any]:
        return {
            "gate_steps": self.effective_steps,
            "gate_step_size_ps": self.gate_step_size,
            "gate_width_ns": float(self.gate_width),
            "gate_offset_ps": float(self.gate_offset),
            "gate_trigger_external": self.gate_trigger_source == "external",
            "gate_arbitrary": bool(self.arbitrary_steps),
        }

    def sidecar_params(self, unit: str) -> dict[str, Any]:
        return {
            "mode": "gated",
            "bit_depth": self.bit_depth,
            "integration_time": self.integration_time,
            "integration_time_ms": self.integration_time if unit == "ms" else None,
            "integration_time_us": self.integration_time if unit == "us" else None,
            "integration_time_unit": unit,
            "iterations": self.iterations,
            "gate_steps": self.effective_steps,
            "gate_step_size_ps": self.gate_step_size,
            "gate_width": self.gate_width,
            "gate_offset": self.gate_offset,
            "gate_direction": self.gate_direction,
            "gate_trigger_source": self.gate_trigger_source,
            "overlap": self.overlap,
            "stream": self.stream,
            "pileup_correction": self.pileup_correction,
            "arbitrary_steps": self.arbitrary_steps,
            "sample_name": self.sample_name,
            "experiment_name": self.experiment_name,
            "notes": self.notes,
        }


class AcquisitionRunner:
    def __init__(
        self,
        protocol: ProtocolClient,
        instrument: InstrumentState,
        hub: WebSocketHub,
        location: DataLocation | str,
        *,
        sensor_size: int = 512,
    ) -> None:
        self._protocol = protocol
        self._instrument = instrument
        self._hub = hub
        self._location = location if isinstance(location, DataLocation) else DataLocation(location)
        self._sensor_size = sensor_size
        self.current: dict[str, Any] | None = None
        # Set after construction (the monitor depends on the runner's siblings).
        self.health_monitor: Any | None = None
        self.calibration_store: Any | None = None

    async def run_intensity(self, params: IntensityParams) -> dict[str, Any]:
        if self._instrument.is_busy:
            return {"status": "error", "message": "instrument busy"}

        await self._instrument.set(InstrumentStatus.ACQUIRING)
        # Single-frame acquires finish within the result grace; the spec expects
        # their first WebSocket frame to be the preview, so only multi-frame
        # runs narrate `busy` first.
        if params.iterations > 1:
            await self._hub.broadcast_busy(mode="intensity", progress=0.0)

        task = asyncio.create_task(self._intensity_op(params))
        self.current = {"mode": "intensity", "task": task, "result": None}

        # Wait slightly past the op's own timeout so a `timeout` result is
        # captured here rather than returned as `running`.
        wait = max(RESULT_GRACE_S, (params.timeout_s or 0.0) + 0.5)
        done, _ = await asyncio.wait({task}, timeout=wait)
        if task in done:
            return task.result()
        return {"status": "running", "mode": "intensity", "total_frames": params.iterations}

    async def _intensity_op(self, params: IntensityParams) -> dict[str, Any]:
        rows = self._sensor_size
        unit = integration_time_unit(params.bit_depth)
        started_at = _now_iso()

        result: dict[str, Any]
        try:
            data, completed, aborted = await self._acquire_io(params)
            result = await asyncio.to_thread(
                self._postprocess, data, params, rows, unit, completed, started_at
            )
            if aborted:
                result["status"] = "aborted"
                result["abort_reason"] = self._instrument.abort_reason
        except TimeoutError:
            await self._protocol.reset()
            result = {"status": "timeout", "message": "acquisition timed out"}
        except NotConnectedError:
            result = {"status": "error", "message": "vendor disconnected"}
        except ProtocolError as exc:
            result = {"status": "error", "message": str(exc)}
        finally:
            await self._instrument.set(InstrumentStatus.IDLE)

        if self.current is not None:
            self.current["result"] = result
        # Preview goes out before the idle-state frame so a client that
        # connected pre-acquire sees the image first (spec ordering).
        if result.get("status") in ("done", "aborted") and "preview" in result:
            await self._hub.broadcast_preview(result["preview"])
        await self._hub.broadcast_state(self._instrument.snapshot())
        return result

    async def _acquire_io(
        self, params: IntensityParams
    ) -> tuple[bytes, int, bool]:
        """Run the acquisition, batching multi-iteration runs.

        Returns ``(data, completed_iterations, aborted)``. Between batches the
        socket is idle (a safe boundary): health polling runs and, if
        auto-protect requested a stop, the run ends early with ``aborted=True``.
        """
        rows = self._sensor_size
        per_frame = bytes_per_frame(
            params.bit_depth, rows, params.roi_width, params.pileup_correction
        )

        if params.iterations <= BATCH_SIZE:
            command = self._intensity_command(params, params.iterations)
            data = await self._send_acquire(
                params, command, params.iterations * per_frame
            )
            return data, params.iterations, False

        chunks: list[bytes] = []
        completed = 0
        aborted = False
        for start in range(0, params.iterations, BATCH_SIZE):
            batch = min(BATCH_SIZE, params.iterations - start)
            command = self._intensity_command(params, batch)
            chunks.append(await self._send_acquire(params, command, batch * per_frame))
            completed += batch
            await self._poll_health()
            if self._instrument.stop_requested:
                aborted = True
                break
        return b"".join(chunks), completed, aborted

    def _intensity_command(self, params: IntensityParams, iterations: int) -> str:
        return commands.intensity(
            bit_depth=params.bit_depth,
            integration_time=params.integration_time,
            iterations=iterations,
            overlap=params.overlap,
            im_width=params.roi_width,
        )

    async def _send_acquire(
        self, params: IntensityParams, command: str, expected: int
    ) -> bytes:
        async def _io() -> bytes:
            await self._protocol.send_command(commands.pileup(params.pileup_correction))
            return await self._protocol.send_acquire(command, expected_bytes=expected)

        if params.timeout_s is not None:
            return await asyncio.wait_for(_io(), params.timeout_s)
        return await _io()

    async def _poll_health(self) -> None:
        if self.health_monitor is not None:
            with contextlib.suppress(Exception):
                await self.health_monitor.poll(force=True)

    def _postprocess(
        self,
        data: bytes,
        params: IntensityParams,
        rows: int,
        unit: str,
        completed: int,
        started_at: str,
    ) -> dict[str, Any]:
        stack = decode_intensity(
            data,
            bit_depth=params.bit_depth,
            rows=rows,
            im_width=params.roi_width,
            iterations=completed,
            pileup=params.pileup_correction,
        )
        result: dict[str, Any] = {
            "status": "done",
            "preview": make_preview(stack[0]),
            "total_frames": completed,
            "integration_time_unit": unit,
            "bytes": len(data),
        }
        result.update(
            self._persist(
                stack,
                mode="intensity",
                params=params,
                unit=unit,
                vendor_frames=completed,
                gate_steps=None,
                started_at=started_at,
            )
        )
        return result

    # --- Persistence ------------------------------------------------------------

    def _persist(
        self,
        stack: np.ndarray,
        *,
        mode: str,
        params: IntensityParams | GatedParams,
        unit: str,
        vendor_frames: int,
        gate_steps: int | None,
        started_at: str,
    ) -> dict[str, Any]:
        """Write the PNG folder + sidecar (and optionally run the reducer).

        Runs synchronously — callers invoke it from a worker thread.
        """
        metadata = build_png_metadata(
            mode=mode,
            integration_time=params.integration_time,
            integration_time_unit=unit,
            iterations=vendor_frames,
            overlap=params.overlap,
            laser_frequency_hz=self._laser_frequency_hz(),
            software_version=self._software_version(),
            taken_at=datetime.now(),
            **params.png_metadata_kwargs(),
        )
        saved = save_acquisition(
            stack,
            base_dir=self._location.base_dir,
            mode=mode,
            bit_depth=params.bit_depth,
            metadata=metadata,
            gate_steps=gate_steps,
            folder_suffix=name_suffix(params.sample_name, params.experiment_name),
        )
        sidecar_path = write_sidecar(
            saved.acq_dir,
            params=params.sidecar_params(unit),
            calibration_state=self._calibration_snapshot(),
            temperatures=self._temperatures(),
            timestamp_start=started_at,
            timestamp_end=_now_iso(),
            png_metadata=metadata,
            frame_count=len(saved.png_files),
        )
        result: dict[str, Any] = {
            "host_path": self._location.display_path(saved.acq_dir),
            "sidecar_path": self._location.display_path(sidecar_path),
        }
        if params.run_reducer:
            reduced = reduce_folder(saved.acq_dir)
            result["reducer_output"] = {
                "meta_json": self._location.display_path(reduced["meta_json"]),
                "movie_npy": self._location.display_path(reduced["movie_npy"]),
                "movie_npy_shape": reduced["movie_npy_shape"],
                "pipeline_compatible": reduced["pipeline_compatible"],
            }
        return result

    def _laser_frequency_hz(self) -> float:
        if self.health_monitor is not None:
            value = float(self.health_monitor.readings_payload()["laser_frequency_hz"])
            if value > 0:
                return value
            return float(self.health_monitor.config.expected_laser_hz)
        return 40e6

    def _temperatures(self) -> dict[str, float]:
        if self.health_monitor is None:
            return {}
        payload = self.health_monitor.readings_payload()
        keys = ("temp_master_fpga", "temp_slave_fpga", "temp_pcb", "temp_chip")
        return {key: float(payload[key]) for key in keys}

    def _calibration_snapshot(self) -> dict[str, Any]:
        if self.calibration_store is None:
            return {}
        snapshot: dict[str, Any] = self.calibration_store.snapshot()
        return snapshot

    def acquisition_context(self) -> dict[str, Any]:
        """Calibration + temperature snapshot for the experiment log."""
        return {
            "calibration_state": self._calibration_snapshot(),
            "temperatures": self._temperatures(),
        }

    def _software_version(self) -> str:
        info = self._protocol.system_info
        if info:
            return str(info.get("sw_version", "unknown"))
        return "unknown"

    # --- Gated ----------------------------------------------------------------

    async def run_gated(self, params: GatedParams) -> dict[str, Any]:
        """Run a gated acquisition synchronously (no busy/timeout spec to honor,
        so the request awaits completion and always returns its full result)."""
        if self._instrument.is_busy:
            return {"status": "error", "message": "instrument busy"}

        await self._instrument.set(InstrumentStatus.ACQUIRING)
        await self._hub.broadcast_busy(mode="gated", progress=0.0)
        try:
            return await self._gated_op(params)
        except NotConnectedError:
            return {"status": "error", "message": "vendor disconnected"}
        except ProtocolError as exc:
            return {"status": "error", "message": str(exc)}
        finally:
            await self._instrument.set(InstrumentStatus.IDLE)
            await self._hub.broadcast_state(self._instrument.snapshot())

    async def _gated_op(self, params: GatedParams) -> dict[str, Any]:
        rows = self._sensor_size
        gate_steps = params.effective_steps
        started_at = _now_iso()
        n_frames = params.iterations * gate_steps
        expected = n_frames * bytes_per_frame(
            params.bit_depth, rows, rows, params.pileup_correction
        )
        unit = integration_time_unit(params.bit_depth)
        command = commands.gated(
            bit_depth=params.bit_depth,
            integration_time=params.integration_time,
            iterations=params.iterations,
            gate_steps=gate_steps,
            gate_step_size=params.gate_step_size,
            gate_offset=params.gate_offset,
            gate_width=params.gate_width,
            gate_direction=params.gate_direction,
            gate_trigger_source=params.gate_trigger_source,
            overlap=params.overlap,
            stream=params.stream,
            arbitrary=bool(params.arbitrary_steps),
        )

        await self._protocol.send_command(commands.pileup(params.pileup_correction))
        if params.arbitrary_steps:
            await self._protocol.send_command(commands.arbitrary_steps(params.arbitrary_steps))
        data = await self._protocol.send_acquire(command, expected_bytes=expected)

        stack = await asyncio.to_thread(
            decode_intensity,
            data,
            bit_depth=params.bit_depth,
            rows=rows,
            im_width=rows,
            iterations=n_frames,
            pileup=params.pileup_correction,
        )

        previews_sent = 0
        for step in range(gate_steps):
            await self._hub.broadcast_preview(
                make_preview(stack[step]), index=step, count=gate_steps
            )
            previews_sent += 1

        persisted = await asyncio.to_thread(
            self._persist,
            stack,
            mode="gated",
            params=params,
            unit=unit,
            vendor_frames=params.iterations,
            gate_steps=gate_steps,
            started_at=started_at,
        )
        return {
            "status": "done",
            "preview": make_preview(stack[0]),
            "total_gate_steps": gate_steps,
            "previews_sent": previews_sent,
            "total_frames": n_frames,
            "integration_time_unit": unit,
            "bytes": len(data),
            **persisted,
        }
