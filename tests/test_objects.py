"""物体后处理、真实 GrabCut、HTTP 与 MCP；无需联网、相机或模型即可跑回归。"""
import base64
import http.client
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import numpy as np
import object_vision as vision
import utils
from app import detect_objects_frame, handler_type
from test_vision import packet


def foreground_fixture():
    image = np.full((240, 320, 3), 35, np.uint8)
    cv2.ellipse(image, (160, 120), (50, 36), 0, 0, 360, (30, 190, 225), -1)
    return image


def predictions():
    outputs = []
    for stride in (8, 16, 32):
        count = (416 // stride) ** 2
        outputs.extend([np.zeros((1, count, 80), np.float32), np.zeros((1, count, 32), np.float32)])
    return outputs


class ObjectVisionTests(unittest.TestCase):
    def test_manual_segmentation_extracts_foreground_without_weights(self):
        context = vision.all_init(ROOT / "models/does-not-exist.onnx")
        image = foreground_fixture()
        result = vision.run_vision(context, image, "manual", roi=[80, 55, 240, 185])
        self.assertTrue(result["found"])
        self.assertIsNone(result["model"])
        self.assertIsNone(result["depth"])
        self.assertIsNone(result["objects"][0]["score"])
        mask = result["objects"][0]["mask"]
        decoded = cv2.imdecode(np.frombuffer(base64.b64decode(mask["image"].split(",")[1]), np.uint8), cv2.IMREAD_GRAYSCALE)
        self.assertEqual(decoded.shape, image.shape[:2])
        self.assertEqual(decoded[120, 160], 255)
        self.assertEqual(decoded[60, 85], 0)
        self.assertEqual(mask["area_px"], np.count_nonzero(decoded))
        self.assertLess(np.linalg.norm(np.array(mask["center"])-[160, 120]), 2)

    def test_empty_foreground_is_not_fabricated(self):
        mask = vision.segment_box(np.zeros((100, 100, 3), np.uint8), [10, 10, 90, 90])
        self.assertFalse(mask["found"])
        self.assertNotIn("image", mask)

    def test_missing_or_corrupt_model_reports_error_without_download(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.onnx"
            context = vision.all_init(path)
            self.assertFalse(vision.model_status(context)["available"])
            with self.assertRaisesRegex(RuntimeError, "setup_objects"):
                vision.run_vision(context, foreground_fixture())
            path.write_bytes(b"corrupt")
            with self.assertRaisesRegex(RuntimeError, "完整性"):
                vision.load_model(context)

    def test_invalid_parameters_and_rois(self):
        context = vision.all_init()
        for args in [dict(task="unknown"), dict(confidence_pct=True), dict(confidence_pct=1),
                     dict(max_objects=6), dict(classes=["custom-part"]), dict(classes="cup"),
                     dict(task="manual", roi=[0, 0, 999, 9]), dict(task="manual", roi=[0, 0, 10.1, 20]),
                     dict(task="manual", roi=[20, 20, 10, 10])]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                vision.run_vision(context, foreground_fixture(), **args)

    def test_postprocessing_class_filter_nms_and_non_square_coordinates(self):
        outputs = predictions()
        # 在同一位置模拟 bottle 与 cup，验证 NMS 不跨类别误删。
        index = 25 * 52 + 25
        outputs[0][0, index, 39] = .9
        outputs[0][0, index+1, 41] = .8
        _, transform = vision.prepare_image(np.zeros((240, 320, 3), np.uint8))
        result = vision.decode_predictions(outputs, (240, 320, 3), transform, .4, [], 5)
        self.assertEqual([x["label"] for x in result], ["bottle", "cup"])
        self.assertAlmostEqual(result[0]["center"][0], 203.5/1.3, delta=.1)
        self.assertAlmostEqual(result[0]["center"][1], (203.5-52)/1.3, delta=.1)
        filtered = vision.decode_predictions(outputs, (240, 320, 3), transform, .4, ["cup"], 5)
        self.assertEqual([x["label"] for x in filtered], ["cup"])
        outputs[0][0, index+1, 39] = .95
        same_class = vision.decode_predictions(outputs, (240, 320, 3), transform, .4, [], 5)
        self.assertEqual(len(same_class), 1)

    def test_no_target_and_malformed_model_outputs(self):
        self.assertEqual(vision.decode_predictions(predictions(), (240, 320, 3), (0, 52, 1.3, 1.3), .4, [], 5), [])
        with self.assertRaisesRegex(RuntimeError, "Missing"):
            vision.decode_predictions([], (240, 320, 3), (0, 52, 1.3, 1.3), .4, [], 5)
        with self.assertRaisesRegex(RuntimeError, "non-finite"):
            vision.decode_predictions([np.full((1, 2704, 80), np.nan)], (240, 320, 3), (0, 52, 1.3, 1.3), .4, [], 5)

    def test_frame_id_and_dimensions_preserved(self):
        image = foreground_fixture()
        payload = {**packet(image), "task": "manual", "roi": [80, 55, 240, 185]}
        result = detect_objects_frame(vision.all_init(), payload)
        self.assertEqual(result["frame_id"], payload["frame_id"])
        self.assertEqual(result["image_size"], [320, 240])

    def test_mcp_tool_runs_segmentation_without_motion(self):
        from mcp_server import dispatch
        context = {"server_url": None, "objects": vision.all_init(), "robot": None}
        frame = packet(foreground_fixture())
        frame.pop("target")
        frame.pop("depth_le_u16")
        result = dispatch(context, {"ready": True}, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": "detect_objects", "arguments": {"frame": frame, "task": "manual", "roi": [80, 55, 240, 185]}}})
        self.assertFalse(result["result"]["isError"])
        value = json.loads(result["result"]["content"][0]["text"])
        self.assertTrue(value["found"])
        self.assertIsNone(context["robot"])
        with self.assertRaises(ValueError):
            utils.call_tool(context, "detect_objects", {"frame": frame, "roi": [False, 1, 5, 6]})

    def test_http_manual_missing_model_and_origin(self):
        class Quiet(handler_type(None, objects=vision.all_init(ROOT / "models/not-installed.onnx"))):
            def log_message(self, *args):
                pass
        with ThreadingHTTPServer(("127.0.0.1", 0), Quiet) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
            try:
                payload = {**packet(foreground_fixture()), "task": "manual", "roi": [80, 55, 240, 185]}
                connection.request("POST", "/api/vision/objects", json.dumps(payload), {"Content-Type": "application/json"})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertTrue(json.loads(response.read())["found"])
                payload["task"] = "objects"
                connection.request("POST", "/api/vision/objects", json.dumps(payload), {"Content-Type": "application/json"})
                response = connection.getresponse()
                self.assertEqual(response.status, 503)
                self.assertIn("setup_objects", json.loads(response.read())["error"])
                connection.request("POST", "/api/vision/objects", "{}", {"Content-Type": "application/json", "Origin": "https://external.invalid"})
                response = connection.getresponse()
                self.assertEqual(response.status, 403)
                response.read()
            finally:
                connection.close()
                server.shutdown()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
