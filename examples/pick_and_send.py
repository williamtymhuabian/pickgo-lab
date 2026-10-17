"""先在项目根目录运行 app.py，再运行 python -B examples/pick_and_send.py。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import all_init, close, get_robot_state, grab_and_send, stop_task


def main():
    # 1. 初始化，连接已有的共享仿真。
    robot = all_init(server_url="http://127.0.0.1:8767")
    task_id = None
    try:
        # 2. 查 GRAB 配置表中的目标，启动搬运。
        task = grab_and_send(robot, "red", speed=6)
        task_id = task["task_id"]
        print("task_id:", task_id)

        # 3. 等待当前任务结果，任务被重置或替换时不把它误报为完成。
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            state = get_robot_state(robot)
            if state["task_id"] != task_id:
                raise RuntimeError("当前任务已被重置或替换")
            print(state["status"], state["phase"])
            if state["status"] in ("SUCCEEDED", "FAILED", "CANCELED"):
                return
            time.sleep(1)
        raise TimeoutError("等待仿真任务超时")
    except (KeyboardInterrupt, TimeoutError):
        # 只停止自己启动的任务，不影响之后由其他入口启动的任务。
        if task_id and get_robot_state(robot)["task_id"] == task_id:
            stop_task(robot)
        raise
    finally:
        close(robot)


if __name__ == "__main__":
    main()
