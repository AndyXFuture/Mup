"""通用新拟态控件库：卡片、按钮、滑块、输入框、封面、虚拟化歌曲列表、歌词视图。"""
from __future__ import annotations

import bisect
import math

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QFrame,
    QLineEdit,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from app.subsonic_client import LyricLine
from ui import icons, theme


# ---------- 绘制辅助 ----------
def _q(c) -> QColor:
    return c if isinstance(c, QColor) else QColor(c)


def _rounded_path(rect: QRectF, radius: float):
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def _paint_raised_shadow(p: QPainter, r: QRectF, radius: float, pal: dict, base: QColor) -> None:
    """外凸卡片：多层偏移的暗/亮阴影 + 底色。强度随主题阴影基础透明度自适应（深色模式更收敛）。"""
    dark = _q(pal["shadow_dark"])
    light = _q(pal["shadow_light"])
    dark_max = dark.alpha()
    light_max = light.alpha()
    offsets = ((6, 7), (5, 6), (4, 5), (3, 4), (2, 3), (1, 2))
    factors = (0.28, 0.42, 0.56, 0.70, 0.85, 1.0)
    # 右下暗影（由外到内递减透明度，近似模糊）
    for (ox, oy), f in zip(offsets, factors):
        c = QColor(dark)
        c.setAlpha(int(dark_max * f))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(r.translated(ox, oy), radius, radius)
    # 左上高光
    for (ox, oy), f in zip(offsets, factors):
        c = QColor(light)
        c.setAlpha(int(light_max * f))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(r.translated(-ox, -oy), radius, radius)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(base)
    p.drawRoundedRect(r, radius, radius)


def _paint_inset_shadow(p: QPainter, r: QRectF, radius: float, pal: dict) -> None:
    """内凹卡片：顶部内阴影 + 底部内高光（模拟凹槽）。"""
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_q(pal["press"]))
    p.drawRoundedRect(r, radius, radius)
    dark = _q(pal["shadow_dark"])
    dark.setAlpha(int(dark.alpha() * 0.8))
    light = _q(pal["shadow_light"])
    light.setAlpha(int(light.alpha() * 0.8))
    clip = _rounded_path(r, radius)
    p.save()
    p.setClipPath(clip)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(dark)
    p.drawRoundedRect(r.translated(0, -5), radius, radius)  # 顶部暗带
    p.setBrush(light)
    p.drawRoundedRect(r.translated(0, 5), radius, radius)   # 底部亮带
    p.restore()
    # 收边描边
    p.setPen(QPen(_q(pal["border"]), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)


def paint_raised(p: QPainter, rect: QRectF, radius: float, fill: str | None = None, inset: bool = False) -> None:
    """绘制新拟态外凸/内凹表面。"""
    pal = theme.CURRENT
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    r = QRectF(rect)
    base = _q(fill) if fill else _q(pal["raise"])
    if inset:
        _paint_inset_shadow(p, r, radius, pal)
    else:
        _paint_raised_shadow(p, r, radius, pal, base)


# ---------- 卡片 ----------
class NeuFrame(QFrame):
    """新拟态容器：raised 卡片或 inset 凹槽。内部预留 shadow margin 存放阴影。"""

    def __init__(self, parent=None, radius: float = 20.0, inset: bool = False, fill: str | None = None,
                 margin: int = 7) -> None:
        super().__init__(parent)
        self._radius = radius
        self._inset = inset
        self._fill = fill
        self._margin = margin
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def set_fill(self, fill: str | None) -> None:
        self._fill = fill
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        m = self._margin
        r = QRectF(self.rect()).adjusted(m, m, -m, -m)
        paint_raised(p, r, self._radius, self._fill, self._inset)


# ---------- 文字按钮 ----------
class NeuButton(QAbstractButton):
    """新拟态文字按钮：raised，hover 提亮，按下位移。"""

    def __init__(self, text: str = "", parent=None, accent: bool = False, ghost: bool = False) -> None:
        super().__init__(parent)
        self.setText(text)
        self.accent = accent
        self.ghost = ghost
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(36)

    def paintEvent(self, event: QPaintEvent) -> None:
        pal = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        pressed = self.isDown()
        hovered = self.underMouse() and not pressed
        if pressed:
            paint_raised(p, r, 14, pal["press"], inset=True)
        elif self.accent or hovered:
            paint_raised(p, r, 14, pal["primary_soft"])
        else:
            paint_raised(p, r, 14, pal["raise"])
        color = QColor(pal["primary_text"]) if (self.accent or hovered) else QColor(pal["text"])
        f = self.font()
        f.setPointSizeF(10)
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        p.setPen(color)
        off = 2 if pressed else 0
        p.drawText(r.translated(off, off), Qt.AlignmentFlag.AlignCenter, self.text())


# ---------- 图标按钮（纯色扁平） ----------
class NeuIconButton(QAbstractButton):
    """纯色扁平图标按钮：常态 muted，hover primary，按下向右下位移。"""

    def __init__(self, icon_name: str, parent=None, px: int = 22) -> None:
        super().__init__(parent)
        self.icon_name = icon_name
        self.px = px
        self.accent_color: str | None = None  # 激活色（如收藏红）
        self.activated = False
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_activated(self, on: bool, color: str | None = None) -> None:
        self.activated = on
        if color:
            self.accent_color = color
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        pal = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.activated and self.accent_color:
            color = QColor(self.accent_color)
        elif self.underMouse() or self.isDown():
            color = QColor(pal["primary"])
        else:
            color = QColor(pal["text_muted"])
        off = 2 if self.isDown() else 0
        pix = icons.pixmap(self.icon_name, color.name(), self.px)
        p.drawPixmap((self.width() - self.px) // 2 + off, (self.height() - self.px) // 2 + off, pix)


# ---------- 播放键 ----------
class SkipButton(QAbstractButton):
    """上一曲/下一曲：实心三角形 + 圆角竖条（与 NeuIconButton 同尺寸同交互）。"""

    def __init__(self, direction: int, parent=None, px: int = 19) -> None:
        super().__init__(parent)
        self.direction = direction  # -1 上一曲（竖条在左、三角指左）；+1 下一曲
        self.px = px
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event: QPaintEvent) -> None:
        pal = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.underMouse() or self.isDown():
            color = QColor(pal["primary"])
        else:
            color = QColor(pal["text_muted"])
        off = 2 if self.isDown() else 0
        cx = self.width() / 2 + off
        cy = self.height() / 2 + off
        s = self.px
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        bar_w = s * 0.20
        bar_h = s * 0.94
        tri_h = s * 0.62
        if self.direction < 0:
            # 上一曲：竖条在左，三角尖朝左并紧贴竖条右侧
            bar_x = cx - s * 0.40 - bar_w / 2
            tip_x = bar_x + bar_w            # 尖角顶点落在竖条右缘（与竖条重合）
        else:
            # 下一曲：竖条在右，三角尖朝右并紧贴竖条左侧
            bar_x = cx + s * 0.40 - bar_w / 2
            tip_x = bar_x                    # 尖角顶点落在竖条左缘（与竖条重合）
        p.drawRoundedRect(QRectF(bar_x, cy - bar_h / 2, bar_w, bar_h), bar_w / 2, bar_w / 2)
        path = QPainterPath()
        if self.direction < 0:
            # 上一曲：尖端朝左（顶点落在竖条右缘）
            path.moveTo(tip_x, cy)
            path.lineTo(tip_x + tri_h * 0.62, cy - tri_h * 0.55)
            path.lineTo(tip_x + tri_h * 0.62, cy + tri_h * 0.55)
        else:
            # 下一曲：尖端朝右（顶点落在竖条左缘）
            path.moveTo(tip_x, cy)
            path.lineTo(tip_x - tri_h * 0.62, cy - tri_h * 0.55)
            path.lineTo(tip_x - tri_h * 0.62, cy + tri_h * 0.55)
        path.closeSubpath()
        # 圆角三角：同色圆头/圆角描边让顶点圆润（与填充重叠）
        pen = QPen(color, max(1.6, s * 0.13))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(color)
        p.drawPath(path)


class PlayButton(QAbstractButton):
    """实心圆形播放/暂停键。"""

    playing = False

    def __init__(self, parent=None, px: int = 44) -> None:
        super().__init__(parent)
        self.px = px
        self.setFixedSize(px, px)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_playing(self, on: bool) -> None:
        self.playing = on
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        pal = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        paint_raised(p, r, r.width() / 2, pal["primary"])
        if self.isDown():
            p.translate(2, 2)
        c = _q(pal["on_primary"])
        cx = self.width() / 2
        cy = self.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        if self.playing:
            # 暂停：两条圆角竖条（略小）
            bw = self.px * 0.10
            gap = self.px * 0.14
            h = self.px * 0.40
            for dx in (-gap / 2 - bw / 2, gap / 2 + bw / 2):
                p.drawRoundedRect(QRectF(cx + dx - bw / 2, cy - h / 2, bw, h), bw / 2, bw / 2)
        else:
            # 播放：实心圆角三角形（略小）
            size = self.px * 0.36
            path = QPainterPath()
            path.moveTo(cx - size * 0.34, cy - size * 0.56)
            path.lineTo(cx - size * 0.34, cy + size * 0.56)
            path.lineTo(cx + size * 0.66, cy)
            path.closeSubpath()
            pen = QPen(c, size * 0.22, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(c)
            p.drawPath(path)


# ---------- 自定义滑块（进度/音量） ----------
class HoverSlider(QWidget):
    """圆角矩形轨道，悬浮时浮现圆形拖动点。

    hoverValueChanged：悬浮（未按下）时发出鼠标所在位置对应的数值，用于进度条实时预览。
    """

    valueChanged = Signal(int)
    hoverValueChanged = Signal(int)
    hoverEnded = Signal()

    def __init__(self, minimum: int = 0, maximum: int = 100, value: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._min = minimum
        self._max = max(maximum, minimum + 1)
        self._val = value
        self._hover = False
        self._drag = False
        self.setMinimumHeight(18)
        self.setMaximumHeight(18)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_range(self, minimum: int, maximum: int) -> None:
        self._min = minimum
        self._max = max(maximum, minimum + 1)
        self._val = max(minimum, min(maximum, self._val))
        self.update()

    def set_value(self, v: int, notify: bool = True) -> None:
        v = max(self._min, min(self._max, int(v)))
        if v == self._val:
            return
        self._val = v
        if notify:
            self.valueChanged.emit(v)
        self.update()

    def value(self) -> int:
        return self._val

    def _ratio(self) -> float:
        return (self._val - self._min) / (self._max - self._min)

    def _value_from_x(self, x: float) -> int:
        w = max(1, self.width())
        ratio = max(0.0, min(1.0, x / w))
        return self._min + round(ratio * (self._max - self._min))

    def _set_from_x(self, x: float) -> None:
        self.set_value(self._value_from_x(x))

    def paintEvent(self, event: QPaintEvent) -> None:
        pal = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        h = self.height()
        track_h = 6
        ty = (h - track_h) / 2
        track = QRectF(1, ty, self.width() - 2, track_h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_q(pal["press"]))
        p.drawRoundedRect(track, track_h / 2, track_h / 2)
        ratio = self._ratio()
        if ratio > 0:
            fill = QRectF(track.left(), ty, track.width() * ratio, track_h)
            p.setBrush(_q(pal["primary"]))
            p.drawRoundedRect(fill, track_h / 2, track_h / 2)
        if self._hover or self._drag:
            cx = track.left() + track.width() * ratio
            cy = h / 2
            p.setBrush(_q(pal["primary"]))
            p.drawEllipse(QRectF(cx - 6.5, cy - 6.5, 13, 13))

    def mousePressEvent(self, event) -> None:
        self._drag = True
        self._set_from_x(event.position().x())
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag and event.buttons() & Qt.MouseButton.LeftButton:
            self._set_from_x(event.position().x())
            event.accept()
        else:
            self._hover = True
            self.hoverValueChanged.emit(self._value_from_x(event.position().x()))
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        self._drag = False
        self.update()
        event.accept()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.hoverValueChanged.emit(self._value_from_x(self.mapFromGlobal(self.cursor().pos()).x()))
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.hoverEnded.emit()
        self.update()
        super().leaveEvent(event)


# ---------- 输入框 ----------
class NeuLineEdit(QLineEdit):
    """内凹新拟态输入框。"""

    def __init__(self, text: str = "", placeholder: str = "", password: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setPlaceholderText(placeholder)
        if password:
            self.setEchoMode(QLineEdit.EchoMode.Password)
        self.setMinimumHeight(40)
        self.setFrame(False)
        # 文本/占位符左侧留白，避免太贴边
        self.setTextMargins(14, 0, 12, 0)

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        paint_raised(p, r, 12, inset=True)
        super().paintEvent(event)


# ---------- 封面 ----------
class CoverArt(QWidget):
    """圆角封面。可选：悬浮变暗 + 中央切换图标；圆形/方形显示切换。"""

    clicked = Signal()

    def __init__(self, parent=None, radius: float = 12.0) -> None:
        super().__init__(parent)
        self._pix: QPixmap | None = None
        self._radius = radius
        self._round = False
        self._hover = False
        self._toggle = False  # 悬浮时显示切换图标
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_pixmap(self, pix: QPixmap | None) -> None:
        self._pix = pix
        self.update()

    def set_round(self, on: bool) -> None:
        self._round = on
        self.update()

    def is_round(self) -> bool:
        return self._round

    def set_toggle_hint(self, on: bool) -> None:
        self._toggle = on

    def paintEvent(self, event: QPaintEvent) -> None:
        pal = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        path = _rounded_path(r, self._radius if not self._round else r.width() / 2)
        if self._pix:
            p.save()
            p.setClipPath(path)
            p.drawPixmap(r.toRect(), self._pix)
            p.restore()
        else:
            grad = QLinearGradient(r.topLeft(), r.bottomRight())
            grad.setColorAt(0.0, QColor("#B9BDF5"))
            grad.setColorAt(1.0, QColor("#6F73E8"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawPath(path)
            ip = icons.pixmap("note", "#FFFFFF", 34, stroke=1.5)
            p.drawPixmap(int((self.width() - 34) / 2), int((self.height() - 34) / 2), ip)
        if self._hover and self._toggle:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 90))
            p.drawPath(path)
            if self._round:
                ico = icons.pixmap("album", pal["on_primary"], 30, stroke=1.8)
            else:
                ico = icons.pixmap("note", pal["on_primary"], 30, stroke=1.8)
            p.drawPixmap(int((self.width() - 30) / 2), int((self.height() - 30) / 2), ico)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit()
        event.accept()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)


# ---------- 虚拟化歌曲列表 ----------
class SongModel(QAbstractListModel):
    def __init__(self, songs=None, parent=None) -> None:
        super().__init__(parent)
        self._songs: list = songs or []

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._songs)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._songs)):
            return None
        song = self._songs[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return song
        return None

    def set_songs(self, songs) -> None:
        self.beginResetModel()
        self._songs = list(songs)
        self.endResetModel()

    def song(self, row: int):
        return self._songs[row] if 0 <= row < len(self._songs) else None


# 歌曲行几何常量（SongDelegate / SortHeader / library_page 命中检测共用）
SONG_ROW_H = 64          # 行高
SONG_COVER_X = 8         # 封面左偏移
SONG_COVER = 48          # 封面尺寸
SONG_TITLE_H = 19        # 歌名高度
SONG_ARTIST_H = 15       # 歌手高度
SONG_TEXT_GAP = 5        # 歌名/歌手间距


def song_cols(x0: int, w: int) -> tuple[int, int, int, int, int, int]:
    """歌曲行三列几何：歌名/歌手列自适应，专辑/时长固定（时长左对齐）。

    返回 (c0x, c0w, alb_x, alb_w, dur_x, dur_w)，与 SongDelegate / SortHeader 共用。
    """
    dur_w = 64
    alb_w = 220
    dur_x = x0 + w - dur_w
    alb_x = dur_x - alb_w
    c0x = x0 + SONG_COVER_X + SONG_COVER + 12   # 封面(左8 + 48) + 间距12
    c0w = alb_x - c0x
    return c0x, c0w, alb_x, alb_w, dur_x, dur_w


def song_zone(rect: QRect, x: float, y: float, artist_text: str = "") -> str:
    """判断点击/悬浮落在歌曲行的哪个区域：cover / artist / album / none。

    artist 区域收窄到文本实际宽度，避免误触整列。
    """
    cs = SONG_COVER
    h = rect.height()
    cover_rect = QRect(rect.left() + SONG_COVER_X, rect.top() + (h - cs) // 2, cs, cs)
    if cover_rect.contains(int(x), int(y)):
        return "cover"
    c0x, c0w, alb_x, alb_w, dur_x, dur_w = song_cols(rect.left(), rect.width())
    block_h = SONG_TITLE_H + SONG_TEXT_GAP + SONG_ARTIST_H
    block_top = cover_rect.top() + (cs - block_h) // 2
    artist_rect = QRect(c0x, block_top + SONG_TITLE_H + SONG_TEXT_GAP, c0w, SONG_ARTIST_H)
    if artist_text:
        # 收窄到文本实际宽度（与绘制字体一致）
        fm = QFontMetrics(QFont("Microsoft YaHei UI", 9))
        artist_rect.setWidth(min(c0w, fm.horizontalAdvance(artist_text)))
    if artist_rect.contains(int(x), int(y)):
        return "artist"
    alb_rect = QRect(alb_x, rect.top(), alb_w - 10, h)
    if alb_rect.contains(int(x), int(y)):
        return "album"
    return "none"


class SongDelegate(QStyledItemDelegate):
    """绘制歌曲行：封面/歌名歌手/专辑/时长；当前行内凹高亮。

    封面交互：悬浮变暗 + 实心三角（悬浮封面时变主题色）；点击开始播放变为暂停标志；
    移开鼠标后当前播放行显示四柱律动动画。
    """

    def __init__(self, cover_manager, parent=None) -> None:
        super().__init__(parent)
        self.cover = cover_manager
        self.current_id: str = ""
        self.is_playing: bool = False
        self.hover_row: int = -1      # 鼠标所在行
        self.cover_hover: int = -1    # 鼠标悬浮在封面区域的行（三角变主题色）
        self.artist_hover: int = -1   # 鼠标悬浮在歌手名区域的行（可点击高亮）
        self.album_hover: int = -1    # 鼠标悬浮在专辑名区域的行（可点击高亮）
        self.cover_right = SONG_COVER_X + SONG_COVER  # 封面区域右边界（用于命中检测）

    def set_current(self, song_id: str, playing: bool = False) -> None:
        self.current_id = song_id
        self.is_playing = playing

    @staticmethod
    def _draw_cover_icon(painter: QPainter, cover_rect: QRect, playing: bool, color: str) -> None:
        """封面中央的实心播放/暂停图标（悬浮时显示）。"""
        cx = cover_rect.center().x()
        cy = cover_rect.center().y()
        s = 20.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        if playing:
            # 暂停：两条实心圆角竖条
            bw = s * 0.30
            gap = s * 0.24
            h = s * 0.66
            for dx in (-gap / 2 - bw / 2, gap / 2 + bw / 2):
                painter.drawRoundedRect(QRectF(cx + dx - bw / 2, cy - h / 2, bw, h), bw * 0.35, bw * 0.35)
        else:
            # 播放：实心圆角三角形
            path = QPainterPath()
            path.moveTo(cx - s * 0.32, cy - s * 0.52)
            path.lineTo(cx - s * 0.32, cy + s * 0.52)
            path.lineTo(cx + s * 0.60, cy)
            path.closeSubpath()
            painter.drawPath(path)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        pal = theme.CURRENT
        song = index.data(Qt.ItemDataRole.UserRole)
        if not song:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRect(option.rect)
        row = index.row()
        is_current = song.id == self.current_id
        hovered = row == self.hover_row or bool(option.state & QStyle.StateFlag.State_MouseOver)
        if is_current:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_q(pal["press"]))
            painter.drawRoundedRect(QRectF(r).adjusted(2, 2, -2, -2), 12, 12)
        elif hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_q(pal["primary_soft"]))
            painter.drawRoundedRect(QRectF(r).adjusted(2, 2, -2, -2), 12, 12)

        y = r.top()
        h = r.height()
        # 封面
        cs = SONG_COVER
        cover_rect = QRect(r.left() + SONG_COVER_X, y + (h - cs) // 2, cs, cs)
        pix = self.cover.get(song.cover_id, 120) if self.cover else None
        cover_path = _rounded_path(QRectF(cover_rect), 8)
        painter.save()
        painter.setClipPath(cover_path)
        if pix:
            painter.drawPixmap(cover_rect, pix)
        else:
            grad = QLinearGradient(cover_rect.topLeft(), cover_rect.bottomRight())
            grad.setColorAt(0.0, QColor("#B9BDF5"))
            grad.setColorAt(1.0, QColor("#6F73E8"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)
            painter.drawRect(cover_rect)
            ip = icons.pixmap("note", "#FFFFFF", 22, stroke=1.6)
            painter.drawPixmap(cover_rect.left() + (cs - 22) // 2, cover_rect.top() + (cs - 22) // 2, ip)
        # 封面上的状态叠加
        cover_hit = row == self.cover_hover
        if hovered or cover_hit:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 70))
            painter.drawRect(cover_rect)
            # 行悬浮(非图标)时白色；图标悬浮时主题色；播放/暂停图标一致
            icon_color = _q(pal["primary"]).name() if cover_hit else "#FFFFFF"
            self._draw_cover_icon(painter, cover_rect, is_current and self.is_playing, icon_color)
        elif is_current and self.is_playing:
            self._draw_equalizer(painter, cover_rect, pal)
        painter.restore()

        # 歌名 / 歌手（紧凑、以封面对齐居中，自适应列宽）
        c0x, c0w, alb_x, alb_w, dur_x, dur_w = song_cols(r.left(), r.width())
        block_h = SONG_TITLE_H + SONG_TEXT_GAP + SONG_ARTIST_H
        block_top = cover_rect.top() + (cs - block_h) // 2
        f1 = QFont(option.font)
        f1.setPointSizeF(10.5)
        f1.setWeight(QFont.Weight.Medium if is_current else QFont.Weight.Normal)
        painter.setFont(f1)
        painter.setPen(_q(pal["primary_text"]) if is_current else _q(pal["text"]))
        painter.drawText(QRect(c0x, block_top, c0w, SONG_TITLE_H),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         self._ellipsize(painter, song.title, c0w))
        # 歌手名（可点击：悬浮主题色 + 下划线）
        f2 = QFont(option.font)
        f2.setPointSizeF(9)
        painter.setFont(f2)
        artist_y = block_top + SONG_TITLE_H + SONG_TEXT_GAP
        artist_color = _q(pal["primary_text"]) if row == self.artist_hover else _q(pal["text_muted"])
        painter.setPen(artist_color)
        artist_text = self._ellipsize(painter, song.artist or "", c0w)
        painter.drawText(QRect(c0x, artist_y, c0w, SONG_ARTIST_H),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, artist_text)
        if row == self.artist_hover:
            aw = painter.fontMetrics().horizontalAdvance(artist_text)
            painter.drawLine(c0x, artist_y + SONG_ARTIST_H - 2, c0x + aw, artist_y + SONG_ARTIST_H - 2)
        # 专辑名（可点击：悬浮主题色 + 下划线）
        album_color = _q(pal["primary_text"]) if row == self.album_hover else _q(pal["text_muted"])
        painter.setPen(album_color)
        album_text = self._ellipsize(painter, song.album or "", max(20, alb_w - 10))
        painter.drawText(QRect(alb_x, y, alb_w - 10, h),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, album_text)
        if row == self.album_hover:
            aw = painter.fontMetrics().horizontalAdvance(album_text)
            painter.drawLine(alb_x, y + h - 3, alb_x + aw, y + h - 3)
        # 时长（左对齐）
        painter.setPen(_q(pal["text_muted"]))
        painter.drawText(QRect(dur_x, y, dur_w - 6, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         _fmt_dur(song.duration))
        painter.restore()

    @staticmethod
    def _draw_equalizer(painter: QPainter, cover_rect: QRect, pal) -> None:
        import time

        t = time.time()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 60))
        painter.drawRect(cover_rect)
        painter.setBrush(QColor("#FFFFFF"))
        # 四柱居中、动画放慢（整体约 20x14）
        bars = 4
        gap = 2
        bw = 3.5
        total = bars * bw + (bars - 1) * gap
        x0 = cover_rect.left() + (cover_rect.width() - total) // 2
        max_h = 14
        base = cover_rect.center().y() + max_h / 2
        for i in range(bars):
            height = max(4, int(max_h * (0.35 + 0.65 * abs((t * 1.4 + i * 1.7) % 2 - 1))))
            painter.drawRoundedRect(x0 + i * (bw + gap), base - height, bw, height, 1.5, 1.5)

    @staticmethod
    def _ellipsize(painter: QPainter, text: str, width: int) -> str:
        fm = painter.fontMetrics()
        if fm.horizontalAdvance(text) <= width:
            return text
        return fm.elidedText(text, Qt.TextElideMode.ElideRight, width)

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), SONG_ROW_H)


# ---------- 跑马灯文本（播放栏歌名过长时前后滚动） ----------
class MarqueeLabel(QWidget):
    """文本超出宽度时自动横向滚动（首尾相接循环），否则静态显示。"""

    clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._text = ""
        self._offset = 0.0
        self._color: QColor | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(18)
        self._timer.timeout.connect(self._tick)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def setText(self, text: str) -> None:
        text = text or ""
        if text != self._text:
            self._text = text
            self._offset = 0.0
            self.update()

    def text(self) -> str:
        return self._text

    def set_color(self, color: str) -> None:
        self._color = _q(color)
        self.update()

    def paintEvent(self, event) -> None:
        if not self._text:
            return
        pal = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        f = self.font()
        p.setFont(f)
        p.setPen(self._color if self._color else _q(pal["text"]))
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(self._text)
        if w <= self.width():
            self._timer.stop()
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)
        else:
            if not self._timer.isActive():
                self._timer.start()
            gap = 36
            span = w + gap
            x = int(-self._offset)
            for pos in (x, x + span):
                if pos + w > -20 and pos < self.width() + 20:
                    p.drawText(QRect(pos, 0, w, self.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)

    def _tick(self) -> None:
        fm = self.fontMetrics()
        w = fm.horizontalAdvance(self._text) + 36
        self._offset += 1.2
        if self._offset > w:
            self._offset = 0.0
        self.update()


def _fmt_dur(seconds: int) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _fmt_ms(ms: int) -> str:
    return _fmt_dur(ms // 1000)


# ---------- 简易列表模型（侧边栏歌单等） ----------
class SimpleModel(QAbstractListModel):
    def __init__(self, items=None, parent=None) -> None:
        super().__init__(parent)
        self._items: list = items or []

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        item = self._items[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return item
        return None

    def set_items(self, items) -> None:
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def update_item(self, row: int, item) -> None:
        if 0 <= row < len(self._items):
            self._items[row] = item
            idx = self.index(row, 0)
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.UserRole])


class SimpleDelegate(QStyledItemDelegate):
    """绘制 (主文本, 副文本, 图标名) 行。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.current_key: str = ""

    def set_current(self, key: str) -> None:
        self.current_key = key

    def paint(self, painter: QPainter, option, index) -> None:
        pal = theme.CURRENT
        item = index.data(Qt.ItemDataRole.UserRole)
        if not item:
            return
        key, primary, secondary, icon_name = item
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRect(option.rect)
        active = key == self.current_key
        if active:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_q(pal["press"]))
            painter.drawRoundedRect(QRectF(r).adjusted(2, 2, -2, -2), 10, 10)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_q(pal["primary_soft"]))
            painter.drawRoundedRect(QRectF(r).adjusted(2, 2, -2, -2), 10, 10)
        if icon_name:
            ico_color = _q(pal["primary_text"]) if active else _q(pal["text_muted"])
            ico = icons.pixmap(icon_name, ico_color.name(), 16, stroke=1.8)
            painter.drawPixmap(r.left() + 10, r.top() + (r.height() - 16) // 2, ico)
            tx = r.left() + 36
        else:
            tx = r.left() + 14
        f1 = QFont(option.font)
        f1.setPointSizeF(9.5)
        f1.setWeight(QFont.Weight.Medium if active else QFont.Weight.Normal)
        painter.setFont(f1)
        painter.setPen(_q(pal["primary_text"]) if active else _q(pal["text"]))
        painter.drawText(QRect(tx, r.top() + 4, r.width() - tx - 8, 18),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, primary)
        if secondary:
            f2 = QFont(option.font)
            f2.setPointSizeF(8)
            painter.setFont(f2)
            painter.setPen(_q(pal["text_muted"]))
            painter.drawText(QRect(tx, r.top() + r.height() - 20, r.width() - tx - 8, 16),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, secondary)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), 46)


# ---------- 专辑网格委托 ----------
class AlbumDelegate(QStyledItemDelegate):
    """网格绘制：封面 + 专辑名（两行）+ 歌曲数。tile 尺寸由页面按视口宽度动态计算。"""

    def __init__(self, cover_manager, parent=None) -> None:
        super().__init__(parent)
        self.cover = cover_manager
        self.tile = 108      # 格子宽度（封面 + 文字），随视口自适应
        self.text_h = 30     # 下方文字区高度

    def paint(self, painter: QPainter, option, index) -> None:
        pal = theme.CURRENT
        album = index.data(Qt.ItemDataRole.UserRole)
        if not album:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRect(option.rect)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        # 封面
        cw = max(60, self.tile - 16)
        cover_rect = QRect(r.left() + (r.width() - cw) // 2, r.top() + 4, cw, cw)
        pix = self.cover.get(album.cover_id, 180) if self.cover else None
        if pix:
            painter.save()
            painter.setClipPath(_rounded_path(QRectF(cover_rect), 12))
            painter.drawPixmap(cover_rect, pix)
            painter.restore()
        else:
            grad = QLinearGradient(cover_rect.topLeft(), cover_rect.bottomRight())
            grad.setColorAt(0.0, QColor("#B9BDF5"))
            grad.setColorAt(1.0, QColor("#6F73E8"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)
            painter.drawRoundedRect(QRectF(cover_rect), 12, 12)
            ip = icons.pixmap("note", "#FFFFFF", int(cw * 0.4), stroke=1.6)
            painter.drawPixmap(cover_rect.left() + (cw - ip.width()) // 2, cover_rect.top() + (cw - ip.height()) // 2, ip)
        if hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 30))
            painter.drawRoundedRect(QRectF(cover_rect), 12, 12)
        # 名称（两行省略）
        f = QFont(option.font)
        f.setPointSizeF(9)
        painter.setFont(f)
        painter.setPen(_q(pal["text"]))
        text_rect = QRect(r.left() + 2, cover_rect.bottom() + 4, r.width() - 4, self.text_h - 12)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
                         painter.fontMetrics().elidedText(album.name or "", Qt.TextElideMode.ElideRight, r.width() - 4))
        if album.song_count:
            f2 = QFont(option.font)
            f2.setPointSizeF(8)
            painter.setFont(f2)
            painter.setPen(_q(pal["text_muted"]))
            painter.drawText(QRect(r.left() + 2, text_rect.bottom() - 2, r.width() - 4, 14),
                             Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter, f"{album.song_count} 首")
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(self.tile, self.tile + self.text_h)


# ---------- 歌手列表委托 ----------
class ArtistDelegate(QStyledItemDelegate):
    """行绘制：封面 + 歌手名 + 专辑数；当前选中行高亮。"""

    def __init__(self, cover_manager, parent=None) -> None:
        super().__init__(parent)
        self.cover = cover_manager
        self.current_key: str = ""

    def set_current(self, artist_id: str) -> None:
        self.current_key = artist_id

    def paint(self, painter: QPainter, option, index) -> None:
        pal = theme.CURRENT
        artist = index.data(Qt.ItemDataRole.UserRole)
        if not artist:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRect(option.rect)
        active = artist.id == self.current_key
        if active:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_q(pal["press"]))
            painter.drawRoundedRect(QRectF(r).adjusted(2, 2, -2, -2), 10, 10)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_q(pal["primary_soft"]))
            painter.drawRoundedRect(QRectF(r).adjusted(2, 2, -2, -2), 10, 10)
        cr = QRect(r.left() + 8, r.top() + (r.height() - 40) // 2, 40, 40)
        pix = self.cover.get(artist.cover_id, 120) if self.cover else None
        if pix:
            painter.save()
            painter.setClipPath(_rounded_path(QRectF(cr), 10))
            painter.drawPixmap(cr, pix)
            painter.restore()
        else:
            grad = QLinearGradient(cr.topLeft(), cr.bottomRight())
            grad.setColorAt(0.0, QColor("#C1B8F0"))
            grad.setColorAt(1.0, QColor("#8A7BE8"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)
            painter.drawRoundedRect(QRectF(cr), 10, 10)
            ip = icons.pixmap("artist", "#FFFFFF", 20, stroke=1.7)
            painter.drawPixmap(cr.left() + 10, cr.top() + 10, ip)
        f = QFont(option.font)
        f.setPointSizeF(10)
        f.setWeight(QFont.Weight.Medium)
        painter.setFont(f)
        painter.setPen(_q(pal["primary_text"]) if active else _q(pal["text"]))
        painter.drawText(QRect(cr.right() + 12, r.top(), r.width() - cr.right() - 70, r.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, artist.name or "")
        f2 = QFont(option.font)
        f2.setPointSizeF(8.5)
        painter.setFont(f2)
        painter.setPen(_q(pal["text_muted"]))
        count = f"{artist.album_count} 首" if artist.album_count else ""
        painter.drawText(QRect(r.right() - 78, r.top(), 68, r.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, count)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), 52)


# ---------- 侧边栏歌单委托（带封面） ----------
class PlaylistDelegate(QStyledItemDelegate):
    """绘制 (id, name, cover_id) 歌单行：封面缩略图 + 名称 + 歌曲数。"""

    def __init__(self, cover_manager, parent=None) -> None:
        super().__init__(parent)
        self.cover = cover_manager
        self.current_id: str = ""
        self.local_covers: dict[str, str] = {}   # pid -> 本地封面路径（自定义模式）
        self._local_pix: dict[str, QPixmap] = {}

    def set_local_covers(self, mapping: dict[str, str]) -> None:
        """注入每歌单的本地自定义封面路径（仅 custom 模式的歌单）。"""
        self.local_covers = dict(mapping)
        self._local_pix.clear()

    def _local_pixmap(self, pid: str, size: int) -> QPixmap | None:
        path = self.local_covers.get(pid)
        if not path:
            return None
        pix = self._local_pix.get(pid)
        if pix is None:
            p = QPixmap(path)
            if p.isNull():
                return None
            pix = p.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
            self._local_pix[pid] = pix
        return pix

    def set_current(self, pid: str) -> None:
        self.current_id = pid

    def paint(self, painter: QPainter, option, index) -> None:
        pal = theme.CURRENT
        item = index.data(Qt.ItemDataRole.UserRole)
        if not item:
            return
        pid, name, count, cover_id = item
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRect(option.rect)
        active = pid == self.current_id
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if active:
            # 选中：主题色浅底 + 左侧主题色指示条
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_q(pal["primary_soft"]))
            painter.drawRoundedRect(QRectF(r).adjusted(2, 2, -2, -2), 10, 10)
            painter.setBrush(_q(pal["primary"]))
            painter.drawRoundedRect(QRectF(r.left() + 2, r.top() + 12, 3, r.height() - 24), 1.5, 1.5)
        elif hover:
            # 悬浮：比选中更浅的凹陷底色，与选中明显区分
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_q(pal["press"]))
            painter.drawRoundedRect(QRectF(r).adjusted(2, 2, -2, -2), 10, 10)
        # 封面（自定义本地封面优先，其次服务器封面）
        cs = 36
        cr = QRect(r.left() + 8, r.top() + (r.height() - cs) // 2, cs, cs)
        pix = self._local_pixmap(pid, 120)
        if pix is None:
            pix = self.cover.get(cover_id, 120) if (self.cover and cover_id) else None
        if pix:
            painter.save()
            painter.setClipPath(_rounded_path(QRectF(cr), 8))
            painter.drawPixmap(cr, pix)
            painter.restore()
        else:
            grad = QLinearGradient(cr.topLeft(), cr.bottomRight())
            grad.setColorAt(0.0, QColor("#B9BDF5"))
            grad.setColorAt(1.0, QColor("#6F73E8"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)
            painter.drawRoundedRect(QRectF(cr), 8, 8)
            ip = icons.pixmap("note", "#FFFFFF", 18, stroke=1.7)
            painter.drawPixmap(cr.left() + (cs - 18) // 2, cr.top() + (cs - 18) // 2, ip)
        # 名称
        f = QFont(option.font)
        f.setPointSizeF(9.5)
        f.setWeight(QFont.Weight.Medium if active else QFont.Weight.Normal)
        painter.setFont(f)
        painter.setPen(_q(pal["primary_text"]) if active else _q(pal["text"]))
        tx = cr.right() + 10
        # 右侧：歌曲数量（较暗、无单位）
        count_w = 42
        name_w = r.width() - tx - count_w - 4
        painter.drawText(QRect(tx, r.top(), name_w, r.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         painter.fontMetrics().elidedText(name or "", Qt.TextElideMode.ElideRight, name_w))
        if count:
            fc = QFont(option.font)
            fc.setPointSizeF(8.5)
            painter.setFont(fc)
            cnt = _q(pal["text_muted"])
            cnt.setAlpha(150)
            painter.setPen(cnt)
            painter.drawText(QRect(r.right() - count_w - 8, r.top(), count_w, r.height()),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, str(count))
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), 48)


def make_list_view(model: QAbstractListModel, delegate: QStyledItemDelegate, parent=None) -> QListView:
    view = QListView(parent)
    view.setModel(model)
    view.setItemDelegate(delegate)
    view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setFrameShape(QFrame.Shape.NoFrame)
    view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    view.setMouseTracking(True)
    view.setSpacing(2)
    view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    return view


# ---------- 歌词视图（中心锚定自动滚动） ----------
class LyricsWidget(QWidget):
    """渲染歌词行，当前行居中放大高亮；随时间自动推进。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._lines: list[LyricLine] = []
        self._current = 0
        self.setMinimumHeight(120)

    def set_lines(self, lines: list[LyricLine]) -> None:
        self._lines = lines or []
        self._current = 0
        self.update()

    def set_position(self, ms: int) -> None:
        if not self._lines:
            return
        # 二分查找当前行
        idx = bisect.bisect_right([l.time_ms for l in self._lines if l.time_ms >= 0], ms) - 1
        idx = max(0, min(idx, len(self._lines) - 1))
        if idx != self._current:
            self._current = idx
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        pal = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self._lines:
            p.setFont(_font(10.5))
            p.setPen(_q(pal["text_muted"]))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "暂无歌词")
            return
        n = len(self._lines)
        center_y = self.height() / 2
        step = 36.0
        lx = 6
        # 当前行（白/主题色高亮，居中）
        self._draw_line(p, pal, self._lines[self._current], center_y, 17.0,
                        QColor(pal["primary_text"]), QFont.Weight.DemiBold, lx)
        # 上下各 3 行：越远越淡（渐隐）
        muted = _q(pal["text_muted"])
        for k in range(1, 4):
            alpha = int(230 - k * 55)
            c = QColor(muted)
            c.setAlpha(max(60, alpha))
            up = self._current - k
            if up >= 0:
                self._draw_line(p, pal, self._lines[up], center_y - step * k, 13.0, c, QFont.Weight.Normal, lx)
            down = self._current + k
            if down < n:
                self._draw_line(p, pal, self._lines[down], center_y + step * k, 13.0, c, QFont.Weight.Normal, lx)

    def _draw_line(self, p: QPainter, pal, line: LyricLine, y: float, size: float, color: QColor, weight, lx: int) -> None:
        f = _font(size)
        f.setWeight(weight)
        p.setFont(f)
        p.setPen(color)
        p.drawText(QRect(lx, int(y - 20), self.width() - lx * 2, 40), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, line.text)


def _font(size_pt: float) -> QFont:
    f = QFont("Microsoft YaHei UI")
    f.setPointSizeF(size_pt)
    return f
