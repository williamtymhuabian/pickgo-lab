# 可选物体检测模型

在项目根目录运行 `python -B setup_objects.py`，下载 OpenCV Zoo NanoDet 固定版本权重与完整许可证。ONNX 大小 3,800,954 字节，使用现有 OpenCV DNN CPU 推理，无需 PyTorch。

ONNX 和临时文件已被 Git 忽略。源码分享时保留本文件即可；用户可按需下载权重。手动框选 GrabCut 分割不依赖该模型。

来源、固定版本、SHA256、许可证及功能边界见 [物体与分割说明](../docs/objects.md)。

v0.5.0 提供 [weights-manifest.json](weights-manifest.json)、根目录 `download-weights.cmd` 和 `setup_objects.py --info` 下载清单。`python -B setup_objects.py --check` 只检查本机大小和 SHA256，不联网；校验通过无需重复下载。新增观测评估同样不需要权重，具体步骤见 [摄像头实操](../docs/camera-validation-2026-10-24.md)。
