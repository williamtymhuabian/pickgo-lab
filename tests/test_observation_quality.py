"""Same-frame sensitivity, API/MCP, budget boundaries and offline weights checks."""
import http.client
import json
import subprocess
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import numpy as np
import object_vision
import observation_quality as Q
import setup_objects
import utils
from app import handler_type, assess_observation_frame
from test_vision import packet


def image_fixture():
    image = np.full((180, 240, 3), 30, np.uint8)
    cv2.ellipse(image, (120, 90), (38, 27), 0, 0, 360, (40, 185, 225), -1)
    return image


class QualityTests(unittest.TestCase):
    def test_real_grabcut_adaptive_stops_after_consistent_three(self):
        result = Q.assess_observation(image_fixture(), [55, 35, 185, 145])
        self.assertEqual(result["status"], "CONSISTENT")
        self.assertEqual(result["metrics"]["sample_count"], 3)
        self.assertEqual(result["stop_reason"], "sufficient_pixel_consistency")
        self.assertFalse(result["robot_execution_authorized"])
        self.assertGreater(result["metrics"]["core_area_px"], 2500)
        self.assertIsNotNone(result["metrics"]["candidate_surface_pixel"])

    def test_fixed_budget_uses_all_five(self):
        result = Q.assess_observation(image_fixture(), [55, 35, 185, 145], policy="fixed")
        self.assertEqual(result["metrics"]["sample_count"], 5)
        self.assertEqual(result["stop_reason"], "max_samples")

    def test_uniform_image_does_not_manufacture_foreground(self):
        result = Q.assess_observation(np.zeros((100, 120, 3), np.uint8), [10, 10, 110, 90])
        self.assertEqual(result["status"], "NO_FOREGROUND")
        self.assertIsNone(result["metrics"]["candidate_surface_pixel"])

    def test_disagreement_cannot_pass_despite_all_masks_nonempty(self):
        a = np.zeros((100, 100), bool)
        b = a.copy()
        a[20:60, 10:40] = True
        b[20:60, 50:80] = True
        stats, core, _ = Q.summarize_masks([a, b, a], 6)
        self.assertFalse(stats["consistent"])
        self.assertEqual(stats["valid_samples"], 3)
        self.assertFalse(core.any())

    def test_hollow_object_candidate_is_inside_foreground(self):
        mask = np.zeros((100, 100), np.uint8)
        cv2.circle(mask, (50, 50), 30, 1, -1)
        cv2.circle(mask, (50, 50), 15, 0, -1)
        stats, _, _ = Q.summarize_masks([mask.astype(bool)] * 3, 3)
        x, y = stats["candidate_surface_pixel"]
        self.assertEqual(mask[y, x], 1)
        self.assertEqual(mask[50, 50], 0)

    def test_single_mask_and_early_budget_stop_are_incomplete(self):
        stats, _, _ = Q.summarize_masks([np.ones((30, 30), bool)], 2)
        self.assertFalse(stats["consistent"])
        with patch.dict(Q.CONFIG, {"time_budget_s": 0}):
            result = Q.assess_observation(image_fixture(), [55, 35, 185, 145])
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["stop_reason"], "time_budget")

    def test_invalid_parameters_rejected(self):
        for kwargs in [dict(roi=[0, 0, 999, 9]), dict(roi=[0, 0, 4, 4]), dict(roi=[True, 0, 20, 20]),
                       dict(tolerance_px=True), dict(tolerance_px=0), dict(max_samples=4), dict(policy="unknown")]:
            values = {"roi": [55, 35, 185, 145], **kwargs}
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Q.assess_observation(image_fixture(), **values)

    def test_busy_assessment_rejects_new_work(self):
        Q._LOCK.acquire()
        try:
            with self.assertRaises(RuntimeError):
                Q.assess_observation(image_fixture(), [55, 35, 185, 145])
        finally:
            Q._LOCK.release()

    def test_frame_metadata_and_mcp_readonly_without_weights(self):
        frame = packet(image_fixture())
        result = assess_observation_frame({**frame, "roi": [55, 35, 185, 145]})
        self.assertEqual(result["frame_id"], frame["frame_id"])
        self.assertEqual(result["image_size"], [240, 180])
        frame.pop("target")
        frame.pop("depth_le_u16")
        context = {"server_url": None, "robot": None}
        value = utils.call_tool(context, "assess_observation", {"frame": frame, "roi": [55, 35, 185, 145]})
        self.assertEqual(value["status"], "CONSISTENT")
        self.assertIsNone(context["robot"])
        tool = next(x for x in utils.list_tools() if x["name"] == "assess_observation")
        self.assertTrue(tool["annotations"]["readOnlyHint"])

    def test_weights_manifest_and_info_do_not_use_network(self):
        manifest = json.loads((ROOT / "models/weights-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["models"][0], setup_objects.download_info())
        self.assertEqual(object_vision.MODEL["sha256"], setup_objects.SHA256)
        with patch("urllib.request.urlopen", side_effect=AssertionError("No network allowed")):
            self.assertFalse(setup_objects.check_model()["network_used"])
            setup_objects.download_info()
        run = subprocess.run([sys.executable, "-B", str(ROOT / "setup_objects.py"), "--info"], capture_output=True, text=True, encoding="utf-8", env={**__import__('os').environ,"PYTHONIOENCODING":"utf-8"})
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["bytes"], 3800954)

    def test_http_status_assessment_and_origin_checks(self):
        class Quiet(handler_type(None, objects=object_vision.all_init(ROOT / "models/missing.onnx"))):
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            connection.request("GET", "/api/vision/status")
            value = json.loads(connection.getresponse().read())
            self.assertTrue(value["assessment"]["ready"])
            self.assertFalse(value["objects"]["available"])
            payload = {**packet(image_fixture()), "roi": [55, 35, 185, 145]}
            connection.request("POST", "/api/vision/assess", json.dumps(payload), {"Content-Type": "application/json"})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["status"], "CONSISTENT")
            connection.request("POST", "/api/vision/assess", "{}", {"Content-Type": "application/json"})
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            connection.request("POST", "/api/vision/assess", "{}", {"Content-Type": "application/json", "Origin": "https://outside.invalid"})
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
