"""沉浸页：大封面（圆形/方形切换）+ 滚动歌词 + 播放控制。

布局参考「沉浸页布局参考.png」：
- 封面放左侧垂直居中；歌名/歌手/歌词在右上栏（左对齐，当前行居中）
- 返回按钮左边距 = 上边距；底部为进度条 + 控制栏
歌词经共享 LyricsManager 获取（时间轴歌词优先）。
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMenu, QToolTip, QVBoxLayout, QWidget

from app.cover_manager import CoverManager
from app.lyrics import LyricsManager
from app.player import MODE_LIST, MODE_ORDER, MODE_RANDOM, MODE_SINGLE, Player
from app.subsonic_client import SubsonicClient
from ui import theme
from ui.widgets import CoverArt, HoverSlider, LyricsWidget, NeuIconButton, PlayButton, SkipButton

_MODE_ICONS = {MODE_LIST: "repeat", MODE_RANDOM: "shuffle", MODE_SINGLE: "repeat_one", MODE_ORDER: "order"}
_MODE_NAMES = {MODE_LIST: "列表循环", MODE_RANDOM: "随机播放", MODE_SINGLE: "单曲循环", MODE_ORDER: "顺序播放"}


class PlayerPage(QWidget):
    """沉浸式播放页。"""

    back_requested = Signal()

    def __init__(self, client: SubsonicClient, player: Player, covers: CoverManager,
                 lyrics: LyricsManager, parent=None) -> None:
        super().__init__(parent)
        self.client = client
        self.player = player
        self.covers = covers
        self.lyrics = lyrics
        self._now_cover_id: str = ""
        self._build()
        self._wire()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        # 沉浸页内容区：上边距=左边距（标题栏常显，返回键紧贴其下）
        root.setContentsMargins(12, 12, 12, 16)
        root.setSpacing(0)

        # 顶栏（渐显内容之一）
        self.top_wrap = QWidget()
        top = QHBoxLayout(self.top_wrap)
        top.setContentsMargins(0, 0, 0, 0)
        self.btn_back = NeuIconButton("back", px=18)
        self.btn_back.setFixedSize(36, 36)
        self.btn_back.clicked.connect(self.back_requested.emit)
        top.addWidget(self.btn_back)
        top.addStretch(1)
        root.addWidget(self.top_wrap)

        # 中部：左右各 50% —— 左封面（垂直居中自适应），右歌名/歌手/歌词
        mid = QHBoxLayout()
        mid.setSpacing(40)
        mid.setContentsMargins(4, 12, 4, 8)

        left = QVBoxLayout()
        left.addStretch(1)
        self.big_cover = CoverArt(radius=24)
        self.big_cover.set_toggle_hint(True)
        self.big_cover.clicked.connect(self._toggle_shape)
        left.addWidget(self.big_cover, 0, Qt.AlignmentFlag.AlignHCenter)
        left.addStretch(1)
        mid.addLayout(left, 1)

        self.right_wrap = QWidget()
        right = QVBoxLayout(self.right_wrap)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(6)
        self.song_title = QLabel("未在播放")
        ft = QFont("Microsoft YaHei UI")
        ft.setPointSizeF(17)
        ft.setWeight(QFont.Weight.DemiBold)
        self.song_title.setFont(ft)
        self.song_title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.song_artist = QLabel("")
        fa = QFont("Microsoft YaHei UI")
        fa.setPointSizeF(11)
        self.song_artist.setFont(fa)
        self.song_artist.setStyleSheet(f"color: {theme.CURRENT['text_muted']};")
        self.song_artist.setAlignment(Qt.AlignmentFlag.AlignLeft)
        right.addWidget(self.song_title)
        right.addWidget(self.song_artist)
        right.addSpacing(10)
        self.lyrics_widget = LyricsWidget()
        right.addWidget(self.lyrics_widget, 1)
        mid.addWidget(self.right_wrap, 1)
        root.addLayout(mid, 1)

        # 底部（渐显内容之二）：进度 + 控制栏（与歌单页统一）
        self.bottom_wrap = QWidget()
        bottom = QVBoxLayout(self.bottom_wrap)
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(4)
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.time_cur = QLabel("00:00")
        self.time_tot = QLabel("00:00")
        for lb in (self.time_cur, self.time_tot):
            f = QFont("Microsoft YaHei UI")
            f.setPointSizeF(8.5)
            lb.setFont(f)
            lb.setStyleSheet(f"color: {theme.CURRENT['text_muted']};")
        self.progress = HoverSlider(0, 1000, 0)
        row1.addWidget(self.time_cur)
        row1.addWidget(self.progress, 1)
        row1.addWidget(self.time_tot)
        bottom.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        # 左侧：沉浸页左下不显示歌曲信息，仅占位保持控制居中
        left_info = QWidget()
        li = QHBoxLayout(left_info)
        li.setContentsMargins(0, 0, 0, 0)
        row2.addWidget(left_info, 1)

        # 中间控制：爱心在播放顺序键左侧，其余与歌单页一致
        center = QWidget()
        cl = QHBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)
        self.like_btn = NeuIconButton("heart", px=19)
        self.like_btn.accent_color = theme.CURRENT["danger"]
        self.like_btn.setFixedSize(34, 34)
        self.like_btn.clicked.connect(self._toggle_like)
        self.btn_mode = NeuIconButton("repeat", px=19)
        self.btn_mode.setToolTip("播放模式")
        self.btn_mode.clicked.connect(self._open_mode_menu)
        self.btn_prev = SkipButton(-1, px=19)
        self.btn_prev.setToolTip("上一曲")
        self.btn_prev.clicked.connect(lambda: self.player.prev())
        self.btn_play = PlayButton(px=46)
        self.btn_play.clicked.connect(lambda: self.player.toggle())
        self.btn_next = SkipButton(1, px=19)
        self.btn_next.setToolTip("下一曲")
        self.btn_next.clicked.connect(lambda: self.player.next())
        for w_ in (self.like_btn, self.btn_mode, self.btn_prev, self.btn_play, self.btn_next):
            cl.addWidget(w_)
        row2.addWidget(center)

        # 右侧：音量（右对齐）
        right_info = QWidget()
        ri = QHBoxLayout(right_info)
        ri.setContentsMargins(0, 0, 0, 0)
        ri.addStretch(1)
        self._vol = VolumeSliderBox(self.player)
        ri.addWidget(self._vol)
        row2.addWidget(right_info, 1)
        bottom.addLayout(row2)
        root.addWidget(self.bottom_wrap)

        # 打开时内容渐显（封面由过渡层放大呈现）
        self._apply_fade(0.0)

    def _apply_fade(self, opacity: float) -> None:
        for wgt in (self.top_wrap, self.right_wrap, self.bottom_wrap):
            eff = QGraphicsOpacityEffect(wgt)
            wgt.setGraphicsEffect(eff)
            eff.setOpacity(opacity)

    def fade_in(self) -> None:
        """封面放大动画的同时，其他内容通过渐变出现。"""
        self._apply_fade(0.0)
        for wgt in (self.top_wrap, self.right_wrap, self.bottom_wrap):
            eff = wgt.graphicsEffect()
            anim = QPropertyAnimation(eff, b"opacity", wgt)
            anim.setDuration(420)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _wire(self) -> None:
        self.player.song_changed.connect(self._on_song_changed)
        self.player.state_changed.connect(lambda s: self.btn_play.set_playing(s == "playing"))
        self.player.position_changed.connect(self._on_position)
        self.player.duration_changed.connect(self._on_duration)
        self.player.mode_changed.connect(self._on_mode_changed)
        self.covers.loaded.connect(self._on_cover_loaded)
        self.lyrics.loaded.connect(self._on_lyrics_loaded)
        self.progress.hoverValueChanged.connect(lambda v: self.time_cur.setText(_fmt_ms(v)))
        self.progress.hoverEnded.connect(self._restore_time)

    def _toggle_shape(self) -> None:
        self.big_cover.set_round(not self.big_cover.is_round())

    def _on_song_changed(self, song) -> None:
        self._now_cover_id = song.cover_id
        self.song_title.setText(song.title)
        self.song_artist.setText(song.artist or "")
        self.big_cover.set_pixmap(self.covers.get(song.cover_id, 600))
        self.like_btn.set_activated(False)
        self.like_btn.icon_name = "heart"
        self.like_btn.update()
        self.lyrics_widget.set_lines([])
        self.lyrics.load(song)

    def _on_lyrics_loaded(self, song_id: str, lines) -> None:
        cur = self.player.queue[self.player.current_index] if self.player.queue and self.player.current_index >= 0 else None
        if cur and cur.id == song_id:
            self.lyrics_widget.set_lines(lines)
            self.lyrics_widget.set_position(self.player.media.position())

    def _on_cover_loaded(self, cover_id: str, pix) -> None:
        if cover_id == self._now_cover_id:
            self.big_cover.set_pixmap(pix)

    def _on_position(self, ms: int) -> None:
        self.progress.set_value(ms, notify=False)
        self.time_cur.setText(_fmt_ms(ms))
        self.lyrics_widget.set_position(ms)

    def _restore_time(self) -> None:
        self.time_cur.setText(_fmt_ms(self.player.media.position()))

    def _on_duration(self, ms: int) -> None:
        self.progress.set_range(0, ms)
        self.time_tot.setText(_fmt_ms(ms))

    def _on_mode_changed(self, mode: str) -> None:
        self.btn_mode.icon_name = _MODE_ICONS.get(mode, "repeat")
        self.btn_mode.update()

    def _toggle_like(self) -> None:
        cur = self.player.queue[self.player.current_index] if self.player.queue and self.player.current_index >= 0 else None
        if not cur:
            return
        now_on = not self.like_btn.activated
        self.like_btn.set_activated(now_on)
        self.like_btn.icon_name = "heart_filled" if now_on else "heart"
        self.like_btn.update()
        try:
            self.client.set_starred(cur.id, now_on)
        except Exception:  # noqa: BLE001
            pass

    def _open_mode_menu(self) -> None:
        menu = QMenu(self.btn_mode)
        for mode in (MODE_LIST, MODE_RANDOM, MODE_SINGLE, MODE_ORDER):
            act = menu.addAction(_MODE_NAMES[mode])
            act.setCheckable(True)
            act.setChecked(mode == self.player.mode)
            act.triggered.connect(lambda checked=False, m=mode: self.player.set_mode(m))
        menu.exec(self.btn_mode.mapToGlobal(self.btn_mode.rect().bottomLeft()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # 封面随窗口自适应：参考参考图约 35-42% 视口高度
        s = min(self.height() * 0.42, self.width() * 0.32, 360)
        self.big_cover.setFixedSize(max(120, int(s)), max(120, int(s)))


class VolumeSliderBox(QWidget):
    """沉浸页音量：图标（点击静音/恢复记忆音量）+ 长滑块（悬浮加宽、显示百分比），与歌单页一致。"""

    def __init__(self, player: Player, parent=None) -> None:
        super().__init__(parent)
        self.player = player
        self._last_volume: int = player.volume
        self.setFixedHeight(34)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.icon_btn = NeuIconButton("volume", px=19)
        self.icon_btn.setToolTip("静音 / 恢复音量")
        self.icon_btn.clicked.connect(self._toggle_mute)
        lay.addWidget(self.icon_btn)
        self.slider = HoverSlider(0, 100, player.volume)
        self.slider.setFixedWidth(120)
        self.slider.valueChanged.connect(lambda v: self.player.set_volume(v))
        self.slider.valueChanged.connect(self._show_pct)
        self.slider.hoverValueChanged.connect(self._show_pct)
        self.slider.hoverEnded.connect(self._hide_pct)
        lay.addWidget(self.slider)
        self.setMouseTracking(True)
        from PySide6.QtCore import QPropertyAnimation

        self._anim = QPropertyAnimation(self.slider, b"maximumWidth", self)
        self._anim.setDuration(160)
        self.player.volume_changed.connect(self._on_volume)

    def _show_pct(self, v: int) -> None:
        # 用系统 QToolTip 显示百分比（跟随鼠标位置，跨窗口不裁切）
        QToolTip.showText(
            self.slider.mapToGlobal(QPoint(self.slider.width() // 2, 0)),
            f"{v}%", self.slider,
        )

    def _hide_pct(self) -> None:
        QToolTip.hideText()

    def _on_volume(self, vol: int) -> None:
        if vol > 0:
            self._last_volume = vol
        self.icon_btn.icon_name = "mute" if vol == 0 else "volume"
        self.icon_btn.update()

    def _toggle_mute(self) -> None:
        if self.player.volume > 0:
            self._last_volume = self.player.volume
            self.player.set_volume(0)
        else:
            self.player.set_volume(self._last_volume if self._last_volume > 0 else 60)

    def enterEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self.slider.width())
        self._anim.setEndValue(150)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hide_pct()
        pos = self.mapFromGlobal(self.cursor().pos())
        if not self.rect().contains(pos):
            self._anim.stop()
            self._anim.setStartValue(self.slider.width())
            self._anim.setEndValue(120)
            self._anim.start()
        super().leaveEvent(event)


def _fmt_dur(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _fmt_ms(ms: int) -> str:
    return _fmt_dur(ms // 1000)
