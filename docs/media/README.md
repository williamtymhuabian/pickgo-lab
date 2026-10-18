# 图片来源与使用范围

- `d435-rgb-real.png`：2026-10-18，经用户授权从 RealSense D435 的 RGB 接口采集一张 640×480 图像，再用本地程序裁剪至 `(248, 42, 550, 308)`，得到 302×266 的橘子近景。仅裁剪，不补画；不含原始画面中的背景人员与电脑屏幕。完整临时画面已清理，仓库仅收录裁剪图。该图只展示 RGB 采集，不代表识别或深度测试成功。
- `d435-device.jpg`：用户提供并授权公开的本机 RealSense D435 摄像头与三脚架实拍照片，原图复制，未修改画面内容。
- `camera-test-stream.png`：本机浏览器联调截图，输入为明确标注的合成视频流，并非真实摄像头拍摄。
- `rgbd-synthetic-vision.png`、`vision-detection.png`：合成 RGB-D 测试输入与原算法的界面结果，深度为合成测试数据。
- `simulation-overview.png`、`simulation-transport.png`、`pick-and-deliver.gif`、`pick-and-deliver.mp4`：项目运动学仿真实际运行的截图与录屏，没有连接实体机器人。
