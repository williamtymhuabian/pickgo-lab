"""PickGo Lab 配置表。沿用原项目 Constants.py 的字典配置方式。"""

APP = {
    "name": "PickGo Lab",
    "version": "0.2.0",
    "host": "127.0.0.1",
    "port": 8767,
    "backend": "sim",
}

# 目标表。当前场景只接受这三个目标，禁止把任意坐标直接下发给机械臂。
GRAB = {
    "red": {"name": "红色方块", "from": "A", "to": "B"},
    "blue": {"name": "蓝色方块", "from": "A", "to": "B"},
    "yellow": {"name": "黄色方块", "from": "A", "to": "B"},
}

ROBOT = {
    "sim": {"name": "PickGo 仿真机器人", "arm_axes": 4, "base": "differential"},
}

MCP = {
    "protocols": ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"),
    "max_message_bytes": 1_000_000,
}
