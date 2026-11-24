"""ChargeDock domain logic; no UI and no network access.

本仓库只支持一种设备：奥丁（Glorious）无线鼠标。ROG 与赛睿耳机的协议已移除。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Reading:
    key: str
    title: str
    model: str
    level: int | None = None
    charging: bool = False
    approximate: bool = False
    error: str = ""
    updated: float = 0
    # False 表示连匹配的接收器/USB 接口都没找到；界面据此不显示这张卡片。
    present: bool = False


MODELS = {"mouse": ("奥丁 Model O-", "GLORIOUS MODEL O- WIRELESS")}


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def defaults() -> dict:
    return {"interval": 60, "dismiss_seconds": 12, "sound": False, "language": "system",
            "tray_percent": True, "badge": True,
            "alerts": {"mouse": {"enabled": True, "threshold": 20}}}


def validate_config(value) -> dict:
    result = defaults()
    if not isinstance(value, dict):
        return result
    from i18n import LANGUAGES
    if isinstance(value.get("language"), str) and value["language"] in LANGUAGES:
        result["language"] = value["language"]
    if value.get("interval") in (30, 60, 120, 300):
        result["interval"] = value["interval"]
    if value.get("dismiss_seconds") in (8, 12, 20, 30):
        result["dismiss_seconds"] = value["dismiss_seconds"]
    result["sound"] = value.get("sound") is True
    # 旧配置没有这两个键时保持开启：常驻数字是这台机器的默认形态。
    result["tray_percent"] = value.get("tray_percent", True) is True
    result["badge"] = value.get("badge", True) is True
    alerts = value.get("alerts", {})
    item = alerts.get("mouse", {}) if isinstance(alerts, dict) else {}
    if isinstance(item, dict):
        result["alerts"]["mouse"]["enabled"] = item.get("enabled", True) is True
        threshold = item.get("threshold", 20)
        if type(threshold) is int:
            result["alerts"]["mouse"]["threshold"] = max(1, min(99, threshold))
    return result


def load_config(path: Path) -> dict:
    try:
        return validate_config(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return defaults()


class AlertPolicy:
    """One reminder per low-battery episode, with 5% recovery hysteresis."""
    def __init__(self):
        self.notified: set[str] = set()
        self.snoozed_until = 0.0

    def evaluate(self, readings: list[Reading], config: dict, now: float | None = None) -> list[Reading]:
        now = time.time() if now is None else now
        notifications = []
        for reading in readings:
            if reading.key not in MODELS:
                continue
            item = config["alerts"][reading.key]
            if not item["enabled"]:
                self.notified.discard(reading.key)
                continue
            if reading.level is None or reading.error:
                continue
            threshold = item["threshold"]
            if reading.charging or reading.level > min(99, threshold + 5):
                self.notified.discard(reading.key)
                continue
            if now < self.snoozed_until:
                continue
            if reading.level <= threshold and reading.key not in self.notified:
                notifications.append(reading)
                self.notified.add(reading.key)
        return notifications


def read_device(interfaces=None) -> Reading:
    """读鼠标电量。没有匹配的接收器/USB 接口时 present=False，界面据此不显示卡片。"""
    import glorious_proto
    import hid_win as hw
    interfaces = hw.enumerate_hid() if interfaces is None else interfaces
    value = glorious_proto.read_device(interfaces)
    if value is None:
        return Reading("mouse", *MODELS["mouse"], error="未找到奥丁接收器或 USB 连接",
                       updated=time.time())
    return Reading("mouse", value.title or MODELS["mouse"][0], MODELS["mouse"][1],
                   value.level, value.charging, present=True,
                   error=value.error, updated=time.time())


def read_all(keys=None) -> list[Reading]:
    """读取所有（当前只有一只鼠标）设备。接口枚举失败时不改动卡片显隐，只报错。"""
    import hid_win as hw
    keys = list(MODELS) if keys is None else list(keys)
    if any(key not in MODELS for key in keys) or len(set(keys)) != len(keys):
        raise ValueError("Unknown or duplicate device keys")
    if not keys:
        return []
    try:
        interfaces = hw.enumerate_hid()
    except Exception as exc:
        return [Reading(key, *MODELS[key], error=f"暂时无法读取：{exc}", present=True) for key in keys]
    try:
        return [read_device(interfaces)]
    except Exception as exc:
        return [Reading(key, *MODELS[key], error=f"暂时无法读取：{exc}", present=True) for key in keys]


def poll_to_file(path: Path, key=None) -> int:
    keys = [key] if isinstance(key, str) else key
    atomic_json(path, [asdict(r) for r in read_all(keys)])
    return 0


def read_poll_file(path: Path, expected_keys=None) -> list[Reading]:
    expected_keys = list(MODELS) if expected_keys is None else expected_keys
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) != len(expected_keys):
        raise ValueError("Incomplete device results")
    readings = [Reading(**item) for item in raw]
    if [r.key for r in readings] != expected_keys:
        raise ValueError("Unexpected devices")
    for reading in readings:
        if reading.level is not None and (type(reading.level) is not int or not 0 <= reading.level <= 100):
            raise ValueError("Invalid battery level")
    return readings


def user_data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "ChargeDock"
