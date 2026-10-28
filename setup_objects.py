"""从 OpenCV 官方仓库获取固定版本的小型 ONNX 权重；不安装额外 Python 包。"""
import hashlib
import argparse
import json
import os
from pathlib import Path
import urllib.request

# 不导入 object_vision，使下载说明在未安装 OpenCV 时也能使用。
REVISION = "510899a2a0adb8c25957915fd030d66dbd553919"
FILENAME = "object_detection_nanodet_2022nov.onnx"
SHA256 = "4b82da9944b88577175ee23a459dce2e26e6e4be573def65b1055dc2d9720186"
SIZE = 3800954
ROOT = Path(__file__).resolve().parent


def download_info():
    base = "https://raw.githubusercontent.com/opencv/opencv_zoo/" + REVISION + "/models/object_detection_nanodet/"
    return {"name": "NanoDet-m-plus-1.5x-416", "filename": FILENAME, "bytes": SIZE,
            "sha256": SHA256, "revision": REVISION,
            "url": "https://media.githubusercontent.com/media/opencv/opencv_zoo/" + REVISION + "/models/object_detection_nanodet/" + FILENAME,
            "license": "Apache-2.0", "license_url": base + "LICENSE", "destination": "models/" + FILENAME,
            "required_for": ["object detection"], "not_required_for": ["manual GrabCut", "observation assessment", "geometry comparison"]}


def check_model():
    destination = ROOT / "models" / FILENAME
    exists = destination.is_file()
    valid = exists and destination.stat().st_size == SIZE and hashlib.sha256(destination.read_bytes()).hexdigest() == SHA256
    return {"available": exists, "valid": valid, "path": str(destination), "network_used": False,
            "message": "本机权重已校验，无需重新下载" if valid else "运行 python -B setup_objects.py 按需下载；手动分割和观测评估不需要权重"}


def setup_model():
    folder = ROOT / "models"
    folder.mkdir(exist_ok=True)
    destination = folder / FILENAME
    if destination.is_file():
        if destination.stat().st_size == SIZE and hashlib.sha256(destination.read_bytes()).hexdigest() == SHA256:
            print("NanoDet 已就绪（SHA256 正确），无需重新下载。")
            return
        raise RuntimeError("已有模型校验失败，请先移走损坏文件：" + str(destination))
    base = "https://raw.githubusercontent.com/opencv/opencv_zoo/" + REVISION + "/models/object_detection_nanodet/"
    with urllib.request.urlopen(base + "LICENSE", timeout=30) as response:
        license_data = response.read(30000)
    if b"Apache License" not in license_data or b"Version 2.0" not in license_data:
        raise RuntimeError("Unexpected upstream license")
    # Git LFS 数据端点；固定修订与发布者 LFS SHA256，校验后才放到正式路径。
    url = "https://media.githubusercontent.com/media/opencv/opencv_zoo/" + REVISION + "/models/object_detection_nanodet/" + FILENAME
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(SIZE + 1)
    if len(data) != SIZE or hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError("模型下载不完整或 SHA256 不符，未安装；请检查网络后重试")
    temporary = folder / (FILENAME + ".part")
    try:
        temporary.write_bytes(data)
        (folder / "NANODET-LICENSE.txt").write_bytes(license_data)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    print("物体检测模型已就绪：", destination)
    print("大小 3,800,954 字节；SHA256", SHA256)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只检查本机权重和 SHA256，不联网")
    parser.add_argument("--info", action="store_true", help="只输出下载清单，不联网")
    args = parser.parse_args()
    try:
        if args.info:
            print(json.dumps(download_info(), ensure_ascii=False, indent=2))
        elif args.check:
            status = check_model()
            print(json.dumps(status, ensure_ascii=False, indent=2))
            raise SystemExit(0 if status["valid"] else 2)
        else:
            setup_model()
    except Exception as error:
        raise SystemExit("模型准备失败：" + str(error))
