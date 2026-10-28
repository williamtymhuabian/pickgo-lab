# v0.5.0 验证记录

开发及回归执行于 2026-10-23 晚，整理于 10 月 24 日。没有打开摄像头、安装依赖或下载新文件，没有连接实体机器人。

## 自动检查

在项目根目录运行：

```powershell
python -B -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/simulation.test.cjs tests/camera.test.cjs tests/observation_state.test.cjs tests/vision_helpers.test.cjs
```

Python 共 52 项全部通过，包括已有部署配置、MCP、颜色与物体检测，以及新增 11 项观测评估检查。JavaScript 包含 9 项运动、8 项相机、16 项观测状态检查，全部通过；图像辅助脚本的 7 项断言通过。Node 测试运行器将部分旧脚本按文件计数，因此汇总行的 19 不等于脚本内部业务检查数量。

新增边界覆盖：同一帧/视频时间重复不累计，旧帧及旧证据过期，累计慢漂移重新收集，来源与类别变化，乱序帧，静态图片不判实时稳定；自适应三次与固定五次真实 GrabCut、空前景、候选不一致、不足候选、忙碌互斥、非法输入、HTTP 来源检查及 MCP 只读工具。原始 legacy 文件完整性检查通过。

## 页面验证

在仅视觉服务模式中使用合成图手动框选：前景面积 7,393 px。自适应策略使用三次候选后停止，固定策略完成五次；两者在该图上的最小候选 IoU 都为 1。此值描述同帧候选一致性，不是真实分割精度。

JSON 报告已解析并确认不包含图像 data URL，`robot_execution_authorized` 为 false。切换来源后旧评估、下载链接与评估按钮失效；空参数不沿用旧运动学结论。抬升高度从 0.10 改为 0.15 m 时，共同采样余量由 39.5 改为 13.0 mm，确认界面参数参与计算。

另用本机已有的 OpenCV `messi5.jpg` 样例及已校验 NanoDet 权重运行离线链路，得到四个候选：sports ball → REOBSERVE；两个 person 候选分别为 REOBSERVE、CONSISTENT；另一个 person 候选为 NO_FOREGROUND。它只验证输出路径及分支，不作为准确率、实际物体数量或泛化性能结论。

## 待实物验收

实际相机类别、掩膜质量、连续帧耗时、误检与漏检，以及默认像素门槛是否合适，按照 [摄像头实操](camera-validation-2026-10-24.md) 验收。当前运动学对照与相机没有空间绑定，没有真实深度、标定或物理抓取成功验证。
