"""In-process test harness for the mock vendor protocol.

Provides the synchronous ``send_command`` API the PRD spec tests use, without
opening a socket. The TCP server (:mod:`mock_server.server`) shares the same
protocol core for end-to-end and bridge integration tests.
"""
from __future__ import annotations

import time

import numpy as np

from mock_server.protocol import DONE, handle
from mock_server.state import MockState


class MockVendorServer:
    def __init__(self, state: MockState | None = None) -> None:
        self.state = state or MockState()
        self.last_image_data: np.ndarray | None = None
        self.last_phasor_data: tuple[np.ndarray, np.ndarray] | None = None
        self.last_response: str = ""

    def send_command(self, command: str) -> str:
        delay = self.state.take_delay()
        if delay:
            time.sleep(delay)

        result = handle(command, self.state)
        if result.image is not None:
            self.last_image_data = result.image
        if result.phasor is not None:
            self.last_phasor_data = result.phasor

        if result.is_error:
            self.last_response = result.text
        else:
            self.last_response = f"{result.text}\n{DONE}" if result.text else DONE
        return self.last_response

    # Convenience pass-throughs for fault-injection in later phases.
    def set_temperature(self, **kwargs: float) -> None:
        self.state.set_temperature(**kwargs)

    def set_voltage(self, vex: float) -> None:
        self.state.set_voltage(vex)

    def set_laser_frequency(self, freq: float) -> None:
        self.state.set_laser_frequency(freq)

    def fail_after_n_commands(self, n: int) -> None:
        self.state.fail_after_n_commands(n)

    def set_next_response_delay(self, seconds: float) -> None:
        self.state.set_next_response_delay(seconds)
