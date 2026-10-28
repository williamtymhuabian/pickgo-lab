"""仅使用标准库读取本机部署配置。"""
import json

from Constants import APP

MAX_CONFIG_BYTES = 16 * 1024


def _reject_constant(value):
    raise ValueError("配置不允许非有限数值: " + value)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("配置包含重复键: " + key)
        result[key] = value
    return result


def load_config(path=None):
    config = {"schema_version": 1, "host": APP["host"],
              "port": APP["port"], "vision_only": False}
    if path is None:
        return config
    with open(path, "rb") as source:
        raw = source.read(MAX_CONFIG_BYTES + 1)
    if len(raw) > MAX_CONFIG_BYTES:
        raise ValueError("配置文件不能超过 16 KiB")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                      parse_constant=_reject_constant)
    if type(data) is not dict:
        raise ValueError("配置必须是 JSON object")
    if data.keys() - config.keys():
        raise ValueError("配置包含未知字段")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("schema_version 必须是整数 1")
    config.update(data)
    if type(config["host"]) is not str or config["host"] != "127.0.0.1":
        raise ValueError("host 必须是 127.0.0.1")
    if type(config["port"]) is not int or not 1 <= config["port"] <= 65535:
        raise ValueError("port 必须是 1 到 65535 的整数")
    if type(config["vision_only"]) is not bool:
        raise ValueError("vision_only 必须是布尔值")
    return config
