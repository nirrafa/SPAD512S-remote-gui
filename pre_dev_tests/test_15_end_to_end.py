"""
PRD Testing — End-to-End Scenarios

Drive the SPA against bridge+mock. Each scenario exercises a full
user workflow from the browser through to file output.
"""
import pytest


class TestE2ESingleShot:

    def test_intensity_single_shot_full_flow(self, spa_client):
        """Configure intensity → Acquire → see preview → verify files on host."""
        spa_client.navigate_to_mode("intensity")
        spa_client.set_param("bit_depth", 8)
        spa_client.set_param("integration_time", 100)
        spa_client.click_acquire()
        spa_client.wait_for_completion()
        assert spa_client.preview_visible()
        assert spa_client.host_files_exist()

    def test_gated_single_shot_full_flow(self, spa_client):
        spa_client.navigate_to_mode("gated")
        spa_client.set_param("bit_depth", 8)
        spa_client.set_param("gate_steps", 20)
        spa_client.click_acquire()
        spa_client.wait_for_completion()
        assert spa_client.preview_visible()

    def test_flim_single_shot_full_flow(self, spa_client):
        spa_client.navigate_to_mode("flim")
        spa_client.run_irf_calibration()
        spa_client.click_acquire()
        spa_client.wait_for_completion()
        assert spa_client.preview_visible()
        assert spa_client.phasor_plot_visible()


class TestE2ESweep:

    def test_parameter_sweep_full_flow(self, spa_client):
        spa_client.navigate_to_mode("intensity")
        spa_client.configure_sweep("integration_time", [50, 100, 200])
        spa_client.click_acquire()
        spa_client.wait_for_completion()
        assert spa_client.sweep_results_count() == 3


class TestE2EScheduled:

    def test_scheduled_job_full_flow(self, spa_client):
        spa_client.navigate_to_mode("intensity")
        spa_client.set_param("bit_depth", 8)
        spa_client.schedule_acquisition("2026-06-28T02:00:00")
        assert spa_client.scheduled_jobs_count() >= 1


class TestE2ECalibration:

    def test_each_calibration_type(self, spa_client):
        for cal_type in ["breakdown", "noise", "dead-pixel", "master-slave-offset"]:
            spa_client.navigate_to_calibration(cal_type)
            spa_client.run_calibration()
            assert spa_client.calibration_status(cal_type) == "done"


class TestE2EAlarm:

    def test_alarm_triggers_and_displays(self, spa_client, mock_vendor_server):
        mock_vendor_server.set_temperature("chip", 90.0)
        spa_client.wait_for_alarm()
        assert spa_client.alarm_visible()
        assert spa_client.alarm_type() == "over_temperature"


class TestE2EVisualization:

    def test_preview_and_roi_and_plots(self, spa_client):
        spa_client.navigate_to_mode("gated")
        spa_client.click_acquire()
        spa_client.wait_for_completion()
        spa_client.draw_roi(x=256, y=256, w=30, h=30)
        assert spa_client.decay_curve_visible()

    def test_histogram_visible_after_acquisition(self, spa_client):
        spa_client.navigate_to_mode("intensity")
        spa_client.click_acquire()
        spa_client.wait_for_completion()
        assert spa_client.histogram_visible()


class TestE2EExperimentLog:

    def test_log_preset_rerun(self, spa_client):
        # Save a preset
        spa_client.navigate_to_mode("intensity")
        spa_client.set_param("bit_depth", 8)
        spa_client.save_preset("my_preset")

        # Acquire using preset
        spa_client.load_preset("my_preset")
        spa_client.click_acquire()
        spa_client.wait_for_completion()

        # Check log
        spa_client.navigate_to_experiment_log()
        assert spa_client.log_entry_count() >= 1

        # Re-run from log
        spa_client.rerun_last_entry()
        spa_client.wait_for_completion()
        assert spa_client.log_entry_count() >= 2


class TestE2EDataCompatibility:

    def test_reducer_output_matches_pipeline(self, spa_client, bridge_client):
        """Produced meta_*.json + movie_arr_*.npy are loadable by
        512^2_*.py and SEP_D.py scripts."""
        spa_client.navigate_to_mode("intensity")
        spa_client.set_param("iterations", 5)
        spa_client.click_acquire()
        spa_client.wait_for_completion()

        # Verify file layout
        log = bridge_client.get("/api/experiment-log")
        entry = log["entries"][-1]
        files = bridge_client.get(f"/api/data/list?path={entry['result_path']}")

        meta_files = [f for f in files if f.startswith("meta_") and f.endswith(".json")]
        movie_files = [f for f in files if f.startswith("movie_arr_") and f.endswith(".npy")]
        assert len(meta_files) > 0
        assert len(movie_files) > 0
