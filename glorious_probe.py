# -*- coding: utf-8 -*-
"""Glorious（奥丁）无线鼠标电量协议探针。

只用于本地诊断：枚举 258A 接口，打印能力表，然后向匹配的接口发一条
Feature Report 电量查询，并把回复原样 hexdump 出来。
不修改设备设置，只发只读查询命令。

用法：
    python glorious_probe.py
    python glorious_probe.py --all          # 打印所有 HID 接口
    python glorious_probe.py --pid 2024     # 只探测指定 PID
"""
from __future__ import annotations

import argparse
import time

import hid_win as hw

# 协议参考（独立实现）：
#   korkje/mow         src/report/battery.rs, src/util/devices.rs
#   krisgfx9/Wireless-Device-Battery-Monitor  src/drivers/glorious.cpp
VENDOR_ID = 0x258A
REPORT_LEN = 65
REPORT_ID = 0

GLORIOUS_MODELS = {
    0x2011: "Model O Wireless (有线/直连)",
    0x2022: "Model O Wireless (2.4G 接收器)",
    0x2013: "Model O- Wireless (有线/直连)",
    0x2024: "Model O- Wireless (2.4G 接收器)",
    0x2012: "Model D Wireless (有线/直连)",
    0x2023: "Model D Wireless (2.4G 接收器)",
    0x2014: "Model D- Wireless (有线/直连)",
    0x2025: "Model D- Wireless (2.4G 接收器)",
    0x2033: "Model O 2 Wireless",
    0x2034: "Model D 2 PRO",
    0x2036: "Model D 2 PRO",
    0x201A: "Model D 2 PRO (有线/直连)",
}

WIRED_PIDS = {0x2011, 0x2012, 0x2013, 0x2014, 0x201A}

STATUS = {0xA1: "唤醒/在线", 0xA4: "休眠", 0xA0: "正在唤醒", 0xA3: "状态未知"}


def hexdump(data: bytes, indent: str = "    ") -> str:
    lines = []
    for row in range(0, len(data), 16):
        chunk = data[row:row + 16]
        text = " ".join(f"{b:02X}" for b in chunk)
        lines.append(f"{indent}{row:02X}  {text}")
    return "\n".join(lines)


def request(level: int = 0) -> bytes:
    packet = bytearray(REPORT_LEN)
    packet[3] = 0x02
    packet[4] = 0x02
    packet[6] = 0x83
    return bytes(packet)


def parse(reply: bytes) -> dict:
    if len(reply) < 9:
        return {"ok": False, "error": "回复长度不足", "raw": reply}
    if reply[6] != 0x83:
        return {"ok": False, "error": "回复不是电量命令 0x83", "raw": reply}
    status = reply[1]
    if status not in STATUS:
        return {"ok": False, "error": f"未知状态 0x{status:02X}", "raw": reply}
    if status != 0xA1:
        return {"ok": False, "state": STATUS[status], "error": STATUS[status], "raw": reply}
    percent = reply[8] or 1
    if percent > 100:
        return {"ok": False, "error": f"电量字段越界 {percent}", "raw": reply}
    return {"ok": True, "level": percent, "charging": reply[7] == 0x01, "raw": reply}


def probe(iface, attempts: int = 3) -> dict:
    print(f"\n=== {iface.vid_pid}  {iface.path.split('#')[-1].split('{')[0]}")
    print(f"    usage      : 0x{iface.usage_page:04X}:0x{iface.usage:04X}")
    print(f"    report len : in={iface.input_len} out={iface.output_len} feature={iface.feature_len}")
    print(f"    product    : {iface.product!r}")
    print(f"    manufacture: {iface.manufacturer!r}")
    print(f"    型号        : {GLORIOUS_MODELS.get(iface.pid, '未知 PID')}")
    try:
        with hw.HidDevice(iface.path, write=True) as dev:
            if not dev.write_access:
                print("    !! 没有写权限，无法发送 Feature Report")
                return {"ok": False, "error": "no write access"}
            length = iface.feature_len or REPORT_LEN
            packet = (request() + bytes(REPORT_LEN))[:length]
            for attempt in range(1, attempts + 1):
                print(f"    -- 第 {attempt} 次查询 --")
                print("      TX:\n" + hexdump(packet))
                dev.set_feature_report(packet)
                time.sleep(0.05)
                reply = dev.get_feature_report(REPORT_ID, length)
                print("      RX:\n" + hexdump(reply))
                result = parse(reply)
                print(f"      => {result}")
                if result.get("ok"):
                    return result
                if reply[1:2] == b"\xA0" and attempt < attempts:
                    time.sleep(0.4)
                    continue
                return result
    except hw.HidError as exc:
        print(f"    !! HID 错误：{exc}")
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "no reply"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="打印所有 HID 接口")
    parser.add_argument("--pid", type=lambda v: int(v, 16), help="只探测指定 PID（十六进制）")
    args = parser.parse_args()

    interfaces = hw.enumerate_hid()
    if args.all:
        for iface in interfaces:
            print(f"{iface.vid_pid} {iface.describe_usage():>12} "
                  f"in={iface.input_len:<3} out={iface.output_len:<3} feat={iface.feature_len:<3} "
                  f"{iface.product!r} {iface.path.split('#')[-1].split('{')[0]}")

    targets = [i for i in interfaces
               if i.vid == VENDOR_ID
               and i.feature_len >= 9
               and (args.pid is None or i.pid == args.pid)]
    print(f"\n找到 {len(targets)} 个可探测接口（VID 0x{VENDOR_ID:04X}）")
    for iface in targets:
        probe(iface)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
