"""Parameter-sweep runner.

A sweep iterates one or more parameters over a set of values, running one
acquisition per point through the existing :class:`AcquisitionRunner` (no
duplicated acquire lifecycle). Each completed point is checkpointed to SQLite so
an interrupted sweep can resume and skip finished points.

Sweeps run as a background task so they survive browser (WebSocket) disconnects:
the HTTP request awaits a *result-ready* event (returning the full ``done``
result for a fast sweep), while the task lingers briefly in the ``running`` state
afterwards so a client reconnecting right after the POST still observes progress
via ``GET /api/acquire/status``.
"""
from __future__ import annotations

import asyncio
import itertools
from typing import Any

from bridge.core.acquisition import AcquisitionRunner, GatedParams, IntensityParams
from bridge.core.checkpoint import CheckpointStore
from bridge.core.instrument import InstrumentState

# After the final point completes, keep the sweep observably ``running`` for this
# long before releasing to idle. This lets a client that reconnects immediately
# after the POST returns still see ``running: True`` (the disconnect-resilience
# contract), without making the fast synchronous POST itself block.
_LINGER_S = 0.5


class SweepError(RuntimeError):
    """A sweep point failed (e.g. a vendor error); the sweep is left resumable."""


def _resolve_points(
    *,
    mode: str,
    base_params: dict[str, Any],
    sweep_parameter: str | None,
    values: list[Any] | None,
    sweep_parameters: dict[str, list[Any]] | None,
) -> list[dict[str, Any]]:
    """Expand the sweep spec into an ordered list of concrete points.

    Single-parameter (``sweep_parameter`` + ``values``) and multi-parameter
    (``sweep_parameters`` cartesian product) forms both reduce to a flat list of
    ``{index, label, value, params}`` dicts.
    """
    points: list[dict[str, Any]] = []
    if sweep_parameters:
        names = list(sweep_parameters.keys())
        combos = list(itertools.product(*(sweep_parameters[name] for name in names)))
        for index, combo in enumerate(combos):
            assignment = dict(zip(names, combo, strict=True))
            label = ", ".join(f"{name}={val}" for name, val in assignment.items())
            points.append(
                {
                    "index": index,
                    "label": label,
                    "value": assignment,
                    "params": {**base_params, **assignment},
                }
            )
    else:
        if sweep_parameter is None or values is None:
            raise ValueError("single-parameter sweep needs sweep_parameter and values")
        for index, value in enumerate(values):
            points.append(
                {
                    "index": index,
                    "label": f"{sweep_parameter}={value}",
                    "value": value,
                    "params": {**base_params, sweep_parameter: value},
                }
            )
    return points


class SweepRunner:
    def __init__(
        self,
        runner: AcquisitionRunner,
        instrument: InstrumentState,
        store: CheckpointStore,
    ) -> None:
        self._runner = runner
        self._instrument = instrument
        self._store = store
        self._task: asyncio.Task[dict[str, Any]] | None = None
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    async def start(
        self,
        *,
        mode: str,
        base_params: dict[str, Any],
        sweep_parameter: str | None = None,
        values: list[Any] | None = None,
        sweep_parameters: dict[str, list[Any]] | None = None,
    ) -> dict[str, Any]:
        if self._instrument.is_busy or self._active:
            return {"status": "error", "message": "instrument busy"}

        points = _resolve_points(
            mode=mode,
            base_params=base_params,
            sweep_parameter=sweep_parameter,
            values=values,
            sweep_parameters=sweep_parameters,
        )
        spec = {
            "mode": mode,
            "base_params": base_params,
            "sweep_parameter": sweep_parameter,
            "values": values,
            "sweep_parameters": sweep_parameters,
            "points": points,
        }
        sweep_id = self._store.create_sweep(spec)
        return await self._launch(sweep_id, mode, points, skip=set())

    async def resume(self) -> dict[str, Any]:
        if self._instrument.is_busy or self._active:
            return {"status": "error", "message": "instrument busy"}

        pending = self._store.latest_incomplete()
        if pending is None:
            return {"status": "error", "message": "no resumable sweep"}
        sweep_id, spec = pending
        done = self._store.completed_indices(sweep_id)
        points = spec["points"]
        return await self._launch(sweep_id, spec["mode"], points, skip=done)

    async def _launch(
        self,
        sweep_id: str,
        mode: str,
        points: list[dict[str, Any]],
        *,
        skip: set[int],
    ) -> dict[str, Any]:
        self._active = True
        ready: asyncio.Event = asyncio.Event()
        outcome: dict[str, Any] = {}

        self._task = asyncio.create_task(
            self._run(sweep_id, mode, points, skip, ready, outcome)
        )
        await ready.wait()
        return dict(outcome)

    async def _run(
        self,
        sweep_id: str,
        mode: str,
        points: list[dict[str, Any]],
        skip: set[int],
        ready: asyncio.Event,
        outcome: dict[str, Any],
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        checkpoints_written = 0
        skipped = len(skip)
        try:
            for point in points:
                if point["index"] in skip:
                    results.append(self._point_summary(point, host_path=None))
                    continue
                if self._instrument.stop_requested:
                    break
                host_path = await self._run_point(mode, point)
                self._store.record_point(
                    sweep_id,
                    point["index"],
                    point["label"],
                    point["value"],
                    host_path,
                )
                checkpoints_written += 1
                results.append(self._point_summary(point, host_path=host_path))
        except SweepError as exc:
            outcome.update(
                {
                    "status": "error",
                    "message": str(exc),
                    "sweep_id": sweep_id,
                    "points_completed": len(results) - skipped,
                    "checkpoints_written": checkpoints_written,
                    "results": results,
                }
            )
            ready.set()
            self._active = False
            return outcome

        self._store.set_status(sweep_id, "done")
        outcome.update(
            {
                "status": "done",
                "sweep_id": sweep_id,
                "points_completed": len(results),
                "points_skipped": skipped,
                "checkpoints_written": checkpoints_written,
                "results": results,
            }
        )
        ready.set()
        # Linger in the running state so a client reconnecting right after the
        # POST still observes the sweep as running (see module docstring).
        await asyncio.sleep(_LINGER_S)
        self._active = False
        return outcome

    def _point_summary(
        self, point: dict[str, Any], *, host_path: str | None
    ) -> dict[str, Any]:
        return {
            "index": point["index"],
            "label": point["label"],
            "value": point["value"],
            "host_path": host_path,
        }

    async def _run_point(self, mode: str, point: dict[str, Any]) -> str | None:
        params = point["params"]
        if mode == "gated":
            result = await self._runner.run_gated(_gated_params(params))
        else:
            result = await self._runner.run_intensity(_intensity_params(params))
        status = result.get("status")
        if status not in ("done", "running"):
            raise SweepError(str(result.get("message") or f"sweep point {status}"))
        return result.get("host_path")  # type: ignore[return-value]


def _intensity_params(params: dict[str, Any]) -> IntensityParams:
    integration_time = params.get("integration_time_ms")
    if integration_time is None:
        integration_time = params.get("integration_time", 100.0)
    return IntensityParams(
        bit_depth=int(params.get("bit_depth", 8)),
        integration_time=float(integration_time),
        iterations=int(params.get("iterations", 1)),
        roi_width=int(params.get("roi_width", 512)),
        overlap=bool(params.get("overlap", False)),
        pileup_correction=bool(params.get("pileup_correction", False)),
        timeout_s=params.get("timeout_s"),
    )


def _gated_params(params: dict[str, Any]) -> GatedParams:
    integration_time = params.get("integration_time_ms")
    if integration_time is None:
        integration_time = params.get("integration_time", 100.0)
    return GatedParams(
        bit_depth=int(params.get("bit_depth", 8)),
        integration_time=float(integration_time),
        iterations=int(params.get("iterations", 1)),
        gate_steps=int(params.get("gate_steps", 10)),
        gate_step_size=float(params.get("gate_step_size_ps", 18.0)),
        gate_offset=int(params.get("gate_offset", 0)),
        gate_width=int(params.get("gate_width", 5)),
        gate_direction=str(params.get("gate_direction", "forward")),
        gate_trigger_source=str(params.get("gate_trigger_source", "external")),
        overlap=bool(params.get("overlap", False)),
        stream=bool(params.get("stream", False)),
        pileup_correction=bool(params.get("pileup_correction", False)),
        arbitrary_steps=params.get("arbitrary_steps"),
    )
