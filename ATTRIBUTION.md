# 来源与致谢

电量岛（本分支）基于已有的 Windows HID 访问代码，只实现奥丁（Glorious）无线鼠标的电量协议，
外加 Qt 托盘界面、提醒及设备活动检测。下列项目是具体的代码来源或协议参考，并非本项目的作者、
赞助方或官方支持方。

## 直接沿用的代码

### yszyszysz233 / 2.4G-battery-viewer

- 原项目：<https://github.com/yszyszysz233/2.4G-battery-viewer>
- 基准提交：[`f0e983e88900592237c7df9ae6b80b9dbeb3020b`](https://github.com/yszyszysz233/2.4G-battery-viewer/tree/f0e983e88900592237c7df9ae6b80b9dbeb3020b)
- 对应文件：[`hid_win.py`](https://github.com/yszyszysz233/2.4G-battery-viewer/blob/f0e983e88900592237c7df9ae6b80b9dbeb3020b/hid_win.py)，提供 Windows HID 枚举、能力查询和读写。
- 本仓库保留上游 Git 历史，以便核对来源和改动。
- 该基准提交未包含 LICENSE 文件。本仓库没有为上游代码新增或替换许可证；引用和保留历史不代表获得上游额外授权。

感谢原作者提供外设电量工具和纯 ctypes 的 Windows HID 实现。

## 电量协议参考

下列项目用于理解设备编号、接口、查询指令和回复字段。本项目用 Python 重新实现协议，
不直接引入相应的 Rust / C++ 源码。

### korkje / mow

- 项目：<https://github.com/korkje/mow>
- 参考文件：[`src/report/battery.rs`](https://github.com/korkje/mow/blob/master/src/report/battery.rs)、
  [`src/util/devices.rs`](https://github.com/korkje/mow/blob/master/src/util/devices.rs)
- 内容：Glorious Core 抓包逆向得到的 65 字节 Feature Report 电量查询、回复字段与状态码、各型号 PID。
- 对应本项目实现：`glorious_proto.py`。

### krisgfx9 / Wireless-Device-Battery-Monitor

- 项目：<https://github.com/krisgfx9/Wireless-Device-Battery-Monitor>
- 参考文件：[`src/drivers/glorious.cpp`](https://github.com/krisgfx9/Wireless-Device-Battery-Monitor/blob/main/src/drivers/glorious.cpp)
- 内容：Windows 端同一协议的判据（Feature 报告长度 65、回复 `[6]=0x83`、状态 `0xA0/0xA1/0xA4`、
  充电位 `[7]`、电量 `[8]`）与 Glorious 各型号 PID 对照。
- 上游许可证：[GPL-3.0](https://github.com/krisgfx9/Wireless-Device-Battery-Monitor/blob/main/LICENSE)。
  此处为上游声明，不表示本项目替所有文件统一授予 GPL 许可。
- 对应本项目实现：`glorious_proto.py`，并用 `glorious_probe.py` 在本机 Model O- Wireless 上复核。

## 运行时与打包依赖

Python、PySide6 / Qt / Shiboken、PyInstaller 和 Microsoft Visual C++ 运行库的说明见
[THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt)，附带的许可证文本位于 [licenses/](licenses/)。

## 图标与产品名称

`assets/app.svg` 是本项目制作的电量岛图标；`app.png` 和 `app.ico` 为其导出资源，界面符号在
`icons.py` 中绘制。Glorious、奥丁等产品名称仅用于标识兼容设备。
