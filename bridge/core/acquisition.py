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
from bridge.services.dark_reference import (
    apply_dark_correction,
    gated_fingerprint,
    intensity_fingerprint,
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
        dark_reference_id: str | None = None,
        purpose: str | None = None,
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
        self.dark_reference_id = dark_reference_id
        # e.g. "intensity_dark_reference" — marks a reference measurement.
        self.purpose = purpose

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
            "dark_reference_id": self.dark_reference_id,
            "purpose": self.purpose,
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
        dark_reference_id: str | None = None,
        purpose: str | None = None,
        cooloff_s: float = 0.0,
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
        self.dark_reference_id = dark_reference_id
        # e.g. "gated_dark_reference" — marks a run whose data serves as a
        # reference measurement rather than a scientific acquisition.
        self.purpose = purpose
        # > 0 switches to the PACED path: one single-step vendor command per
        # gate offset with this sleep between steps, letting the sensor cool
        # off (DCR is heat-driven). 0 = the normal single continuous command.
        self.cooloff_s = cooloff_s

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
            "dark_reference_id": self.dark_reference_id,
            "purpose": self.purpose,
            "cooloff_s": self.cooloff_s,
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
        self.dark_reference_store: Any | None = None

    async def run_intensity(
        self, params: IntensityParams, *, keep_stack: bool = False
    ) -> dict[str, Any]:
        """Run an intensity acquisition.

        ``keep_stack`` (in-process callers only, e.g. the dark-reference
        builder) always awaits completion and attaches the raw decoded stack
        under ``"_stack"``; it must be popped before serialization.
        """
        if self._instrument.is_busy:
            return {"status": "error", "message": "instrument busy"}

        await self._instrument.set(InstrumentStatus.ACQUIRING)
        # Single-frame acquires finish within the result grace; the spec expects
        # their first WebSocket frame to be the preview, so only multi-frame
        # runs narrate `busy` first.
        if params.iterations > 1:
            await self._hub.broadcast_busy(mode="intensity", progress=0.0)

        task = asyncio.create_task(self._intensity_op(params, keep_stack=keep_stack))
        self.current = {"mode": "intensity", "task": task, "result": None}

        if keep_stack:
            return await task

        # Wait slightly past the op's own timeout so a `timeout` result is
        # captured here rather than returned as `running`.
        wait = max(RESULT_GRACE_S, (params.timeout_s or 0.0) + 0.5)
        done, _ = await asyncio.wait({task}, timeout=wait)
        if task in done:
            return task.result()
        return {"status": "running", "mode": "intensity", "total_frames": params.iterations}

    async def _intensity_op(
        self, params: IntensityParams, *, keep_stack: bool = False
    ) -> dict[str, Any]:
        rows = self._sensor_size
        unit = integration_time_unit(params.bit_depth)
        started_at = _now_iso()

        reference, dark_provenance, ref_error = self._resolve_dark_reference(
            params.dark_reference_id, intensity_fingerprint(params)
        )
        if ref_error is not None:
            await self._instrument.set(InstrumentStatus.IDLE)
            await self._hub.broadcast_state(self._instrument.snapshot())
            return {"status": "error", "message": ref_error}

        result: dict[str, Any]
        try:
            data, completed, aborted = await self._acquire_io(params)
            result = await asyncio.to_thread(
                self._postprocess,
                data,
                params,
                rows,
                unit,
                completed,
                started_at,
                reference=reference,
                dark_provenance=dark_provenance,
                keep_stack=keep_stack,
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
        except ValueError as exc:
            result = {"status": "error", "message": f"dark correction failed: {exc}"}
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

    async def capture_live_frame(self, params: IntensityParams) -> dict[str, Any]:
        """One quick, unpersisted intensity frame for the on-demand live view.

        Unlike :meth:`run_intensity`, nothing is written to disk, no reducer
        runs, and nothing is logged to the experiment log — this is a
        focus/alignment aid, not a scientific acquisition. Callers pass
        ``iterations=1``; the busy guard and single-socket serialization are
        the same as any other acquisition, so this only ever holds the socket
        for the duration of one short capture.
        """
        if self._instrument.is_busy:
            return {"status": "error", "message": "instrument busy"}

        await self._instrument.set(InstrumentStatus.ACQUIRING)
        result: dict[str, Any]
        try:
            data, completed, _aborted = await self._acquire_io(params)
            stack = await asyncio.to_thread(
                decode_intensity,
                data,
                bit_depth=params.bit_depth,
                rows=self._sensor_size,
                im_width=params.roi_width,
                iterations=completed,
                pileup=params.pileup_correction,
            )
            result = {"status": "done", "preview": make_preview(stack[0])}
        except TimeoutError:
            await self._protocol.reset()
            result = {"status": "timeout", "message": "live capture timed out"}
        except NotConnectedError:
            result = {"status": "error", "message": "vendor disconnected"}
        except ProtocolError as exc:
            result = {"status": "error", "message": str(exc)}
        finally:
            await self._instrument.set(InstrumentStatus.IDLE)
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
        *,
        reference: np.ndarray | None = None,
        dark_provenance: dict[str, Any] | None = None,
        keep_stack: bool = False,
    ) -> dict[str, Any]:
        stack = decode_intensity(
            data,
            bit_depth=params.bit_depth,
            rows=rows,
            im_width=params.roi_width,
            iterations=completed,
            pileup=params.pileup_correction,
        )
        # Correction shapes only the derived view; the persisted stack below
        # stays raw (see docs/design_gated_dcr_correction.md).
        display_stack = stack
        if reference is not None:
            display_stack = apply_dark_correction(stack, reference)
        result: dict[str, Any] = {
            "status": "done",
            "preview": make_preview(display_stack[0]),
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
                dark_correction=dark_provenance,
            )
        )
        if dark_provenance is not None:
            result["dark_corrected"] = True
            result["dark_reference_id"] = params.dark_reference_id
            result["dark_reference_path"] = dark_provenance.get("reference_npy_path")
        if keep_stack:
            result["_stack"] = stack
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
        dark_correction: dict[str, Any] | None = None,
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
            dark_correction=dark_correction,
        )
        result: dict[str, Any] = {
            "host_path": self._location.display_path(saved.acq_dir),
            "sidecar_path": self._location.display_path(sidecar_path),
        }
        if params.run_reducer:
            # Write the reduced meta_/movie_arr_ alongside the PNGs (inside the
            # acq dir) so they travel with the acquisition and are listed under
            # its result_path — the default writes to the parent folder.
            reduced = reduce_folder(saved.acq_dir, out_dir=saved.acq_dir)
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

    async def run_gated(
        self, params: GatedParams, *, keep_stack: bool = False
    ) -> dict[str, Any]:
        """Run a gated acquisition synchronously (no busy/timeout spec to honor,
        so the request awaits completion and always returns its full result).

        ``keep_stack`` attaches the raw decoded stack under ``"_stack"`` for
        in-process callers (the dark-reference builder); it must be popped
        before the result is serialized.
        """
        if self._instrument.is_busy:
            return {"status": "error", "message": "instrument busy"}

        await self._instrument.set(InstrumentStatus.ACQUIRING)
        await self._hub.broadcast_busy(mode="gated", progress=0.0)
        try:
            return await self._gated_op(params, keep_stack=keep_stack)
        except NotConnectedError:
            return {"status": "error", "message": "vendor disconnected"}
        except ProtocolError as exc:
            return {"status": "error", "message": str(exc)}
        finally:
            await self._instrument.set(InstrumentStatus.IDLE)
            await self._hub.broadcast_state(self._instrument.snapshot())

    def _resolve_dark_reference(
        self, dark_reference_id: str | None, current_fingerprint: dict[str, Any]
    ) -> tuple[np.ndarray | None, dict[str, Any] | None, str | None]:
        """Load + fingerprint-check the requested dark reference.

        Returns ``(reference, provenance, error)`` — provenance carries the
        reference's id/paths/creation time for the sidecar and experiment log.
        Runs before any vendor command so a mismatched reference fails fast
        without wasting an acquisition. Mode-specific fingerprints have
        disjoint key sets, so a gated reference can never match an intensity
        acquisition (or vice versa).
        """
        if dark_reference_id is None:
            return None, None, None
        if self.dark_reference_store is None:
            return None, None, "dark reference store not configured"
        stored = self.dark_reference_store.get(dark_reference_id)
        if stored is None:
            return None, None, f"dark reference {dark_reference_id!r} not found"
        stored_fingerprint, reference = stored
        if stored_fingerprint != current_fingerprint:
            mismatched = sorted(
                set(current_fingerprint) | set(stored_fingerprint)
            )
            mismatched = [
                k
                for k in mismatched
                if stored_fingerprint.get(k) != current_fingerprint.get(k)
            ]
            return None, None, (
                "dark reference config does not match the requested "
                f"acquisition (differs on: {', '.join(mismatched)})"
            )
        meta = self.dark_reference_store.meta(dark_reference_id) or {}
        provenance = {
            "applied": True,
            "reference_id": dark_reference_id,
            "reference_npy_path": meta.get("npy_path"),
            "reference_source_path": meta.get("source_path"),
            "reference_created_at": meta.get("created_at"),
            "reference_iterations": meta.get("iterations"),
            "method": "clip(signal - reference, 0)",
        }
        return reference, provenance, None

    async def _gated_op(
        self, params: GatedParams, *, keep_stack: bool = False
    ) -> dict[str, Any]:
        rows = self._sensor_size
        started_at = _now_iso()

        reference, dark_provenance, ref_error = self._resolve_dark_reference(
            params.dark_reference_id, gated_fingerprint(params)
        )
        if ref_error is not None:
            return {"status": "error", "message": ref_error}

        unit = integration_time_unit(params.bit_depth)
        aborted = False
        if params.cooloff_s > 0:
            stack, gate_steps, aborted, data_bytes = await self._paced_gated_io(params, rows)
            if gate_steps == 0:
                return {
                    "status": "aborted",
                    "abort_reason": self._instrument.abort_reason,
                    "message": "aborted before the first gate step completed",
                }
            n_frames = params.iterations * gate_steps
            if aborted and gate_steps != params.effective_steps and reference is not None:
                # A partial paced stack no longer matches the reference's step
                # count — persist the raw partial data, skip the display
                # correction rather than mis-applying it.
                reference = None
                dark_provenance = None
        else:
            gate_steps = params.effective_steps
            n_frames = params.iterations * gate_steps
            expected = n_frames * bytes_per_frame(
                params.bit_depth, rows, rows, params.pileup_correction
            )
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
                await self._protocol.send_command(
                    commands.arbitrary_steps(params.arbitrary_steps)
                )
            data = await self._protocol.send_acquire(command, expected_bytes=expected)
            data_bytes = len(data)

            stack = await asyncio.to_thread(
                decode_intensity,
                data,
                bit_depth=params.bit_depth,
                rows=rows,
                im_width=rows,
                iterations=n_frames,
                pileup=params.pileup_correction,
            )

        # Correction shapes only the derived views (previews, result preview);
        # the persisted raw stack below stays untouched — raw data is ground
        # truth (see docs/design_gated_dcr_correction.md).
        display_stack = stack
        if reference is not None:
            try:
                display_stack = await asyncio.to_thread(
                    apply_dark_correction, stack, reference
                )
            except ValueError as exc:
                return {"status": "error", "message": f"dark correction failed: {exc}"}

        previews_sent = 0
        for step in range(gate_steps):
            await self._hub.broadcast_preview(
                make_preview(display_stack[step]), index=step, count=gate_steps
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
            dark_correction=dark_provenance,
        )
        result: dict[str, Any] = {
            "status": "aborted" if aborted else "done",
            "preview": make_preview(display_stack[0]),
            "total_gate_steps": gate_steps,
            "previews_sent": previews_sent,
            "total_frames": n_frames,
            "integration_time_unit": unit,
            "bytes": data_bytes,
            **persisted,
        }
        if aborted:
            result["abort_reason"] = self._instrument.abort_reason
        if params.cooloff_s > 0:
            result["cooloff_s"] = params.cooloff_s
        if dark_provenance is not None:
            result["dark_corrected"] = True
            result["dark_reference_id"] = params.dark_reference_id
            result["dark_reference_path"] = dark_provenance.get("reference_npy_path")
        if keep_stack:
            result["_stack"] = stack
        return result

    async def _paced_gated_io(
        self, params: GatedParams, rows: int
    ) -> tuple[np.ndarray, int, bool, int]:
        """Gated sweep as one single-step vendor command per gate offset, with
        ``cooloff_s`` sleep between steps so the sensor can shed heat (DCR is
        thermally driven).

        The socket is idle at every step boundary — a safe boundary, so health
        polling and stop/auto-protect run between steps (the paced path has the
        mid-run protection that the single-command continuous path lacks,
        cf. bug B-32). Returns ``(stack, completed_steps, aborted)`` with the
        stack in the standard sweep-major layout (first ``completed_steps``
        frames = one full sweep) so persistence, previews, decay curves, and
        dark correction behave identically to the continuous path.
        """
        if params.arbitrary_steps:
            offsets = [float(v) for v in params.arbitrary_steps]
        else:
            offsets = [
                float(params.gate_offset) + i * params.gate_step_size
                for i in range(params.gate_steps)
            ]
            if params.gate_direction == "reverse":
                offsets.reverse()

        per_step_bytes = params.iterations * bytes_per_frame(
            params.bit_depth, rows, rows, params.pileup_correction
        )
        await self._protocol.send_command(commands.pileup(params.pileup_correction))

        step_stacks: list[np.ndarray] = []
        aborted = False
        wire_bytes = 0
        for index, offset in enumerate(offsets):
            command = commands.gated(
                bit_depth=params.bit_depth,
                integration_time=params.integration_time,
                iterations=params.iterations,
                gate_steps=1,
                gate_step_size=params.gate_step_size,
                gate_offset=int(round(offset)),
                gate_width=params.gate_width,
                gate_direction="forward",
                gate_trigger_source=params.gate_trigger_source,
                overlap=params.overlap,
                stream=params.stream,
                arbitrary=False,
            )
            data = await self._protocol.send_acquire(command, expected_bytes=per_step_bytes)
            wire_bytes += len(data)
            frames = await asyncio.to_thread(
                decode_intensity,
                data,
                bit_depth=params.bit_depth,
                rows=rows,
                im_width=rows,
                iterations=params.iterations,
                pileup=params.pileup_correction,
            )
            step_stacks.append(frames)

            if index < len(offsets) - 1:
                await self._poll_health()
                if self._instrument.stop_requested:
                    aborted = True
                    break
                await asyncio.sleep(params.cooloff_s)

        completed = len(step_stacks)
        if completed == 0:
            return np.empty((0, rows, rows), dtype=np.uint16), 0, True, wire_bytes
        # Collected step-major (steps, iterations, H, W); transpose to the
        # sweep-major frame order every other consumer expects.
        collected = np.stack(step_stacks)
        sweep_major = collected.transpose(1, 0, 2, 3).reshape(
            params.iterations * completed, *collected.shape[2:]
        )
        return np.ascontiguousarray(sweep_major), completed, aborted, wire_bytes
