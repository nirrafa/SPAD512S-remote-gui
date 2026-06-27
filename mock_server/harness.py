"""In-process test harness for the mock vendor protocol.

Provides the synchronous ``send_command`` API the PRD spec tests use, without
opening a socket. The TCP server (:mod:`mock_server.server`) shares the same
protocol core for end-to-end and bridge integration tests.
"""
from __future__ import annotations

import asyncio
import threading
import time

import numpy as np

from mock_server.protocol import DONE, handle
from mock_server.server import MockVendorTCPServer
from mock_server.state import MockState


class MockVendorServer:
    def __init__(self, state: MockState | None = None) -> None:
        self.state = state or MockState()
        self.last_image_data: np.ndarray | None = None
        self.last_phasor_data: tuple[np.ndarray, np.ndarray] | None = None
        self.last_response: str = ""

        # Background TCP server (started on demand for bridge integration tests).
        self._tcp: MockVendorTCPServer | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._fixed_port: int = 0

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

    # --- Background TCP server (for bridge integration tests) ----------------

    @property
    def port(self) -> int:
        return self._fixed_port

    def start(self) -> None:
        """Start the TCP server in a background thread (idempotent).

        Rebinds the same port across restarts so the bridge can reconnect.
        """
        if self._thread is not None:
            return
        ready = threading.Event()
        error: list[BaseException] = []

        def run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._tcp = MockVendorTCPServer(
                host="127.0.0.1", port=self._fixed_port, state=self.state
            )
            try:
                loop.run_until_complete(self._tcp.start())
                self._fixed_port = self._tcp.sockets_port
            except BaseException as exc:  # noqa: BLE001
                error.append(exc)
                ready.set()
                return
            ready.set()
            loop.run_forever()
            loop.close()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        ready.wait(5)
        if error:
            raise error[0]

    def stop(self) -> None:
        """Stop the TCP server and close active connections (idempotent)."""
        if self._thread is None or self._loop is None or self._tcp is None:
            return
        loop, tcp = self._loop, self._tcp
        asyncio.run_coroutine_threadsafe(tcp.stop(), loop).result(5)
        loop.call_soon_threadsafe(loop.stop)
        self._thread.join(5)
        self._thread = None
        self._tcp = None
        self._loop = None
        time.sleep(0.3)  # allow a connected bridge to observe the EOF

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
