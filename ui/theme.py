"""主题：基于 DESIGN.md 的 Extruded Light 新拟态，支持浅色/深色切换。

配色（靛蓝主色 + 陶土底）：
- 浅色: clay #E8EAF0, primary #4648d4
- 深色: clay #23262E, primary #6054F1
"""
from __future__ import annotations

import winreg

from PySide6.QtGui import QColor

LIGHT: dict = {
    "clay": "#E8EAF0",
    "raise": "#EEF0F6",
    "press": "#DFE2EC",
    "text": "#181C20",
    "text_muted": "#4B4A5A",
    "primary": "#4648d4",
    "primary_soft": "#E1E0FF",
    "primary_text": "#2F2EBE",
    "on_primary": "#FFFFFF",
    "border": QColor(24, 28, 32, 22),
    "shadow_dark": QColor(154, 166, 191, 120),
    "shadow_light": QColor(255, 255, 255, 210),
    "danger": "#E8463A",
    "ok": "#1DC981",
}

DARK: dict = {
    # 暗色模式：背景/灰色参考 QQ 音乐（近黑炭），主题色保持紫色
    "clay": "#1a1a1a",
    "raise": "#242424",
    "press": "#1e1e1e",
    "text": "#f2f2f2",
    "text_muted": "#9aa0a6",
    "primary": "#6054F1",
    "primary_soft": "#2A2B57",
    "primary_text": "#C7C8FF",
    "on_primary": "#FFFFFF",
    "border": QColor(242, 242, 242, 24),
    "shadow_dark": QColor(0, 0, 0, 160),
    "shadow_light": QColor(255, 255, 255, 46),
    "danger": "#F0705E",
    "ok": "#2BD9A0",
}

_FONT = '"Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif'


CURRENT: dict = LIGHT  # 全局当前调色板，控件在 paint 时读取


def palette(dark: bool) -> dict:
    return DARK if dark else LIGHT


def system_dark() -> bool:
    """读取 Windows 系统深浅色设置（AppsUseLightTheme=0 表示深色）。"""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
    except Exception:  # noqa: BLE001
        return False


def effective_dark(setting: str) -> bool:
    """按配置项解析最终深浅色：'dark'/'light' 强制，'system' 跟随系统。"""
    if setting == "dark":
        return True
    if setting == "light":
        return False
    return system_dark()


def set_theme(dark: bool) -> None:
    global CURRENT
    CURRENT = DARK if dark else LIGHT


def build_qss(p: dict) -> str:
    """基础控件 QSS（新拟态元素由自定义控件绘制）。"""
    # 滚动条：取文字灰，压暗成低透明度 → 较暗 + 圆角
    from PySide6.QtGui import QColor

    _sb = QColor(p["text_muted"])
    _sb.setAlpha(70)
    _sb_h = QColor(p["text_muted"])
    _sb_h.setAlpha(160)
    sb = f"rgba({_sb.red()},{_sb.green()},{_sb.blue()},{_sb.alpha()})"
    sb_h = f"rgba({_sb_h.red()},{_sb_h.green()},{_sb_h.blue()},{_sb_h.alpha()})"
    return f"""
    * {{ font-family: {_FONT}; }}
    QWidget {{ color: {p['text']}; background: transparent; }}
    QToolTip {{
        background: {p['raise']}; color: {p['text']};
        border: none; border-radius: 6px; padding: 4px 8px;
    }}
    QMenu {{
        background: {p['raise']}; color: {p['text']};
        border: none; border-radius: 14px; padding: 6px;
    }}
    QMenu::item {{
        padding: 7px 18px; border-radius: 8px; margin: 1px 2px;
    }}
    QMenu::item:selected {{ background: {p['primary_soft']}; color: {p['primary_text']}; }}
    QMenu::separator {{ height: 1px; background: {p['border'].name()}; margin: 4px 8px; }}
    QScrollBar:vertical {{
        background: transparent; width: 8px; margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {sb}; border-radius: 4px; min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {sb_h}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QScrollBar:horizontal {{
        background: transparent; height: 8px; margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {sb}; border-radius: 4px; min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {sb_h}; }}
    """
