"""轻量物体检测与框选前景分割；模型按需加载，不连接摄像头或机器人。"""
import base64
import hashlib
import threading
import time
from pathlib import Path

import cv2
import numpy as np

MODEL = {
    "name": "NanoDet-m-plus-1.5x-416",
    "filename": "object_detection_nanodet_2022nov.onnx",
    "revision": "510899a2a0adb8c25957915fd030d66dbd553919",
    "sha256": "4b82da9944b88577175ee23a459dce2e26e6e4be573def65b1055dc2d9720186",
    "bytes": 3800954,
    "license": "Apache-2.0",
    "source": "https://github.com/opencv/opencv_zoo/tree/main/models/object_detection_nanodet",
}
MODEL_PATH = Path(__file__).resolve().parent / "models" / MODEL["filename"]
CLASSES = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich",
    "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book",
    "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
)


def all_init(model_path=MODEL_PATH):
    return {"path": Path(model_path), "net": None, "lock": threading.Lock()}


def model_status(context):
    path = context["path"]
    return {**MODEL, "available": path.is_file(), "loaded": context["net"] is not None,
            "classes": list(CLASSES), "manual_segmentation_ready": True,
            "setup": "python -B setup_objects.py", "segmentation": "box-prompted GrabCut, not learned instance masks"}


def load_model(context):
    # 调用方持有 lock。ONNX 为数据权重；不自动联网或下载可执行程序。
    if context["net"] is None:
        path = context["path"]
        if not path.is_file():
            raise RuntimeError("物体模型尚未准备，请在项目目录运行 python -B setup_objects.py；手动框选分割仍可使用")
        if path.stat().st_size != MODEL["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != MODEL["sha256"]:
            raise RuntimeError("物体模型完整性校验失败，请移走损坏文件后重新运行 setup_objects.py")
        try:
            net = cv2.dnn.readNetFromONNX(str(path))
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        except cv2.error as error:
            raise RuntimeError("OpenCV 无法加载物体模型：" + str(error)) from error
        context["net"] = net
    return context["net"]


def prepare_image(image):
    h, w = image.shape[:2]
    scale = 416 / max(h, w)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    left, top = (416 - nw) // 2, (416 - nh) // 2
    canvas = np.zeros((416, 416, 3), np.uint8)
    canvas[top:top+nh, left:left+nw] = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_AREA)
    # OpenCV Zoo NanoDet demo uses RGB input with these trained normalization values.
    rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32)
    normalized = (rgb - np.array([103.53, 116.28, 123.675], np.float32)) / np.array([57.375, 57.12, 58.395], np.float32)
    return cv2.dnn.blobFromImage(normalized), (left, top, nw / w, nh / h)


def decode_predictions(outputs, image_shape, transform, confidence, class_filter, max_objects):
    # 按每层点数和通道数配对，而不是依赖 ONNX 输出名称顺序。
    layers = {}
    for output in outputs:
        value = np.asarray(output)
        if value.ndim == 3 and value.shape[0] == 1:
            value = value[0]
        if value.ndim != 2 or value.shape[1] not in (80, 32) or not np.isfinite(value).all():
            raise RuntimeError("Unsupported NanoDet output shape or non-finite values")
        layers[(value.shape[0], value.shape[1])] = value
    boxes, scores, labels = [], [], []
    for stride in (8, 16, 32):
        side = 416 // stride
        cls = layers.get((side * side, 80))
        reg = layers.get((side * side, 32))
        if cls is None or reg is None:
            raise RuntimeError("Missing NanoDet output level")
        if class_filter:
            allowed = np.array([CLASSES.index(name) for name in class_filter])
            class_ids = allowed[np.argmax(cls[:, allowed], axis=1)]
        else:
            class_ids = np.argmax(cls, axis=1)
        probability = cls[np.arange(len(cls)), class_ids]
        indices = np.flatnonzero(probability >= confidence)
        indices = indices[np.argsort(probability[indices])[::-1][:1000]]
        if not len(indices):
            continue
        logits = reg[indices].reshape(-1, 4, 8)
        weights = np.exp(logits - logits.max(axis=2, keepdims=True))
        distances = ((weights / weights.sum(axis=2, keepdims=True)) * np.arange(8)).sum(axis=2) * stride
        x = (indices % side) * stride + (stride - 1) / 2
        y = (indices // side) * stride + (stride - 1) / 2
        xyxy = np.column_stack((x-distances[:, 0], y-distances[:, 1], x+distances[:, 2], y+distances[:, 3]))
        boxes.extend(np.clip(xyxy, 0, 416))
        scores.extend(probability[indices])
        labels.extend(class_ids[indices])
    if not boxes:
        return []
    boxes, scores, labels = np.asarray(boxes), np.asarray(scores), np.asarray(labels)
    wh = boxes.copy()
    wh[:, 2:] -= wh[:, :2]
    keep = []
    for label in np.unique(labels):
        members = np.flatnonzero(labels == label)
        chosen = cv2.dnn.NMSBoxes(wh[members].tolist(), scores[members].tolist(), confidence, 0.6)
        keep.extend(members[np.asarray(chosen, dtype=int).reshape(-1)].tolist())
    h, w = image_shape[:2]
    left, top, sx, sy = transform
    results = []
    for index in sorted(keep, key=lambda i: float(scores[i]), reverse=True):
        box = (boxes[index] - [left, top, left, top]) / [sx, sy, sx, sy]
        box = np.clip(box, [0, 0, 0, 0], [w, h, w, h])
        x1, y1, x2, y2 = [float(v) for v in box]
        if x2-x1 < 2 or y2-y1 < 2:
            continue
        cx, cy = (x1+x2)/2, (y1+y2)/2
        results.append({"id": len(results), "class_id": int(labels[index]), "label": CLASSES[labels[index]],
                        "score": round(float(scores[index]), 4), "box": [round(v, 2) for v in box],
                        "center": [round(cx, 2), round(cy, 2)],
                        "pixel_error": [round(cx-w/2, 2), round(cy-h/2, 2)], "mask": None})
        if len(results) >= max_objects:
            break
    return results


def segment_box(image, box):
    h, w = image.shape[:2]
    # 保留图像边界作为背景种子；坐标均为当前送检图像上的像素。
    x1, y1 = max(1, int(np.floor(box[0]))), max(1, int(np.floor(box[1])))
    x2, y2 = min(w-1, int(np.ceil(box[2]))), min(h-1, int(np.ceil(box[3])))
    if x2-x1 < 3 or y2-y1 < 3:
        raise ValueError("框选区域过小，请完整框住目标并留少量背景")
    mask = np.zeros((h, w), np.uint8)
    try:
        cv2.grabCut(image, mask, (x1, y1, x2-x1, y2-y1), np.zeros((1, 65), np.float64),
                    np.zeros((1, 65), np.float64), 3, cv2.GC_INIT_WITH_RECT)
    except cv2.error as error:
        raise RuntimeError("GrabCut 无法分离前景，请调整框选与背景：" + str(error)) from error
    binary = np.isin(mask, [cv2.GC_FGD, cv2.GC_PR_FGD]).astype(np.uint8) * 255
    area = int(np.count_nonzero(binary))
    if not area:
        return {"method": "grabcut", "found": False, "reason": "EMPTY_FOREGROUND", "area_px": 0}
    moments = cv2.moments(binary, binaryImage=True)
    center = [round(moments["m10"]/moments["m00"], 2), round(moments["m01"]/moments["m00"], 2)]
    ok, png = cv2.imencode(".png", binary)
    if not ok:
        raise RuntimeError("Cannot encode segmentation mask")
    return {"method": "grabcut", "found": True, "area_px": area, "center": center,
            "encoding": "png-mask-u8", "width": w, "height": h,
            "image": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
            "note": "Box-prompted foreground extraction; can include background or multiple objects"}


def run_vision(context, image, task="objects", confidence_pct=40, classes=None, roi=None, max_objects=5):
    if task not in ("objects", "segment", "manual"):
        raise ValueError("Unsupported object vision task")
    if type(confidence_pct) is not int or not 10 <= confidence_pct <= 95:
        raise ValueError("confidence_pct must be an integer from 10 to 95")
    if type(max_objects) is not int or not 1 <= max_objects <= 5:
        raise ValueError("max_objects must be an integer from 1 to 5")
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("Expected uint8 BGR image")
    h, w = image.shape[:2]
    if not (8 <= w <= 640 and 8 <= h <= 480):
        raise ValueError("Unsupported image dimensions")
    if classes is not None and (not isinstance(classes, list) or len(classes) > 80
                                or any(not isinstance(name, str) or name not in CLASSES for name in classes)):
        raise ValueError("classes must contain COCO class names")
    if task == "manual":
        if (not isinstance(roi, list) or len(roi) != 4 or any(type(v) is not int for v in roi)
                or not (0 <= roi[0] < roi[2] <= w and 0 <= roi[1] < roi[3] <= h)):
            raise ValueError("roi must be integer [x1,y1,x2,y2] inside the submitted image")
    started = time.perf_counter()
    with context["lock"]:
        if task == "manual":
            x1, y1, x2, y2 = roi
            results = [{"id": 0, "label": "selected foreground", "class_id": None, "score": None,
                        "box": roi, "center": [(x1+x2)/2, (y1+y2)/2],
                        "pixel_error": [(x1+x2)/2-w/2, (y1+y2)/2-h/2], "mask": segment_box(image, roi)}]
        else:
            net = load_model(context)
            blob, transform = prepare_image(image)
            try:
                net.setInput(blob)
                outputs = net.forward(net.getUnconnectedOutLayersNames())
            except cv2.error as error:
                raise RuntimeError("物体推理失败：" + str(error)) from error
            results = decode_predictions(outputs, image.shape, transform, confidence_pct / 100, classes, max_objects)
            if task == "segment":
                for item in results:
                    try:
                        item["mask"] = segment_box(image, item["box"])
                    except (ValueError, RuntimeError):
                        item["mask"] = {"found": False, "method": "grabcut", "reason": "SEGMENTATION_FAILED", "area_px": 0}
    found = any(item["mask"]["found"] for item in results) if task == "manual" else bool(results)
    return {"task": task, "backend": "opencv-grabcut" if task == "manual" else "opencv-dnn-nanodet",
            "found": found, "objects": results, "count": len(results), "depth": None,
            "elapsed_ms": round((time.perf_counter()-started)*1000, 1),
            "segmentation_method": "grabcut" if task in ("segment", "manual") else None,
            "coordinate_system": "submitted-image-pixels", "model": None if task == "manual" else MODEL["name"]}
