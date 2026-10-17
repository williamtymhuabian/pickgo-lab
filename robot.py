"""仿真通信层：函数＋上下文字典，不初始化任何真实设备。"""
import json
import queue
import shutil
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def all_init(backend="sim"):
    if backend != "sim":
        raise ValueError("Only the sim backend is implemented")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("共享仿真需要 Node.js；也可以直接打开 index.html 使用离线模式")
    process = subprocess.Popen(
        [node, str(ROOT / "simulator-worker.cjs")], cwd=ROOT,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
        text=True, encoding="utf-8", bufsize=1,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    robot = {"backend": backend, "process": process, "lock": threading.Lock(),
             "output": queue.Queue(), "sequence": 0, "closed": False}

    def read_output():
        try:
            for line in process.stdout:
                robot["output"].put(json.loads(line))
        except (ValueError, OSError) as error:
            robot["output"].put({"error": str(error)})
        finally:
            robot["output"].put(None)

    threading.Thread(target=read_output, daemon=True).start()
    try:
        run_command(robot, "state")
    except Exception:
        close(robot)
        raise
    return robot


def run_command(robot, command, params=None, source="python"):
    # HTTP 并发请求在这里串行下发；不重试动作，避免超时后重复抓取。
    with robot["lock"]:
        if robot["closed"] or robot["process"].poll() is not None:
            raise RuntimeError("Simulation process is closed; restart the service")
        robot["sequence"] += 1
        request = {"id": robot["sequence"], "command": command,
                   "params": params or {}, "source": source}
        try:
            robot["process"].stdin.write(json.dumps(request, ensure_ascii=False, allow_nan=False) + "\n")
            robot["process"].stdin.flush()
            reply = robot["output"].get(timeout=5)
            if reply is None or reply.get("id") != request["id"]:
                raise OSError("Simulation worker disconnected")
        except (OSError, queue.Empty) as error:
            close(robot)
            raise RuntimeError("Simulation communication failed; command was not retried") from error
        if "error" in reply:
            raise ValueError(reply["error"])
        return reply["result"]


def close(robot):
    robot["closed"] = True
    process = robot["process"]
    if process.stdin and not process.stdin.closed:
        try:
            process.stdin.close()
        except OSError:
            pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=2)
    if process.stdout:
        process.stdout.close()
