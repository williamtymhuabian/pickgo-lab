# PickGo Lab 摄像头实践：从 RGB 识别走向深度感知

这次给 PickGo Lab 增加了 RGB 摄像头输入：浏览器采集彩色画面，本机 Python 调用原颜色与矩形识别函数，再将检测结果绘制到对应的送检帧上。

真正需要理清的，是从“能看到画面”到“知道物体在哪里”之间的步骤。彩色视频、有效深度、相机坐标和机器人坐标，各自需要独立验证。这篇记录已完成的 RGB 接入，也整理下一步深度开发的具体路线。

项目地址：[PickGo Lab](https://github.com/williamtymhuabian/pickgo-lab)。

## 一、先跑通 RGB 采集与识别

准备 Python 3.10 或以上版本，在本机安装依赖并启动视觉模式：

~~~bash
git clone https://github.com/williamtymhuabian/pickgo-lab.git
cd pickgo-lab
python -m pip install -r requirements.txt
python -B app.py --vision-only
~~~

用本机 Edge 或 Chrome 打开 [视觉页面](http://127.0.0.1:8767/vision.html?source=camera)，Windows 也可以双击 `start-camera.cmd`。此模式不需要 Node.js；博客本身只展示文章和图片，识别服务运行在读者自己的电脑上。

先用合成图确认服务可用，再选择摄像头的 RGB 接口。点击“打开摄像头”后才申请视频权限，不采集麦克风。浏览器采集需要安全上下文，本机 localhost 属于可用于开发的环境。[getUserMedia 官方说明](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)

当前开发记录中，D435 的 RGB 接口曾以 640×480 打开，并将画面交给原算法；当次结果为“未识别到目标”。它说明采集与送检已经连通，实物颜色识别仍需针对光照、颜色阈值和目标大小继续验证。真实深度尚未接入。

这次补拍了一张 D435 RGB 真实画面，原始采集分辨率为 640×480。为避免展示背景人员与电脑屏幕，文章只使用 302×266 的橘子近景裁剪图。拍完即释放相机，没有采集音频。

![2026-10-18 D435 RGB 实拍：本地裁剪后的橘子近景；仅展示彩色采集，不代表目标识别或深度测距成功](https://williamtymhuabian.github.io/personal-site/assets/projects/pickgo-d435-rgb-real.png)

## 二、预览在动，检测框要跟着送检帧

摄像头预览与实际送检图像分开展示。一次识别经过以下步骤：

~~~text
RGB 视频 → 选择区域 → 等比缩放至 320×240 → PNG 送检
         → 本机 OpenCV → 原 det_color / det_rect
         → 核对 frame_id → 在对应送检帧上绘制结果
~~~

连续识别在上一次返回后才采集下一帧，同一页面最多一个识别请求。切换来源、颜色或裁剪区域后，旧结果失效；未识别到目标时清空旧中心与角度。

![RGB 页面联调截图：输入为浏览器合成测试视频流，未打开真实相机；用于检查预览、送检帧和原算法输出](https://williamtymhuabian.github.io/personal-site/assets/projects/pickgo-camera-test-stream.png)

这张图专门验证软件链路，不作为 D435 实拍效果。原函数含 0.4 秒等待，识别频率与预览帧率也应分开看。

切换来源、关闭设备或离开页面会释放视频轨道。取消连续识别只暂停送检，仍保留预览。[MediaStreamTrack.stop 说明](https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/stop)

## 三、相机选型：先用已有 D435 完成闭环前的验证

我的第一选择是继续使用已有的 **RealSense D435**。当前最需要补齐的是深度采集、配准和坐标链路，可以先用现有设备验证这些问题，再根据实测距离决定是否换机。

![本机 RealSense D435 摄像头与三脚架的实拍照片](https://williamtymhuabian.github.io/personal-site/assets/projects/pickgo-d435-device.jpg)

上图是本次使用的摄像头与三脚架实拍，展示设备的实际安装状态。

按当前项目可能发展的场景，我会考虑三款具体型号。以下是选型建议，工作距离取自官方页面，实际表现还取决于材质、光照、分辨率和安装方式，规格核对日期为 2026-10-18。

- **D435：现有设备优先。** 官方理想范围为 0.3—3 m，适合先做桌面物体观察、目标测距和 RGB-D 接口开发。其 RGB 是滚动快门，深度成像器是全局快门，运动场景需要留意彩色与深度的时序差异。[D435 官方规格](https://store.realsenseai.com/buy-realsense-depth-camera-d435.html)
- **D405：明确需要近距离抓取时考虑。** 官方标准理想范围为 7—50 cm，适合腕部或近距离工位观察。它的彩色信息来自左侧成像器经 ISP 输出，选购前要确认颜色效果、安装距离和遮挡是否满足任务。[D405 官方说明](https://www.realsenseai.com/products/d405-series/)
- **D455：移动底盘与较远场景时考虑。** 官方理想范围为 0.6—6 m，具备全局快门 RGB 与深度成像、集成 IMU；更适合需要较远环境观察的方向。它能否满足某个抓取距离仍要单独测试。[D455 官方说明](https://www.realsenseai.com/product-family/450-series/)

建议先记录相机到目标的实际距离，再比较有效深度比例和测距误差。购买判断应由这些结果驱动；目前没有必要为了让项目看起来完整就一次购入多款设备。

## 四、深度相机开发：先做独立采集，再接回页面

浏览器获得的 RGB 视频不包含可直接读取的毫米深度。RealSense 深度开发应从官方 SDK 与 Python 包 `pyrealsense2` 入手，先在 RealSense Viewer 中检查设备、RGB、深度和 USB 连接，再开发独立采集程序。[官方 SDK 与安装入口](https://github.com/realsenseai/librealsense)

建议由 Python 统一持有 D435 的 RGB 与深度流，网页读取本机服务提供的帧和检测结果。这样可以避免浏览器和 SDK 同时争用同一设备，也方便保存同一组图像、内参和时间戳。

第一步只做“像素对应的三维表面点”。下面是独立实验的最小示意，尚未接入项目，也未在本轮硬件上运行。示例配置需与设备支持的流模式匹配。

~~~python
import pyrealsense2 as rs

pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
align = rs.align(rs.stream.color)

started = False
try:
    pipeline.start(config)
    started = True
    for _ in range(30):
        frames = pipeline.wait_for_frames(5000)
    aligned = align.process(frames)
    depth = aligned.get_depth_frame()
    color = aligned.get_color_frame()
    if not depth or not color:
        raise RuntimeError("没有取得对齐后的 RGB-D 帧")
    # 这里只测图像中心，不代表已经检测到了目标。
    u, v = color.get_width() // 2, color.get_height() // 2
    z_m = depth.get_distance(u, v)
    if z_m <= 0:
        raise RuntimeError("该像素无有效深度，请换位置或检查场景")
    intrinsics = depth.profile.as_video_stream_profile().intrinsics
    point_m = rs.rs2_deproject_pixel_to_point(intrinsics, [u, v], z_m)
    print("相机坐标中的表面点 / m:", point_m)
finally:
    if started:
        pipeline.stop()
~~~

这里用 `rs.align(rs.stream.color)` 把深度对齐到彩色图像，再读取匹配的内参。官方提供了 [深度对齐 Python 示例](https://github.com/realsenseai/librealsense/blob/master/wrappers/python/examples/align-depth2color.py) 和 [align 接口说明](https://realsenseai.github.io/librealsense/python_docs/_generated/pyrealsense2.align.html)。

`get_distance` 返回米制深度；读取原始 Z16 数据时则必须使用实际 `depth_scale` 转换，不能一律假定原始值就是毫米。深度伪彩图只用于显示，测距需要原始深度值。[depth_frame 接口说明](https://realsenseai.github.io/librealsense/python_docs/_generated/pyrealsense2.depth_frame.html)

对齐解决空间像素对应关系，仍需记录并检查 RGB、深度时间戳。相机坐标的轴向为右、下、前，三维点单位为米。它到机器人基座的转换还需要外参；固定相机与腕部相机的标定流程也不同。[官方投影与坐标说明](https://dev.realsenseai.com/docs/projection-in-realsense-sdk-2-0/)

## 五、接下来具体写哪些代码

我会按下面的依赖顺序推进。这些文件名是拟新增模块，当前尚未实现；每一步先验收，再进入下一步。

1. **`sensors/realsense_source.py`：统一采集接口。** 打开指定设备，输出 RGB、原始深度、内参、深度比例、帧号与各流时间戳；断连和超时明确报错，退出时释放设备。验收标准是能保存一组可读取、元数据完整的 RGB-D 样本。
2. **`vision/pixel_mapping.py`：还原送检坐标。** 记录当前 320×240 送检过程中的裁剪区域、缩放和留边，把检测坐标逆变换回原始彩色像素。黑边内的点应拒绝；不能直接拿送检中心去索引原始深度。
3. **`vision/depth_target.py`：目标区域测距。** 在对齐后的目标内部筛选有效深度，避开边界混入的背景和深度空洞，输出有效比例、离散程度与失败原因。选定有效表面像素后用它自身的深度反投影，保留采样位置；暂不把一个表面点宣称为完整物体位姿。
4. **`calibration/camera_to_base.py`：坐标转换。** 明确相机安装方式，保存有版本的外参与单位，在已知测量点上检查转换误差。标定缺失、过期或误差不满足任务要求时，只显示观测，不输出可执行抓取目标。
5. **`experiments/rgbd_replay.py`：先回放，再接控制。** 保存 RGB、Z16、元数据和算法输出，使没有相机时也能复现同一组检测。先向仿真提供带时间戳的估计位置，确认过期帧、无效深度和不可达点会被拒绝，再考虑实体机械臂。

原 `legacy/utils.py` 与颜色阈值继续保留，新的采集与坐标处理放在适配层。现在的 `det_rect` 角度只是二维轮廓角度；真正抓取还要结合目标几何、表面法线或姿态估计、夹爪约束与运动规划。

第一个可以独立完成的小目标是：**在网页点击物体，显示对应三维表面点，并保存这次 RGB-D 观测。** 先用已知距离的静止物体测误差，再比较不同距离、光照和材质下的有效比例与抖动。

## 六、可以继续探索的三个小方向

**让系统解释为什么看不准。** 当目标颜色占比不足、深度空洞多、帧过期或坐标标定缺失时，页面显示具体原因，并保留失败样本。它既是调试工具，也能成为持续更新的实验内容。

**让机器人为观察选择位置。** 固定视角看不清时，先在仿真中比较几个观察位，尝试改善可见面积和深度有效比例，再决定是否靠近或改变视角。可以从规则策略开始，记录移动代价与观测收益。

**给语言指令加上几何核验。** 例如“找到红色盒子，靠近后观察”。语言模块负责解析目标与步骤，视觉模块返回观测，几何模块核对距离和可达性，再由执行器决定动作。这可以作为向 VLN／移动操作延伸的小实验；目前属于项目设想，尚无研究新颖性或效果结论。

## 七、已经验证的范围

现有项目的 36 项测试已通过，覆盖运动核心、摄像头辅助、视觉接口与 MCP 集成。浏览器联调使用合成图与合成视频流，检查了帧标识、连续识别不积压、设备释放与移动端布局；这些结果不能代替真实深度验收。

本次另从 D435 RGB 补拍一张实图，确认彩色采集可用；没有对橘子补做识别测试，也没有获取真实深度。下一步最有价值的进展，是把一张真实 RGB-D 观测变成有单位、坐标、时间戳和误差记录的三维估计，再让后续任务使用这个估计。

源码与运行说明：[PickGo Lab](https://github.com/williamtymhuabian/pickgo-lab)。

---
原文：https://williamtymhuabian.github.io/personal-site/#/post/pickgo-lab-camera
作者：Williamtym
