"""主窗口：无边框、自定义标题栏、原生边缘缩放、页面堆叠、沉浸页过渡动画、设置对话框。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import (
    QAbstractNativeEventFilter,
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QRadioButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.config import APP_NAME, APP_VERSION, APP_DIR, RESOURCE_DIR, Config, SHUTDOWN_WAIT_MS
from app import autostart, subsonic_client
from app.cover_manager import CoverManager
from app.hotkeys import GlobalHotkeys
from app.lyrics import LyricsManager
from app.player import Player
from app.subsonic_client import SubsonicClient
from ui import anim, icons, theme
from ui.pages.connect_page import ConnectPage, PingThread
from ui.pages.library_page import LibraryPage
from ui.pages.player_page import PlayerPage
from ui.widgets import NeuButton, NeuIconButton

_APP_ICON = RESOURCE_DIR / "app_icon.ico"


def _brand_pixmap() -> QPixmap:
    """标题栏品牌图标：优先使用 app_icon.ico，缺失时退回音符线性图标。"""
    if _APP_ICON.exists():
        return QIcon(str(_APP_ICON)).pixmap(18, 18)
    return icons.pixmap("note", theme.CURRENT["primary"], 18, stroke=1.8)

WM_NCHITTEST = 0x0084
WM_GETMINMAXINFO = 0x0024
WM_NCLBUTTONDBLCLK = 0x00A3
HTCLIENT = 1
HTCAPTION = 2
HTLEFT, HTRIGHT, HTTOP, HTBOTTOM = 10, 11, 12, 15
HTTOPLEFT, HTTOPRIGHT, HTBOTTOMLEFT, HTBOTTOMRIGHT = 13, 14, 16, 17

TITLE_H = 42
MIN_W, MIN_H = 960, 640
EDGE = 6

# 窗口四周的内阴影（聚焦提示）：默认关闭。
# 它会沿窗口四边压一圈 14px 暗带，正好叠在侧边栏/播放栏外侧的拟态阴影上，
# 视觉上就是「拟态边框变粗/发黑」。历史上多次被误认为拟态阴影退化，故置 0。
FOCUS_GLOW_W = 14
FOCUS_GLOW_ACTIVE = 0.0   # 获得焦点时（0 = 不画）
FOCUS_GLOW_IDLE = 0.0     # 失焦：不画（避免常驻一圈暗边）
FOCUS_GLOW_MS = 160       # 聚焦/失焦过渡时长


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", _POINT),
        ("ptMaxSize", _POINT),
        ("ptMaxPosition", _POINT),
        ("ptMinTrackSize", _POINT),
        ("ptMaxTrackSize", _POINT),
    ]


class _NativeFilter(QAbstractNativeEventFilter):
    """处理 WM_NCHITTEST（无边框拖动/缩放）与 WM_GETMINMAXINFO（最小尺寸）。"""

    def __init__(self, win: "MainWindow") -> None:
        super().__init__()
        self.win = win

    def nativeEventFilter(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_NCHITTEST:
                return (True, self._hit_test(msg))
            if msg.message == WM_GETMINMAXINFO:
                info = ctypes.cast(msg.lParam, ctypes.POINTER(_MINMAXINFO)).contents
                info.ptMinTrackSize.x = MIN_W
                info.ptMinTrackSize.y = MIN_H
                return (True, 0)
            if msg.message == WM_NCLBUTTONDBLCLK:
                # 双击标题栏：最大化 ↔ 窗口化（不依赖系统对无边框窗口的默认行为）
                if msg.wParam == HTCAPTION and self.win.isVisible():
                    self.win._toggle_max()
                    return (True, 0)
        return (False, 0)

    def _hit_test(self, msg) -> int:
        x = msg.lParam & 0xFFFF
        y = (msg.lParam >> 16) & 0xFFFF
        w = self.win
        gx, gy = w.x(), w.y()
        gw, gh = w.width(), w.height()
        for btn in (w.btn_theme, w.btn_settings, w.btn_min, w.btn_max, w.btn_close):
            if btn.isVisible():
                b = btn.geometry()
                if gx + b.x() <= x <= gx + b.x() + b.width() and gy + b.y() <= y <= gy + b.y() + b.height():
                    return HTCLIENT
        if y < gy + TITLE_H:
            return HTCAPTION
        left = x < gx + EDGE
        right = x > gx + gw - EDGE
        top = y < gy + EDGE
        bottom = y > gy + gh - EDGE
        if left and top:
            return HTTOPLEFT
        if right and top:
            return HTTOPRIGHT
        if left and bottom:
            return HTBOTTOMLEFT
        if right and bottom:
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM
        return HTCLIENT


class _TransitionOverlay(QWidget):
    """封面放大/缩小的过渡动画层。"""

    done = Signal()

    def __init__(self, parent: QWidget, pix: QPixmap) -> None:
        super().__init__(parent)
        self._pix = pix
        self._src = QRect()
        self._dst = QRect()
        self._t = 0.0
        self._dim = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(320)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_t", v), self.update()))
        self._anim.finished.connect(self.done.emit)
        self.hide()

    def start(self, src: QRect, dst: QRect, dim: float) -> None:
        self._src = QRect(src)
        self._dst = QRect(dst)
        self._dim = dim
        self._t = 0.0
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(0, 0, 0, int(self._dim * self._t)))
        t = self._t
        x = self._src.x() + (self._dst.x() - self._src.x()) * t
        y = self._src.y() + (self._dst.y() - self._src.y()) * t
        w = self._src.width() + (self._dst.width() - self._src.width()) * t
        h = self._src.height() + (self._dst.height() - self._src.height()) * t
        # 封面放大过程保持圆角（半径在源/目标之间插值，避免短暂直角）
        r_src = 10
        r_dst = 26
        radius = r_src + (r_dst - r_src) * t
        target = QRect(round(x), round(y), round(w), round(h))
        path = QPainterPath()
        path.addRoundedRect(QRectF(target), radius, radius)
        p.save()
        p.setClipPath(path)
        p.drawPixmap(target, self._pix)
        p.restore()


class MainWindow(QWidget):
    """无边框主窗口。"""

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.setWindowTitle("音珏 - Mup")
        self.setMinimumSize(MIN_W, MIN_H)
        # 恢复上次窗口尺寸（无记录时用默认 1080x720）
        try:
            ws = self.config.player.get("window_size") or []
            w_, h_ = int(ws[0]), int(ws[1])
        except (TypeError, ValueError, IndexError):
            w_, h_ = 1080, 720
        if not (MIN_W <= w_ <= 4096 and MIN_H <= h_ <= 4096):
            w_, h_ = 1080, 720
        self.resize(w_, h_)
        # 恢复上次窗口位置（无记录或已移出屏幕时回主屏居中）
        try:
            pos = self.config.player.get("window_pos") or []
            px_, py_ = int(pos[0]), int(pos[1])
        except (TypeError, ValueError, IndexError):
            px_ = py_ = None
        if px_ is not None and self._pos_on_screen(px_, py_, w_, h_):
            self.move(px_, py_)
        else:
            self._center_on_primary(w_, h_)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowMinimizeButtonHint)  # 保留 WS_MINIMIZEBOX，任务栏按钮可最小化
        if _APP_ICON.exists():
            self.setWindowIcon(QIcon(str(_APP_ICON)))

        self.client: SubsonicClient | None = None
        self.covers = CoverManager(None, self)
        self.player = Player(None, self)
        self.lyrics = LyricsManager(None, self)
        self.hotkeys = GlobalHotkeys(self)
        self._auto_ping: PingThread | None = None
        self._overlay: _TransitionOverlay | None = None
        self._system_theme_timer = QTimer(self)
        self._system_theme_timer.setInterval(15000)
        self._system_theme_timer.timeout.connect(self._check_system_theme)

        # 焦点阴影：强度由 _glow_anim 在聚焦/失焦间平滑过渡
        self._focus_factor: float = FOCUS_GLOW_IDLE
        self._glow_anim = QVariantAnimation(self)
        self._glow_anim.setDuration(FOCUS_GLOW_MS)
        self._glow_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._glow_anim.valueChanged.connect(self._on_glow_value)

        self._build_chrome()
        self._build_pages()
        anim.set_reduced_motion(bool((self.config.data.get("ui") or {}).get("reduce_motion")))
        self._apply_theme(theme.effective_dark(self.config.theme))
        self._register_hotkeys()
        self._auto_connect()
        self._build_tray()
        # Ctrl+F：聚焦侧边栏搜索框（沉浸页时自动切回歌单页）
        self._search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self._search_shortcut.activated.connect(self._focus_search)

        self._native = _NativeFilter(self)
        QApplication.instance().installNativeEventFilter(self._native)
        self._system_theme_timer.start()

    # ---------- 窗口位置辅助 ----------
    def _pos_on_screen(self, x: int, y: int, w: int, h: int) -> bool:
        """恢复的位置是否至少与任一屏幕可视区域相交（显示器变化后避免跑到屏幕外）。"""
        r = QRect(x, y, w, h)
        for screen in QGuiApplication.screens():
            if screen.availableGeometry().intersects(r):
                return True
        return False

    def _center_on_primary(self, w: int, h: int) -> None:
        scr = QGuiApplication.primaryScreen()
        if scr:
            ag = scr.availableGeometry()
            self.move(ag.x() + (ag.width() - w) // 2, ag.y() + (ag.height() - h) // 2)

    # ---------- 界面 ----------
    def paintEvent(self, event) -> None:
        """整窗陶土色背景 + 四周内阴影（聚焦时更明显），页面内容叠加其上。"""
        p = QPainter(self)
        rect = self.rect()
        p.fillRect(rect, QColor(theme.CURRENT["clay"]))
        self._paint_focus_glow(p, rect)

    def _paint_focus_glow(self, p: QPainter, rect: QRect) -> None:
        """沿窗口四边画一圈由外向内的阴影，用来一眼看出窗口边界与是否获得焦点。

        画在窗口内侧（无边框 + 整窗铺底色，外侧没有可绘制区域），
        页面子控件背景透明，因此这圈阴影会透出来。
        """
        base = theme.CURRENT["shadow_dark"]
        alpha = int(base.alpha() * self._focus_factor * 0.9)
        if alpha <= 0:
            return
        col = lambda a: QColor(base.red(), base.green(), base.blue(), a)  # noqa: E731
        w = FOCUS_GLOW_W
        r = rect
        bands = (
            (QRect(r.left(), r.top(), r.width(), w), QPoint(r.left(), r.top()), QPoint(r.left(), r.top() + w)),
            (QRect(r.left(), r.bottom() - w + 1, r.width(), w),
             QPoint(r.left(), r.bottom()), QPoint(r.left(), r.bottom() - w)),
            (QRect(r.left(), r.top(), w, r.height()), QPoint(r.left(), r.top()), QPoint(r.left() + w, r.top())),
            (QRect(r.right() - w + 1, r.top(), w, r.height()),
             QPoint(r.right(), r.top()), QPoint(r.right() - w, r.top())),
        )
        p.setPen(Qt.PenStyle.NoPen)
        for band, g0, g1 in bands:
            g = QLinearGradient(g0, g1)
            g.setColorAt(0.0, col(alpha))
            g.setColorAt(1.0, col(0))
            p.fillRect(band, g)

    def _animate_focus_glow(self, active: bool) -> None:
        """聚焦/失焦时平滑过渡阴影强度。最大化时窗口占满屏幕，不画这圈阴影（屏边不需要提示）。"""
        self._glow_anim.stop()
        self._glow_anim.setStartValue(self._focus_factor)
        target = FOCUS_GLOW_ACTIVE if (active and not self.isMaximized()) else FOCUS_GLOW_IDLE
        self._glow_anim.setEndValue(target)
        self._glow_anim.start()

    def _on_glow_value(self, value) -> None:
        self._focus_factor = float(value)
        self.update()

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.ActivationChange:
            self._animate_focus_glow(self.isActiveWindow())
        super().changeEvent(event)

    def _build_chrome(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        title = QWidget()
        title.setFixedHeight(TITLE_H)
        self.title_bar = title
        t = QHBoxLayout(title)
        t.setContentsMargins(14, 0, 8, 0)
        t.setSpacing(8)
        self.brand_icon = QLabel()
        self.brand_icon.setPixmap(_brand_pixmap())
        self.brand_label = QLabel("音珏 - Mup")
        f = QFont("Microsoft YaHei UI")
        f.setPointSizeF(9.5)
        f.setWeight(QFont.Weight.DemiBold)
        self.brand_label.setFont(f)
        self.brand_label.setStyleSheet(f"color: {theme.CURRENT['text']};")
        t.addWidget(self.brand_icon)
        t.addWidget(self.brand_label)
        t.addStretch(1)
        self.btn_theme = NeuIconButton("auto", px=15)
        self.btn_theme.setFixedSize(30, 30)
        self.btn_theme.setToolTip("外观主题（点击切换）")
        self.btn_theme.clicked.connect(self._cycle_theme)
        t.addWidget(self.btn_theme)
        self.btn_settings = NeuIconButton("settings", px=15)
        self.btn_settings.setFixedSize(30, 30)
        self.btn_settings.setToolTip("设置")
        self.btn_settings.clicked.connect(self._open_settings)
        t.addWidget(self.btn_settings)
        self.btn_min = NeuIconButton("minimize", px=15)
        self.btn_min.setFixedSize(30, 30)
        self.btn_max = NeuIconButton("maximize", px=14)
        self.btn_max.setFixedSize(30, 30)
        self.btn_close = NeuIconButton("close", px=14)
        self.btn_close.setFixedSize(30, 30)
        self.btn_close.accent_color = theme.CURRENT["danger"]
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close.clicked.connect(self.close)
        t.addWidget(self.btn_settings)
        t.addWidget(self.btn_min)
        t.addWidget(self.btn_max)
        t.addWidget(self.btn_close)
        root.addWidget(title)

        # 内容容器（过渡动画作用于此）
        self.content = QWidget()
        cv = QVBoxLayout(self.content)
        cv.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        cv.addWidget(self.stack)
        root.addWidget(self.content, 1)

    def _build_pages(self) -> None:
        self.connect_page = ConnectPage(self.config)
        self.stack.addWidget(self.connect_page)
        self._library: LibraryPage | None = None
        self._player: PlayerPage | None = None
        self.connect_page.connected.connect(self._on_connected)

    def _on_connected(self, client: SubsonicClient) -> None:
        self.client = client
        self.covers.set_client(client)
        self.player.set_client(client)
        self.lyrics.set_client(client)
        # 恢复音量与播放模式（需在构建播放栏之前，使滑块初始值正确）
        self.player.set_volume(int(self.config.player.get("volume", 80)))
        self.player.set_mode(self.config.player.get("mode", "list"))
        if self._library is None:
            self._library = LibraryPage(client, self.player, self.covers, self.lyrics, self.config)
            self._library.open_immersive.connect(self._open_immersive)
            self.stack.addWidget(self._library)
        else:
            # 重新连接：不重建页面，更新客户端引用并重新拉取歌单列表（保持现有 UI 状态）
            self._library.set_client(client)
            self._library.refresh_playlists()
        if self._player is None:
            self._player = PlayerPage(client, self.player, self.covers, self.lyrics)
            self._player.back_requested.connect(self._close_immersive)
            self.stack.addWidget(self._player)
        self.stack.setCurrentWidget(self._library)
        self.brand_label.show()
        self.brand_icon.show()

    def _auto_connect(self) -> None:
        srv = self.config.server
        if not (srv.get("host") and srv.get("username")):
            return
        client = SubsonicClient(srv["host"], srv["port"], srv["username"], srv["password"])
        self.connect_page._show_status("正在自动连接…")
        self._auto_ping = PingThread(client, self)
        self._auto_ping.done.connect(self._on_auto_done)
        self._auto_ping.start()

    def _on_auto_done(self, ok: bool, msg: str) -> None:
        if ok:
            self._on_connected(SubsonicClient(self.config.server["host"], self.config.server["port"],
                                              self.config.server["username"], self.config.server["password"]))
        else:
            self.connect_page._show_status(msg or "自动连接失败，请重新填写", error=True)

    # ---------- 沉浸页过渡 ----------
    def _open_immersive(self, pix: QPixmap, global_rect: QRect) -> None:
        if self._library is None:
            return
        src = QRect(self.content.mapFromGlobal(global_rect.topLeft()), global_rect.size())
        # 放大到沉浸页新封面的位置（歌词上方，而非全屏）
        if self._player is not None:
            # 首次打开时沉浸页尚未布局，big_cover 还是默认 640x480（或 0x0）→ 先按内容区大小强制布局一次，避免放大过大
            if self._player.big_cover.width() < 100 or self._player.big_cover.width() > 400:
                self._player.resize(self.content.size())
                self._player.show()
                self._player.layout().activate()
                self._player.hide()
            cover_rect = QRect(self._player.big_cover.mapToGlobal(self._player.big_cover.rect().topLeft()),
                               self._player.big_cover.size())
            dst = QRect(self.content.mapFromGlobal(cover_rect.topLeft()), cover_rect.size())
        else:
            dst = QRect(self.content.rect())
        # 先切到沉浸页并开始内容渐显，让「封面放大」与「背景/内容渐变出现」同时进行
        # （此前是等封面放大动画结束后才 fade_in，观感上分成了两段）
        # 但目标位置的封面必须先隐藏：否则过渡层正在放大的封面与页面里已就位的封面会同框出现两个
        if self._player is not None:
            self.stack.setCurrentWidget(self._player)
            self._player.big_cover.hide()
            self._player.fade_in()
        overlay = _TransitionOverlay(self.content, pix)
        overlay.done.connect(lambda: self._finish_open(overlay))
        self._overlay = overlay
        overlay.start(src, dst, 0.45)

    def _finish_open(self, overlay: _TransitionOverlay) -> None:
        """封面放大结束：此时才把封面交还给沉浸页（内容已同步渐显完成），再淡出过渡层。"""
        if self._player is not None:
            self._player.big_cover.show()  # 动画完毕后再替换，避免双封面
        # 淡出 overlay
        eff = QPropertyAnimation(overlay, b"windowOpacity", overlay)
        eff.setStartValue(1.0)
        eff.setEndValue(0.0)
        eff.setDuration(180)
        eff.finished.connect(overlay.deleteLater)
        eff.start()
        self._overlay = None

    def _close_immersive(self) -> None:
        if self._library is None or self._player is None:
            return
        self.stack.setCurrentWidget(self._library)
        pix = self._player.big_cover._pix
        if pix is None:
            pix = self._player.big_cover.grab()
        cover_rect = QRect(self._library.cover.mapToGlobal(self._library.cover.rect().topLeft()),
                           self._library.cover.size())
        dst = QRect(self.content.mapFromGlobal(cover_rect.topLeft()), cover_rect.size())
        src_rect = QRect(self._player.big_cover.mapToGlobal(self._player.big_cover.rect().topLeft()),
                         self._player.big_cover.size())
        src = QRect(self.content.mapFromGlobal(src_rect.topLeft()), src_rect.size())
        overlay = _TransitionOverlay(self.content, pix)
        overlay.done.connect(overlay.deleteLater)
        overlay.start(src, dst, 0.0)

    # ---------- 主题 ----------
    _THEME_CYCLE = ("system", "dark", "light")
    _THEME_ICONS = {"system": "auto", "dark": "moon", "light": "sun"}
    _THEME_NAMES = {"system": "跟随系统", "dark": "深色", "light": "浅色"}

    def _apply_theme(self, dark: bool) -> None:
        theme.set_theme(dark)
        QApplication.instance().setStyleSheet(theme.build_qss(theme.CURRENT))
        self.brand_icon.setPixmap(_brand_pixmap())
        self.brand_label.setStyleSheet(f"color: {theme.CURRENT['text']};")
        self.btn_close.accent_color = theme.CURRENT["danger"]
        self._update_theme_btn()
        for w in QApplication.instance().topLevelWidgets():
            w.update()

    def _update_theme_btn(self) -> None:
        """标题栏主题按钮：图标/提示随当前主题模式刷新。"""
        mode = self.config.theme
        if mode not in self._THEME_ICONS:
            mode = "system"
        self.btn_theme.icon_name = self._THEME_ICONS[mode]
        self.btn_theme.setToolTip(f"外观主题：{self._THEME_NAMES[mode]}（点击切换）")
        self.btn_theme.update()

    def _cycle_theme(self) -> None:
        """点击标题栏主题按钮：跟随系统 → 深色 → 浅色 → 循环。"""
        order = self._THEME_CYCLE
        cur = self.config.theme
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else "system"
        self.config.data["theme"] = nxt
        self.config.save()
        self._apply_theme(theme.effective_dark(nxt))

    def _check_system_theme(self) -> None:
        """跟随系统模式下，系统深浅色变化时自动切换。"""
        if self.config.theme == "system":
            self._apply_theme(theme.system_dark())

    # ---------- 快捷键 ----------
    def _register_hotkeys(self) -> None:
        cfg = self.config.hotkeys
        for action, combo in cfg.items():
            self.hotkeys.register_combo(action, combo)
        self.hotkeys.register_media_keys()
        self.hotkeys.install_media_hook()
        self.hotkeys.triggered.connect(self._on_hotkey)

    def _on_hotkey(self, action: str) -> None:
        if action in ("play_pause", "media_play_pause"):
            self.player.toggle()
        elif action in ("next", "media_next"):
            self.player.next()
        elif action in ("prev", "media_prev"):
            self.player.prev()
        elif action in ("volume_up", "media_volume_up"):
            self._set_volume(self.player.volume + 5)
        elif action in ("volume_down", "media_volume_down"):
            self._set_volume(self.player.volume - 5)
        elif action == "media_stop":
            self.player.stop()

    def _set_volume(self, v: int) -> None:
        self.player.set_volume(v)
        self.config.player["volume"] = v
        self.config.save()

    # ---------- 设置 ----------
    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.config, self)
        dlg.reconnect_requested.connect(self._show_connect)
        dlg.theme_changed.connect(self._apply_theme)
        dlg.exec()

    def _show_connect(self) -> None:
        self.stack.setCurrentWidget(self.connect_page)

    def _focus_search(self) -> None:
        """Ctrl+F：切回歌单页并把焦点放到搜索框（沉浸页也可直接使用）。"""
        if self._library is None:
            return
        self.stack.setCurrentWidget(self._library)
        self._library.focus_search()

    # ---------- 窗口控制 ----------
    def _toggle_max(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._animate_focus_glow(self.isActiveWindow())  # 最大化时去掉边缘阴影

    def _build_tray(self) -> None:
        """托盘图标：关闭窗口时最小化到托盘，右键可退出。"""
        self._tray: QSystemTrayIcon | None = None
        self._tray_menu: QMenu | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self)
        if _APP_ICON.exists():
            self._tray.setIcon(QIcon(str(_APP_ICON)))
        # 必须持有 menu 引用，否则 Python GC 会销毁 QMenu 导致“退出”信号失效
        self._tray_menu = QMenu()
        act_show = self._tray_menu.addAction("显示主界面")
        self._tray_menu.addSeparator()
        act_quit = self._tray_menu.addAction("退出")
        act_show.triggered.connect(self._tray_show)
        act_quit.triggered.connect(self._quit_app)
        self._tray.setContextMenu(self._tray_menu)
        self._tray.setToolTip(APP_NAME)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._tray_show()

    def _tray_show(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self) -> None:
        """托盘菜单「退出」：停止播放 → 关闭窗口 → 退出事件循环（确保进程结束）。"""
        self._really_quit = True
        try:
            self.player.stop()
        except Exception:  # noqa: BLE001
            pass
        self._tray_menu = None  # 释放菜单引用
        self.close()
        QApplication.instance().quit()

    def _shutdown_background(self) -> None:
        """真正退出前回收所有后台线程。

        QThread 若在运行中被父对象连带析构，Qt 会 qFatal 直接终止进程（实测退出码 0xC0000409）。
        这里先置全局停止位让分页等长循环提前返回，再逐个等待线程结束。
        """
        subsonic_client.request_stop()
        ping = self._auto_ping
        self._auto_ping = None
        if ping is not None and ping.isRunning():
            ping.requestInterruption()
            ping.wait(SHUTDOWN_WAIT_MS)
        self.connect_page.shutdown()
        if self._library is not None:
            self._library.shutdown()
        self.lyrics.shutdown()
        if self.client is not None:
            self.client.close()

    def closeEvent(self, event) -> None:
        self.config.player["window_size"] = [self.width(), self.height()]
        self.config.player["window_pos"] = [self.x(), self.y()]
        self.config.player["volume"] = self.player.volume
        self.config.player["mode"] = self.player.mode
        if self.player.queue and self.player.current_index >= 0:
            self.config.player["last_song_id"] = self.player.queue[self.player.current_index].id
            self.config.player["last_position"] = self.player.media.position()
        self.config.player["last_playlist_id"] = self._library.active_playlist_id if self._library else ""
        self.config.player["last_playlist_cover_id"] = self._library.song_header.current_cover_id() if self._library else ""
        self.config.save()
        self.player.stream_cache.cancel_all()  # 中断进行中的音频下载，避免残留 .partial
        # 关闭窗口 → 最小化到托盘（不退出）；只有托盘菜单「退出」才真正退出
        if getattr(self, "_really_quit", False) or self._tray is None:
            self.hide()  # 先隐藏窗口，线程回收期间用户感觉是“立即关闭”
            self._shutdown_background()
            self.hotkeys.unregister_all()  # 真正退出才注销热键；隐藏到托盘需保持媒体键可用
            if self._tray:
                self._tray.hide()
            super().closeEvent(event)
        else:
            self.hide()
            event.ignore()


class SettingsDialog(QDialog):
    """设置：连接参数、主题、快捷键说明、关于（分组卡片式布局）。"""

    reconnect_requested = Signal()
    theme_changed = Signal(bool)

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("设置")
        self.setFixedWidth(460)
        self.setModal(True)
        # 记录主题相关控件，切换主题时可整体刷新配色
        self._cards: list[QFrame] = []
        self._sections: list[QLabel] = []
        self._labels: list[tuple[QLabel, str]] = []  # (label, kind: title/text/muted/strong/key)

        v = QVBoxLayout(self)
        v.setSpacing(14)
        v.setContentsMargins(24, 22, 24, 22)

        # 标题
        title = QLabel("设置")
        ft = QFont("Microsoft YaHei UI")
        ft.setPointSizeF(15)
        ft.setWeight(QFont.Weight.DemiBold)
        title.setFont(ft)
        self._labels.append((title, "title"))
        v.addWidget(title)
        v.addSpacing(2)

        # —— 连接设置 ——
        card_c = self._card()
        cv = QVBoxLayout(card_c)
        cv.setSpacing(10)
        cv.addWidget(self._section("连接设置"))
        cur = self.config.server
        addr = QLabel(f"{cur['host']}:{cur['port']}（{cur['username']}）")
        addr.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._labels.append((addr, "text"))
        cv.addWidget(addr)
        addr2 = QLabel(f"协议 {cur['protocol']} · 通过音桥接入飞牛音乐")
        self._labels.append((addr2, "muted"))
        cv.addWidget(addr2)
        btn = NeuButton("重新填写连接参数", ghost=True)
        btn.clicked.connect(self._reconnect)
        btn.setFixedHeight(34)
        cv.addSpacing(2)
        cv.addWidget(btn)
        v.addWidget(card_c)

        # —— 开机自启 ——
        card_b = self._card()
        bv = QVBoxLayout(card_b)
        bv.setSpacing(8)
        bv.addWidget(self._section("开机自启"))
        self.chk_autostart = QCheckBox("登录系统时自动启动 Mup")
        self.chk_autostart.setChecked(autostart.is_enabled())
        self.chk_autostart.toggled.connect(self._on_autostart)
        bv.addWidget(self.chk_autostart)
        tip_b = QLabel("可在系统「任务管理器 → 启动」中直接启用/禁用。")
        self._labels.append((tip_b, "muted"))
        bv.addWidget(tip_b)
        v.addWidget(card_b)

        # —— 动效 ——
        card_m = self._card()
        mv = QVBoxLayout(card_m)
        mv.setSpacing(8)
        mv.addWidget(self._section("动效"))
        self.chk_motion = QCheckBox("减少动效（关闭按下/悬浮/入场等过渡动画）")
        self.chk_motion.setChecked(bool((self.config.data.get("ui") or {}).get("reduce_motion")))
        self.chk_motion.toggled.connect(self._on_reduce_motion)
        mv.addWidget(self.chk_motion)
        tip_m = QLabel("关闭后所有过渡瞬时完成，适合低配设备或不喜欢动画时使用。")
        self._labels.append((tip_m, "muted"))
        mv.addWidget(tip_m)
        v.addWidget(card_m)

        # —— 主题 ——
        card_t = self._card()
        tv = QVBoxLayout(card_t)
        tv.setSpacing(10)
        tv.addWidget(self._section("外观主题"))
        th = QHBoxLayout()
        th.setSpacing(8)
        self.radio_system = QRadioButton("跟随系统")
        self.radio_light = QRadioButton("浅色")
        self.radio_dark = QRadioButton("深色")
        mode = self.config.theme
        self.radio_system.setChecked(mode == "system")
        self.radio_light.setChecked(mode == "light")
        self.radio_dark.setChecked(mode == "dark")
        self._radios = (self.radio_system, self.radio_light, self.radio_dark)
        for rb in self._radios:
            rb.toggled.connect(self._on_theme)
            th.addWidget(rb)
        th.addStretch(1)
        tv.addLayout(th)
        v.addWidget(card_t)

        # —— 快捷键 ——
        card_h = self._card()
        hv = QVBoxLayout(card_h)
        hv.setSpacing(8)
        hv.addWidget(self._section("快捷键"))
        for action, combo in self.config.hotkeys.items():
            row = QHBoxLayout()
            kb = QLabel(combo)
            kf = QFont("Consolas", 10)
            kf.setWeight(QFont.Weight.Medium)
            kb.setFont(kf)
            self._labels.append((kb, "key"))
            row.addWidget(kb)
            row.addSpacing(6)
            name = QLabel(_ACTION_NAMES.get(action, action))
            self._labels.append((name, "text"))
            row.addWidget(name)
            row.addStretch(1)
            hv.addLayout(row)
        tip = QLabel("系统媒体键（播放/暂停、上/下一曲、音量±）已自动注册；\n"
                     "全局搜索 Ctrl+F 聚焦侧边栏搜索框（Esc 退出搜索）；\n"
                     "自定义快捷键可在 config.json 中修改。")
        tip.setWordWrap(True)
        self._labels.append((tip, "muted"))
        hv.addSpacing(2)
        hv.addWidget(tip)
        v.addWidget(card_h)

        # —— 关于 ——
        card_a = self._card()
        av = QVBoxLayout(card_a)
        av.setSpacing(6)
        av.addWidget(self._section("关于"))
        about = QLabel(f"{APP_NAME}  v{APP_VERSION}")
        abf = QFont("Microsoft YaHei UI")
        abf.setPointSizeF(11)
        abf.setWeight(QFont.Weight.Medium)
        about.setFont(abf)
        self._labels.append((about, "strong"))
        av.addWidget(about)
        about2 = QLabel("基于 PySide6 · Subsonic / Jellyfin 协议 · 通过音桥连接飞牛音乐")
        self._labels.append((about2, "muted"))
        av.addWidget(about2)
        v.addWidget(card_a)

        self._restyle()

    def _card(self) -> QFrame:
        card = QFrame()
        self._cards.append(card)
        return card

    def _section(self, text: str) -> QLabel:
        lb = QLabel(text)
        f = QFont("Microsoft YaHei UI")
        f.setPointSizeF(9.5)
        f.setWeight(QFont.Weight.DemiBold)
        lb.setFont(f)
        self._sections.append(lb)
        return lb

    def _restyle(self) -> None:
        """按当前主题重设对话框配色（背景/卡片/文字/主题单选选中标记）。"""
        pal = theme.CURRENT
        self.setStyleSheet(f"QDialog {{ background: {pal['clay']}; }}")
        for card in self._cards:
            card.setStyleSheet(f"QFrame {{ background: {pal['raise']}; border-radius: 14px; }}")
        for sec in self._sections:
            sec.setStyleSheet(f"color: {pal['primary_text']};")
        for lb, kind in self._labels:
            if kind == "title":
                lb.setStyleSheet(f"color: {pal['text']};")
            elif kind == "strong":
                lb.setStyleSheet(f"color: {pal['text']};")
            elif kind == "text":
                lb.setStyleSheet(f"color: {pal['text']}; font-size: 12px;")
            elif kind == "muted":
                lb.setStyleSheet(f"color: {pal['text_muted']}; font-size: 11px;")
            elif kind == "key":
                lb.setStyleSheet(f"background: {pal['press']}; color: {pal['primary_text']};"
                                 f"border-radius: 6px; padding: 2px 9px;")
        # 主题单选：选中态为主题色圆点（清晰的选中图标），随主题刷新
        radio_qss = (
            f"QRadioButton {{ color: {pal['text']}; font-size: 12px; spacing: 6px; }}"
            f"QRadioButton::indicator {{ width: 15px; height: 15px; border-radius: 8px;"
            f" border: 2px solid {pal['text_muted']}; background: transparent; }}"
            f"QRadioButton::indicator:hover {{ border-color: {pal['primary']}; }}"
            f"QRadioButton::indicator:checked {{ border-color: {pal['primary']};"
            f" background: {pal['primary']}; }}"
        )
        for rb in self._radios:
            rb.setStyleSheet(radio_qss)
        # 开机自启 / 减少动效 复选框：与主题单选同风格（主题色选中标记）
        chk_qss = (
            f"QCheckBox {{ color: {pal['text']}; font-size: 12px; spacing: 6px; }}"
            f"QCheckBox::indicator {{ width: 15px; height: 15px; border-radius: 4px;"
            f" border: 2px solid {pal['text_muted']}; background: transparent; }}"
            f"QCheckBox::indicator:hover {{ border-color: {pal['primary']}; }}"
            f"QCheckBox::indicator:checked {{ border-color: {pal['primary']};"
            f" background: {pal['primary']}; }}"
        )
        for chk in (self.chk_autostart, self.chk_motion):
            chk.setStyleSheet(chk_qss)
        # 让对话框内自定义绘制控件（NeuButton 等）按新主题重画
        self.update()
        for child in self.findChildren(QWidget):
            child.update()

    def _reconnect(self) -> None:
        self.accept()
        self.reconnect_requested.emit()

    def _on_autostart(self, checked: bool) -> None:
        if not autostart.set_enabled(checked):
            self.chk_autostart.setChecked(not checked)  # 写入失败回滚，避免显示与事实不符

    def _on_reduce_motion(self, checked: bool) -> None:
        ui_cfg = self.config.data.setdefault("ui", {})
        ui_cfg["reduce_motion"] = bool(checked)
        self.config.save()
        anim.set_reduced_motion(checked)

    def _on_theme(self, checked: bool) -> None:
        if not checked:
            return
        if self.radio_system.isChecked():
            mode = "system"
        elif self.radio_dark.isChecked():
            mode = "dark"
        else:
            mode = "light"
        self.config["theme"] = mode
        self.config.save()
        self.theme_changed.emit(theme.effective_dark(mode))
        self._restyle()  # 设置页 UI 随主题同步刷新


_ACTION_NAMES = {
    "play_pause": "播放 / 暂停",
    "next": "下一曲",
    "prev": "上一曲",
    "volume_up": "音量 +",
    "volume_down": "音量 -",
}
