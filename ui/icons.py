"""统一线性图标库：stroke 风格 SVG，可指定颜色与尺寸，保持图标风格一致。"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# stroke 线性图标路径（viewBox 0 0 24 24）
ICON_PATHS: dict[str, str] = {
    "home": '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    "list": '<path d="M4 6h16M4 12h16M4 18h10"/>',
    "heart": '<path d="M12 20s-7-4.6-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.4-7 10-7 10z"/>',
    "heart_filled": '<path d="M12 20s-7-4.6-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.4-7 10-7 10z" fill="currentColor" stroke="none"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
    "artist": '<circle cx="9" cy="8" r="3"/><path d="M3 20c1-3 3-4 6-4s5 1 6 4"/><circle cx="17" cy="9" r="2.5"/><path d="M16 14c2.5.4 4 1.6 5 3.5"/>',
    "album": '<rect x="3" y="5" width="8" height="7" rx="2"/><rect x="13" y="5" width="8" height="7" rx="2"/><rect x="3" y="14" width="8" height="5" rx="2"/><rect x="13" y="14" width="8" height="5" rx="2"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.3 1a7 7 0 0 0-2-1.2L14.2 3h-4L9.4 5.6a7 7 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.6A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.6 2 3.4 2.3-1a7 7 0 0 0 2 1.2L10.2 21h4l.4-2.6a7 7 0 0 0 2-1.2l2.3 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2z"/>',
    "note": '<path d="M9 18V6l10-2v12"/><circle cx="7" cy="18" r="2.5"/><circle cx="17" cy="16" r="2.5"/>',
    "play": '<path d="M7 5l11 7-11 7z"/>',
    "pause": '<path d="M9.5 6v12M14.5 6v12"/>',
    "prev": '<path d="M11 6l-6 6 6 6z"/><path d="M19 6l-6 6 6 6z"/>',
    "next": '<path d="M13 6l6 6-6 6z"/><path d="M5 6l6 6-6 6z"/>',
    "prev_line": '<path d="M6 6v12"/><path d="M18 6l-9 6 9 6z"/>',
    "next_line": '<path d="M18 6v12"/><path d="M6 6l9 6-9 6z"/>',
    # —— 播放栏圆润可爱风（QQ音乐式：填充+粗圆头）——
    "shuffle": '<path d="M16.5 3.5h4.5v4.5" stroke-width="2.2"/><path d="M21 3.5L3.5 21" stroke-width="2"/><path d="M21 16v4.5h-4.5" stroke-width="2.2"/><path d="M14.5 14.5L21 21" stroke-width="2"/><path d="M3.5 3.5L6.5 6.5" stroke-width="2"/><path d="M9.5 9.5l2 2" stroke-width="2"/>',
    "repeat": '<path d="M16.5 3l4 3.2-4 3.2" stroke-width="2.2"/><path d="M20.5 6.2H8a4.5 4.5 0 0 0-4.5 4.5V11" stroke-width="2.2"/><path d="M7.5 21l-4-3.2 4-3.2" stroke-width="2.2"/><path d="M3.5 17.8H16a4.5 4.5 0 0 0 4.5-4.5v-.3" stroke-width="2.2"/>',
    "repeat_one": '<path d="M16.5 3l4 3.2-4 3.2" stroke-width="2.2"/><path d="M20.5 6.2H8a4.5 4.5 0 0 0-4.5 4.5" stroke-width="2.2"/><path d="M7.5 21l-4-3.2 4-3.2" stroke-width="2.2"/><path d="M3.5 17.8H16a4.5 4.5 0 0 0 4.5-4.5" stroke-width="2.2"/><circle cx="12" cy="11.5" r="1.6" fill="@FILL@" stroke="none"/>',
    "order": '<path d="M4 6.5h16M4 12h16M4 17.5h10"/>',
    "volume": '<path d="M4 9.5v5h3l4.5 3.4V6.1L7 9.5H4z" fill="@FILL@" stroke="none"/><path d="M14.2 9.3a4.2 4.2 0 0 1 0 5.4" stroke-width="2.2"/><path d="M16.4 6.9a8 8 0 0 1 0 10.2" stroke-width="2"/>',
    "mute": '<path d="M4 9.5v5h3l4.5 3.4V6.1L7 9.5H4z" fill="@FILL@" stroke="none"/><path d="M15.5 9.5l5 5M20.5 9.5l-5 5" stroke-width="2.2"/>',
    "lyrics": '<path d="M3.5 8h17M3.5 12h17M3.5 16h9.5" stroke-width="2.2"/>',
    "refresh": '<path d="M20 11.5a8.5 8.5 0 1 0-2.2 5.8" stroke-width="2.2"/><path d="M20 5v6.5h-6.5" stroke-width="2.4"/>',
    "edit": '<path d="M4.5 19.5l1-4 9.2-9.2a2.1 2.1 0 0 1 3 3L8.5 18.5l-4 1z" stroke-width="2"/><path d="M13.3 7.7l3 3" stroke-width="2"/>',
    "queue": '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 12h8"/>',
    "back": '<path d="M15 5l-7 7 7 7"/>',
    "add": '<path d="M12 5v14M5 12h14"/>',
    "chevron_down": '<path d="M6 9l6 6 6-6"/>',
    "refresh": '<path d="M20 11A8 8 0 1 0 18.3 16"/><path d="M20 5v6h-6"/>',
    "check": '<path d="M4 12l5 5L20 6"/>',
    "maximize": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "minimize": '<path d="M5 12h14"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
}


def _render_pixmap(name: str, color: str, px: int, stroke: float = 1.9) -> QPixmap:
    paths = ICON_PATHS.get(name, ICON_PATHS["note"]).replace("@FILL@", color)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{px}" height="{px}">'
        f'<g fill="none" stroke="{color}" stroke-width="{stroke}" '
        f'stroke-linecap="round" stroke-linejoin="round">{paths}</g></svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pix = QPixmap(px, px)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    return pix


def icon(name: str, color: str, px: int = 22, stroke: float = 1.9) -> QIcon:
    return QIcon(_render_pixmap(name, color, px, stroke))


def pixmap(name: str, color: str, px: int = 22, stroke: float = 1.9) -> QPixmap:
    return _render_pixmap(name, color, px, stroke)
