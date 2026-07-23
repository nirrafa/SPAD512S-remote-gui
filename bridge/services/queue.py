"""Acquisition queue: run a mixed series of measurements unattended.

The user builds a list like "2 gated with these settings, then 3 intensity
with those" and walks away. Items run strictly sequentially through the
existing :class:`AcquisitionRunner` (single-socket serialization, busy guard,
safe-boundary aborts all come for free), and every completed item is recorded
in the experiment log with the same provenance as a hand-started acquisition.

Like sweeps, the queue runs as a background task so it survives browser
disconnects; progress is polled via ``GET /api/queue/status``. The queue is
in-memory — a bridge restart clears it (the completed items remain in the
experiment log and on disk).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from bridge.core.acquisition import AcquisitionRunner
from bridge.core.instrument import InstrumentState
from bridge.services.experiment_log import ExperimentLog
from bridge.services.sweep import _gated_params, _intensity_params

MAX_ITEMS = 200  # after repeat expansion — a sanity bound, not a real limit


class AcquisitionQueue:
    def __init__(
        self,
        runner: AcquisitionRunner,
        instrument: InstrumentState,
        log: ExperimentLog,
    ) -> None:
        self._runner = runner
        self._instrument = instrument
        self._log = log
        self._task: asyncio.Task[None] | None = None
        self._items: list[dict[str, Any]] = []
        self._active = False
        self._started_at: float | None = None
        # Own stop flag: the instrument's stop_requested is cleared every time
        # an item's op returns to IDLE, so it can't reliably signal "stop the
        # whole series" — /api/acquire/stop calls request_stop() instead.
        self._stop = False

    @property
    def active(self) -> bool:
        return self._active

    def request_stop(self) -> None:
        self._stop = True

    async def start(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Expand repeats, validate, and launch the background run."""
        if self._active or self._instrument.is_busy:
            return {"status": "error", "message": "instrument busy"}

        expanded: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            mode = str(item.get("mode", ""))
            if mode not in ("intensity", "gated"):
                return {
                    "status": "error",
                    "message": f"item {index}: unsupported mode {mode!r}",
                }
            repeat = int(item.get("repeat", 1))
            if repeat < 1:
                return {"status": "error", "message": f"item {index}: repeat must be >= 1"}
            params = dict(item.get("params") or {})
            for _ in range(repeat):
                expanded.append({"mode": mode, "params": params, "status": "pending"})
        if not expanded:
            return {"status": "error", "message": "queue is empty"}
        if len(expanded) > MAX_ITEMS:
            return {
                "status": "error",
                "message": f"queue too long ({len(expanded)} > {MAX_ITEMS} items)",
            }

        self._items = expanded
        self._active = True
        self._stop = False
        self._started_at = time.time()
        self._task = asyncio.create_task(self._run())
        return {"status": "started", "total": len(expanded)}

    async def _run(self) -> None:
        try:
            for item in self._items:
                if self._stop or self._instrument.stop_requested:
                    item["status"] = "skipped"
                    continue
                item["status"] = "running"
                try:
                    if item["mode"] == "gated":
                        result = await self._runner.run_gated(_gated_params(item["params"]))
                    else:
                        result = await self._runner.run_intensity(
                            _intensity_params(item["params"])
                        )
                        if result.get("status") == "running":
                            # Long acquisitions return early with `running`;
                            # the series must wait for true completion before
                            # starting the next item.
                            task = (self._runner.current or {}).get("task")
                            if task is not None:
                                result = await task
                except Exception as exc:  # noqa: BLE001 — one bad item must not kill the series
                    item["status"] = "error"
                    item["message"] = str(exc)
                    continue

                status = str(result.get("status"))
                item["status"] = status if status in ("done", "aborted") else "error"
                item["host_path"] = result.get("host_path")
                if result.get("message"):
                    item["message"] = result.get("message")
                if result.get("dark_corrected"):
                    item["dark_corrected"] = True
                if status in ("done", "aborted"):
                    ctx = self._runner.acquisition_context()
                    logged = dict(item["params"])
                    logged["queued"] = True
                    if result.get("dark_corrected"):
                        logged["dark_corrected"] = True
                        logged["dark_reference_id"] = result.get("dark_reference_id")
                        logged["dark_reference_npy_path"] = result.get("dark_reference_path")
                    self._log.log_acquisition(
                        mode=item["mode"],
                        params=logged,
                        result_path=result.get("host_path"),
                        calibration_state=ctx["calibration_state"],
                        temperatures=ctx["temperatures"],
                        sample_name=item["params"].get("sample_name"),
                        experiment_name=item["params"].get("experiment_name"),
                        notes=item["params"].get("notes"),
                    )
                if status == "aborted":
                    # An abort (user stop / auto-protect) stops the whole
                    # series — remaining items are marked skipped below.
                    break
        finally:
            for item in self._items:
                if item["status"] in ("pending", "running"):
                    item["status"] = "skipped"
            self._active = False

    def status(self) -> dict[str, Any]:
        done = sum(1 for i in self._items if i["status"] in ("done", "aborted", "error", "skipped"))
        return {
            "running": self._active,
            "total": len(self._items),
            "completed": done,
            "started_at": self._started_at,
            "items": [
                {
                    "index": index,
                    "mode": item["mode"],
                    "status": item["status"],
                    "host_path": item.get("host_path"),
                    "message": item.get("message"),
                    "dark_corrected": item.get("dark_corrected", False),
                    "params": item["params"],
                }
                for index, item in enumerate(self._items)
            ],
        }
