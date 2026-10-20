"""开机自启：通过 HKCU\\...\\Run 注册表项实现，可在任务管理器「启动」页直接启用/禁用。"""
from __future__ import annotations

import sys
from pathlib import Path

import winreg

from app.config import APP_DIR, APP_NAME

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command() -> str:
    """当前程序的自启命令行：打包后用 exe 路径，源码运行用 pythonw + main.py。"""
    if getattr(sys, "frozen", False):  # PyInstaller 打包
        return f'"{sys.executable}"'
    pyw = Path(sys.executable).with_name("pythonw.exe")
    py = str(pyw) if pyw.exists() else sys.executable
    return f'"{py}" "{APP_DIR / "main.py"}"'


def is_enabled() -> bool:
    """是否已注册开机自启。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_enabled(on: bool) -> bool:
    """写入/删除开机自启注册表项；成功返回 True。"""
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            if on:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except OSError:
                    pass  # 本来就没有该值
        return True
    except OSError as exc:  # noqa: BLE001
        print(f"[autostart] 设置开机自启失败: {exc}")
        return False
