"""Mutable state for the mock vendor server.

Holds device readings (temperatures, voltages, frequencies), feature flags,
calibration status, and a set of test hooks used by reliability/fault-injection
tests in later phases.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SENSOR_ROWS = 512
VALID_WIDTHS = (4, 8, 16, 32, 64, 128, 256, 512)
INT_BIT_DEPTHS = (1, 4, 6, 7, 8, 9, 10, 11, 12)
GATED_BIT_DEPTHS = (6, 7, 8, 9, 10, 11, 12)


@dataclass
class MockState:
    # Geometry / capabilities
    rows: int = SENSOR_ROWS
    hardware_flavour: str = "512"

    # Voltages (V)
    vq: float = 24.0
    vex: float = 5.0

    # Temperatures (°C): master FPGA, slave FPGA, PCB, chip
    t_master: float = 42.0
    t_slave: float = 41.0
    t_pcb: float = 35.0
    t_chip: float = -15.0

    # Trigger frequencies (Hz)
    laser_freq: float = 40_000_000.0
    frame_freq: float = 100.0

    # Toggles
    cooling_enabled: bool = True
    pileup_correction: bool = False
    overexposed: bool = False

    # Calibration status flags
    breakdown_calibrated: bool = False
    noise_calibrated: bool = False
    dead_pixel_calibrated: bool = False
    master_slave_offset_calibrated: bool = False
    flim_irf_calibrated: bool = False

    # Gated arbitrary steps (set via Ga)
    arbitrary_steps: list[float] = field(default_factory=list)

    # --- Test hooks (fault injection / timing), used in later phases ---
    command_count: int = 0
    _fail_after: int | None = None
    _next_delay_s: float = 0.0

    # Reusable RNG seed for reproducible synthetic data
    seed: int = 1234

    def set_temperature(self, *, chip: float | None = None, master: float | None = None,
                        slave: float | None = None, pcb: float | None = None) -> None:
        if chip is not None:
            self.t_chip = chip
        if master is not None:
            self.t_master = master
        if slave is not None:
            self.t_slave = slave
        if pcb is not None:
            self.t_pcb = pcb

    def set_voltage(self, target: str, value: float) -> None:
        if target not in ("vex", "vq"):
            raise ValueError(f"unknown voltage target: {target!r}")
        setattr(self, target, value)

    def set_laser_frequency(self, freq: float) -> None:
        self.laser_freq = freq

    def simulate_overexposure(self) -> None:
        self.overexposed = True

    def fail_after_n_commands(self, n: int) -> None:
        self._fail_after = n

    def set_next_response_delay(self, seconds: float) -> None:
        self._next_delay_s = seconds

    def should_fail(self) -> bool:
        return self._fail_after is not None and self.command_count > self._fail_after

    def take_delay(self) -> float:
        delay, self._next_delay_s = self._next_delay_s, 0.0
        return delay
