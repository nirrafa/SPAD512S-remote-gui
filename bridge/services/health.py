"""Health monitor: polling, alarm evaluation, and auto-protect.

Owns the latest device readings and the alarm set. A background loop polls the
instrument on a configurable interval; the single TCP socket means health polls
must never interleave with an in-flight acquisition (learnings.md), so the poll
falls back to cached readings while the instrument is busy. The acquisition
runner calls :meth:`poll` directly at batch boundaries (socket idle = safe), so
auto-abort can fire mid-acquisition.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import Any

from bridge.core.instrument import InstrumentState
from bridge.core.ws_hub import WebSocketHub
from bridge.protocol import commands
from bridge.protocol.client import NotConnectedError, ProtocolClient, ProtocolError
from bridge.protocol.decoder import parse_health, parse_voltages


@dataclass
class HealthConfig:
    poll_interval_s: float = 0.5
    temp_threshold_chip: float = 75.0
    vex_max: float = 25.0
    expected_laser_hz: float = 40_000_000.0
    laser_tolerance: float = 0.25
    missing_laser_hz: float = 1.0

    def to_dict(self) -> dict[str, float]:
        return {
            "poll_interval_s": self.poll_interval_s,
            "temp_threshold_chip": self.temp_threshold_chip,
            "vex_max": self.vex_max,
            "expected_laser_hz": self.expected_laser_hz,
            "laser_tolerance": self.laser_tolerance,
            "missing_laser_hz": self.missing_laser_hz,
        }


@dataclass
class Readings:
    temp_master_fpga: float = 0.0
    temp_slave_fpga: float = 0.0
    temp_pcb: float = 0.0
    temp_chip: float = 0.0
    vq: float = 0.0
    vex: float = 0.0
    cooling_active: bool = True
    laser_frequency_hz: float = 0.0
    frame_frequency_hz: float = 0.0
    saturated: bool = False
    valid: bool = False
    vex_reduced: bool = False
    last_updated: float | None = None
    alarms: list[dict[str, Any]] = field(default_factory=list)


class HealthMonitor:
    def __init__(
        self,
        protocol: ProtocolClient,
        instrument: InstrumentState,
        hub: WebSocketHub,
        *,
        config: HealthConfig | None = None,
    ) -> None:
        self._protocol = protocol
        self._instrument = instrument
        self._hub = hub
        self.config = config or HealthConfig()
        self._readings = Readings()
        self._active_alarm_types: set[str] = set()
        self._loop_task: asyncio.Task[None] | None = None
        self._stopping = False

    # --- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        self._loop_task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        if self._loop_task is not None:
            self._loop_task.cancel()
            with contextlib.suppress(BaseException):
                await self._loop_task
            self._loop_task = None

    async def _run(self) -> None:
        while not self._stopping:
            with contextlib.suppress(Exception):
                await self.poll()
            await asyncio.sleep(self.config.poll_interval_s)

    # --- polling --------------------------------------------------------------

    async def poll(self, *, force: bool = False) -> Readings:
        """Refresh readings and evaluate alarms.

        Sends ``R``+``V`` only when the socket is free: when the instrument is
        idle, or when ``force`` is set (the runner calls with ``force`` at a
        batch boundary, where it transiently owns the socket). Otherwise keeps
        the cached readings so health remains available during acquisitions.
        """
        if force or not self._instrument.is_busy:
            with contextlib.suppress(NotConnectedError, ProtocolError, ValueError):
                await self._read_instrument()
        await self._apply_auto_protect()
        self._evaluate_alarms()
        await self._broadcast_new_alarms()
        return self._readings

    async def _read_instrument(self) -> None:
        if not self._protocol.connected:
            self._readings.valid = False  # don't present stale values as live
            return
        health_text = await self._protocol.send_command(commands.readout())
        volt_text = await self._protocol.send_command(commands.voltages())
        health = parse_health(health_text)
        vq, vex = parse_voltages(volt_text)
        r = self._readings
        r.temp_master_fpga = health["temp_master_fpga"]
        r.temp_slave_fpga = health["temp_slave_fpga"]
        r.temp_pcb = health["temp_pcb"]
        r.temp_chip = health["temp_chip"]
        r.laser_frequency_hz = health["laser_frequency_hz"]
        r.frame_frequency_hz = health["frame_frequency_hz"]
        r.cooling_active = health["cooling_active"]
        r.saturated = health["saturated"]
        r.vq = vq
        r.vex = vex
        r.valid = True
        r.last_updated = time.time()

    # --- alarm evaluation -----------------------------------------------------

    def _evaluate_alarms(self) -> None:
        r = self._readings
        cfg = self.config
        alarms: list[dict[str, Any]] = []

        if r.valid and r.temp_chip > cfg.temp_threshold_chip:
            alarms.append({"type": "over_temperature", "severity": "critical",
                           "value": r.temp_chip, "threshold": cfg.temp_threshold_chip})
        if r.valid and not r.cooling_active:
            alarms.append({"type": "cooling_failure", "severity": "critical"})
        if r.valid and abs(r.laser_frequency_hz) <= cfg.missing_laser_hz:
            alarms.append({"type": "missing_laser_trigger", "severity": "warning"})
        elif r.valid and not _laser_in_range(r.laser_frequency_hz, cfg):
            alarms.append({"type": "abnormal_laser_trigger", "severity": "warning",
                           "value": r.laser_frequency_hz})
        if r.valid and r.saturated:
            alarms.append({"type": "suspected_overexposure", "severity": "warning"})
        if r.vex_reduced:
            alarms.append({"type": "vex_reduced", "severity": "warning", "value": r.vex})

        r.alarms = alarms

    # --- auto-protect ---------------------------------------------------------

    async def _apply_auto_protect(self) -> None:
        """Take protective action + update flags (before alarms are evaluated)."""
        r = self._readings
        cfg = self.config
        if r.valid and r.temp_chip > cfg.temp_threshold_chip and self._instrument.is_busy:
            await self._instrument.request_stop("over_temperature")
        if r.valid and r.vex > cfg.vex_max:
            # Actually command the safe bias, not just flag it — but only when the
            # socket is free (never interleave a set during an acquisition).
            if not self._instrument.is_busy and self._protocol.connected:
                with contextlib.suppress(NotConnectedError, ProtocolError):
                    await self._protocol.send_command(commands.set_vex(cfg.vex_max))
                    r.vex = cfg.vex_max
            # Latched: auto-protect itself brings vex back within range, so an
            # in-range unlatch here would erase the warning one poll after
            # raising it (a race the pre-dev suite caught). The flag means
            # "auto-protect intervened since the last manual bias change" and
            # is cleared by a successful /api/settings/vex.
            r.vex_reduced = True

    async def _broadcast_new_alarms(self) -> None:
        current = {a["type"]: a for a in self._readings.alarms}
        # Update the active-set BEFORE awaiting so a concurrent poll can't
        # re-classify the same alarm as new and double-broadcast it.
        new_payloads = [p for t, p in current.items() if t not in self._active_alarm_types]
        self._active_alarm_types = set(current)
        for payload in new_payloads:
            await self._hub.broadcast_alarm(payload)

    # --- payload --------------------------------------------------------------

    def readings_payload(self) -> dict[str, Any]:
        r = self._readings
        return {
            "temp_master_fpga": r.temp_master_fpga,
            "temp_slave_fpga": r.temp_slave_fpga,
            "temp_pcb": r.temp_pcb,
            "temp_chip": r.temp_chip,
            "vq": r.vq,
            "vex": r.vex,
            "cooling_active": r.cooling_active,
            "laser_frequency_hz": r.laser_frequency_hz,
            "frame_frequency_hz": r.frame_frequency_hz,
            "saturated": r.saturated,
            "vex_reduced": r.vex_reduced,
            "readings_valid": r.valid,
            "last_updated": r.last_updated,
            "alarms": list(r.alarms),
        }

    def clear_vex_reduced(self) -> None:
        """A deliberate, successful manual bias change supersedes the latched
        auto-protect warning."""
        self._readings.vex_reduced = False

    def config_payload(self) -> dict[str, float]:
        return self.config.to_dict()

    def update_config(self, **values: float) -> None:
        for key, value in values.items():
            if hasattr(self.config, key) and value is not None:
                setattr(self.config, key, float(value))
        # A too-small interval would busy-loop R+V on the single socket and
        # starve user commands; keep a hard floor regardless of the request.
        self.config.poll_interval_s = max(self.config.poll_interval_s, 0.1)


def _laser_in_range(freq: float, cfg: HealthConfig) -> bool:
    lo = cfg.expected_laser_hz * (1.0 - cfg.laser_tolerance)
    hi = cfg.expected_laser_hz * (1.0 + cfg.laser_tolerance)
    return lo <= freq <= hi
