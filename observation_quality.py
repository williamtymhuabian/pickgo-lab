"""同一送检帧的分割敏感性评估。纯像素建议，不控制机器人、不需要权重。"""
import base64
import itertools
import threading
import time

import cv2
import numpy as np

from object_vision import segment_box

CONFIG = {"version": "1", "min_samples": 3, "min_pair_iou": .85,
          "max_area_spread": .25, "time_budget_s": 4.0}
_LOCK = threading.Lock()


def capabilities():
    return {"ready": True, "version": CONFIG["version"], "weights_required": False,
            "policies": ["adaptive", "fixed"], "max_samples": 5,
            "scope": "same-frame ROI sensitivity; not probability, temporal tracking or robot execution approval"}


def encode_mask(binary):
    ok, png = cv2.imencode(".png", binary.astype(np.uint8) * 255)
    if not ok:
        raise RuntimeError("Cannot encode assessment mask")
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def decode_mask(result, shape):
    if not result.get("found"):
        return np.zeros(shape, bool)
    image = cv2.imdecode(np.frombuffer(base64.b64decode(result["image"].split(",", 1)[1]), np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None or image.shape != shape:
        raise RuntimeError("Segmentation returned incompatible mask")
    return image > 0


def candidate_boxes(roi, width, height):
    x1, y1, x2, y2 = roi
    d = max(2, round(min(x2-x1, y2-y1) * .03))
    candidates = [("original", roi), ("expand", [x1-d,y1-d,x2+d,y2+d]),
                  ("contract", [x1+d,y1+d,x2-d,y2-d]),
                  ("left", [x1-d,y1,x2-d,y2]), ("right", [x1+d,y1,x2+d,y2])]
    result = []
    seen = set()
    for name, box in candidates:
        clipped = [max(1, box[0]), max(1, box[1]), min(width-1, box[2]), min(height-1, box[3])]
        if clipped[2]-clipped[0] >= 3 and clipped[3]-clipped[1] >= 3 and tuple(clipped) not in seen:
            seen.add(tuple(clipped))
            result.append((name, clipped))
    return result


def summarize_masks(masks, tolerance_px):
    if not masks:
        raise ValueError("No masks supplied")
    areas = [int(np.count_nonzero(mask)) for mask in masks]
    valid = [mask for mask, area in zip(masks, areas) if area]
    union = np.logical_or.reduce(masks)
    core = np.logical_and.reduce(masks)
    centers = []
    for mask in valid:
        y, x = np.nonzero(mask)
        centers.append([float(x.mean()), float(y.mean())])
    pairs = []
    for a, b in itertools.combinations(masks, 2):
        total = int(np.count_nonzero(a | b))
        pairs.append(float(np.count_nonzero(a & b) / total) if total else 0.)
    spread = max((float(np.linalg.norm(np.array(a)-b)) for a, b in itertools.combinations(centers, 2)), default=0.)
    median = float(np.median(areas))
    area_spread = (max(areas)-min(areas))/median if median else 0.
    clearance = cv2.distanceTransform(core.astype(np.uint8), cv2.DIST_L2, 5)
    # 共同前景内部的像素采样点，不声明为物理抓取点。
    _, radius, _, location = cv2.minMaxLoc(clearance)
    point = [int(location[0]), int(location[1])] if np.any(core) else None
    enough = len(masks) >= CONFIG["min_samples"]
    consistent = (enough and len(valid) == len(masks) and min(pairs, default=0.) >= CONFIG["min_pair_iou"]
                  and area_spread <= CONFIG["max_area_spread"] and spread <= tolerance_px
                  and point is not None and radius >= tolerance_px)
    return {"sample_count": len(masks), "valid_samples": len(valid), "areas_px": areas,
            "min_pair_iou": round(min(pairs), 4) if pairs else None,
            "max_center_spread_px": round(spread, 2), "area_spread_ratio": round(area_spread, 4),
            "core_area_px": int(np.count_nonzero(core)), "union_area_px": int(np.count_nonzero(union)),
            "candidate_surface_pixel": point, "core_clearance_px": round(radius, 2),
            "consistent": bool(consistent)}, core, union & ~core


def assess_observation(image, roi, tolerance_px=6, max_samples=5, policy="adaptive"):
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("Expected uint8 BGR image")
    h, w = image.shape[:2]
    if not (8 <= w <= 640 and 8 <= h <= 480):
        raise ValueError("Unsupported assessment image dimensions")
    if (not isinstance(roi, list) or len(roi) != 4 or any(type(v) is not int for v in roi)
            or not (0 <= roi[0] < roi[2] <= w and 0 <= roi[1] < roi[3] <= h)
            or min(roi[2]-roi[0], roi[3]-roi[1]) < 8):
        raise ValueError("roi must be integer [x1,y1,x2,y2] inside image and at least 8 pixels wide/high")
    if type(tolerance_px) is not int or not 1 <= tolerance_px <= 30:
        raise ValueError("tolerance_px must be an integer from 1 to 30")
    if type(max_samples) is not int or max_samples not in (3, 5):
        raise ValueError("max_samples must be 3 or 5")
    if policy not in ("adaptive", "fixed"):
        raise ValueError("Unsupported assessment policy")
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError("观测评估正在运行，请稍后重试")
    try:
        started = time.perf_counter()
        masks, samples = [], []
        stop = "max_samples"
        boxes = candidate_boxes(roi, w, h)[:max_samples]
        for name, box in boxes:
            try:
                found = segment_box(image, box)
                mask = decode_mask(found, (h, w))
                reason = found.get("reason")
            except (ValueError, RuntimeError):
                mask, reason = np.zeros((h, w), bool), "SEGMENTATION_FAILED"
            masks.append(mask)
            samples.append({"variant": name, "roi": box, "found": bool(np.any(mask)), "reason": reason})
            stats, core, disagreement = summarize_masks(masks, tolerance_px)
            if policy == "adaptive" and stats["consistent"]:
                stop = "sufficient_pixel_consistency"
                break
            if time.perf_counter()-started > CONFIG["time_budget_s"]:
                stop = "time_budget"
                break
        if not masks:
            raise ValueError("ROI cannot produce an assessment candidate")
        if stats["valid_samples"] == 0:
            status, advice = "NO_FOREGROUND", "没有提取到前景，请扩大框选、改善背景或重新拍摄。"
        elif stats["sample_count"] < CONFIG["min_samples"]:
            status, advice = "INCOMPLETE", "候选数量不足，无法评价一致性，请调整区域后重试。"
        elif stats["consistent"]:
            status, advice = "CONSISTENT", "候选分割在当前像素规则下较一致；仍需检查时序新鲜度和任务坐标。"
        else:
            status, advice = "REOBSERVE", "分割或采样点对框选较敏感，建议调整视角、背景或手动框选后复查。"
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        x1, y1, x2, y2 = roi
        crop = gray[y1:y2, x1:x2]
        return {"backend": "opencv-grabcut-roi-sensitivity", "assessment_version": CONFIG["version"],
                "status": status, "advice": advice, "roi": roi, "policy": policy,
                "max_samples": max_samples, "stop_reason": stop, "samples": samples,
                "metrics": stats, "thresholds": {"tolerance_px": tolerance_px,
                    "min_pair_iou": CONFIG["min_pair_iou"], "max_area_spread": CONFIG["max_area_spread"]},
                "image_diagnostics": {"mean_gray": round(float(crop.mean()), 1),
                    "laplacian_variance": round(float(cv2.Laplacian(crop, cv2.CV_64F).var()), 1),
                    "roi_at_image_edge": x1 <= 1 or y1 <= 1 or x2 >= w-1 or y2 >= h-1},
                "masks": {"core": encode_mask(core), "disagreement": encode_mask(disagreement)},
                "elapsed_ms": round((time.perf_counter()-started)*1000, 1),
                "scope": "Pixel sensitivity only; not detection accuracy, independent views, metric pose or grasp permission",
                "requires_robot_calibration": True, "robot_execution_authorized": False}
    finally:
        _LOCK.release()
