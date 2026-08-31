"""主窗口：无边框、自定义标题栏、原生边缘缩放、页面堆叠、沉浸页过渡动画、设置对话框。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import (
    QAbstractNativeEventFilter,
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
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

from app.config import APP_NAME, APP_VERSION, APP_DIR, RESOURCE_DIR, Config
from app.cover_manager import CoverManager
from app.hotkeys import GlobalHotkeys
from app.lyrics import LyricsManager
from app.player import Player
from app.subsonic_client import SubsonicClient
from ui import icons, theme
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
HTCLIENT = 1
HTCAPTION = 2
HTLEFT, HTRIGHT, HTTOP, HTBOTTOM = 10, 11, 12, 15
HTTOPLEFT, HTTOPRIGHT, HTBOTTOMLEFT, HTBOTTOMRIGHT = 13, 14, 16, 17

TITLE_H = 42
MIN_W, MIN_H = 960, 640
EDGE = 6


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
        return (False, 0)

    def _hit_test(self, msg) -> int:
        x = msg.lParam & 0xFFFF
        y = (msg.lParam >> 16) & 0xFFFF
        w = self.win
        gx, gy = w.x(), w.y()
        gw, gh = w.width(), w.height()
        for btn in (w.btn_settings, w.btn_min, w.btn_max, w.btn_close):
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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
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

        self._build_chrome()
        self._build_pages()
        self._apply_theme(theme.effective_dark(self.config.theme))
        self._register_hotkeys()
        self._auto_connect()
        self._build_tray()

        self._native = _NativeFilter(self)
        QApplication.instance().installNativeEventFilter(self._native)
        self._system_theme_timer.start()

    # ---------- 界面 ----------
    def paintEvent(self, event) -> None:
        """整窗陶土色背景，页面内容叠加其上。"""
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.CURRENT["clay"]))

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
        overlay = _TransitionOverlay(self.content, pix)
        overlay.done.connect(lambda: self._finish_open(overlay))
        self._overlay = overlay
        overlay.start(src, dst, 0.45)

    def _finish_open(self, overlay: _TransitionOverlay) -> None:
        if self._player is not None:
            self.stack.setCurrentWidget(self._player)
            # 封面放大动画同时，其他内容渐变出现
            self._player.fade_in()
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
    def _apply_theme(self, dark: bool) -> None:
        theme.set_theme(dark)
        QApplication.instance().setStyleSheet(theme.build_qss(theme.CURRENT))
        self.brand_icon.setPixmap(_brand_pixmap())
        self.brand_label.setStyleSheet(f"color: {theme.CURRENT['text']};")
        self.btn_close.accent_color = theme.CURRENT["danger"]
        for w in QApplication.instance().topLevelWidgets():
            w.update()

    def _check_system_theme(self) -> None:
        """跟随系统模式下，系统深浅色变化时自动切换。"""
        if self.config.theme == "system":
            self._apply_theme(theme.system_dark())

    # ---------- 快捷键 ----------
    def _register_hotkeys(self) -> None:
        cfg = self.config.hotkeys
        for action, combo in cfg.items():
            self.hotkeys.register_combo(action, combo)
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

    # ---------- 窗口控制 ----------
    def _toggle_max(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

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

    def closeEvent(self, event) -> None:
        self.config.player["window_size"] = [self.width(), self.height()]
        self.config.player["volume"] = self.player.volume
        self.config.player["mode"] = self.player.mode
        if self.player.queue and self.player.current_index >= 0:
            self.config.player["last_song_id"] = self.player.queue[self.player.current_index].id
            self.config.player["last_position"] = self.player.media.position()
        self.config.player["last_playlist_id"] = self._library.active_playlist_id if self._library else ""
        self.config.save()
        self.hotkeys.unregister_all()
        # 关闭窗口 → 最小化到托盘（不退出）；只有托盘菜单「退出」才真正退出
        if getattr(self, "_really_quit", False) or self._tray is None:
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
        pal = theme.CURRENT
        self.setStyleSheet(f"QDialog {{ background: {pal['clay']}; }}")

        v = QVBoxLayout(self)
        v.setSpacing(14)
        v.setContentsMargins(24, 22, 24, 22)

        # 标题
        title = QLabel("设置")
        ft = QFont("Microsoft YaHei UI")
        ft.setPointSizeF(15)
        ft.setWeight(QFont.Weight.DemiBold)
        title.setFont(ft)
        v.addWidget(title)
        v.addSpacing(2)

        # —— 连接设置 ——
        card_c = self._card()
        cv = QVBoxLayout(card_c)
        cv.setSpacing(10)
        cv.addWidget(self._section("连接设置"))
        cur = self.config.server
        addr = QLabel(f"{cur['host']}:{cur['port']}（{cur['username']}）")
        addr.setStyleSheet(f"color: {pal['text']}; font-size: 12px;")
        addr.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        addr2 = QLabel(f"协议 {cur['protocol']} · 通过音桥接入飞牛音乐")
        addr2.setStyleSheet(f"color: {pal['text_muted']}; font-size: 11px;")
        cv.addWidget(addr)
        cv.addWidget(addr2)
        btn = NeuButton("重新填写连接参数", ghost=True)
        btn.clicked.connect(self._reconnect)
        btn.setFixedHeight(34)
        cv.addSpacing(2)
        cv.addWidget(btn)
        v.addWidget(card_c)

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
        for rb in (self.radio_system, self.radio_light, self.radio_dark):
            rb.toggled.connect(self._on_theme)
            rb.setStyleSheet(f"QRadioButton {{ font-size: 12px; }}"
                             f"QRadioButton::indicator {{ width: 15px; height: 15px; }}")
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
            kb.setStyleSheet(
                f"background: {pal['press']}; color: {pal['primary_text']};"
                f"border-radius: 6px; padding: 2px 9px;"
            )
            name = QLabel(_ACTION_NAMES.get(action, action))
            name.setStyleSheet(f"color: {pal['text']}; font-size: 12px;")
            row.addWidget(kb)
            row.addSpacing(6)
            row.addWidget(name)
            row.addStretch(1)
            hv.addLayout(row)
        tip = QLabel("系统媒体键（播放/暂停、上/下一曲、音量±）已自动注册；\n自定义快捷键可在 config.json 中修改。")
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color: {pal['text_muted']}; font-size: 11px;")
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
        av.addWidget(about)
        about2 = QLabel("基于 PySide6 · Subsonic / Jellyfin 协议 · 通过音桥连接飞牛音乐")
        about2.setStyleSheet(f"color: {pal['text_muted']}; font-size: 11px;")
        av.addWidget(about2)
        v.addWidget(card_a)

    def _card(self) -> QFrame:
        pal = theme.CURRENT
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {pal['raise']}; border-radius: 14px; }}"
        )
        return card

    def _section(self, text: str) -> QLabel:
        pal = theme.CURRENT
        lb = QLabel(text)
        f = QFont("Microsoft YaHei UI")
        f.setPointSizeF(9.5)
        f.setWeight(QFont.Weight.DemiBold)
        lb.setFont(f)
        lb.setStyleSheet(f"color: {pal['primary_text']};")
        return lb

    def _reconnect(self) -> None:
        self.accept()
        self.reconnect_requested.emit()

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


_ACTION_NAMES = {
    "play_pause": "播放 / 暂停",
    "next": "下一曲",
    "prev": "上一曲",
    "volume_up": "音量 +",
    "volume_down": "音量 -",
}
