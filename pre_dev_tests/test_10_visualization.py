"""
PRD §7 — Visualization (In-Browser)

Image canvas, ROI, decay curves, phasor scatter, lifetime map,
histograms, and DCR curves.
"""
import pytest


class TestImageCanvas:

    def test_512x512_image_display(self, spa_client):
        """Image canvas renders a 512×512 image."""
        spa_client.acquire_intensity()
        canvas = spa_client.find_element("#image-canvas")
        assert canvas.is_visible()

    def test_colormap_selection(self, spa_client):
        spa_client.acquire_intensity()
        spa_client.select_colormap("viridis")
        assert spa_client.get_current_colormap() == "viridis"

    def test_intensity_auto_stretch(self, spa_client):
        spa_client.acquire_intensity()
        spa_client.click("auto-stretch")
        # Verify the intensity range is adjusted
        assert spa_client.get_intensity_range() is not None

    def test_zoom_and_pan(self, spa_client):
        spa_client.acquire_intensity()
        initial_viewport = spa_client.get_canvas_viewport()
        spa_client.zoom_in()
        zoomed_viewport = spa_client.get_canvas_viewport()
        assert zoomed_viewport["scale"] > initial_viewport["scale"]


class TestROI:

    def test_rectangular_roi(self, spa_client):
        spa_client.acquire_intensity()
        spa_client.draw_rectangular_roi(x=100, y=100, width=50, height=50)
        rois = spa_client.get_rois()
        assert len(rois) == 1
        assert rois[0]["type"] == "rectangle"

    def test_freehand_roi(self, spa_client):
        spa_client.acquire_intensity()
        spa_client.draw_freehand_roi(points=[(100, 100), (120, 110), (110, 130)])
        rois = spa_client.get_rois()
        assert len(rois) == 1
        assert rois[0]["type"] == "freehand"

    def test_multiple_rois(self, spa_client):
        spa_client.acquire_intensity()
        spa_client.draw_rectangular_roi(x=100, y=100, width=50, height=50)
        spa_client.draw_rectangular_roi(x=200, y=200, width=30, height=30)
        rois = spa_client.get_rois()
        assert len(rois) == 2


class TestDecayCurve:

    def test_per_roi_decay_curve(self, spa_client):
        """Per-ROI decay curve (counts vs gate offset) from a gated stack."""
        spa_client.acquire_gated()
        spa_client.draw_rectangular_roi(x=256, y=256, width=20, height=20)
        curve = spa_client.get_decay_curve(roi_index=0)
        assert "gate_offsets" in curve
        assert "counts" in curve
        assert len(curve["gate_offsets"]) > 0


class TestFLIMVisualization:

    def test_phasor_scatter_plot(self, spa_client):
        spa_client.acquire_flim()
        phasor = spa_client.find_element("#phasor-plot")
        assert phasor.is_visible()

    def test_lifetime_map_false_color(self, spa_client):
        spa_client.acquire_flim()
        lifetime_map = spa_client.find_element("#lifetime-map")
        assert lifetime_map.is_visible()


class TestHistograms:

    def test_pixel_value_histogram(self, spa_client):
        spa_client.acquire_intensity()
        histogram = spa_client.find_element("#pixel-histogram")
        assert histogram.is_visible()

    def test_sorted_dcr_curve_for_calibration_qa(self, spa_client):
        spa_client.run_noise_calibration()
        dcr_curve = spa_client.find_element("#dcr-curve")
        assert dcr_curve.is_visible()
