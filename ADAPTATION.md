# 适配指南：改型号、改名字、改提醒

本分支只支持一种设备：**奥丁（Glorious）无线鼠标**。所有设备相关代码集中在三个文件：

| 文件 | 作用 |
| --- | --- |
| `glorious_proto.py` | 258A Feature Report 协议；`DEVICES` 表列出 PID、型号名、是否直连 |
| `core.py` | `MODELS`（默认标题/型号串）、`read_device()`、提醒策略、配置校验 |
| `ui.py` | 卡片副标题、托盘数字图标、任务栏浮标、设置页开关 |

## 常见改动

| 需求 | 修改位置 |
| --- | --- |
| 加同协议的接收器 PID | `glorious_proto.DEVICES` 加一行 `DeviceSpec(title, pid, wired)` |
| 改显示名称 | `core.MODELS["mouse"]` + 四种语言的 `locales/*.json`（把中文原文当 key） |
| 改副标题 | `ui.DeviceCard.SUBTITLES["mouse"]` |
| 改提醒阈值范围/默认值 | `core.defaults()`、`core.validate_config()`、`ui.Panel.build_settings()` |
| 改提醒去重与暂停 | `core.AlertPolicy`、`ui.Controller.snooze()` |
| 改托盘图标画法 | `icons.level_pixmap()` / `level_icon()` |
| 改浮标位置 | `ui.taskbar_geometry()` / `badge_position()` |
| 改刷新间隔选项 | `core.validate_config()` 与 `ui.Panel.build_settings()` |
| 新增语言或文案 | [LOCALIZATION.md](LOCALIZATION.md) |

## 怎么确认 PID 和报告长度

1. 插上接收器，运行 `python glorious_probe.py`：它会打印 258A 接口的 Usage、输入/输出/Feature
   报告长度和产品名，然后发一次只读查询并 hexdump 回复。
2. 需要看全部 HID 接口时用 `python glorious_probe.py --all`。
3. 只有在 **Feature 报告长度 = 65** 且回复 `[6] == 0x83` 时才算同一协议；
   `[1] = 0xA1` 在线、`0xA4` 休眠、`0xA0` 正在唤醒，`[7] = 1` 充电中，`[8]` 电量百分比。
4. 往 `DEVICES` 里加之前，先用探针确认这个 PID 真的回 `0x83`；不要对未知接口轮流试写。

## 提醒逻辑要点

- 只对 `core.MODELS` 里登记的 key 生效；未知 key 的读数一律不提醒。
- 低电量阶段只提醒一次；充电或恢复到阈值 +5% 以上才重新允许提醒。
- 充电中、未连接（`present=False`）、无效电量、读取失败都不触发提醒。
- 暂停 30 分钟只影响通知，不影响读取和界面显示。

## 交给 AI 改的时候

把仓库链接、你想改什么、以及 `python glorious_probe.py` 的输出一起给它。要求它：

- 先跑 `python -m unittest discover -p "test_*.py"` 确认基线是绿的；
- 改完补测试，尤其是协议解析边界（休眠、正在唤醒、电量越界、命令不匹配）；
- 不要改 `LICENSING.md` / `ATTRIBUTION.md` 里的来源说明。

## 本地运行

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m unittest discover -p "test_*.py" -v
.venv\Scripts\python chargedock.py --data-dir .\dev-data    # 直接跑界面
.venv\Scripts\python chargedock.py --once                    # 只看一次 JSON 读数
```

打包：`.venv\Scripts\python -m PyInstaller --noconfirm ChargeDock.spec`

不要提交个人设置（`settings.json`）、诊断中的设备序列号或开发环境凭据。
