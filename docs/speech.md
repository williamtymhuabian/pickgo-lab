# 中文识别播报

2026-10-24 完成实测，v0.6.0 同步到 GitHub。识别与前景提取算法未因 TTS 改变。

## 使用

从本目录启动 `python -B app.py --vision-only --port 8771`，打开 `http://127.0.0.1:8771/vision.html?source=camera&task=segment`。已有服务时需重启后刷新页面，才能使用新接口。

1. 打开 RGB 相机，用“常见物体检测”先检查类别。需要前景掩膜时切换到“物体检测＋前景分割”。
2. 在“中文语音播报”点击“试音”。
3. 检测后点击“播报当前结果”；点击某个候选目标可优先播报该类别，在后续仍检测到同类时保留该偏好。
4. 同时勾选“自动播报识别结果”和“连续识别”，可连续使用。连续结果需两次相同类别组合，至少间隔 6 秒，同内容 20 秒内不重复。
5. “停止播报”会取消当前音频/合成请求并关闭自动播报，视觉识别可继续。切换来源、任务或关闭相机会清除旧目标；页面隐藏会停声并关闭自动播报。

播报语句使用“可能识别到”，不把模型分数解释成正确率。未知类别或没有目标会明确说明；手动框选只播报已提取前景，不猜测名称。自动播报不使用超过 2.5 秒的旧帧；手动播报允许复听当前冻结结果。

## 本地语音与数据

Windows 后端通过固定 PowerShell 脚本调用已安装的 `System.Speech` 中文语音。文本经 UTF-8/Base64 从 stdin 作为数据传入，不拼接到脚本、命令或 SSML 中；最长 120 字符，合成超时 12 秒，一次仅运行一个合成进程，最近 8 条音频缓存在内存。

接口为 `GET /api/vision/speech/status`、`POST /api/vision/speech`（JSON `text`）。沿用本机同源访问限制。音频以 WAV data URL 返回页面，不在磁盘生成 WAV 文件。浏览器若阻止自动播放，可以点击音频控件的播放键。

非 Windows 服务可使用浏览器已有的本地中文语音；没有本地中文语音时显示不可用，不自动使用远程语音。状态端点的 Windows available 表示运行平台和组件路径满足条件，实际语音缺失等问题在合成时报告。

本功能不申请麦克风权限、不调用云 TTS、不下载模型。每次“拍摄一帧并识别”确实会采集送检图，但图片只在内存中处理，不自动保存照片或录像。只有用户主动下载前景 PNG 才导出图像。

## 本次实测

- D435 RGB 视频为 640×480，送检图为 320×240。
- 用户摆放的是金属保温杯。最初一帧返回 cup 44.0%，后续有 bottle 51.9%、杯子漏检及其他候选；中心放大未改善该样例，已恢复完整画面。不能据此声称稳定识别保温杯。
- Windows 本地中文语音成功生成有效 RIFF/WAVE。浏览器音频 readyState 为 4、播放到末尾、error 为空，用户确认听到试音及结果播报。
- 播报测试阶段使用常见物体检测、完整画面、连续识别与自动播报；整轮测试结束后已按用户要求停止视觉服务并释放相机。
- 这次 RGB / TTS 测试没有保存相机照片、导出前景图或录制视频，没有读取深度或执行机器人动作；随后单独进行的深度验证见 [RGB-D 记录](realsense-depth.md)。

## 验证

新增 `tests/test_speech.py` 5 项检查覆盖纯文本输入、缓存、超时、错误音频和 HTTP 同源限制。完整 Python 回归为 57 项，已通过。`tests/speech.test.cjs` 8 项检查覆盖中文类别、去重限频、来源变化后的迟到音频、浏览器自动播放阻止和旧帧/隐藏页面；原 JavaScript 回归亦通过。

```powershell
python -B -m unittest discover -s tests -p 'test_*.py'
node --test tests/speech.test.cjs tests/camera.test.cjs tests/observation_state.test.cjs tests/vision_helpers.test.cjs tests/simulation.test.cjs
```

语音组件依据：[Microsoft SpeechSynthesizer](https://learn.microsoft.com/en-us/dotnet/api/system.speech.synthesis.speechsynthesizer)、[浏览器 SpeechSynthesis](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis)。
