"""PickGo Lab 本机入口：共享运动仿真、原颜色算法、物体检测与前景分割。"""
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
from deployment_config import load_config

ROOT = Path(__file__).resolve().parent
STATIC = {"/": "index.html", "/index.html": "index.html", "/vision.html": "vision.html", "/camera.js": "camera.js", "/vision_helpers.js": "vision_helpers.js",
          "/simulator-core.js": "simulator-core.js", "/observation_state.js": "observation_state.js", "/observation_ui.js": "observation_ui.js", "/vision_speech.js": "vision_speech.js", "/depth_client.js":"depth_client.js"}


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


def detect_objects_frame(objects, payload):
    if objects is None:
        raise RuntimeError("视觉依赖未安装，请运行 python -m pip install -r requirements.txt")
    from object_vision import run_vision
    image, _ = decode_frame(payload)
    result = run_vision(objects, image, payload.get("task", "objects"),
                        payload.get("confidence_pct", 40), payload.get("classes"),
                        payload.get("roi"), payload.get("max_objects", 5))
    result["frame_id"] = str(payload.get("frame_id", ""))[:80]
    result["image_size"] = [image.shape[1], image.shape[0]]
    return result


def assess_observation_frame(payload):
    from observation_quality import assess_observation
    image, _ = decode_frame(payload)
    result = assess_observation(image, payload.get("roi"), payload.get("tolerance_px", 6),
                                payload.get("max_samples", 5), payload.get("policy", "adaptive"))
    result["frame_id"] = str(payload.get("frame_id", ""))[:80]
    result["image_size"] = [image.shape[1], image.shape[0]]
    return result


def detect_frame(detector, payload):
    if detector is None:
        raise RuntimeError("视觉依赖未安装，请运行 python -m pip install -r requirements.txt")
    image, depth = decode_frame(payload)
    result = detector.detect(image, payload.get("target", "red"), depth)
    result["frame_id"] = str(payload.get("frame_id", ""))[:80]
    result["image_size"] = [image.shape[1], image.shape[0]]
    result["backend"] = "original-python-opencv"
    return result


def handler_type(detector, context=None, objects=None, depth_camera=None):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, value, status=200):
            data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # A canceled browser request is already gone; do not send a second response.
                return

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
            if route == "/api/depth/status":
                from realsense_camera import status, create_camera
                return self.send_json(status(depth_camera if depth_camera is not None else create_camera()))
            if route == "/api/vision/speech/status":
                from speech_audio import status
                return self.send_json(status())
            if route == "/api/vision/status":
                from importlib.util import find_spec
                object_status = None
                if objects is not None and find_spec("cv2") and find_spec("numpy"):
                    from object_vision import model_status
                    object_status = model_status(objects)
                assessment_status = None
                if object_status is not None:
                    from observation_quality import capabilities
                    assessment_status = capabilities()
                return self.send_json({"ready": detector is not None, "provenance": detector.provenance() if detector else None,
                                       "objects": object_status, "assessment": assessment_status, "max_frame": [640, 480], "storage": "Images processed in memory only"})
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
            self.send_header("Content-Type", "text/javascript; charset=utf-8" if route.endswith(".js") else "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if not self.same_origin():
                return self.send_json({"error": "Local same-origin access required"}, 403)
            route = urlsplit(self.path).path
            if route not in ("/api/vision/detect", "/api/vision/objects", "/api/vision/assess", "/api/vision/speech", "/api/robot/command", "/api/depth/open", "/api/depth/frame", "/api/depth/measure", "/api/depth/close"):
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
                if route.startswith('/api/depth/'):
                    if depth_camera is None:
                        raise RuntimeError('RGB-D 入口未启用，请重启本机服务')
                    from realsense_camera import open_camera, read_frame, measure_frame, close_camera
                    if route == '/api/depth/open':
                        return self.send_json(open_camera(depth_camera))
                    token = payload.get('token')
                    if route == '/api/depth/close':
                        if not isinstance(token,str):
                            raise ValueError('Missing RGB-D session')
                        return self.send_json(close_camera(depth_camera,token))
                    if route == '/api/depth/measure':
                        return self.send_json(measure_frame(depth_camera,token,payload.get('frame_id'),payload.get('x'),payload.get('y')))
                    point = payload.get('point')
                    if point is not None and (not isinstance(point,list) or len(point)!=2 or any(type(v) is not int for v in point)):
                        raise ValueError('测距点必须是两个整数像素坐标')
                    return self.send_json(read_frame(depth_camera,token,objects,point=point,task=payload.get('task','objects'),confidence_pct=payload.get('confidence_pct',40),classes=payload.get('classes')))
                if route == "/api/vision/speech":
                    from speech_audio import synthesize, validate_text
                    return self.send_json(synthesize(validate_text(payload.get("text"))))
                if route == "/api/robot/command":
                    if context is None:
                        raise RuntimeError("Simulation is not enabled")
                    command, params = payload.get("command"), payload.get("params", {})
                    if command not in ("start", "pause", "resume", "stop", "reset", "select", "speed", "joint", "jaw", "stow", "drive") or not isinstance(params, dict):
                        raise ValueError("Invalid command or parameters")
                    source = "mcp" if payload.get("source") == "mcp" else "web"
                    return self.send_json(utils.run_command({**context, "source": source}, command, params))
                if route == "/api/vision/assess":
                    if objects is None:
                        raise RuntimeError("视觉依赖未安装，请运行 python -m pip install -r requirements.txt")
                    return self.send_json(assess_observation_frame(payload))
                self.send_json(detect_objects_frame(objects, payload) if route == "/api/vision/objects" else detect_frame(detector, payload))
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


def parse_options(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="部署 JSON 配置文件")
    parser.add_argument("--check-config", action="store_true", help="输出有效配置后退出，不启动服务")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--vision-only", action="store_true", default=None, help="camera / vision only; no Node.js or simulation process")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except (OSError, ValueError, RecursionError) as error:
        parser.error(str(error))
    args.schema_version = config["schema_version"]
    args.host = config["host"]
    if args.port is None:
        args.port = config["port"]
    if args.vision_only is None:
        args.vision_only = config["vision_only"]
    return args


def main(argv=None):
    args = parse_options(argv)
    if args.check_config:
        print(json.dumps({"schema_version": args.schema_version, "host": args.host,
                          "port": args.port, "vision_only": args.vision_only},
                         ensure_ascii=False, allow_nan=False))
        return
    detector, objects = None, None
    try:
        from legacy_vision import LegacyColorDetector
        detector = LegacyColorDetector()
        from object_vision import all_init as objects_init
        objects = objects_init()
    except ImportError:
        print("视觉依赖未安装，运动仿真和 MCP 可以正常使用。", flush=True)
    context = None if args.vision_only else utils.all_init(detector=detector)
    from realsense_camera import create_camera, close_camera
    depth_camera = create_camera()
    try:
        with ThreadingHTTPServer((args.host, args.port), handler_type(detector, context, objects, depth_camera)) as server:
            page = "/vision.html?source=camera" if args.vision_only else "/"
            print(f"PickGo Lab: http://127.0.0.1:{args.port}{page}", flush=True)
            if context:
                print(f"MCP: python -B mcp_server.py --server-url http://127.0.0.1:{args.port}", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        close_camera(depth_camera)
        if context:
            utils.close(context)


if __name__ == "__main__":
    main()
