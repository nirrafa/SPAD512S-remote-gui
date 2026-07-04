"""Scheduled / overnight acquisition jobs.

A job is queued with a start time and runs unattended (pure asyncio, no extra
deps): a background task sleeps until the start time, then runs the acquisition
through the existing :class:`AcquisitionRunner`. Jobs survive with no browser
connected and are visible in the experiment log.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from bridge.core.acquisition import AcquisitionRunner
from bridge.services.experiment_log import ExperimentLog
from bridge.services.sweep import _gated_params, _intensity_params


class ScheduledJob:
    def __init__(
        self, job_id: str, mode: str, params: dict[str, Any], start_time: str
    ) -> None:
        self.job_id = job_id
        self.mode = mode
        self.params = params
        self.start_time = start_time
        self.state = "scheduled"
        self.result: dict[str, Any] | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "mode": self.mode,
            "start_time": self.start_time,
            "state": self.state,
            "result": self.result,
        }


class Scheduler:
    def __init__(self, runner: AcquisitionRunner, log: ExperimentLog) -> None:
        self._runner = runner
        self._log = log
        self._jobs: dict[str, ScheduledJob] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def schedule(
        self, *, mode: str, params: dict[str, Any], start_time: str
    ) -> ScheduledJob:
        job_id = uuid.uuid4().hex[:12]
        job = ScheduledJob(job_id, mode, params, start_time)
        self._jobs[job_id] = job
        self._log.add(
            mode=mode, params=params, scheduled=True, job_id=job_id, state="scheduled"
        )
        task = asyncio.create_task(self._run(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    def get(self, job_id: str) -> ScheduledJob | None:
        return self._jobs.get(job_id)

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()

    async def _run(self, job: ScheduledJob) -> None:
        delay = _seconds_until(job.start_time)
        if delay > 0:
            await asyncio.sleep(delay)
        job.state = "running"
        self._log.update(job.job_id, state="running")
        try:
            if job.mode == "gated":
                result = await self._runner.run_gated(_gated_params(job.params))
            else:
                result = await self._runner.run_intensity(_intensity_params(job.params))
        except Exception as exc:  # noqa: BLE001 — a scheduled job must not crash the loop
            job.state = "failed"
            job.result = {"status": "error", "message": str(exc)}
            self._log.update(job.job_id, state="failed")
            return
        job.result = result
        job.state = "failed" if result.get("status") == "error" else "completed"
        self._log.update(job.job_id, state=job.state, result_path=result.get("host_path"))


def _seconds_until(start_time: str) -> float:
    try:
        when = datetime.fromisoformat(start_time)
    except ValueError:
        return 0.0
    now = datetime.now(tz=when.tzinfo) if when.tzinfo else datetime.now()
    return max((when - now).total_seconds(), 0.0)
