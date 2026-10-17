"""PickGo Lab 本机入口：共享运动仿真＋可选原代码视觉验证。"""
import argparse
import base64
import binascii
import json
import struct
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import utils
from Constants import APP

ROOT = Path(__file__).resolve().parent
STATIC = {"/": "index.html", "/index.html": "index.html", "/vision.html": "vision.html"}


def reject_constant(value):
    raise ValueError("Invalid JSON constant: " + value)


def decode_frame(payload):
    import cv2
    import numpy as np
    if not isinstance(payload, dict):
        raise ValueError("Expected frame object")
    if payload.get("encoding") != "png-rgb" or payload.get("depth_unit") not in (None, "mm"):
        raise ValueError("Unsupported frame encoding")
    image_data = payload.get("image", "")
    if not isinstance(image_data, str) or not image_data.startswith("data:image/png;base64,"):
        raise ValueError("Expected PNG data URL")
    raw = base64.b64decode(image_data.split(",", 1)[1], validate=True)
    if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Invalid PNG")
    w, h = struct.unpack(">II", raw[16:24])
    if not (8 <= w <= 640 and 8 <= h <= 480):
        raise ValueError("Image exceeds supported dimensions")
    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.shape[:2] != (h, w):
        raise ValueError("Cannot decode image")
    if payload.get("width") != w or payload.get("height") != h:
        raise ValueError("Frame metadata does not match image")
    depth = None
    if payload.get("depth_le_u16") is not None:
        encoded = payload["depth_le_u16"]
        if not isinstance(encoded, str):
            raise ValueError("Invalid depth buffer")
        buffer = base64.b64decode(encoded, validate=True)
        if len(buffer) != w*h*2:
            raise ValueError("Depth buffer does not match image dimensions")
        depth = np.frombuffer(buffer, dtype="<u2").reshape(h, w).astype(np.uint16, copy=False)
    return image, depth


def detect_frame(detector, payload):
    if detector is None:
        raise RuntimeError("视觉依赖未安装，请运行 python -m pip install -r requirements.txt")
    image, depth = decode_frame(payload)
    result = detector.detect(image, payload.get("target", "red"), depth)
    result["frame_id"] = str(payload.get("frame_id", ""))[:80]
    result["image_size"] = [image.shape[1], image.shape[0]]
    result["backend"] = "original-python-opencv"
    return result


def handler_type(detector, context=None):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, value, status=200):
            data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def same_origin(self):
            expected = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in expected:
                return False
            origin = self.headers.get("Origin")
            return (origin is None or origin in {"http://"+host for host in expected}) and self.headers.get("Sec-Fetch-Site") != "cross-site"

        def do_GET(self):
            if not self.same_origin():
                return self.send_json({"error": "Local same-origin access required"}, 403)
            route = urlsplit(self.path).path
            if route == "/api/vision/status":
                return self.send_json({"ready": detector is not None, "provenance": detector.provenance() if detector else None, "max_frame": [640, 480], "storage": "Images processed in memory only"})
            if route == "/api/robot/state":
                try:
                    if context is None:
                        raise RuntimeError("Simulation is not enabled")
                    return self.send_json(utils.get_robot_state(context))
                except RuntimeError as error:
                    return self.send_json({"error": str(error)}, 503)
            if route not in STATIC:
                return self.send_json({"error": "Not found"}, 404)
            data = (ROOT/STATIC[route]).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if not self.same_origin():
                return self.send_json({"error": "Local same-origin access required"}, 403)
            route = urlsplit(self.path).path
            if route not in ("/api/vision/detect", "/api/robot/command"):
                return self.send_json({"error": "Not found"}, 404)
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.send_json({"error": "Expected application/json"}, 415)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1_000_000:
                    return self.send_json({"error": "Frame request exceeds 1 MB limit"}, 413)
                payload = json.loads(self.rfile.read(size), parse_constant=reject_constant)
                if not isinstance(payload, dict):
                    raise ValueError("Expected request object")
                if route == "/api/robot/command":
                    if context is None:
                        raise RuntimeError("Simulation is not enabled")
                    command, params = payload.get("command"), payload.get("params", {})
                    if command not in ("start", "pause", "resume", "stop", "reset", "select", "speed", "joint", "jaw", "stow", "drive") or not isinstance(params, dict):
                        raise ValueError("Invalid command or parameters")
                    source = "mcp" if payload.get("source") == "mcp" else "web"
                    return self.send_json(utils.run_command({**context, "source": source}, command, params))
                self.send_json(detect_frame(detector, payload))
            except (ValueError, TypeError, KeyError, binascii.Error) as error:
                self.send_json({"error": str(error)}, 400)
            except RuntimeError as error:
                self.send_json({"error": str(error)}, 503)
            except Exception as error:
                print("Request error:", type(error).__name__, str(error), file=sys.stderr, flush=True)
                self.send_json({"error": "Request failed"}, 500)

        def log_message(self, format, *args):
            if not self.path.startswith("/api/robot/state"):
                super().log_message(format, *args)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=APP["port"])
    args = parser.parse_args()
    detector = None
    try:
        from legacy_vision import LegacyColorDetector
        detector = LegacyColorDetector()
    except ImportError:
        print("视觉依赖未安装，运动仿真和 MCP 可以正常使用。", flush=True)
    context = utils.all_init(detector=detector)
    try:
        with ThreadingHTTPServer((APP["host"], args.port), handler_type(detector, context)) as server:
            print(f"PickGo Lab: http://127.0.0.1:{args.port}/", flush=True)
            print(f"MCP: python -B mcp_server.py --server-url http://127.0.0.1:{args.port}", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        utils.close(context)


if __name__ == "__main__":
    main()
