# PickGo Lab MCP 接入

## 推荐：与网页共用一个场景

先运行 `python -B app.py`，浏览器打开 <http://127.0.0.1:8767/>。然后在支持经典 MCP stdio 的客户端中添加本项目服务，参考根目录 `mcp.example.json`：

- `command` 使用本机 Python 可执行文件路径；已有合适环境时可使用 `python`。
- `args` 的脚本路径改成项目内 `mcp_server.py` 的绝对路径。脚本不依赖客户端当前工作目录。
- `--server-url` 必须和网页服务端口相同。开发预览如用 8768，则两处都用 8768。
- MCP 客户端启动的是 `mcp_server.py`，不要用带提示与 pause 的 `start.cmd`。

配置属于常见的 `mcpServers` JSON 格式，不同客户端的配置位置和字段可能不同；此仓库提供接入文件，没有修改电脑上任何 MCP 客户端设置。

此模式：客户端 → stdio MCP → `utils.py` → 本机 HTTP → 同一个 `simulator-worker.cjs` → `simulator-core.js`。网页查询并展示相同的 `instance_id`、`task_id`、位姿和事件；右上角显示最近控制来自 `web` 或 `mcp`。关闭网页或 MCP attach 客户端不会关闭服务端场景，也不会取消已接收任务。

## 独立模式

不需要网页时，可把客户端参数设为 `-B /绝对路径/mcp_server.py --standalone`。需要 Node.js，但不需要 app.py、OpenCV、NumPy 或 npm 依赖；只有调用 `det_color` 才需要视觉依赖。

独立模式由 MCP 进程持有一个单独场景，与已打开的网页没有关系。关闭 MCP stdin 后退出，并回收它创建的 Node 进程。默认 attach 模式则仅断开客户端。

## 工具与任务

- `get_capabilities({})`：查看 sim 能力、目标配置和限制。
- `get_robot_state({})`：读取场景状态。`backend` 为 sim；`task_id` 标识一次搬运，`instance_id` 标识场景进程。
- `grab_and_send({"target":"red","speed":3})`：目标可为 red、blue、yellow；速度可为 1、3、6，默认 3。立即返回 RUNNING 和 task_id，不等待整段动作完成。运行中再次启动会返回业务错误。
- `pause_task({})`、`resume_task({})`：暂停和继续，保持原 task_id。
- `stop_task({})`：停止并保留场景与持物状态，返回 CANCELED。
- `reset_scene({})`：恢复初始场景，清空 task_id；未完成的任务状态不再保留。
- `det_color({"target":"blue","frame":{...}})`：运行原视觉函数。frame 必须含 `encoding:"png-rgb"`、PNG data URL `image`、整数 width/height，最大 640×480。可选 `depth_unit:"mm"`、`depth_le_u16`（与图像同尺寸的 uint16 小端毫米深度原始字节 base64）。不要把 JPEG、压缩深度 PNG 或世界坐标放到这个字段。无深度就省略深度字段，不会补造距离。

例如让客户端执行：“查询 PickGo Lab 状态，把蓝色方块搬到 B 台，之后查询这个 task_id 的结果。”客户端调用 grab_and_send 后应间隔约 0.5–1 秒查询 get_robot_state，直至 SUCCEEDED、FAILED 或 CANCELED。task_id 变为空或改变表示任务被重置或替换，不能据此报告旧任务成功。

不支持 MCP tasks 扩展，task_id 是本项目业务字段。MCP 请求取消通知不会停止已经接收的搬运；要停止运动，请显式调用 stop_task。失败时不自动重发动作；通信失败可能发生在动作已接受之后，先查询状态再决定下一步。

## 按原项目习惯扩展

v0.5.0 新增只读 `assess_observation`：参数 `frame` 使用同一 PNG 帧格式，`roi:[x1,y1,x2,y2]` 为该帧内的整数框，`tolerance_px` 为 1–30 整数（默认 6），`max_samples` 为 3 或 5（默认 5），`policy` 为 `adaptive` 或 `fixed`。不需要 NanoDet 权重，需要 OpenCV / NumPy。返回候选分割指标、共同前景掩膜及建议；不打开相机、不发送运动指令，也不替调用者收集连续观测。`robot_execution_authorized` 始终为 false。MCP 调用者需自行提供帧并检查新鲜度，页面的连续帧跟踪状态属于前端。详见 [实操与指标边界](camera-validation-2026-10-24.md)。

v0.4.0 新增只读 `detect_objects` 工具。`task` 可选 `objects`（物体检测）、`segment`（检测＋GrabCut 前景）、`manual`（手动框选前景）；共用现有 PNG 帧格式。`confidence_pct` 为 10–95 整数，`target_class` 为 `all` 或 COCO 英文类别名，手动模式需要 `roi:[x1,y1,x2,y2]`。输入与结果都是当前图像像素，不打开摄像头或执行运动。模型准备、返回掩膜格式与分割边界见 [物体与分割说明](objects.md)。

`Constants.py` 的 APP / ROBOT / GRAB 对应配置字典；`utils.py` 的 all_init / grab_and_send / pause_task 等对应动作函数；TOOL 字典对应原项目按名称分发的写法。`examples/pick_and_send.py` 展示“初始化 → 启动 → 等结果”的明确步骤。

增加业务动作时，先写普通函数及输入检查，再加入 TOOL 的名称、描述和 JSON Schema；网页、脚本和 MCP 可复用相同函数。接实体设备时修改 robot.py 后端，不能把 sim 返回值直接当作硬件回执；当前只有 sim，其他后端会直接拒绝初始化。

## 协议范围

使用 Python 标准库实现轻量 stdio 服务，不额外安装 MCP SDK；支持经典协议版本 2025-11-25、2025-06-18、2025-03-26、2024-11-05 的 initialize、initialized、ping、tools/list、tools/call 子集。未识别的方法返回 -32601；未知工具或非法参数返回 -32602；正常调用遇到忙碌、未连接、缺少视觉依赖等执行错误返回工具结果 isError=true。

每行一条 UTF-8 JSON-RPC，stdout 只输出协议消息，诊断写入 stderr；请求上限 1 MB。不支持 resources、prompts、Streamable HTTP、实时相机流、MCP tasks 扩展或 2026-07-28 的新发现协议。使用现代协议的客户端需支持回退到经典 initialize；仅支持新协议的客户端不能直接接入。HTTP /api/* 是本项目内部接口，不是 MCP HTTP 传输端点。

协议依据：[经典生命周期](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)、[stdio 传输](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)、[工具协议](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)。本机服务只监听 127.0.0.1，并校验 Host 和 Origin；MCP attach 只接受本机 http 地址，不走系统代理、不跟随跳转。当前所有动作只影响仿真。

## 验证

运行 `python -B tests/test_mcp.py`。测试真实 stdio 子进程、协议握手、工具枚举、参数错误、运行/暂停/继续/停止/重置、无视觉依赖运行、原视觉函数调用，以及网页和 MCP 共用状态与跨域请求拒绝。测试使用本机临时端口，不连接外网或实体机器人。
