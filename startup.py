"""登录时自动启动（HKCU\\...\\Run）。只写当前用户的一个值，不申请管理员权限。"""
from __future__ import annotations

import subprocess
import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ChargeDock"


def startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            command = winreg.QueryValueEx(key, VALUE_NAME)[0]
        return str(Path(sys.executable)).lower() in str(command).lower()
    except OSError:
        return False


def set_startup(enabled: bool) -> None:
    if enabled and not getattr(sys, "frozen", False):
        raise RuntimeError("请在 EXE 版本中启用开机启动")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            command = subprocess.list2cmdline([sys.executable, "--background"])
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
