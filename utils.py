"""业务动作入口。原项目的函数式写法：查配置、检查参数、下发动作、返回状态。"""
import importlib.util
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import robot as robot_driver
from Constants import APP, GRAB, ROBOT


def all_init(server_url=None, source="python", detector=None):
    if server_url:
        url = urlsplit(server_url)
        if (url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost")
                or not url.port or url.username or url.password or url.path not in ("", "/")
                or url.query or url.fragment):
            raise ValueError("server-url must be http://127.0.0.1:PORT without a path")
    return {"robot": None if server_url else robot_driver.all_init(APP["backend"]),
            "server_url": server_url.rstrip("/") if server_url else None,
            "source": source, "detector": detector}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_local(context, path, payload=None):
    data = None if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
    request = urllib.request.Request(context["server_url"] + path, data=data,
                                     headers={"Content-Type": "application/json"})
    try:
        # 回环请求不走系统代理，也不跟随跳转。
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=35 if path in ("/api/vision/objects", "/api/vision/assess") else 8) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            message = json.load(error).get("error", str(error))
        except ValueError:
            message = str(error)
        raise ValueError(message) from error
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        raise RuntimeError("未连接到 PickGo Lab，请先运行 app.py 并检查端口；动作不会自动重试") from error


def run_command(context, command, params=None):
    if context["server_url"]:
        if command == "state":
            return request_local(context, "/api/robot/state")
        return request_local(context, "/api/robot/command", {
            "command": command, "params": params or {}, "source": context["source"],
        })
    return robot_driver.run_command(context["robot"], command, params, context["source"])


def get_robot_state(context):
    return run_command(context, "state")


def grab_and_send(context, target, speed=3):
    # 1. 查目标表；2. 启动“取物→托盘→运输→投放”；3. 返回 task_id，不阻塞等完成。
    if target not in GRAB:
        raise ValueError("目标不在 GRAB 配置表中")
    if type(speed) is not int or speed not in (1, 3, 6):
        raise ValueError("速度必须为 1、3 或 6")
    return run_command(context, "start", {"target": target, "speed": speed})


def pause_task(context):
    return run_command(context, "pause")


def resume_task(context):
    return run_command(context, "resume")


def stop_task(context):
    return run_command(context, "stop")


def reset_scene(context):
    return run_command(context, "reset")


def get_capabilities(context):
    return {"name": APP["name"], "version": APP["version"], "backend": "sim",
            "robot": ROBOT["sim"], "targets": GRAB, "state_shared_with_web": bool(context["server_url"]),
            "vision": "original color detector; optional NanoDet COCO objects; box-prompted GrabCut segmentation; local Chinese TTS; optional RealSense aligned RGB-D in web UI",
            "vision_dependencies_installed": all(importlib.util.find_spec(x) is not None for x in ("cv2", "numpy")),
            "limitations": ["kinematic simulation", "RealSense RGB-D requires optional SDK and explicit web session; no MCP camera stream", "no vision feedback in motion tasks",
                            "no hardware backend", "no MCP task extension; poll get_robot_state with task_id"]}


def det_color(context, frame, target="red"):
    payload = {**frame, "target": target}
    if context["server_url"]:
        return request_local(context, "/api/vision/detect", payload)
    # 需要视觉时才加载，纯运动/MCP 不依赖 OpenCV。
    from app import detect_frame
    if context["detector"] is None:
        from legacy_vision import LegacyColorDetector
        context["detector"] = LegacyColorDetector()
    return detect_frame(context["detector"], payload)


def close(context):
    if context["robot"]:
        robot_driver.close(context["robot"])


def detect_objects(context, frame, task="objects", confidence_pct=40, target_class="all", roi=None):
    payload = {**frame, "task": task, "confidence_pct": confidence_pct,
               "classes": [] if target_class == "all" else [target_class], "roi": roi}
    if context["server_url"]:
        return request_local(context, "/api/vision/objects", payload)
    from app import detect_objects_frame
    if context.get("objects") is None:
        from object_vision import all_init as objects_init
        context["objects"] = objects_init()
    return detect_objects_frame(context["objects"], payload)


def schema(properties=None, required=None):
    return {"type": "object", "properties": properties or {}, "required": required or [], "additionalProperties": False}


def assess_observation(context, frame, roi, tolerance_px=6, max_samples=5, policy="adaptive"):
    payload = {**frame, "roi": roi, "tolerance_px": tolerance_px, "max_samples": max_samples, "policy": policy}
    if context["server_url"]:
        return request_local(context, "/api/vision/assess", payload)
    from app import assess_observation_frame
    return assess_observation_frame(payload)


# 与原项目 switch_case 字典一样，将外部名称映射到明确的动作函数。
TOOL = {
    "get_capabilities": (get_capabilities, "查询 PickGo Lab 的能力、目标配置和当前限制。", schema(), True),
    "get_robot_state": (get_robot_state, "查询仿真状态、task_id、底盘/机械臂/物体。轮询直到 SUCCEEDED/FAILED/CANCELED。", schema(), True),
    "grab_and_send": (grab_and_send, "在仿真中启动取物台 A 到投放台 B 的搬运，立即返回 task_id 和状态。", schema({
        "target": {"type": "string", "enum": list(GRAB)},
        "speed": {"type": "integer", "enum": [1, 3, 6]},
    }, ["target"]), False),
    "pause_task": (pause_task, "暂停当前仿真任务，保留抓取和场景状态。", schema(), False),
    "resume_task": (resume_task, "继续已暂停的仿真任务。", schema(), False),
    "stop_task": (stop_task, "停止仿真任务，保留持物状态；这不是实体设备急停。", schema(), False),
    "reset_scene": (reset_scene, "重置仿真场景，清除当前任务和物体位置。", schema(), False),
    "det_color": (det_color, "对传入 RGB PNG 和可选毫米深度执行用户原始颜色检测算法，不读取真实相机。", schema({
        "target": {"type": "string", "enum": ["red", "blue", "yellow", "auto"]},
        "frame": schema({
            "encoding": {"type": "string", "enum": ["png-rgb"]},
            "image": {"type": "string"}, "width": {"type": "integer", "minimum": 8, "maximum": 640},
            "height": {"type": "integer", "minimum": 8, "maximum": 480},
            "frame_id": {"type": "string"}, "depth_unit": {"type": "string", "enum": ["mm"]},
            "depth_le_u16": {"type": "string"},
        }, ["encoding", "image", "width", "height"]),
    }, ["frame"]), True),
}

# 复用 PNG 帧约定；只读视觉工具不会自动启动搬运任务或打开摄像头。
TOOL["detect_objects"] = (detect_objects, "识别传入 PNG 中的 COCO 物体，或用框选 GrabCut 提取前景。结果为像素坐标，不执行机器人动作。", schema({
    "frame": TOOL["det_color"][2]["properties"]["frame"],
    "task": {"type": "string", "enum": ["objects", "segment", "manual"]},
    "confidence_pct": {"type": "integer", "minimum": 10, "maximum": 95},
    "target_class": {"type": "string"},
    "roi": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
}, ["frame"]), True)

TOOL["assess_observation"] = (assess_observation, "对同一 PNG 帧的框选区域做 3–5 次 GrabCut 敏感性评估；无权重、只读，不代表正确率、实时新鲜度或抓取许可。", schema({
    "frame": TOOL["det_color"][2]["properties"]["frame"],
    "roi": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
    "tolerance_px": {"type": "integer", "minimum": 1, "maximum": 30},
    "max_samples": {"type": "integer", "enum": [3, 5]},
    "policy": {"type": "string", "enum": ["adaptive", "fixed"]},
}, ["frame", "roi"]), True)


def validate(value, rule):
    kind = rule["type"]
    correct = {"object": isinstance(value, dict), "string": isinstance(value, str), "array": isinstance(value, list),
               "integer": type(value) is int}[kind]
    if not correct:
        raise ValueError("Expected " + kind)
    if "enum" in rule and value not in rule["enum"]:
        raise ValueError("Value is not in the allowed list")
    if kind == "integer" and not rule.get("minimum", value) <= value <= rule.get("maximum", value):
        raise ValueError("Integer exceeds allowed range")
    if kind == "array":
        if not rule.get("minItems", 0) <= len(value) <= rule.get("maxItems", len(value)):
            raise ValueError("Array length exceeds allowed range")
        for item in value:
            validate(item, rule["items"])
    if kind == "object":
        if set(value) - set(rule["properties"]):
            raise ValueError("Unknown argument")
        if set(rule["required"]) - set(value):
            raise ValueError("Required argument is missing")
        for key, item in value.items():
            validate(item, rule["properties"][key])


def list_tools():
    return [{"name": name, "description": info[1], "inputSchema": info[2],
             "annotations": {"readOnlyHint": info[3], "openWorldHint": False,
                             "destructiveHint": name == "reset_scene"}}
            for name, info in TOOL.items()]


def call_tool(context, name, arguments):
    if name not in TOOL:
        raise ValueError("Unknown tool: " + str(name))
    function, _, rule, _ = TOOL[name]
    validate(arguments, rule)
    return function(context, **arguments)
