"""Playwright-backed harness for the browser E2E / visualization spec tests.

The bridge-only tests use an in-process ``TestClient``; the browser tests need
a *real* HTTP server serving the built SPA. This module runs the bridge in a
background uvicorn thread (connected to the mock TCP server) and drives it with
a real Chromium page via Playwright. ``SpaClient`` exposes the vocabulary
``test_10``/``test_15`` speak (navigate, set params, acquire, draw ROIs, read
plots, presets, log, …).

Requires ``playwright`` + a browser (``python -m playwright install chromium``);
tests skip cleanly when either is missing.
"""
from __future__ import annotations

import contextlib
import json
import re
import socket
import threading
import time
from typing import Any

import requests
import uvicorn
from bridge.config import Settings
from bridge.main import create_app

_TAB = {
    "intensity": "Intensity",
    "gated": "Gated",
    "flim": "FLIM",
    "raw1bit": "Raw 1-bit",
    "sweep": "Sweep",
    "calibration": "Calibration",
    "health": "Health",
    "log": "Log",
}

_PARAM_LABEL = {
    "bit_depth": "Bit depth",
    "integration_time": "Integration time",
    "integration_time_ms": "Integration time",
    "iterations": "Iterations",
    "roi_width": "ROI width",
    "gate_steps": "Gate steps",
}


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


class ThreadedBridge:
    """Run ``create_app`` under uvicorn in a daemon thread (lifespan runs, so the
    bridge connects to the mock and serves the built SPA)."""

    def __init__(self, settings: Settings) -> None:
        self.base_url = f"http://127.0.0.1:{settings.bridge_port}"
        self._app = create_app(settings)
        config = uvicorn.Config(
            self._app, host="127.0.0.1", port=settings.bridge_port, log_level="warning"
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self, timeout: float = 20.0) -> None:
        self._thread.start()
        deadline = time.time() + timeout
        while not self._server.started and time.time() < deadline:
            time.sleep(0.05)
        if not self._server.started:
            raise RuntimeError("bridge failed to start")
        # Wait for the vendor (mock) connection so acquisitions succeed.
        while time.time() < deadline:
            try:
                if requests.get(f"{self.base_url}/api/status", timeout=2).json().get(
                    "vendor_connected"
                ):
                    return
            except requests.RequestException:
                pass
            time.sleep(0.1)

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(10)


class SpaClient:
    def __init__(self, page: Any, base_url: str) -> None:
        self.page = page
        self.base_url = base_url
        self.http = requests.Session()

    # --- HTTP helper ----------------------------------------------------------

    def api_get(self, path: str) -> Any:
        return self.http.get(self.base_url + path, timeout=10).json()

    # --- navigation -----------------------------------------------------------

    def _tab(self, label: str) -> None:
        self.page.locator(".tabs button", has_text=re.compile(f"^{re.escape(label)}$")).click()

    def navigate_to_mode(self, mode: str) -> None:
        self._tab(_TAB[mode])

    def navigate_to_experiment_log(self) -> None:
        self._tab("Log")
        # The page fetches the log on mount; wait for a row (or the empty state)
        # so a caller reading the count doesn't race the fetch.
        with contextlib.suppress(Exception):
            self.page.wait_for_selector(".log-table tbody tr", timeout=5000)

    def navigate_to_calibration(self, cal_type: str = "") -> None:
        self._current_cal = cal_type
        self._tab("Calibration")

    # --- generic element access ----------------------------------------------

    def find_element(self, selector: str) -> Element:
        return Element(self.page, selector)

    def click(self, target: str) -> None:
        mapping = {
            "auto-stretch": '[data-testid="auto-stretch"]',
        }
        self.page.locator(mapping.get(target, target)).first.click()

    def set_param(self, name: str, value: Any) -> None:
        label = _PARAM_LABEL.get(name, name)
        control = self.page.get_by_label(re.compile(label)).first
        tag = control.evaluate("el => el.tagName")
        if tag == "SELECT":
            control.select_option(str(value))
        else:
            control.fill(str(value))

    # --- acquisition ----------------------------------------------------------

    def click_acquire(self) -> None:
        self.page.locator(
            "button", has_text=re.compile("^(Acquire|Start sweep)")
        ).first.click()

    def acquire_intensity(self) -> None:
        self.navigate_to_mode("intensity")
        self.click_acquire()
        self.wait_for_completion()

    def acquire_gated(self) -> None:
        self.navigate_to_mode("gated")
        self.click_acquire()
        self.wait_for_completion()

    def acquire_flim(self) -> None:
        self.navigate_to_mode("flim")
        self.run_irf_calibration()
        self.click_acquire()
        self.wait_for_completion()

    def run_irf_calibration(self) -> None:
        self.page.locator("button", has_text="Calibrate IRF").click()
        self._wait_idle()

    def wait_for_completion(self, timeout: float = 40.0) -> None:
        self._wait_idle(timeout)
        # Let the browser paint the preview/plots the acquire response carried.
        self.page.wait_for_timeout(400)

    def _wait_idle(self, timeout: float = 40.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                status = self.api_get("/api/acquire/status")
            except requests.RequestException:
                status = {"running": False}
            if not status.get("running"):
                return
            time.sleep(0.2)

    # --- visibility helpers ---------------------------------------------------

    def preview_visible(self) -> bool:
        return "peak" in (self.page.locator(".canvas-controls").first.inner_text() or "")

    def phasor_plot_visible(self) -> bool:
        return self.page.locator("#phasor-plot").is_visible()

    def decay_curve_visible(self) -> bool:
        return self.page.locator("#decay-curve").is_visible()

    def histogram_visible(self) -> bool:
        return self.page.locator("#pixel-histogram").is_visible()

    def host_files_exist(self) -> bool:
        log = self.api_get("/api/experiment-log")
        entries = log.get("entries", [])
        if not entries:
            return False
        path = entries[-1].get("result_path")
        if not path:
            return False
        files = self.api_get(f"/api/data/list?path={path}")
        return isinstance(files, list) and len(files) > 0

    # --- colormap / stretch / zoom -------------------------------------------

    def select_colormap(self, name: str) -> None:
        self.page.get_by_label(re.compile("Colormap")).first.select_option(name)

    def get_current_colormap(self) -> str:
        return str(self.page.get_by_label(re.compile("Colormap")).first.input_value())

    def get_intensity_range(self) -> str | None:
        loc = self.page.locator(".viewer-toolbar", has_text="range")
        return loc.first.inner_text() if loc.count() else None

    def get_canvas_viewport(self) -> dict[str, float]:
        scale = self.page.locator(".image-canvas-stage").first.get_attribute("data-scale")
        return {"scale": float(scale or "1")}

    def zoom_in(self) -> None:
        self.page.locator("button", has_text=re.compile("^zoom in$")).click()
        self.page.wait_for_timeout(100)

    # --- ROI ------------------------------------------------------------------

    def _set_roi_mode(self, mode: str) -> None:
        self.page.locator(".roi-tools button", has_text=re.compile(f"^{mode}$")).click()

    def _overlay_box(self) -> dict[str, float]:
        box = self.page.locator(".roi-overlay").first.bounding_box()
        if box is None:
            raise RuntimeError("ROI overlay not visible")
        return box

    def draw_rectangular_roi(self, x: int, y: int, width: int, height: int) -> None:
        self._set_roi_mode("rectangle")
        box = self._overlay_box()
        scale = box["width"] / 512.0
        sx, sy = box["x"] + x * scale, box["y"] + y * scale
        ex, ey = box["x"] + (x + width) * scale, box["y"] + (y + height) * scale
        self.page.mouse.move(sx, sy)
        self.page.mouse.down()
        self.page.mouse.move((sx + ex) / 2, (sy + ey) / 2)
        self.page.mouse.move(ex, ey)
        self.page.mouse.up()
        self.page.wait_for_timeout(100)

    def draw_roi(self, x: int, y: int, w: int, h: int) -> None:
        self.draw_rectangular_roi(x, y, w, h)

    def draw_freehand_roi(self, points: list[tuple[int, int]]) -> None:
        self._set_roi_mode("freehand")
        box = self._overlay_box()
        scale = box["width"] / 512.0
        screen = [(box["x"] + px * scale, box["y"] + py * scale) for px, py in points]
        self.page.mouse.move(*screen[0])
        self.page.mouse.down()
        for sx, sy in screen[1:]:
            self.page.mouse.move(sx, sy)
        self.page.mouse.up()
        self.page.wait_for_timeout(100)

    def get_rois(self) -> list[dict[str, str]]:
        rois = self.page.locator(".roi-overlay .roi")
        out: list[dict[str, str]] = []
        for i in range(rois.count()):
            has_rect = rois.nth(i).locator("rect").count() > 0
            out.append({"type": "rectangle" if has_rect else "freehand"})
        return out

    def get_decay_curve(self, roi_index: int = 0) -> dict[str, Any]:
        raw = self.page.locator("#decay-curve").get_attribute("data-decay")
        data = json.loads(raw or "{}")
        series = data.get("series", [])
        counts = series[roi_index]["counts"] if roi_index < len(series) else []
        return {"gate_offsets": data.get("gate_offsets", []), "counts": counts}

    # --- sweep / schedule -----------------------------------------------------

    def configure_sweep(self, parameter: str, values: list[Any]) -> None:
        # The UI sweeps `integration_time_ms`; accept the spec's shorthand.
        param = "integration_time_ms" if parameter == "integration_time" else parameter
        self._tab("Sweep")
        self.page.get_by_label(re.compile("Sweep parameter", re.I)).first.select_option(param)
        self.page.get_by_label(re.compile("^Values", re.I)).first.fill(
            ", ".join(str(v) for v in values)
        )

    def sweep_results_count(self) -> int:
        return self.page.locator(".sweep-results tbody tr").count()

    def schedule_acquisition(self, start_time: str) -> None:
        self._tab("Sweep")
        # datetime-local wants YYYY-MM-DDTHH:MM.
        self.page.get_by_label(re.compile("Start time", re.I)).first.fill(start_time[:16])
        self.page.locator("button", has_text=re.compile("^Schedule$")).first.click()
        self.page.wait_for_timeout(400)

    def scheduled_jobs_count(self) -> int:
        return self.page.locator('[data-testid="scheduled-job"]').count()

    # --- calibration ----------------------------------------------------------

    def run_calibration(self) -> None:
        cal = getattr(self, "_current_cal", "") or "breakdown"
        self.page.locator(f'[data-cal="{cal}"] button').first.click()
        self.page.wait_for_timeout(500)
        self._wait_idle()
        # Poll the card until the vendor step lands (status refresh is async).
        self.page.locator(f'[data-cal="{cal}"][data-state="done"]').wait_for(timeout=15000)

    def calibration_status(self, cal_type: str) -> str:
        row = self.page.locator(f'[data-cal="{cal_type}"]')
        return str(row.first.get_attribute("data-state") or "none")

    def run_noise_calibration(self) -> None:
        self.navigate_to_calibration("noise")
        self.page.locator('[data-cal="noise"] button').first.click()
        self.page.wait_for_timeout(500)
        self._wait_idle()
        self.page.wait_for_selector("#dcr-curve", timeout=15000)

    # --- alarm ----------------------------------------------------------------

    def wait_for_alarm(self, timeout: float = 15.0) -> None:
        self._tab("Health")
        self.page.locator(".alarm-banner, .alarm", has_text=re.compile("temperature", re.I)).first.wait_for(
            timeout=timeout * 1000
        )

    def alarm_visible(self) -> bool:
        return self.page.locator(".alarm-banner, .alarm").count() > 0

    def alarm_type(self) -> str:
        el = self.page.locator("[data-alarm-type]").first
        if el.count():
            return str(el.get_attribute("data-alarm-type"))
        return "over_temperature" if self.alarm_visible() else ""

    # --- presets / log --------------------------------------------------------

    def save_preset(self, name: str) -> None:
        self.page.locator('.preset-selector input[type="text"]').first.fill(name)
        self.page.locator(".preset-selector button", has_text="save preset").first.click()
        self.page.wait_for_timeout(200)

    def load_preset(self, name: str) -> None:
        self.page.locator(".preset-selector select").first.select_option(label=name)
        self.page.locator(".preset-selector button", has_text=re.compile("^load$")).first.click()

    def log_entry_count(self) -> int:
        return self.page.locator(".log-table tbody tr").count()

    def rerun_last_entry(self) -> None:
        before = self.page.locator(".log-table tbody tr").count()
        self.page.locator(".log-table button", has_text="re-run").first.click()
        self.wait_for_completion()
        self.page.locator("button", has_text="refresh").first.click()
        try:
            self.page.wait_for_function(
                "n => document.querySelectorAll('.log-table tbody tr').length > n",
                arg=before,
                timeout=8000,
            )
        except Exception:  # noqa: BLE001
            self.page.wait_for_timeout(500)


class Element:
    def __init__(self, page: Any, selector: str) -> None:
        self._loc = page.locator(selector)

    def is_visible(self) -> bool:
        return self._loc.count() > 0 and self._loc.first.is_visible()
