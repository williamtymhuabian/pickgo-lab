# 代码来源与许可说明

`legacy/utils.py` 来自项目所有者提供的机器人原工程。本项目逐字节保留该文件；来源路径、字节数和 SHA256 记录在 `legacy/source-manifest.json`，并由测试校验。

运行视觉适配器时，仅通过 AST 白名单加载 det_color、det_rect 和指定 HSV 配置，不导入原文件的 ROS、串口或硬件初始化代码。

浏览器仿真、界面、本机服务、MCP 入口、摄像头辅助模块、测试和文档为本项目开发内容。原始机器人代码的权利与许可沿用其原有来源。仓库当前未指定统一开源许可证；未擅自给原始代码、厂商 SDK 或新增内容附加 MIT、Apache 等授权声明。

物体模式使用 OpenCV Zoo NanoDet 的公开模型接口与可选 ONNX 权重，来源与固定版本见 `docs/objects.md`。该模型按上游 Apache-2.0 许可分发，完整许可证随准备脚本保存为 `models/NANODET-LICENSE.txt`；此第三方许可不改变原机器人代码或项目其他文件的许可归属。

Git 默认排除本机下载的模型权重、下载目录、厂商驱动、SDK、Python / Node 环境和真实相机图像。手动打源码压缩包时也应排除这些内容；模型可由 `setup_objects.py` 按需获取。
