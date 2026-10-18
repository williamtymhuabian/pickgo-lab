import base64
import hashlib
import http.client
import json
import re
import socket
import sys
import threading
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2
import numpy as np
from legacy_vision import LegacyColorDetector, SOURCE
from app import decode_frame, handler_type
from http.server import ThreadingHTTPServer


def fixture(color="red", center=(190, 108), rotation=18, visible=True, depth_valid=True):
    image = np.full((240, 320, 3), 48, dtype=np.uint8)
    depth = np.full((240, 320), 1000, dtype=np.uint16)
    if visible:
        hsv = {"red": [4, 190, 200], "blue": [108, 190, 210], "yellow": [24, 190, 210]}[color]
        bgr = cv2.cvtColor(np.uint8([[hsv]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
        corners = cv2.boxPoints((center, (100, 72), rotation)).astype(np.int32)
        cv2.fillConvexPoly(image, corners, bgr)
        cv2.fillConvexPoly(depth, corners, 650)
    if not depth_valid:
        depth.fill(0)
    return image, depth


def packet(image, depth=None, target="red"):
    ok, png = cv2.imencode(".png", image)
    assert ok
    return {"width": image.shape[1], "height": image.shape[0], "encoding": "png-rgb", "target": target,
            "frame_id": "test-frame", "depth_unit": "mm", "image": "data:image/png;base64,"+base64.b64encode(png).decode(),
            "depth_le_u16": base64.b64encode(depth.astype("<u2").tobytes()).decode() if depth is not None else None}


class VisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = LegacyColorDetector()

    def test_original_file_is_unchanged(self):
        manifest = json.loads((ROOT/"legacy/source-manifest.json").read_text(encoding="utf-8"))
        expected = manifest["sha256"]
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), expected)
        self.assertEqual(self.detector.source_hash, expected)
        self.assertEqual(set(self.detector.lines), {"det_color", "det_rect", "col_dict_daylight_shelf_1"})

    def test_canceled_detection_does_not_break_the_local_server(self):
        entered, release = threading.Event(), threading.Event()
        errors = []
        detector = self.detector

        class DelayedDetector:
            def detect(self, *args):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("test request was not released")
                return detector.detect(*args)

            def provenance(self):
                return detector.provenance()

        class RecordingServer(ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                errors.append(sys.exc_info()[1])

        server = RecordingServer(("127.0.0.1", 0), handler_type(DelayedDetector()))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            image, _ = fixture()
            client.request("POST", "/api/vision/detect", json.dumps(packet(image)),
                           {"Content-Type": "application/json"})
            self.assertTrue(entered.wait(3))
            client.sock.shutdown(socket.SHUT_RDWR)
            client.close()
            release.set()
            followup = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                followup.request("GET", "/api/vision/status")
                response = followup.getresponse()
                self.assertEqual(response.status, 200)
                self.assertTrue(json.loads(response.read())["ready"])
            finally:
                followup.close()
        finally:
            release.set()
            client.close()
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
        self.assertEqual(errors, [])

    def test_colors_centers_angles_and_depth(self):
        for color, center, rotation in [("red", (190, 108), 18), ("blue", (112, 144), 52), ("yellow", (220, 102), -24)]:
            with self.subTest(color=color):
                image, depth = fixture(color, center, rotation)
                found = self.detector.detect(image, color, depth)
                self.assertTrue(found["found"])
                self.assertEqual(found["color"], color)
                self.assertLess(np.linalg.norm(np.asarray(found["center"])-center), 1.5)
                self.assertAlmostEqual(found["angle_deg"], rotation % 90, delta=1.2)
                self.assertEqual(found["depth"]["mm"], 650)
                self.assertEqual(found["depth"]["valid_samples"], 25)
                self.assertEqual(len(found["corners"]), 4)

    def test_missing_wrong_color_and_too_small_target(self):
        image, _ = fixture(visible=False)
        self.assertFalse(self.detector.detect(image)["found"])
        image, _ = fixture("blue")
        self.assertFalse(self.detector.detect(image, "red")["found"])
        image[:] = 48
        image[100:120, 140:160] = [51, 67, 200]
        self.assertFalse(self.detector.detect(image, "red")["found"])

    def test_actual_browser_palette_does_not_detect_background(self):
        page = (ROOT/"vision.html").read_text(encoding="utf-8")
        background = re.search(r"ctx.fillStyle='(#[0-9a-f]{6})';ctx.fillRect", page)[1]
        for color in ["red", "blue", "yellow"]:
            with self.subTest(color=color):
                palette = re.search(r"const colors=\{([^}]+)\}", page)[1]
                fill = re.search(color+r":'(#[0-9a-f]{6})'", palette)[1]
                def bgr(hex_color):
                    return [int(hex_color[i:i+2], 16) for i in (5, 3, 1)]
                image = np.empty((240, 320, 3), dtype=np.uint8)
                image[:] = bgr(background)
                self.assertFalse(self.detector.detect(image, color)["found"])
                corners = cv2.boxPoints(((245, 120), (100, 72), 80)).astype(np.int32)
                cv2.fillConvexPoly(image, corners, bgr(fill))
                result = self.detector.detect(image, color)
                self.assertTrue(result["found"])
                self.assertGreater(result["center"][0], 240)
                self.assertAlmostEqual(result["angle_deg"], 80, delta=1.2)

    def test_empty_contours_do_not_crash(self):
        image = np.full((240, 320, 3), 48, dtype=np.uint8)
        image[::2, ::2] = [51, 67, 200]
        result = self.detector.detect(image)
        self.assertFalse(result["found"])
        self.assertEqual(result["reason"], "EMPTY_CONTOURS")

    def test_missing_or_invalid_depth_is_not_fabricated(self):
        image, depth = fixture(depth_valid=False)
        self.assertIsNone(self.detector.detect(image, depth_mm=depth)["depth"])
        self.assertIsNone(self.detector.detect(image)["depth"])

    def test_frame_decode_preserves_rgb_depth_alignment(self):
        image, depth = fixture()
        decoded, decoded_depth = decode_frame(packet(image, depth))
        np.testing.assert_array_equal(decoded, image)
        np.testing.assert_array_equal(decoded_depth, depth)
        broken = packet(image, depth)
        broken["width"] = 100
        with self.assertRaisesRegex(ValueError, "metadata"):
            decode_frame(broken)
        broken = packet(image, depth)
        broken["depth_le_u16"] = base64.b64encode(b"short").decode()
        with self.assertRaisesRegex(ValueError, "Depth buffer"):
            decode_frame(broken)

    def test_no_robot_modules_imported(self):
        image, _ = fixture()
        self.detector.detect(image)
        for module in ["rospy", "frrpc", "grap", "Arm1_server_M1_for_log"]:
            self.assertNotIn(module, sys.modules)

    def test_http_api_and_validation(self):
        class Quiet(handler_type(self.detector)):
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def request(method, path, body=None, headers=None):
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=8)
                connection.request(method, path, body, headers or {})
                response = connection.getresponse()
                status, value = response.status, json.loads(response.read())
                connection.close()
                return status, value
            code, value = request("GET", "/api/vision/status")
            self.assertEqual(code, 200)
            self.assertTrue(value["ready"])
            image, depth = fixture()
            payload = packet(image, depth)
            # Deliberately wrong ground truth is ignored; only pixels determine the center.
            payload["object_center"] = [-999, -999]
            code, value = request("POST", "/api/vision/detect", json.dumps(payload), {"Content-Type": "application/json"})
            self.assertEqual(code, 200)
            self.assertTrue(value["found"])
            self.assertEqual(value["frame_id"], "test-frame")
            self.assertGreater(value["center"][0], 180)
            code, _ = request("POST", "/api/vision/detect", "{}", {"Content-Type": "application/json", "Origin": "https://external.invalid"})
            self.assertEqual(code, 403)
            code, _ = request("POST", "/api/vision/detect", "{}", {"Content-Type": "application/json"})
            self.assertEqual(code, 400)
            code, _ = request("POST", "/api/vision/detect", "x", {"Content-Type": "text/plain"})
            self.assertEqual(code, 415)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
