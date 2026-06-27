"""Instrument state manager.

Tracks the high-level operating state and broadcasts changes. The vendor
protocol is request/response with no multiplexing, so only one acquisition may
run at a time; the ``busy`` guard rejects overlapping acquisitions.
"""
from __future__ import annotations

import enum
from collections.abc import Awaitable, Callable


class InstrumentStatus(enum.StrEnum):
    IDLE = "idle"
    ACQUIRING = "acquiring"
    CALIBRATING = "calibrating"
    STOPPING = "stopping"


StateListener = Callable[["InstrumentState"], Awaitable[None]]


class InstrumentState:
    def __init__(self, on_change: StateListener | None = None) -> None:
        self._status = InstrumentStatus.IDLE
        self._on_change = on_change
        self._stop_requested = False

    @property
    def status(self) -> InstrumentStatus:
        return self._status

    @property
    def is_busy(self) -> bool:
        return self._status in (InstrumentStatus.ACQUIRING, InstrumentStatus.CALIBRATING)

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested

    async def set(self, status: InstrumentStatus) -> None:
        self._status = status
        if status == InstrumentStatus.IDLE:
            self._stop_requested = False
        if self._on_change is not None:
            await self._on_change(self)

    async def request_stop(self) -> None:
        self._stop_requested = True
        if self.is_busy:
            await self.set(InstrumentStatus.STOPPING)

    def snapshot(self) -> dict[str, object]:
        return {"instrument_state": self._status.value, "stop_requested": self._stop_requested}
