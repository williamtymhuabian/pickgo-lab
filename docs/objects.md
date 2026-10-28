# 物体识别与前景分割

v0.4.0 在原颜色识别之外增加常见物体检测、检测框引导前景分割和手动框选前景分割。输入仍为本机摄像头或本地图片，结果不控制机器人。

## 本机使用

在项目目录运行：

```bash
python -m pip install -r requirements.txt
python -B setup_objects.py
python -B app.py --vision-only
```

已经安装原视觉依赖时，不必再次安装。`setup_objects.py` 只下载一次固定版本 NanoDet ONNX 和许可证，不安装 PyTorch、CUDA、ONNX Runtime、驱动或 SDK。权重为 3,800,954 字节，约 3.8 MB；推理由现有 OpenCV DNN 在 CPU 上执行。模型在首次物体检测时校验 SHA256 并加载，运行期间不访问外网。

默认地址：<http://127.0.0.1:8767/vision.html?task=objects>。端口占用时可用 `--port 8770`，并访问对应端口。旧服务不会自动更新，修改代码后需重新启动服务。

页面提供四种方式：

1. **原颜色识别**：保留用户原 `det_color` / `det_rect` 和 HSV 配置，输出原矩形、中心与角度。
2. **常见物体检测**：NanoDet 输出 COCO 80 类中的类别、检测分数、矩形框、中心与像素偏差。最多显示 5 个物体，可筛选类别和最低分数。
3. **物体检测＋前景分割**：先检测，再分别在检测框内运行 GrabCut，显示二值前景的半透明叠加、像素面积和质心。分割失败时仍保留检测框，但明确显示分割未成功。
4. **手动框选前景分割**：不用模型。先点击冻结输入，再在送检图上拖动框住目标，点击分割；适合尝试未收录的零件。它不会推断框内物体的名称，也不为手选区域生成检测分数。

可用摄像头模式地址：`/vision.html?source=camera&task=segment`。选择 RGB 接口后手动点击打开相机。不会因为访问页面就申请相机权限。D435 真实深度使用独立 `source=realsense` 入口，需安装可选 SDK，见 [RGB-D 说明](realsense-depth.md)。

物体模式默认进入本地图片输入，避免把合成色块当作真实类别测试图。使用摄像头时，检测框与掩膜画在实际送检帧上，实时预览独立；连续识别等待上一次完成，手动分割则禁用连续识别并固定使用已冻结帧。

## 分割与坐标的含义

这是 **物体检测 + 框提示的 GrabCut 前景提取**，不是训练好的实例分割网络，也不是 SAM 或开放词汇识别。

- COCO 预设类别包括 bottle、cup、cell phone、keyboard、mouse、book、person 等。中文提示用于操作，结果和类别筛选使用标准英文类别名。螺丝、专用零件、任意品牌或指定款式不一定有对应类别。
- 检测分数是模型输出，不代表该场景下已验证的正确率。遮挡、小目标、模糊和相似背景会影响检测。
- GrabCut 可能提取多个前景、保留背景或漏掉细边缘；检测框不精确时尤其明显。手动框选应完整包含目标并留少量背景。画面边缘保留一像素背景种子，贴边物体可能有边缘损失。
- 掩膜是当前送检图尺寸的黑白 PNG，白色为前景；面积为非零像素数。分割成功时页面中心取掩膜质心，否则取检测框中心。它们都不是抓取点保证。
- 页面送检图为 320×240。HTTP / MCP 可接收最大 640×480，返回坐标、框和掩膜均对应输入图像；网络内部 416×416 的等比缩放与补边由后端还原。
- RGB 物体检测接口不输出机械臂角度、距离、三维坐标或深度。RGB-D 页面会另外查询匹配送检帧的光轴深度 Z；它不是物体位姿或机械臂坐标。RGB 分割不能替代 RGB-D 标定。

选择一个分割成功的结果后，可点击“下载所选前景 PNG（透明背景）”。文件保留送检图尺寸和前景原色，背景 alpha 为零；仅这一主动操作会导出图片，不自动录制或保存相机帧。

更改任务、来源、缩放、类别、阈值或关闭相机后，旧框、导出链接和冻结区域失效。重新冻结、框选后才能提交手动分割，避免把旧区域套到新图像上。

## Python / HTTP / MCP

新增函数入口仍采用函数和字典组织：

```python
result = utils.detect_objects(
    context,
    frame,                    # 与 det_color 一样的 png-rgb PNG 帧字典
    task="segment",           # objects / segment / manual
    confidence_pct=40,         # 整数 10–95
    target_class="cup",        # all 或标准 COCO 类别名
)
```

手动分割传 `task="manual", roi=[x1,y1,x2,y2]`，ROI 必须为同一输入帧内的整数像素坐标。框选是用户提供的分割提示，不是真实世界位置。没有模型时，手动分割照常工作。

HTTP：`POST /api/vision/objects`。在现有帧字段上增加 `task`、`confidence_pct`、`classes`（类别名数组或空数组）、可选 `roi` 与 `max_objects`（1–5）。深度字段不参与该后端，结果 `depth` 始终为空。

结果包含 `task`、`frame_id`、`image_size`、`found`、`objects`、`count`、`elapsed_ms`。每个物体含 `label`、`class_id`、`score`、`box`（xyxy）、`center`、`pixel_error` 与 `mask`。有效 mask 含 `image` PNG data URL、`area_px`、`center` 与 `method="grabcut"`；无前景或分割失败时不补造掩膜。

MCP 新增只读工具 `detect_objects`，参数对应 Python 入口。客户端需自己提供 PNG 帧，不会读取或打开用户摄像头。attach 模式复用本机服务的模型，standalone 模式按需加载独立模型。掩膜随工具 JSON 文本结果返回；目前未实现 MCP 图像内容块、资源链接或相机视频流。

## 模型来源、校验与仓库大小

来源：[OpenCV Zoo NanoDet](https://github.com/opencv/opencv_zoo/tree/main/models/object_detection_nanodet)。预处理、回归分布解码和坐标还原参照该模型公开接口，在本项目中以函数组织，并增加按类别 NMS、输入校验、模型完整性校验和线程锁。

- 固定修订：`510899a2a0adb8c25957915fd030d66dbd553919`。
- 文件：`object_detection_nanodet_2022nov.onnx`。
- SHA256：`4b82da9944b88577175ee23a459dce2e26e6e4be573def65b1055dc2d9720186`，来自官方 Git LFS 指针。
- 模型许可证：Apache-2.0。下载时保存上游完整许可证到 `models/NANODET-LICENSE.txt`，它不改变项目原机器人代码的许可归属。
- 模型权重由 `.gitignore` 排除，读者克隆源码后运行准备脚本即可，不需要把 Python 环境或其他大文件上传 GitHub。如手动打源码压缩包，应同样排除 `downloads/` 和本机权重；许可证和 `models/README.md` 可以保留。

GrabCut 的原理与限制见 [OpenCV 官方说明](https://docs.opencv.org/4.x/d8/d83/tutorial_py_grabcut.html)。

## 验证与未验收部分

v0.5.0 在现有检测/分割之上新增只读观测评估与记录，不新增模型。启动、下载清单、连续帧检查、框敏感性评估与人工复核步骤见 [2026-10-24 摄像头实操](camera-validation-2026-10-24.md)。同帧候选一致性不是分割准确率；新模块不生成世界坐标或控制指令。

```bash
python -B tests/test_objects.py
node tests/vision_helpers.test.cjs
```

新增后端测试覆盖真实 GrabCut 前景/空前景、缺失与损坏模型、非正方形图像坐标还原、类别筛选、按类别 NMS、非法 ROI、HTTP 来源限制和 MCP 调用。前端辅助测试覆盖透明背景的像素与坐标转换。原 35 项颜色、运动、MCP 和相机回归继续保留。

2026-10-19 本机开发验证：官方模型成功加载；空白图没有返回目标；OpenCV 公开 `messi5.jpg` 经页面等比缩放后检测到人物与足球，并生成前景掩膜；页面手动框选足球也返回有效前景。这只是功能连通样例，不是识别率、分割精度或相机帧率评测。

2026-10-24 后续实测：D435 RGB 识别、GrabCut 及观测评估已连通，见 [RGB 实测](camera-smoke-test-2026-10-24.md)；中文播报与真实深度点选也已连通，见 [语音](speech.md) 和 [RGB-D](realsense-depth.md)。金属保温杯出现 cup/bottle 混淆、漏检及深度空洞，未做准确率或测距精度评测。物体检测和分割结果尚未用于仿真自动搬运，也未控制实体机器人。
