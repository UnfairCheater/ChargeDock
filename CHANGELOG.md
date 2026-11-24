# 变更记录

## v1.0.0 — 2026-11-24

首个个人发布版，基于 [SgZincanya/ChargeDock](https://github.com/SgZincanya/ChargeDock) 的
`main` 分支（commit `b2e25a9`）。

### 新增

- **奥丁 / Glorious 无线鼠标电量协议**：`glorious_proto.py`
  - 258A 供应商 Feature Report 协议：请求 `[3]=02 [4]=02 [6]=83`，回复 `[1]=状态 [7]=充电 [8]=电量`
  - 支持 Model O / O- / D / D- 的无线（`0x2022`/`0x2024`/`0x2023`/`0x2025`）与直连（`0x2011`–`0x2014`）
  - 状态机：`0xA1` 在线、`0xA4` 休眠、`0xA0` 正在唤醒（400ms 后重问一次）
- **`glorious_probe.py`**：本机诊断探针，打印接口能力表并 hexdump 一次真实查询
- **任务栏常驻电量**
  - 托盘图标直接画百分比（多尺寸 16–48px，按 DPI 选档，低于阈值转红，未知电量显示 `—`）
  - 任务栏条内数字浮标：`Shell_TrayWnd` + `TrayNotifyWnd` 定位，贴通知区域左侧 8px、垂直居中，
    每 3 秒跟随重贴并 `raise_()`；任务栏自动隐藏时退回可用区域；全屏应用在前台时让位
  - 两个开关 `tray_percent` / `badge`，默认开启
- **`startup.py`**：登录自启（从原 `asus_control.py` 抽出的部分）
- **`Reading.present`**：区分"没有这个设备"与"设备在但读不到"
- 测试：`test_glorious.py`、`test_tray.py`、任务栏定位与全屏判定用例

### 变更

- 鼠标类别先走 Glorious 协议，未发现接收器再回退 ROG 协议
- 设置页新增"托盘图标显示百分比""右下角数字浮标"两个开关
- 未检测到设备时不再显示 ROG 占位卡片，改为一行"未检测到设备 · 插入接收器后会自动出现"
- 键盘/耳机的"没找到设备"文案改为通用说法

### 移除

- 奥创电量浮窗的全部控制代码、设置界面、管理员提权 Helper（`asus_control.py`、`--asus-action`）
- 四语言文案中 19 条奥创相关条目

### 验证

- 单元测试 111 项全绿：`python -m unittest discover -p "test_*.py"`
- 实机验证（Glorious Model O- Wireless）：2.4G 接收器 `258A:2024` 与直连 `258A:2013` 均读数正常
