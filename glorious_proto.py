# -*- coding: utf-8 -*-
"""Glorious（奥丁）无线鼠标电量查询。只发送只读电量命令，不更改灯光、DPI 或任何设置。

协议参考（独立实现，未复制源码）：
https://github.com/korkje/mow/blob/master/src/report/battery.rs
https://github.com/korkje/mow/blob/master/src/util/devices.rs
https://github.com/krisgfx9/Wireless-Device-Battery-Monitor/blob/main/src/drivers/glorious.cpp

协议摘要（258A = 联阳 / SinoWealth 供应商 VID，多家品牌共用）：
  接口：Feature Report 长度为 65 的 HID 顶层集合，report id 0。
  请求：65 字节，[3]=0x02 [4]=0x02 [6]=0x83，其余为 0。
  回复：[1]=状态，[6]=0x83 回显，[7]=充电中(1)，[8]=电量百分比。
        状态 0xA1 = 在线，0xA4 = 休眠，0xA0 = 正在唤醒，其余视为不可达。
"""
from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass
from typing import Optional

import hid_win as hw

VENDOR_ID = 0x258A
REPORT_ID = 0
REPORT_LEN = 65
COMMAND = 0x83
REPLY_DELAY = 0.05      # Glorious Core 的固件响应间隔，取自 glorious.cpp 的 replyDelayMs
WAKE_DELAY = 0.4        # 0xA0（正在唤醒）后等一会儿再问一次

STATUS_AWAKE = 0xA1
STATUS_ASLEEP = 0xA4
STATUS_WAKING = 0xA0


@dataclass(frozen=True)
class DeviceSpec:
    title: str
    pid: int
    wired: bool


# 无线 PID 是接收器，有线 PID 是直连（此时鼠标一定在充电）。
DEVICES = (
    DeviceSpec("奥丁 Model O-", 0x2013, True),
    DeviceSpec("奥丁 Model O-", 0x2024, False),
    DeviceSpec("奥丁 Model O", 0x2011, True),
    DeviceSpec("奥丁 Model O", 0x2022, False),
    DeviceSpec("奥丁 Model D-", 0x2014, True),
    DeviceSpec("奥丁 Model D-", 0x2025, False),
    DeviceSpec("奥丁 Model D", 0x2012, True),
    DeviceSpec("奥丁 Model D", 0x2023, False),
)


@dataclass
class GloriousReading:
    title: str
    level: Optional[int] = None
    charging: bool = False
    detail: str = ""
    error: str = ""
    raw: bytes = b""


def match_device(iface: hw.HidInterface) -> Optional[DeviceSpec]:
    """只按 VID + PID + Feature 报告长度识别，不碰 Usage，也不轮流试写未知接口。"""
    if iface.vid != VENDOR_ID or iface.feature_len != REPORT_LEN:
        return None
    return next((s for s in DEVICES if s.pid == iface.pid), None)


def request_packet(length: int = REPORT_LEN) -> bytes:
    packet = bytearray(max(length, 9))
    packet[3] = 0x02
    packet[4] = 0x02
    packet[6] = COMMAND
    return bytes(packet[:length])


def parse_reply(spec: DeviceSpec, reply: bytes) -> Optional[GloriousReading]:
    """解析回复；不是电量回复时返回 None，由调用方继续等待。"""
    if len(reply) < 9 or reply[6] != COMMAND:
        return None
    status = reply[1]
    if status == STATUS_WAKING:
        return GloriousReading(spec.title, error="鼠标正在唤醒，请稍后刷新", raw=reply)
    if status == STATUS_ASLEEP:
        return GloriousReading(spec.title, error="鼠标休眠或未连接，请动一下鼠标后刷新", raw=reply)
    if status != STATUS_AWAKE:
        return GloriousReading(spec.title, error="设备返回了无法识别的状态", raw=reply)
    level = reply[8]
    if level > 100:
        return GloriousReading(spec.title, error="设备返回无效电量", raw=reply)
    # 0% 只出现在刚唤醒的瞬间，不当作电池耗尽。
    return GloriousReading(spec.title, max(1, level), spec.wired or reply[7] == 1, raw=reply)


def read_interface(iface: hw.HidInterface, attempts: int = 2) -> Optional[GloriousReading]:
    spec = match_device(iface)
    if spec is None:
        return None
    result = GloriousReading(spec.title, detail=f"{iface.vid_pid} · Glorious HID Feature 电量协议")
    # 面板与托盘子进程可能同时读同一只鼠标，串行化避免互相抢走回复。
    kernel = hw.kernel32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.ReleaseMutex.restype = ctypes.c_int
    kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
    mutex = kernel.CreateMutexW(None, False, f"Local\\GloriousBattery_{spec.pid:04X}")
    if not mutex:
        result.error = "无法创建设备读取锁"
        return result
    acquired = False
    try:
        acquired = kernel.WaitForSingleObject(mutex, 2000) in (0, 0x80)
        if not acquired:
            result.error = "设备正在被另一窗口读取，请稍后刷新"
            return result
        with hw.HidDevice(iface.path, write=True) as dev:
            if not dev.write_access:
                result.error = "无法写入查询命令，请关闭占用设备的程序后重试"
                return result
            length = iface.feature_len or REPORT_LEN
            packet = request_packet(length)
            for attempt in range(1, attempts + 1):
                dev.set_feature_report(packet)
                time.sleep(REPLY_DELAY)
                reply = dev.get_feature_report(REPORT_ID, length)
                parsed = parse_reply(spec, reply)
                if parsed is None:
                    continue
                if parsed.error and reply[1:2] == bytes((STATUS_WAKING,)) and attempt < attempts:
                    time.sleep(WAKE_DELAY)
                    continue
                parsed.detail = result.detail
                return parsed
        result.error = "设备未回复电量查询，请动一下鼠标并检查接收器"
    except (OSError, hw.HidError) as exc:
        result.error = f"读取失败：{exc}"
    finally:
        if acquired:
            kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)
    return result


def read_device(interfaces=None) -> Optional[GloriousReading]:
    """找到一个 Glorious 接口并读取电量；完全没有匹配接口时返回 None。"""
    last: Optional[GloriousReading] = None
    found = False
    for iface in hw.enumerate_hid() if interfaces is None else interfaces:
        if match_device(iface) is None:
            continue
        found = True
        reading = read_interface(iface)
        if reading is None:
            continue
        if reading.level is not None:
            return reading
        last = reading
    if not found:
        return None
    return last
