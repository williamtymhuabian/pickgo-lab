# PickGo Lab v0.3.0：RGB 摄像头接入与可达性实验

上一篇分享了 PickGo Lab 的离线搬运仿真，以及网页、Python 和 MCP 共用场景的方式。这次整理的 v0.3.0，继续完善视觉输入：让浏览器接入内置或 USB 彩色摄像头，把采集到的图像交给本机原识别函数，再把结果画回对应的送检帧。

一个容易忽略的问题是：摄像头预览一直在动，检测结果却晚一些才返回。如果把旧结果直接画在最新预览上，检测框看起来就会跟错目标。这一版先把“哪一帧得到什么结果”处理清楚，同时补上打开超时、取消授权和来源切换后的设备释放。

项目地址：[PickGo Lab](https://github.com/williamtymhuabian/pickgo-lab)。前一版介绍见 [浏览器、Python 与 MCP 搬运仿真实践](https://williamtymhuabian.github.io/personal-site/#/post/pickgo-lab)。

## 一、这次新增了什么

目前可以分别运行三类功能：

- 离线运动仿真：浏览器打开 index.html，观察抓取、托盘固定、绕障运输和投放。
- 共享仿真：启动 app.py，让网页、Python 脚本和 MCP 工具查看同一个运动场景。
- 独立视觉验证：使用合成 RGB-D 图、本地图片或 RGB 摄像头输入，调用原颜色与矩形识别函数。

v0.3.0 的新增重点是第三类：设备选择、实时预览、单帧与连续识别、送检区域中心放大，以及不启动仿真进程的 `--vision-only` 模式。

视觉结果目前用于检查输入输出，尚未用于控制自动搬运；真实深度采集、相机配准和实体机器人后端仍未实现。

## 二、先把本机视觉页面跑起来

准备 Python 3.10 或以上版本，克隆项目并安装视觉依赖：

~~~bash
git clone https://github.com/williamtymhuabian/pickgo-lab.git
cd pickgo-lab
python -m pip install -r requirements.txt
python -B app.py --vision-only
~~~

用本机 Edge 或 Chrome 打开 [摄像头模式](http://127.0.0.1:8767/vision.html?source=camera)。Windows 也可以双击 `start-camera.cmd`。

这一模式不需要 Node.js，也不创建运动仿真进程。如果端口被占用，可以追加 `--port 8769`，并改用对应端口访问。

先切回合成 RGB-D 测试图，检查原识别函数是否可用，再切到摄像头输入。这样可以把“算法或服务没有正常工作”和“真实画面不满足识别条件”分开排查。

![v0.3.0 合成 RGB-D 测试图与原算法输出：此处的深度来自合成输入，并非真实相机测距](https://williamtymhuabian.github.io/personal-site/assets/projects/pickgo-lab-v030-synthetic.png)

浏览器采集需要用户授权，并受安全上下文和浏览器设置限制。请使用本机地址运行；静态博客展示截图和文档，不替读者运行本机 Python 服务。[浏览器采集说明](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)

## 三、让检测框对应实际送检的那一帧

视觉页面把两个画面分开：左侧是持续更新的视频预览，右侧是实际交给 Python 的图像和对应检测结果。

一次识别的流程是：

~~~text
视频流 → 选定区域 → 等比缩放到 320×240 → PNG 送检
        → 本机 OpenCV → 原 det_color / det_rect
        → 校验帧标识 → 在该送检帧上绘制结果
~~~

前端会带上 `frame_id`，返回结果必须与本次请求匹配。切换来源、目标颜色或送检区域后，旧结果会失效；没有识别到目标时，中心和角度也会清空。

连续识别采用“上一次返回，再采下一帧”的方式。同一页面最多保留一个识别请求，避免画面持续采集时堆积旧任务。原函数包含 0.4 秒等待，因此预览帧率和识别频率需要分开看。

下面这张截图来自本轮浏览器联调：输入是明确标注的合成测试视频流，原 Python 函数实际完成了识别。它用来验证采集接口、送检和结果显示，没有打开真实摄像头，也不能代表 D435 的实物识别效果。

![浏览器合成测试视频流联调，非真实相机拍摄：左侧预览，右侧送检帧；RGB 输入没有有效深度](https://williamtymhuabian.github.io/personal-site/assets/projects/pickgo-lab-v030-camera.png)

送检图像保持原始宽高比，必要时留边；中心放大改变的是取样区域。页面中的中心和像素误差都基于 320×240 送检图像，矩形角度是 OpenCV 的原始结果，不能直接当作机器人坐标或机械臂转角。

## 四、打开与关闭摄像头，也需要验证

点击“打开摄像头”后才发起视频请求，代码明确设置 `audio: false`。设备选择只枚举视频输入，不申请麦克风。

设备名称可辨认时，列表会区分 RGB 与 Depth / IR 接口。RealSense 的设备名称可能同时出现“Depth Camera”和“RGB”，因此当前辅助判断优先检查接口名称后缀。名称只是选择提示，不能凭一个通用 UVC 名称推断设备支持哪些深度能力。

打开过程还有几个需要处理的状态：用户拒绝权限、迟迟不作选择、设备被占用、打开后断开，以及点击取消后视频流才迟到。辅助模块用请求代次区分这些过程，过期的视频流会释放轨道，不重新占用相机。

切换图像来源、关闭设备或离开页面时，会停止已有轨道并清空 video 的 `srcObject`。取消“连续识别”只暂停送检，仍保留预览；需要释放设备时点击“关闭摄像头”。轨道停止的行为可参考 [MediaStreamTrack.stop](https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/stop)。

本轮还修复了一个服务端问题：客户端取消识别请求后，结果写回已断开的连接会触发异常。现在会结束这次响应写入，避免重复发送错误响应；新增回归检查验证服务仍能接受后续请求。

## 五、保留原算法，也把限制写清楚

`legacy/utils.py` 继续按原字节保留，测试检查 SHA256。适配层只提取 `det_color`、`det_rect` 和指定 HSV 配置，不导入整个原工程，也不执行其中的 ROS、串口或实体机器人初始化。

当前方法识别的是满足原 HSV 配置的颜色区域及其矩形轮廓。代码有颜色占比约 4% 的门槛，也有轮廓尺寸检查；光照、反光、相机颜色和目标占画面比例都会影响结果。

识别不到时，可以先确认目标颜色、改善光照、靠近物体或使用中心放大，再与合成测试图对照。本次保持原函数与阈值不变，先验证输入链路，再按实际场景检查识别效果。

仓库的开发记录保留了此前 D435 RGB 640×480 采集和送检已连通、当次未识别到目标的情况。本轮使用合成图与浏览器测试视频流验证软件行为，没有再次启用真实相机。真实红蓝黄物体的效果仍需单独验收。

RGB 输入没有毫米深度；合成 RGB-D 测试图里的 650 mm 只是测试数据。真实深度流、时间同步和 RGB-D 配准，需要后续适配，当前不从灰度或 RGB 图像补造距离。

## 六、一个可复现实验：目标移动 10 cm 后会怎样

除了接入视频，我也运行了仓库里的固定停车位探测。命令是：

~~~bash
node experiments/reachability-probe.cjs
~~~

实验每次创建全新的运动仿真实例，只改变红色方块的 y 坐标，固定时间步为 0.04 秒，其他场景与动作程序保持不变。结果为：

~~~text
目标 y=0.76 m  → SUCCEEDED，仿真时间 48.68 s
目标 y=0.86 m  → FAILED / OUT_OF_REACH，仿真时间 8.16 s
目标 y=0.96 m  → FAILED / OUT_OF_REACH，仿真时间 8.16 s
目标 y=1.06 m  → FAILED / OUT_OF_REACH，仿真时间 8.16 s
目标 y=1.16 m  → FAILED / OUT_OF_REACH，仿真时间 8.16 s
~~~

这些是五个确定输入的结果，不是随机成功率，时间也不是实体机器人耗时。当前程序使用固定取物停车位，目标移动后，预抓取位置可能超出机械臂工作空间。

下一步很适合增加“执行前可达性检查”和“抓取停车位选择”：先检查底盘通路、停车间隙和各阶段逆解，再执行任务。只检验最终抓取点还不够，预抓取、抬升、托盘放置等阶段都要满足约束。这些属于后续计划，当前版本尚未实现。

## 七、这次发布验证了哪些内容

本轮通过 36 项测试：运动核心 9 项、摄像头辅助模块 8 项、视觉接口 10 项、MCP 与共享状态集成 9 项。

~~~bash
node tests/simulation.test.cjs
node tests/camera.test.cjs
python -B tests/test_vision.py
python -B tests/test_mcp.py
~~~

浏览器联调另外检查了送检帧标识、连续识别不积压、RGB 不补造深度、来源切换后轨道释放，以及 320px 和 390px 手机布局。上述测试使用合成输入和本机临时服务，不代表真实设备或复杂环境下的效果。

离线运动演示继续保留，数学核心没有因这次摄像头接入而改变：

![既有运动仿真演示：抓取、托盘固定、绕障运输与投放；视觉结果尚未接入控制闭环](https://raw.githubusercontent.com/williamtymhuabian/pickgo-lab/main/docs/media/pick-and-deliver.gif)

v0.3.0 适合用来学习视频输入、帧结果一致性、设备生命周期，以及固定运动流程的局限。后续如果继续做视觉闭环，我希望每一步都有可复现输入、明确坐标和可以解释的失败原因。

源码、运行说明与更新记录：[PickGo Lab](https://github.com/williamtymhuabian/pickgo-lab)。

---
原文：https://williamtymhuabian.github.io/personal-site/#/post/pickgo-lab-v030
作者：Williamtym
