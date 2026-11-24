# 奥丁（Glorious）无线鼠标电量适配说明

本分支在 `电量岛 · ChargeDock` 上把电量来源换成 **Glorious / 奥丁 无线鼠标**：整个程序只读这一条
供应商 HID 协议，ROG 与赛睿耳机的协议已从代码中删除。

## 实机验证结果

| 项目 | 值 |
| --- | --- |
| 硬件 | Glorious Model O- Wireless（2.4G 接收器） |
| 接口 | `VID 0x258A` / `PID 0x2024`，产品名 `Model O- Wireless`，厂商 `Glorious` |
| 集合 | Usage Page `0xFFFF` / Usage `0x0000`，Feature 报告长度 **65**（只支持 Feature，Input/Output 为 0） |
| 实测查询 | TX `00 00 00 00 02 02 00 83 …` → RX `00 A1 00 02 02 00 83 00 14 …` = **20%，未充电** |

`0x258A` 是联阳（SinoWealth）的供应商 VID，很多品牌共用，所以只按 **VID + PID + Feature 长度 65**
匹配，不按产品名判断，也不对未知 PID 轮流试写。

## 协议

```
请求：65 字节 Feature Report（report id 0）
      [3]=0x02  [4]=0x02  [6]=0x83，其余为 0
回复：同一 report id
      [1]=状态  [6]=0x83 回显  [7]=充电中(1)  [8]=电量百分比(0–100)
状态：0xA1 在线  0xA4 休眠  0xA0 正在唤醒  其他 = 不可达
时序：发完等 50 ms 再读；遇到 0xA0 再等 400 ms 重问一次
```

支持的 PID（无线为接收器，有线为直连，直连一律按充电中处理）：

| 型号 | 无线 | 有线 |
| --- | --- | --- |
| Model O | 0x2022 | 0x2011 |
| Model O- | **0x2024** | 0x2013 |
| Model D | 0x2023 | 0x2012 |
| Model D- | 0x2025 | 0x2014 |

新增型号只需在 `glorious_proto.DEVICES` 里加一行 `DeviceSpec(title, pid, wired)`；
协议相同的 Hitscan / G-Wolves / WLMouse 等品牌如果 VID 也落在自家供应商号段，需要另外扩
`match_device()` 的白名单，不能因为“协议一样”就直接放进 258A 表里。

## 代码位置

| 文件 | 内容 |
| --- | --- |
| `glorious_proto.py` | 协议实现：报文构造、回复解析、读取锁、唤醒重试 |
| `core.py` | `MODELS`（只有 mouse）、`read_device()`、提醒策略、配置校验 |
| `ui.py` | 鼠标卡片副标题、托盘数字图标、任务栏浮标、设置页开关 |
| `locales/*.json` | 四语言文案（中文原文作 msgid） |
| `glorious_probe.py` | 本机诊断探针：打印接口能力表并 hexdump 一次真实查询 |
| `test_glorious.py` | 匹配、报文、解析、唤醒重试、缺失设备的单元测试 |

设备只有一类（`core.MODELS == {"mouse": …}`），删掉 ROG/耳机后不再需要“显示哪几类设备”的
开关，卡片是否出现在只看 `Reading.present`。

## 本地使用

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m unittest discover -p "test_*.py" -v
.venv\Scripts\python chargedock.py --data-dir .\dev-data    # 直接跑界面
.venv\Scripts\python chargedock.py --once                    # 只看一次 JSON 读数
```

诊断（不动设置，只发只读电量命令）：

```powershell
.venv\Scripts\python glorious_probe.py           # 探测 258A 接口
.venv\Scripts\python glorious_probe.py --all     # 顺带列出所有 HID 接口
```

打包：

```powershell
.venv\Scripts\python -m PyInstaller --noconfirm ChargeDock.spec
```

## 常驻电量显示

两个开关都在设置页，默认都开：

| 开关 | 位置 | 说明 |
| --- | --- | --- |
| `tray_percent` 托盘图标显示百分比 | **托盘图标本身** | 图标画成圆角数字（多尺寸 16–48px，按 DPI 自动选），低于阈值转红，未知电量显示 `—` |
| `badge` 右下角数字浮标 | **任务栏条内部**，通知区域左侧 | 独立顶层小窗，`WA_TranslucentBackground` + 自绘圆角底，点左键展开电量窗口、右键出托盘菜单、滚轮立即刷新 |

定位逻辑（`ui.taskbar_geometry()` / `ui.badge_position()`）：

- `FindWindowW("Shell_TrayWnd")` 取任务栏矩形，`FindWindowExW(..., "TrayNotifyWnd", ...)` 取通知区域（时钟 + 托盘图标）
  的左边界，浮标贴在它左边 8px、任务栏内垂直居中。
- 实测本机：任务栏 `(0,1392) 2560×48`，通知区域左边界 `2275`，浮标落点 `(2215,1403) 52×26`，
  完全落在任务栏条内、距托盘区 8px。
- 竖排任务栏按条内居中、贴底处理；任务栏自动隐藏时退回可用区域右下角。
- 每 3 秒重贴一次并 `raise_()`：托盘图标增减会推动通知区域边界，而且任务栏本身也是置顶窗口，
  点过任务栏后要把浮标重新压上去。
- 前台窗口铺满整屏（游戏 / 全屏视频）时浮标自动让位，不在画面上乱飘；退回桌面就回来。
- 浮标不抢焦点（`WA_ShowWithoutActivating` + `WindowDoesNotAcceptFocus`），不进 Alt-Tab。
- 电量窗口展开时浮标自动让开，收起后回来（`eventFilter` 监听面板 Show/Hide）。
- Windows 11 可能把托盘图标塞进 `^` 溢出区，浮标不受影响；想把托盘数字也拖出来常显，
  把图标从 `^` 拖到任务栏即可（系统按应用记忆）。
- 低电量判定沿用鼠标提醒的开关和阈值；提醒关掉时浮标只显示数字、不变红。

## 设备没插的时候

`Reading.present` 只有真的匹配到接收器/USB 接口才是 `True`。

- `glorious_proto.read_device()` 在一个匹配接口都没有时返回 `None`，不再编造占位读数
  （上游曾用 ROG 的占位读数，于是没插接收器时界面显示成 ROG 鼠标）。
- `core.read_device()` 拿到 `None` 时给出 `present=False`，标题仍是「奥丁 Model O-」。
- 界面只显示 `present` 为真的卡片；一个都没有时只留一行“未检测到设备 · 插入接收器后会自动出现”，
  托盘图标回到应用图标，任务栏浮标隐藏。
- 枚举 HID 失败这类“不知道插没插”的异常仍然按 `present=True` 处理，卡片保留并显示错误，
  避免界面闪一下消失。

## 已知限制

- 只走 2.4G 接收器或有线直连；蓝牙模式没有这条供应商接口，读不到电量。
- 鼠标长时间休眠时接收器会回 `0xA4`，界面显示“休眠或未连接”，动一下鼠标再刷新即可。
- 刚唤醒瞬间电量可能返回 0，这里按 1% 处理，不当作电池耗尽，也不触发低电量提醒。
- 协议实现参考公开的逆向成果（见 `ATTRIBUTION.md`），只发送电量查询，不写任何设置。

## 来源

- korkje/mow — `src/report/battery.rs`、`src/util/devices.rs`（Glorious Core 抓包逆向，含电池报告）
- krisgfx9/Wireless-Device-Battery-Monitor — `src/drivers/glorious.cpp`（Windows 端同协议，含状态码与 65 字节长度判据）
- 上述两个项目的协议结论在本分支上用 `glorious_probe.py` 在本机 Model O- Wireless 上复核过。
