"""Run selected original vision functions without importing ROS or robot modules."""
import ast
import hashlib
import time
from pathlib import Path

import cv2
import numpy as np

SOURCE = Path(__file__).resolve().parent / "legacy/utils.py"
PROFILE = "col_dict_daylight_shelf_1"
FUNCTIONS = ("det_color", "det_rect")


class NumpyCompat:
    """np.int0 is an old alias of np.intp; keep the original function unchanged."""
    def __getattr__(self, name):
        return np.intp if name == "int0" else getattr(np, name)


class LegacyColorDetector:
    def __init__(self, source=SOURCE):
        self.path = Path(source)
        raw = self.path.read_bytes()
        text = raw.decode("utf-8-sig")
        tree = ast.parse(text, filename=str(self.path))
        selected = []
        self.lines = {}
        self.hashes = {}
        for node in tree.body:
            name = node.name if isinstance(node, ast.FunctionDef) else None
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
            if name in (*FUNCTIONS, PROFILE):
                selected.append(node)
                self.lines[name] = node.lineno
                self.hashes[name] = hashlib.sha256(ast.get_source_segment(text, node).encode()).hexdigest()
        if set(self.lines) != {*FUNCTIONS, PROFILE}:
            raise RuntimeError("Original vision functions or HSV profile are missing")
        # Compile only the two definitions and one HSV assignment. No imports or
        # initialization from the original module run here. The original body,
        # including the 0.4-second sleep, is not rewritten.
        self.code = compile(ast.Module(body=selected, type_ignores=[]), str(self.path), "exec")
        self.source_hash = hashlib.sha256(raw).hexdigest()

    def provenance(self):
        return {
            "source": "legacy/utils.py",
            "source_sha256": self.source_hash,
            "function_sha256": self.hashes,
            "functions": list(FUNCTIONS),
            "lines": self.lines,
            "hsv_profile": PROFILE,
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "compatibility": "np.int0 mapped to np.intp; original function bodies unchanged",
            "hardware_imports": False,
        }

    def detect(self, bgr, color="red", depth_mm=None):
        if color not in ("red", "blue", "yellow", "auto"):
            raise ValueError("Unsupported target color")
        if not isinstance(bgr, np.ndarray) or bgr.dtype != np.uint8 or bgr.ndim != 3 or bgr.shape[2] != 3:
            raise ValueError("Expected uint8 BGR image")
        h, w = bgr.shape[:2]
        if h < 8 or w < 8 or h > 480 or w > 640:
            raise ValueError("Image must be between 8x8 and 640x480 pixels")
        if depth_mm is not None and (depth_mm.shape != (h, w) or depth_mm.dtype != np.uint16):
            raise ValueError("Depth must be uint16 millimetres with matching dimensions")
        logs = []

        def log(*args):
            if len(logs) < 10:
                logs.append(" ".join(str(a) for a in args)[:240])

        namespace = {"np": NumpyCompat(), "cv2": cv2, "time": time, "Log_Arm1_server_print": log}
        exec(self.code, namespace)
        profile = namespace[PROFILE]
        ranges = [(name, value) for name, value in profile.items() if color == "auto" or name == PROFILE + color]
        namespace["color_list"] = [name for name, _ in ranges]
        namespace["hsv_mask_list"] = [[value["hsv_l"], value["hsv_h"]] for _, value in ranges]
        started = time.perf_counter()
        try:
            result = namespace["det_color"](bgr)
            if result is None:
                return self._missing(started, logs)
            low, high = result
            mask = cv2.inRange(cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV), low, high)
            rect = namespace["det_rect"](mask)
            if rect is None:
                return self._missing(started, logs)
        except ValueError as error:
            # The original det_rect does max(contours) without an empty guard.
            if "max() arg is an empty sequence" not in str(error):
                raise
            return self._missing(started, logs, "EMPTY_CONTOURS")
        corners, cx, cy, angle = rect
        detected = next(name.removeprefix(PROFILE) for name, value in ranges
                        if np.array_equal(low, value["hsv_l"]) and np.array_equal(high, value["hsv_h"]))
        depth = None
        if depth_mm is not None:
            x, y = int(round(float(cx))), int(round(float(cy)))
            roi = depth_mm[max(0, y-2):min(h, y+3), max(0, x-2):min(w, x+3)]
            values = roi[roi > 0]
            if values.size:
                depth = {"mm": float(np.median(values)), "valid_samples": int(values.size), "method": "new adapter: median of valid 5x5 depth samples"}
        return {
            "found": True, "color": detected,
            "corners": corners.astype(int).tolist(),
            "center": [float(cx), float(cy)],
            "pixel_error": [float(cx)-w/2, float(cy)-h/2],
            "angle_deg": float(angle),
            "angle_convention": "OpenCV minAreaRect raw angle; not robot joint yaw",
            "hsv_low": low.tolist(), "hsv_high": high.tolist(),
            "depth": depth, "elapsed_ms": round((time.perf_counter()-started)*1000, 1),
            "logs": logs,
        }

    @staticmethod
    def _missing(started, logs, reason="NO_MATCH"):
        return {"found": False, "reason": reason, "depth": None,
                "elapsed_ms": round((time.perf_counter()-started)*1000, 1), "logs": logs}
