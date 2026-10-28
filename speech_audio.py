"""Offline Windows TTS. Speech text is stdin data, never executable code."""
import base64
import functools
import os
from pathlib import Path
import subprocess
import sys
import threading

LOCK = threading.Lock()
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([Console]::In.ReadToEnd().Trim()))
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$stream = New-Object IO.MemoryStream
try {
    $voice = $synth.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'zh*' } | Select-Object -First 1
    if (-not $voice) { throw 'No installed Chinese voice' }
    $synth.SelectVoice($voice.VoiceInfo.Name)
    $synth.SetOutputToWaveStream($stream)
    $synth.Speak($text)
    $synth.SetOutputToNull()
    [Console]::Out.Write([Convert]::ToBase64String($stream.ToArray()))
} finally { $synth.Dispose(); $stream.Dispose() }
"""


def status():
    return {"available": sys.platform == "win32" and POWERSHELL.is_file(),
            "backend": "windows-local", "network_used": False}


def validate_text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 120:
        raise ValueError("播报内容需为 1–120 个字符")
    if any(ord(c) < 32 for c in value):
        raise ValueError("播报内容不能含控制字符")
    return value.strip()


@functools.lru_cache(maxsize=8)
def synthesize(text):
    text = validate_text(text)
    if not status()["available"]:
        raise RuntimeError("当前系统没有 Windows 本地语音，请使用浏览器本地中文语音")
    if not LOCK.acquire(blocking=False):
        raise RuntimeError("语音正在合成，请稍后重试")
    try:
        command = base64.b64encode(SCRIPT.encode("utf-16-le")).decode("ascii")
        try:
            process = subprocess.run(
                [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-EncodedCommand", command],
                input=base64.b64encode(text.encode("utf-8")), capture_output=True,
                timeout=12, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError("本地语音合成未完成，请重试或检查中文语音组件") from error
        if process.returncode:
            raise RuntimeError("本地语音不可用，请检查 Windows 中文语音组件")
        try:
            data = base64.b64decode(process.stdout.strip(), validate=True)
        except ValueError as error:
            raise RuntimeError("语音引擎返回了无效音频") from error
        if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            raise RuntimeError("语音引擎没有返回 WAV 音频")
        return {"audio": "data:audio/wav;base64," + base64.b64encode(data).decode("ascii"),
                "backend": "windows-local", "text": text, "network_used": False}
    finally:
        LOCK.release()
