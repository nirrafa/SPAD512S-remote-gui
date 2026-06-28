"""Background acquisition runner.

Acquisitions run as a background task so the HTTP request can return promptly:
short acquisitions finish within a grace window and return their full result;
long ones return ``running`` and complete unattended (broadcasting progress and
the final preview over WebSocket). This is also what lets a second request be
rejected as *busy* while the first is still in flight.
"""
from __future__ import annotations

import asyncio
from typing import Any

from bridge.core.instrument import InstrumentState, InstrumentStatus
from bridge.core.ws_hub import WebSocketHub
from bridge.protocol import commands
from bridge.protocol.client import NotConnectedError, ProtocolClient, ProtocolError
from bridge.protocol.decoder import (
    bytes_per_frame,
    decode_intensity,
    integration_time_unit,
)
from bridge.services.file_writer import save_stack
from bridge.services.preview import make_preview

# Acquisitions finishing within this window return their full result; longer
# ones return `running` (and finish in the background). Small enough that a
# large multi-frame acquisition is reliably still in flight, large enough that
# typical single/few-frame acquisitions return `done` synchronously.
RESULT_GRACE_S = 0.3


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
    ) -> None:
        self.bit_depth = bit_depth
        self.integration_time = integration_time
        self.iterations = iterations
        self.roi_width = roi_width
        self.overlap = overlap
        self.pileup_correction = pileup_correction
        self.timeout_s = timeout_s


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

    @property
    def effective_steps(self) -> int:
        if self.arbitrary_steps:
            return len(self.arbitrary_steps)
        return self.gate_steps


class AcquisitionRunner:
    def __init__(
        self,
        protocol: ProtocolClient,
        instrument: InstrumentState,
        hub: WebSocketHub,
        data_root: str,
        *,
        sensor_size: int = 512,
    ) -> None:
        self._protocol = protocol
        self._instrument = instrument
        self._hub = hub
        self._data_root = data_root
        self._sensor_size = sensor_size
        self.current: dict[str, Any] | None = None

    async def run_intensity(self, params: IntensityParams) -> dict[str, Any]:
        if self._instrument.is_busy:
            return {"status": "error", "message": "instrument busy"}

        await self._instrument.set(InstrumentStatus.ACQUIRING)
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
        expected = params.iterations * bytes_per_frame(
            params.bit_depth, rows, params.roi_width, params.pileup_correction
        )
        command = commands.intensity(
            bit_depth=params.bit_depth,
            integration_time=params.integration_time,
            iterations=params.iterations,
            overlap=params.overlap,
            im_width=params.roi_width,
        )

        result: dict[str, Any]
        try:
            data = await self._acquire_io(params, command, expected)
            result = await asyncio.to_thread(
                self._postprocess, data, params, rows, unit
            )
        except TimeoutError:
            await self._protocol.reset()
            result = {"status": "timeout", "message": "acquisition timed out"}
        except NotConnectedError:
            result = {"status": "error", "message": "vendor disconnected"}
        except ProtocolError as exc:
            result = {"status": "error", "message": str(exc)}
        finally:
            await self._instrument.set(InstrumentStatus.IDLE)
            await self._hub.broadcast_state(self._instrument.snapshot())

        if self.current is not None:
            self.current["result"] = result
        if result.get("status") == "done":
            await self._hub.broadcast_preview(result["preview"])
        return result

    async def _acquire_io(
        self, params: IntensityParams, command: str, expected: int
    ) -> bytes:
        async def _io() -> bytes:
            await self._protocol.send_command(commands.pileup(params.pileup_correction))
            return await self._protocol.send_acquire(command, expected_bytes=expected)

        if params.timeout_s is not None:
            return await asyncio.wait_for(_io(), params.timeout_s)
        return await _io()

    def _postprocess(
        self, data: bytes, params: IntensityParams, rows: int, unit: str
    ) -> dict[str, Any]:
        stack = decode_intensity(
            data,
            bit_depth=params.bit_depth,
            rows=rows,
            im_width=params.roi_width,
            iterations=params.iterations,
            pileup=params.pileup_correction,
        )
        preview = make_preview(stack[0])
        host_path = save_stack(stack, data_root=self._data_root, mode="intensity")
        return {
            "status": "done",
            "preview": preview,
            "host_path": host_path,
            "total_frames": params.iterations,
            "integration_time_unit": unit,
            "bytes": len(data),
        }

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

        host_path = await asyncio.to_thread(
            save_stack, stack, data_root=self._data_root, mode="gated"
        )
        return {
            "status": "done",
            "preview": make_preview(stack[0]),
            "host_path": host_path,
            "total_gate_steps": gate_steps,
            "previews_sent": previews_sent,
            "total_frames": n_frames,
            "integration_time_unit": unit,
            "bytes": len(data),
        }
