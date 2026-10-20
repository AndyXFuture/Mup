"""歌单页：侧边栏导航 + 主内容（歌曲/专辑/歌手/搜索）+ 底部播放栏（QQ 音乐式三段布局）。"""
from __future__ import annotations

import logging
from pathlib import Path
from shutil import copy2

from PySide6.QtCore import QEvent, QModelIndex, QPoint, QPropertyAnimation, QRect, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QKeySequence, QLinearGradient, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractButton,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.config import Config, APP_DIR, SHUTDOWN_WAIT_MS
from app.cover_manager import CoverManager
from app.lyrics import LyricsManager
from app.player import MODE_LIST, MODE_ORDER, MODE_RANDOM, MODE_SINGLE, STATE_PLAYING, Player
from app.subsonic_client import Album, Artist, Playlist, Song, SubsonicClient
from ui import anim, icons, theme
from ui.anim import mix
from ui.widgets import (
    AlbumDelegate,
    ArtistDelegate,
    CoverArt,
    FadeVeil,
    HoverSlider,
    ListEdgeFade,
    MarqueeLabel,
    MotionButton,
    NeuButton,
    NeuFrame,
    NeuIconButton,
    NeuLineEdit,
    PlayButton,
    PlaylistDelegate,
    SimpleModel,
    SkipButton,
    SongDelegate,
    SongModel,
    make_list_view,
    song_cols,
    song_zone,
    SONG_COVER,
    SONG_COVER_X,
)

_MODE_ICONS = {MODE_LIST: "repeat", MODE_RANDOM: "shuffle", MODE_SINGLE: "repeat_one", MODE_ORDER: "order"}
_MODE_NAMES = {MODE_LIST: "列表循环", MODE_RANDOM: "随机播放", MODE_SINGLE: "单曲循环", MODE_ORDER: "顺序播放"}

_VIEW_SONG, _VIEW_ALBUM, _VIEW_ARTIST, _VIEW_PLACEHOLDER = 0, 1, 2, 3

MAX_PLAYLIST_CACHE = 10  # 内存中最多保留多少个已加载歌单（防止长期使用内存单调增长）

# 侧边栏宽度（可拖拽右边缘调整）
SIDEBAR_MIN_W, SIDEBAR_MAX_W, SIDEBAR_DEF_W = 180, 360, 204
SIDEBAR_HANDLE_W = 8  # 拖拽热区宽度（压在侧边栏右缘，不可见，仅切换光标）


class SidebarResizer(QWidget):
    """侧边栏右缘拖拽条：纯功能入口，拖动改变侧边栏宽度。

    做成覆盖条而不是放进布局，避免改动原有 16px 外边距体系与卡片间距。
    """

    def __init__(self, page: "LibraryPage", parent=None) -> None:
        super().__init__(parent)
        self._page = page
        self._start_x = 0.0
        self._start_w = 0
        self.setFixedWidth(SIDEBAR_HANDLE_W)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setToolTip("拖动调整侧边栏宽度")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_x = event.globalPosition().x()
            self._start_w = self._page.sidebar.width()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._page.set_sidebar_width(int(self._start_w + event.globalPosition().x() - self._start_x))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._page.save_sidebar_width()  # 松手才落盘，拖动过程不写配置
            event.accept()
            return
        super().mouseReleaseEvent(event)


# ---------- 后台数据线程 ----------
class DataThread(QThread):
    result = Signal(object)

    def __init__(self, fn, parent=None) -> None:
        super().__init__(parent)
        self.fn = fn

    def run(self) -> None:
        try:
            payload = ("ok", self.fn())
        except Exception as exc:  # noqa: BLE001
            payload = ("err", str(exc))
        if self.isInterruptionRequested():
            return  # 正在退出：丢弃结果，避免回写已销毁的界面
        self.result.emit(payload)


# ---------- 侧边栏导航项 ----------
class NavItem(MotionButton):
    def __init__(self, icon_name: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self.icon_name = icon_name
        self._label = text
        self.active = False
        self.SCALE_ON_PRESS = 1.0  # 整行导航不缩放（缩放会显得怪），只做悬浮渐变
        self._icon_pix = None
        self.setFixedHeight(38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_active(self, on: bool) -> None:
        self.active = on
        self.update()

    def paintEvent(self, event) -> None:
        pal = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.rect().adjusted(2, 2, -2, -2)
        hv = self.hover_t()
        if self.active:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(pal["press"]))
            p.drawRoundedRect(QRect(r), 10, 10)
        elif hv > 0.01:
            c = QColor(pal["primary_soft"])
            c.setAlpha(int(c.alpha() * hv))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(QRect(r), 10, 10)
        color = mix(QColor(pal["text_muted"]), QColor(pal["primary_text"]), hv) \
            if not self.active else QColor(pal["primary_text"])
        key = (self.icon_name, color.name())
        if self._icon_pix is None or self._icon_pix[0] != key:
            self._icon_pix = (key, icons.pixmap(self.icon_name, color.name(), 16, stroke=1.8))
        p.drawPixmap(r.left() + 8, r.top() + (r.height() - 16) // 2, self._icon_pix[1])
        f = QFont("Microsoft YaHei UI")
        f.setPointSizeF(9.5)
        f.setWeight(QFont.Weight.Medium if self.active else QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(QColor(pal["text"]) if self.active
                 else mix(QColor(pal["text_muted"]), QColor(pal["text"]), hv))
        p.drawText(QRect(r.left() + 32, r.top(), r.width() - 40, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label)


# ---------- 通用歌曲头 ----------
class SongHeader(QWidget):
    play_all = Signal()
    play_random = Signal()
    refresh_requested = Signal()
    edit_cover_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(4, 2, 4, 2)
        h.setSpacing(16)
        self.cover = CoverArt(radius=18)
        self.cover.setFixedSize(96, 96)
        h.addWidget(self.cover)
        info = QVBoxLayout()
        info.setSpacing(4)
        self.title = QLabel("")
        f = QFont("Microsoft YaHei UI")
        f.setPointSizeF(15)
        f.setWeight(QFont.Weight.DemiBold)
        self.title.setFont(f)
        self.meta = QLabel("")
        fm = QFont("Microsoft YaHei UI")
        fm.setPointSizeF(9)
        self.meta.setFont(fm)
        self.meta.setStyleSheet(f"color: {theme.CURRENT['text_muted']};")
        info.addWidget(self.title)
        info.addWidget(self.meta)
        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.btn_play_all = NeuButton("播放全部", accent=True)
        self.btn_random_all = NeuButton("随机播放")
        self.btn_play_all.setMinimumWidth(110)
        self.btn_random_all.setMinimumWidth(110)
        self.btn_play_all.clicked.connect(self.play_all.emit)
        self.btn_random_all.clicked.connect(self.play_random.emit)
        btns.addWidget(self.btn_play_all)
        btns.addWidget(self.btn_random_all)
        self.btn_refresh = NeuIconButton("refresh", px=17)
        self.btn_refresh.setToolTip("重新加载")
        self.btn_refresh.setFixedSize(34, 34)
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        btns.addWidget(self.btn_refresh)
        self.btn_edit_cover = NeuIconButton("edit", px=17)
        self.btn_edit_cover.setToolTip("自定义封面")
        self.btn_edit_cover.setFixedSize(34, 34)
        self.btn_edit_cover.clicked.connect(self.edit_cover_requested.emit)
        btns.addWidget(self.btn_edit_cover)
        btns.addStretch(1)
        info.addSpacing(8)
        info.addLayout(btns)
        info.addStretch(1)
        h.addLayout(info, 1)
        self._cover_id = ""
        self._local_cover = False  # 当前显示的是否为本地自定义封面

    def set_data(self, title: str, meta: str, cover_id: str = "") -> None:
        self.title.setText(title)
        self.meta.setText(meta)
        self._cover_id = cover_id
        self._local_cover = False
        self.cover.set_pixmap(None)

    def set_local_cover(self, pix) -> None:
        """显示本地自定义封面并标记，后续服务器封面 loaded 事件不再覆盖。"""
        self._local_cover = True
        self.cover.set_pixmap(pix)

    def is_local_cover(self) -> bool:
        return self._local_cover

    def current_cover_id(self) -> str:
        return self._cover_id


# ---------- 可点击排序列头 ----------
class SortHeader(QWidget):
    """三列可点击列头：歌名/歌手、专辑、时长。点击循环切换排序。"""

    changed = Signal(int, int)  # (列, 模式)

    COL0_LABELS = ("歌名 / 歌手", "歌名 ↑", "歌名 ↓", "歌手 ↑", "歌手 ↓")
    COL1_LABELS = ("专辑", "专辑 ↑", "专辑 ↓")
    COL2_LABELS = ("时长", "时长 ↑", "时长 ↓")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state = {0: 0, 1: 0, 2: 0}
        self.setMinimumHeight(24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_state(self, col: int, mode: int) -> None:
        self._state[col] = mode
        self.update()

    def reset(self) -> None:
        self._state = {0: 0, 1: 0, 2: 0}
        self.update()

    def _cols(self):
        w = self.width()
        c0x, c0w, alb_x, alb_w, dur_x, dur_w = song_cols(0, w)
        # 歌名/歌手表头与封面(头像)左对齐；专辑/时长与下方内容左对齐
        c0 = QRect(SONG_COVER_X, 0, c0x + c0w - SONG_COVER_X, self.height())
        return c0, QRect(alb_x, 0, alb_w, self.height()), QRect(dur_x, 0, dur_w, self.height())

    def paintEvent(self, event) -> None:
        pal = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        f = QFont("Microsoft YaHei UI")
        f.setPointSizeF(8.5)
        p.setFont(f)
        c0, c1, c2 = self._cols()
        texts = (self.COL0_LABELS[self._state[0]], self.COL1_LABELS[self._state[1]], self.COL2_LABELS[self._state[2]])
        c = QColor(pal["primary_text"]) if self._state[0] else QColor(pal["text_muted"])
        p.setPen(c)
        p.drawText(c0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, texts[0])
        c = QColor(pal["primary_text"]) if self._state[1] else QColor(pal["text_muted"])
        p.setPen(c)
        p.drawText(c1, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, texts[1])
        c = QColor(pal["primary_text"]) if self._state[2] else QColor(pal["text_muted"])
        p.setPen(c)
        p.drawText(c2, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, texts[2])

    def mousePressEvent(self, event) -> None:
        x = event.position().x()
        for col, rect in enumerate(self._cols()):
            if rect.left() <= x <= rect.right():
                max_mode = {0: 4, 1: 2, 2: 2}[col]
                nxt = (self._state[col] + 1) % (max_mode + 1)
                self._state[col] = nxt
                self.update()
                self.changed.emit(col, nxt)
                return
        event.ignore()


def _apply_sort(songs: list, col: int, mode: int) -> list:
    if mode == 0:
        return songs
    key = None
    rev = False
    if col == 0:
        if mode == 1:
            key = lambda s: (s.title or "").lower(); rev = False
        elif mode == 2:
            key = lambda s: (s.title or "").lower(); rev = True
        elif mode == 3:
            key = lambda s: (s.artist or "").lower(); rev = False
        elif mode == 4:
            key = lambda s: (s.artist or "").lower(); rev = True
    elif col == 1:
        if mode == 1:
            key = lambda s: (s.album or "").lower(); rev = False
        elif mode == 2:
            key = lambda s: (s.album or "").lower(); rev = True
    elif col == 2:
        if mode == 1:
            key = lambda s: s.duration; rev = False
        elif mode == 2:
            key = lambda s: s.duration; rev = True
    if key is None:
        return songs
    return sorted(songs, key=key, reverse=rev)


# ---------- 迷你歌词条 ----------
class MiniLyrics(QWidget):
    """播放栏上方当前歌词：背景由不透明渐变到半透明。

    歌词条**有意覆盖在内容区底部之上**（向上渐隐、与列表自然融合），因此这里用
    `WA_TransparentForMouseEvents` 让鼠标事件穿透到下层列表——既保留覆盖与渐变观感，
    又不吞掉列表最后一行的悬浮/点击。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._text = ""
        self.setFixedHeight(46)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_text(self, text: str) -> None:
        text = text or ""
        if text != self._text:
            self._text = text
            self.setVisible(bool(text))
            self.update()

    def paintEvent(self, event) -> None:
        pal = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # 底部半透明 → 顶部全透明（向上渐隐，重叠 UI 区域自然融入）
        base = QColor(pal["clay"])
        bottom = QColor(base)
        bottom.setAlpha(205)
        top = QColor(base)
        top.setAlpha(0)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, top)
        grad.setColorAt(1.0, bottom)
        p.fillRect(self.rect(), grad)
        if self._text:
            f = QFont("Microsoft YaHei UI")
            f.setPointSizeF(12.5)
            p.setFont(f)
            c = QColor(pal["text"])
            c.setAlpha(235)
            p.setPen(c)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter, self._text)


# ---------- 歌单页 ----------
class LibraryPage(QWidget):
    """主界面：侧边栏 + 内容区 + 迷你歌词 + 底部播放栏。"""

    open_immersive = Signal(object, QRect)  # (pixmap, 封面全局矩形)

    def __init__(self, client: SubsonicClient, player: Player, covers: CoverManager,
                 lyrics: LyricsManager, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.client = client
        self.player = player
        self.covers = covers
        self.lyrics = lyrics
        self.config = config
        self.playlists: list[Playlist] = []
        self.current_songs: list[Song] = []
        self._base_songs: list[Song] = []          # 未排序原始顺序（切回默认排序用）
        self.artist_songs: list[Song] = []
        self._base_artist_songs: list[Song] = []
        self.active_playlist_id: str = ""
        self._play_after_pid: str = ""              # 双击歌单后待自动播放的目标歌单 id
        self._playlist_cache: dict[str, list] = {}  # 本次运行已加载的歌单缓存（key=playlist_id）
        # 视图意图令牌：快速切换导航（收藏/最近播放/专辑/歌手）时，先发的慢请求若晚到，
        # 令牌已变则丢弃其结果，避免旧数据把界面切回去、导航与内容不一致
        self._view_token: int = 0
        # 搜索状态
        self._nav_active: NavItem | None = None      # 当前高亮的导航项（搜索退出时据此恢复）
        self._search_active: bool = False
        self._search_query: str = ""
        self._search_prev_nav: NavItem | None = None
        self._restore_pending: bool = False        # 启动后待恢复上次歌曲
        self._now_cover_id: str = ""
        # 歌单自定义封面：{playlist_id: {"mode": "auto"/"custom", "path": str}}
        self._cover_overrides: dict[str, dict] = dict(self.config.player.get("playlist_covers") or {})
        self._cover_dir = APP_DIR / "covers"
        try:
            self._cover_dir.mkdir(parents=True, exist_ok=True)
        except OSError:  # noqa: BLE001
            pass
        self._threads: list[QThread] = []
        self._lyric_lines = []
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(90)
        self._anim_timer.timeout.connect(self._anim_tick)
        # 封面预取分片计时器（避免同步磁盘读取阻塞 UI）
        self._cover_prefetch_queue: list[str] = []
        self._cover_prefetch_timer = QTimer(self)
        self._cover_prefetch_timer.setInterval(0)
        self._cover_prefetch_timer.timeout.connect(self._prefetch_cover_chunk)
        # 封面加载后的重绘合并（每轮事件循环至多重绘一次）
        self._cover_repaint_pending = False
        self._cover_repaint_timer = QTimer(self)
        self._cover_repaint_timer.setSingleShot(True)
        self._cover_repaint_timer.setInterval(0)
        self._cover_repaint_timer.timeout.connect(self._flush_cover_repaint)
        # 侧边栏宽度（可拖拽右边缘调整、记忆到 config）
        try:
            self._sidebar_w = int(self.config.player.get("sidebar_width", SIDEBAR_DEF_W))
        except (TypeError, ValueError):
            self._sidebar_w = SIDEBAR_DEF_W
        self._sidebar_w = max(SIDEBAR_MIN_W, min(SIDEBAR_MAX_W, self._sidebar_w))
        self._build()
        self._wire()
        self._apply_cover_overrides()
        # 启动预载上次歌单头部封面：不等歌单列表加载完，直接显示（自定义优先，否则磁盘缓存服务器封面）
        self._preload_header_cover()
        self.refresh_playlists()

    def _preload_header_cover(self) -> None:
        """按 config 的上次歌单信息提前设置头部大图，避免「歌单页没加载好阻塞封面」。"""
        pid = self.config.player.get("last_playlist_id", "")
        if not pid:
            return
        opix = self._get_override_pixmap(pid, 192)
        if opix is not None:
            self.song_header.set_local_cover(opix)
            return
        cid = self.config.player.get("last_playlist_cover_id", "")
        if cid:
            pix = self.covers.get(cid, 200)
            if pix:
                self.song_header.cover.set_pixmap(pix)
                self.song_header._cover_id = cid

    # ---------- 构建 ----------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        content = QHBoxLayout()
        content.setSpacing(14)
        content.setContentsMargins(16, 4, 16, 0)
        root.addLayout(content, 1)

        # ---- 侧边栏 ----
        sidebar = NeuFrame(self, radius=18)
        sidebar.setFixedWidth(self._sidebar_w)
        self.sidebar = sidebar
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(16, 12, 16, 14)
        sv.setSpacing(2)

        # 搜索框（侧边栏顶部）：Ctrl+F 聚焦；回车/防抖自动搜索；Esc 或清空退出搜索
        self.search_box = NeuLineEdit("", "搜索歌曲 (Ctrl+F)")
        self.search_box.setFixedHeight(36)
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setTextMargins(26, 0, 24, 0)  # 给左侧搜索图标与右侧清除按钮留位
        self._search_icon = self.search_box.addAction(
            icons.icon("search", theme.CURRENT["text_muted"], 15, stroke=2.0),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._search_icon.setToolTip("搜索")
        self._search_icon.triggered.connect(lambda: self._run_search(force=True))
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(300)  # 输入停顿 300ms 再发请求，避免逐字搜索
        self._search_debounce.timeout.connect(self._run_search)
        self.search_box.textChanged.connect(self._on_search_text)
        self.search_box.returnPressed.connect(lambda: self._run_search(force=True))
        sv.addWidget(self.search_box)
        sv.addSpacing(8)

        self.nav_home = NavItem("home", "首页")
        sv.addWidget(self.nav_home)
        self.nav_starred = NavItem("heart", "收藏")
        self.nav_recent = NavItem("clock", "最近播放")
        self.nav_artist = NavItem("artist", "歌手")
        self.nav_album = NavItem("album", "专辑")
        sv.addWidget(self.nav_starred)
        sv.addWidget(self.nav_recent)
        sv.addWidget(self.nav_artist)
        sv.addWidget(self.nav_album)
        sv.addSpacing(10)
        pl_header = QWidget()
        plh = QHBoxLayout(pl_header)
        plh.setContentsMargins(0, 0, 0, 0)
        plh.setSpacing(0)
        plh.addWidget(self._section_label("我的歌单"), 1)
        btn_reload_pl = NeuIconButton("refresh", px=13)
        btn_reload_pl.setFixedSize(22, 22)
        btn_reload_pl.setToolTip("重新加载歌单列表")
        btn_reload_pl.clicked.connect(lambda: self.refresh_playlists(preserve_current=True))
        plh.addWidget(btn_reload_pl)
        sv.addWidget(pl_header)

        self._pl_model = SimpleModel()
        self._pl_delegate = PlaylistDelegate(self.covers)
        self._pl_view = make_list_view(self._pl_model, self._pl_delegate)
        sv.addWidget(self._pl_view, 1)
        content.addWidget(sidebar)
        # 侧边栏右缘拖拽条（覆盖条，不占布局；位置由 _layout_sidebar_handle 跟随侧边栏）
        self._sb_resizer = SidebarResizer(self, self)
        self._sb_resizer.raise_()

        # A2：列表上下缘渐隐（有内容超出时提示还能滚动），鼠标穿透
        self._pl_fade = ListEdgeFade(self._pl_view, self._pl_view)

        # ---- 主内容区（多视图堆叠） ----
        self.content_stack = QStackedWidget()
        content.addWidget(self.content_stack, 1)

        # 视图 0：歌曲列表
        view_song = QWidget()
        vs = QVBoxLayout(view_song)
        vs.setContentsMargins(12, 14, 12, 12)
        vs.setSpacing(8)
        self.song_header = SongHeader()
        self.song_header.play_all.connect(self._play_all)
        self.song_header.play_random.connect(self._play_random)
        self.song_header.refresh_requested.connect(self._reload_playlist)
        vs.addWidget(self.song_header)
        self.list_header = SortHeader()
        vs.addWidget(self.list_header)
        self.song_model = SongModel()
        self.song_delegate = SongDelegate(self.covers)
        self.song_view = make_list_view(self.song_model, self.song_delegate)
        self.song_view.setSpacing(2)
        self.song_view.doubleClicked.connect(self._on_song_double_clicked)
        self.song_view.viewport().installEventFilter(self)
        self._song_fade = ListEdgeFade(self.song_view, self.song_view)
        vs.addWidget(self.song_view, 1)
        self.content_stack.addWidget(view_song)

        # 视图 1：专辑网格
        view_album = QWidget()
        va = QVBoxLayout(view_album)
        va.setContentsMargins(12, 14, 12, 12)
        va.setSpacing(10)
        ah = QHBoxLayout()
        self.album_back = NeuIconButton("back", px=16)
        self.album_back.setToolTip("返回")
        self.album_back.hide()
        self.album_back.clicked.connect(self._album_back)
        ah.addWidget(self.album_back)
        self.album_title = QLabel("专辑")
        f = QFont("Microsoft YaHei UI")
        f.setPointSizeF(15)
        f.setWeight(QFont.Weight.DemiBold)
        self.album_title.setFont(f)
        ah.addWidget(self.album_title)
        ah.addStretch(1)
        va.addLayout(ah)
        self.album_model = SimpleModel()
        self.album_delegate = AlbumDelegate(self.covers)
        self.album_view = make_list_view(self.album_model, self.album_delegate)
        self.album_view.setViewMode(QListView.ViewMode.IconMode)
        self.album_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.album_view.setMovement(QListView.Movement.Static)
        self.album_view.setUniformItemSizes(True)
        self.album_view.setSpacing(14)
        self.album_view.installEventFilter(self)
        self.album_view.clicked.connect(self._on_album_clicked)
        va.addWidget(self.album_view, 1)
        self.content_stack.addWidget(view_album)

        # 视图 2：歌手双栏（左窄列表 + 右歌曲列表）
        view_artist = QWidget()
        vat = QHBoxLayout(view_artist)
        vat.setContentsMargins(12, 14, 12, 12)
        vat.setSpacing(14)
        left_col = QVBoxLayout()
        left_col.setSpacing(8)
        self.artist_title = QLabel("歌手")
        self.artist_title.setFont(f)
        left_col.addWidget(self.artist_title)
        self.artist_model = SimpleModel()
        self.artist_delegate = ArtistDelegate(self.covers)
        self.artist_view = make_list_view(self.artist_model, self.artist_delegate)
        self.artist_view.setFixedWidth(236)
        self.artist_view.clicked.connect(self._on_artist_clicked)
        left_col.addWidget(self.artist_view, 1)
        vat.addLayout(left_col)
        right_col = QVBoxLayout()
        right_col.setSpacing(8)
        self.artist_header = SongHeader()
        self.artist_header.play_all.connect(self._play_artist_all)
        self.artist_header.play_random.connect(self._play_artist_random)
        right_col.addWidget(self.artist_header)
        self.artist_sort_header = SortHeader()
        right_col.addWidget(self.artist_sort_header)
        self.artist_song_model = SongModel()
        self.artist_song_delegate = SongDelegate(self.covers)
        self.artist_song_view = make_list_view(self.artist_song_model, self.artist_song_delegate)
        self.artist_song_view.setSpacing(2)
        self.artist_song_view.doubleClicked.connect(self._on_artist_song_double_clicked)
        self.artist_song_view.viewport().installEventFilter(self)
        right_col.addWidget(self.artist_song_view, 1)
        vat.addLayout(right_col, 1)
        self.content_stack.addWidget(view_artist)

        # 视图 3：占位
        view_ph = QWidget()
        vp = QVBoxLayout(view_ph)
        vp.addStretch(1)
        self.placeholder_label = QLabel("")
        f = QFont("Microsoft YaHei UI")
        f.setPointSizeF(11)
        self.placeholder_label.setFont(f)
        self.placeholder_label.setStyleSheet(f"color: {theme.CURRENT['text_muted']};")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vp.addWidget(self.placeholder_label)
        vp.addStretch(1)
        self.content_stack.addWidget(view_ph)

        # ---- 底部播放栏（与内容区同宽同留白；迷你歌词为悬浮重叠层，不占布局） ----
        bottom_wrap = QVBoxLayout()
        bottom_wrap.setContentsMargins(16, 16, 16, 16)
        bottom_wrap.setSpacing(0)
        self._bar = self._build_player_bar()
        bottom_wrap.addWidget(self._bar)
        root.addLayout(bottom_wrap)

        # 迷你歌词：叠加在内容区之上、播放栏之上，顶部渐变透明与 UI 重叠
        self.mini_lyrics = MiniLyrics(self)
        self.mini_lyrics.raise_()
        # B2：视图切换时「从底色淡入」（只画一层底色，不用离屏渲染）
        self._veil = FadeVeil(self)

    def _section_label(self, text: str, center: bool = True) -> QLabel:
        lb = QLabel(text)
        f = QFont("Microsoft YaHei UI")
        f.setPointSizeF(8.5)
        f.setWeight(QFont.Weight.DemiBold)
        lb.setFont(f)
        if center:
            lb.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lb.setStyleSheet(f"color: {theme.CURRENT['primary']}; padding-top: 2px;")
        else:
            lb.setStyleSheet(f"color: {theme.CURRENT['primary']}; padding-left: 10px; padding-top: 2px;")
        return lb

    # ---------- 底部播放栏 ----------
    def _build_player_bar(self) -> QWidget:
        bar = NeuFrame(self, radius=18)
        bar.setFixedHeight(140)
        b = QVBoxLayout(bar)
        # 内边距对齐 8px 栅格（DESIGN.md spacing.base）；左 = 下 = 16，保证封面左右下留白一致
        b.setContentsMargins(16, 16, 16, 16)
        b.setSpacing(4)

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
        b.addLayout(row1)
        # 弹性间距吸收余量：让控制行（含封面）紧贴下内边距，
        # 从而封面「左留白 == 下留白」都等于 16px
        b.addStretch(1)

        # 控制行：左/右等宽拉伸，中间控制真居中
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        # 左侧信息：封面 + [爱心与歌名同行 / 歌手与爱心左对齐]
        left = QWidget()
        ll = QHBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(12)  # sm：封面与文字间距（DESIGN.md spacing.sm）
        self.cover = CoverArt(radius=12)
        self.cover.setFixedSize(76, 76)
        self.cover.clicked.connect(lambda: self._emit_open_immersive())
        ll.addWidget(self.cover)
        info = QVBoxLayout()
        info.setSpacing(4)  # xs：歌名与歌手间距（DESIGN.md spacing.xs）
        info.addStretch(1)  # 文字块在封面高度内垂直居中（24+4+20=48 vs 封面 76）
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self.like_btn = NeuIconButton("heart", px=15)
        self.like_btn.accent_color = theme.CURRENT["danger"]
        self.like_btn.setFixedSize(22, 22)
        self.like_btn.clicked.connect(self._toggle_like)
        title_row.addWidget(self.like_btn)
        self.now_title = MarqueeLabel()
        ft = QFont("Microsoft YaHei UI")
        ft.setPointSizeF(12)  # = 16px，DESIGN.md body-md
        ft.setWeight(QFont.Weight.Medium)
        self.now_title.setFont(ft)
        self.now_title.setFixedHeight(24)  # body-md lineHeight
        self.now_title.setMinimumWidth(120)
        title_row.addWidget(self.now_title, 1)
        info.addLayout(title_row)
        self.now_artist = MarqueeLabel()
        fa = QFont("Microsoft YaHei UI")
        fa.setPointSizeF(10.5)  # = 14px，DESIGN.md label-md
        self.now_artist.setFont(fa)
        self.now_artist.setFixedHeight(20)  # label-md lineHeight
        self.now_artist.set_color(theme.CURRENT["text_muted"])
        self.now_artist.setMinimumWidth(120)
        self.now_artist.setCursor(Qt.CursorShape.PointingHandCursor)
        self.now_artist.setToolTip("点击查看歌手")
        self.now_artist.clicked.connect(self._open_now_artist)
        info.addWidget(self.now_artist)
        info.addStretch(1)
        ll.addLayout(info, 1)
        row2.addWidget(left, 1)

        # 中间控制（不参与拉伸，靠左右等宽居中）
        center = QWidget()
        cl = QHBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)
        self.btn_mode = NeuIconButton("repeat", px=19)
        self.btn_mode.setToolTip("播放模式")
        self.btn_mode.clicked.connect(self._open_mode_menu)
        self.btn_prev = SkipButton(-1, px=19)
        self.btn_prev.setToolTip("上一曲")
        self.btn_prev.clicked.connect(lambda: self.player.prev())
        self.btn_play = PlayButton(px=42)
        self.btn_play.clicked.connect(lambda: self.player.toggle())
        self.btn_next = SkipButton(1, px=19)
        self.btn_next.setToolTip("下一曲")
        self.btn_next.clicked.connect(lambda: self.player.next())
        for w_ in (self.btn_mode, self.btn_prev, self.btn_play, self.btn_next):
            cl.addWidget(w_)
        row2.addWidget(center)

        # 右侧：歌词入口 + 音量（右对齐）
        right = QWidget()
        rl = QHBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)
        rl.addStretch(1)
        self.btn_lyrics = NeuIconButton("lyrics", px=19)
        self.btn_lyrics.setToolTip("歌词（沉浸页）")
        self.btn_lyrics.clicked.connect(lambda: self._emit_open_immersive())
        rl.addWidget(self.btn_lyrics)
        self._vol = VolumeControl(self, self.player)
        rl.addWidget(self._vol)
        row2.addWidget(right, 1)
        b.addLayout(row2)
        return bar

    # ---------- 信号接线 ----------
    def _wire(self) -> None:
        self.nav_home.clicked.connect(self.show_recent_albums)
        self.nav_starred.clicked.connect(self.show_starred)
        self.nav_recent.clicked.connect(self.show_play_queue)
        self.nav_artist.clicked.connect(self.show_artists)
        self.nav_album.clicked.connect(self.show_albums)

        self._pl_view.clicked.connect(self._on_playlist_clicked)
        self._pl_view.doubleClicked.connect(self._on_playlist_double_clicked)
        self.song_header.edit_cover_requested.connect(self._edit_cover)
        self.list_header.changed.connect(lambda col, mode: self._sort_songs(col, mode))
        self.artist_sort_header.changed.connect(lambda col, mode: self._sort_artist_songs(col, mode))

        self.player.song_changed.connect(self._on_song_changed)
        self.player.state_changed.connect(self._on_state_changed)
        self.player.position_changed.connect(self._on_position)
        self.player.duration_changed.connect(self._on_duration)
        self.player.mode_changed.connect(self._on_mode_changed)
        self.progress.valueChanged.connect(lambda v: self.player.seek(v))
        self.progress.hoverValueChanged.connect(lambda v: self.time_cur.setText(_fmt_ms(v)))
        self.progress.hoverEnded.connect(self._restore_time)
        self.covers.loaded.connect(self._on_cover_loaded)
        self.lyrics.loaded.connect(self._on_lyrics_loaded)
        # 搜索框内按 Esc：清空并退出搜索，回到搜索前的页面
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.search_box)
        esc.setContext(Qt.ShortcutContext.WidgetShortcut)
        esc.activated.connect(self._exit_search)

    def _restore_time(self) -> None:
        self.time_cur.setText(_fmt_ms(self.player.media.position()))

    def _on_cover_loaded(self, cover_id: str, pix) -> None:
        # 每张封面加载完成都立刻重绘 5 个视图代价过高（打开 200 首歌单 ≈ 上千次整视口重绘），
        # 这里合并为「每轮事件循环至多重绘一次」
        if not self._cover_repaint_pending:
            self._cover_repaint_pending = True
            self._cover_repaint_timer.start()
        # 本地自定义封面已显示时不覆盖
        if cover_id == self.song_header.current_cover_id() and not self.song_header.is_local_cover():
            self.song_header.cover.set_pixmap(pix)
        if cover_id == self.artist_header.current_cover_id():
            self.artist_header.cover.set_pixmap(pix)
        if cover_id == self._now_cover_id:
            self.cover.set_pixmap(pix)

    def _flush_cover_repaint(self) -> None:
        self._cover_repaint_pending = False
        self.song_view.viewport().update()
        self.artist_song_view.viewport().update()
        self.album_view.viewport().update()
        self.artist_view.viewport().update()
        self._pl_view.viewport().update()

    def _queue_cover_prefetch(self, cover_ids: list) -> None:
        self._cover_prefetch_queue = list(cover_ids)
        if self._cover_prefetch_queue:
            self._cover_prefetch_timer.start()

    def _prefetch_cover_chunk(self) -> None:
        """每轮只取少量封面，避免同步磁盘读取把 UI 线程堵住。"""
        for _ in range(8):
            if not self._cover_prefetch_queue:
                self._cover_prefetch_timer.stop()
                return
            cid = self._cover_prefetch_queue.pop(0)
            if cid:
                self.covers.get(cid, 200)

    # ---------- 歌词 ----------
    def _on_lyrics_loaded(self, song_id: str, lines) -> None:
        # 快速切歌时旧线程的结果可能晚到：只接受当前播放歌曲的歌词
        cur = self._current_song()
        if cur is None or cur.id != song_id:
            return
        self._lyric_lines = lines

    def _update_mini_lyrics(self) -> None:
        if not self._lyric_lines:
            self.mini_lyrics.set_text("")
            return
        ms = self.player.media.position()
        current = ""
        timed = False
        for line in self._lyric_lines:
            if line.time_ms < 0:
                continue
            timed = True
            if line.time_ms <= ms:
                current = line.text
            else:
                break
        if not timed:
            # 无时间轴歌词：显示第一行
            current = self._lyric_lines[0].text
        self.mini_lyrics.set_text(current)

    # ---------- 歌单 ----------
    def set_client(self, client) -> None:
        """重新连接后更新客户端引用并复位本次运行的歌单缓存（不重建 UI、不改样式）。"""
        self.client = client
        self._playlist_cache.clear()  # 防止旧服务器/旧状态的歌单内容命中缓存

    def _cache_playlist(self, playlist_id: str, songs: list) -> None:
        """写入歌单缓存并做容量上限（防长期浏览大量歌单后内存单调增长）。"""
        self._playlist_cache[playlist_id] = list(songs)
        while len(self._playlist_cache) > MAX_PLAYLIST_CACHE:
            oldest = next(iter(self._playlist_cache))
            if oldest == self.active_playlist_id:
                break  # 正在看的歌单不淘汰
            self._playlist_cache.pop(oldest, None)

    def refresh_playlists(self, preserve_current: bool = False, reload_songs: bool = False) -> None:
        """重新拉取服务器歌单列表刷新侧边栏。

        preserve_current=True 时刷新后仍停留在当前歌单；
        reload_songs=True 时顺带强制重载当前歌单歌曲（「重新加载」按钮用，避免二次加载）。
        """
        t = DataThread(self.client.get_playlists, self)
        t.result.connect(lambda payload, pc=preserve_current, rs=reload_songs:
                         self._on_playlists_loaded(payload, pc, rs))
        t.finished.connect(lambda: self._clean_thread(t))
        self._threads.append(t)
        t.start()

    def _on_playlists_loaded(self, payload, preserve_current: bool = False, reload_songs: bool = False) -> None:
        kind, data = payload
        if kind != "ok":
            return
        # 「我喜欢」歌单置顶（按名称匹配），其余保持服务器返回顺序
        like = [p for p in data if (p.name or "").strip() == "我喜欢"]
        rest = [p for p in data if (p.name or "").strip() != "我喜欢"]
        data = like + rest
        self.playlists = data
        items = [(p.id, p.name, int(p.song_count or 0), p.cover_id) for p in data]
        self._pl_model.set_items(items)
        # 预取歌单封面（200px）——分片进行，避免几十上百个封面同步读磁盘阻塞 UI 线程
        self._queue_cover_prefetch([p.cover_id for p in data if p.cover_id])
        if data:
            # 默认打开上次的歌单（若无则第一个），并准备恢复上次歌曲
            if preserve_current and self.active_playlist_id and any(p.id == self.active_playlist_id for p in data):
                target = self.active_playlist_id  # 手动刷新：停留在当前打开的歌单
            else:
                target = self.config.player.get("last_playlist_id", "") or data[0].id
                if not any(p.id == target for p in data):
                    target = data[0].id
                self._restore_pending = True  # 仅启动/重新连接场景标记恢复
            self.load_playlist(target, force=reload_songs)
        else:
            self._show_placeholder("服务器上没有歌单，请先在飞牛音乐中添加")
        # 后台补充真实歌曲数（部分服务端 getPlaylists 不带 songCount）
        if data:
            t = DataThread(lambda: self.client.get_playlist_counts(data), self)
            t.result.connect(self._on_playlist_counts)
            t.finished.connect(lambda: self._clean_thread(t))
            self._threads.append(t)
            t.start()

    def _on_playlist_counts(self, payload) -> None:
        kind, counts = payload
        if kind != "ok" or not counts:
            return
        items = self._pl_model._items
        for row, it in enumerate(items):
            if len(it) < 3:
                continue
            real = int(counts.get(it[0], it[2] or 0) or 0)
            if int(it[2] or 0) != real:
                self._pl_model.update_item(row, (it[0], it[1], real, it[3]))

    def load_playlist(self, playlist_id: str, force: bool = False, play_after: bool = False) -> None:
        """加载歌单：立即显示「加载中」；命中缓存则瞬时填充，否则两段式加载——
        第一段快速取前 50 首立即可用，第二段后台拉全量后替换，提高打开反应速度。

        play_after 仅由双击歌单传入：表示这一趟加载完成后自动「播放全部」。
        每次加载都会重设该意图，因此加载失败或用户改用单击都不会残留（避免单击却自动开播）。
        """
        self._play_after_pid = playlist_id if play_after else ""
        self._new_view_token()  # 切歌单也换视图，令导航等其他请求的迟到结果失效
        self.active_playlist_id = playlist_id
        self._pl_delegate.set_current(playlist_id)
        self._pl_view.viewport().update()
        self.list_header.reset()
        pl = next((p for p in self.playlists if p.id == playlist_id), None)
        # 立即显示加载中状态（也解决从歌手页跳回时的“点了没反应”）
        self._show_loading(pl.name if pl else "歌单", pl.cover_id if pl else "")
        if not force and playlist_id in self._playlist_cache:
            QTimer.singleShot(0, lambda: self._apply_cached_playlist(playlist_id))
            return
        # 第一段：快速前 50（不触发 Jellyfin 补全，秒回）
        t = DataThread(lambda: self.client.get_playlist_songs(playlist_id, jellyfin=False), self)
        t.result.connect(lambda payload, pip=playlist_id, ppl=pl, f=force: self._on_fast_result(payload, pip, ppl, f))
        t.finished.connect(lambda: self._clean_thread(t))
        self._threads.append(t)
        t.start()

    def _on_fast_result(self, payload, playlist_id: str, pl, force: bool = False) -> None:
        """快速段完成：立即填充前 50 首，随后启动全量加载。"""
        kind, data = payload
        if kind != "ok" or not data:
            return
        if playlist_id != self.active_playlist_id:
            return
        total = int(getattr(pl, "song_count", 0) or 0) if pl else 0
        # force=True（用户点「重新加载」）时必须继续跑全量，不能因为旧缓存就直接收尾，
        # 否则刷新按钮拿不到服务器最新数据
        full_now = (bool(total > 0 and len(data) >= total)
                    or (not force and playlist_id in self._playlist_cache))
        self._show_playlist_songs(data, pl, fast=not full_now)
        if full_now:
            # 快速段本身就是全量（服务器支持分页 / 已有缓存）→ 直接收尾（_show_playlist_songs 已非 fast）
            if playlist_id not in self._playlist_cache:
                self._cache_playlist(playlist_id, data)
            return
        # 第二段：全量（含 Jellyfin 补全）
        t2 = DataThread(lambda: self.client.get_playlist_songs(playlist_id), self)
        t2.result.connect(lambda payload2, pid=playlist_id, ppl=pl: self._on_full_result(payload2, pid, ppl))
        t2.finished.connect(lambda: self._clean_thread(t2))
        self._threads.append(t2)
        t2.start()

    def _on_full_result(self, payload, playlist_id: str, pl) -> None:
        kind, data = payload
        if kind != "ok" or not data:
            return
        self._cache_playlist(playlist_id, data)
        if playlist_id != self.active_playlist_id:
            return
        if len(data) > (self.song_model.rowCount() if hasattr(self, "song_model") else 0):
            self._show_playlist_songs(data, pl)
        self._finalize_load()

    def _apply_cached_playlist(self, playlist_id: str) -> None:
        if playlist_id != self.active_playlist_id:
            return
        data = self._playlist_cache.get(playlist_id)
        if data is None:
            return
        pl = next((p for p in self.playlists if p.id == playlist_id), None)
        self._show_playlist_songs(data, pl)
        self._finalize_load()

    def _show_playlist_songs(self, data: list, pl, fast: bool = False) -> None:
        if pl:
            meta = f"{len(data)} 首"
            if pl.duration:
                meta += f" · {_fmt_dur(pl.duration)}"
            cover_id = pl.cover_id
            # 侧边栏歌单封面兜底：服务器未给封面时用第一首歌的封面
            if not cover_id and data and data[0].cover_id:
                cover_id = data[0].cover_id
                self._update_playlist_cover(pl.id, cover_id)
            # 歌单自定义封面优先：有本地图则直接显示本地图，不再显示服务器封面（避免先闪服务器封面）
            opix = self._get_override_pixmap(pl.id, 192)
            if opix is not None:
                self._show_songs(data, pl.name, meta, "")
                self.song_header._cover_id = cover_id  # 保留真实 cover_id，供关闭时保存
                self.song_header.set_local_cover(opix)
            else:
                self._show_songs(data, pl.name, meta, cover_id)
        else:
            self._show_songs(data, "歌单", f"{len(data)} 首", "")
        # 快速段（前 50）不触发播放/恢复，等全量段完成后统一收尾
        if fast:
            return
        self._finalize_load()

    def _finalize_load(self) -> None:
        """全量歌单就绪后的统一收尾：双击自动播放全部 + 启动恢复上次歌曲。"""
        # 双击歌单 → 加载完成后直接开始播放全部（只对当时双击的那个歌单生效：
        # 若期间用户又单击了别的歌单 / 加载失败，意图作废，避免“单击却自动开播”）
        if self._play_after_pid:
            if self._play_after_pid == self.active_playlist_id:
                self._play_after_pid = ""
                if self.current_songs:
                    self._play_all()
            else:
                self._play_after_pid = ""
        # 启动恢复：首次歌单加载完成后显示上次歌曲
        self._maybe_restore()

    def _maybe_restore(self) -> None:
        """启动后恢复上次播放的歌曲到播放栏（不自动播放，并恢复进度）。"""
        if not self._restore_pending:
            return
        self._restore_pending = False
        sid = self.config.player.get("last_song_id", "")
        if not sid or not self.current_songs:
            return
        song = next((s for s in self.current_songs if s.id == sid), None)
        if song:
            self.player.restore(self.current_songs, song, int(self.config.player.get("last_position", 0) or 0))

    def _show_loading(self, title: str, cover_id: str = "") -> None:
        """跳转到歌单页并显示“正在加载…”，随后由加载结果替换为真实内容。"""
        self.current_songs = []
        self._base_songs = []
        self.song_model.set_songs([])
        self.song_header.set_data(title, "正在加载…", cover_id)
        self.list_header.show()
        self.content_stack.setCurrentIndex(_VIEW_SONG)
        # 歌单自定义封面优先
        opix = self._get_override_pixmap(self.active_playlist_id, 192)
        if opix is not None:
            self.song_header.set_local_cover(opix)
        elif cover_id:
            pix = self.covers.get(cover_id, 200)
            if pix:
                self.song_header.cover.set_pixmap(pix)

    def _reload_playlist(self) -> None:
        """随机播放旁刷新按钮：强制重新加载当前歌单，并同步刷新侧边栏歌单列表。"""
        if self._search_active:
            self._run_search(force=True)  # 搜索结果页的刷新 = 重搜当前关键词
            return
        # 服务器上新增/删除歌单后，仅重载歌曲看不到变化 → 先刷新侧边栏歌单列表（保留当前歌单），
        # 并让同一次刷新顺带强制重载当前歌单歌曲（reload_songs=True）——避免这里再调一次
        # load_playlist 造成同一歌单并发跑两套「快取+全量」请求
        self.refresh_playlists(preserve_current=True, reload_songs=True)

    # ---------- 歌单自定义封面 ----------
    def _path_to_pixmap(self, path: str, size: int = 200) -> QPixmap | None:
        if not path:
            return None
        p = QPixmap(path)
        if p.isNull():
            return None
        return p.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation)

    def _get_override_pixmap(self, playlist_id: str, size: int = 200) -> QPixmap | None:
        """歌单自定义封面优先（custom 模式且有本地文件）。"""
        ov = self._cover_overrides.get(playlist_id)
        if not ov or ov.get("mode") != "custom":
            return None
        path = str(ov.get("path") or "")
        return self._path_to_pixmap(path, size)

    def _apply_cover_overrides(self) -> None:
        """把 custom 模式的本地封面路径注入侧边栏委托。"""
        mapping = {
            pid: str(ov.get("path") or "")
            for pid, ov in self._cover_overrides.items()
            if ov.get("mode") == "custom" and Path(str(ov.get("path") or "")).exists()
        }
        self._pl_delegate.set_local_covers(mapping)
        self._pl_view.viewport().update()

    def _save_cover_overrides(self) -> None:
        self.config.player["playlist_covers"] = self._cover_overrides
        self.config.save()

    def _edit_cover(self) -> None:
        """刷新按钮右侧编辑图标：选择显示服务器封面或自定义本地封面。"""
        pid = self.active_playlist_id
        if not pid:
            return
        pl = next((p for p in self.playlists if p.id == pid), None)
        title = pl.name if pl else "歌单"
        ov = self._cover_overrides.get(pid) or {}
        current_mode = ov.get("mode", "auto")
        menu = QMenu(self)
        act_pick = menu.addAction("选择本地图片…")
        menu.addSeparator()
        act_server = menu.addAction("使用服务器封面")
        act_custom = menu.addAction("使用自定义封面")
        for act, mode in ((act_server, "auto"), (act_custom, "custom")):
            act.setCheckable(True)
            act.setChecked(current_mode == mode)
        if current_mode == "custom":
            act_pick.setIcon(icons.pixmap("check", theme.CURRENT["primary_text"], 16, stroke=2))
        pos = self.song_header.btn_edit_cover.mapToGlobal(
            QPoint(0, self.song_header.btn_edit_cover.height() + 4))
        chosen = menu.exec(pos)
        if chosen is act_pick:
            self._pick_cover_image(pid)
        elif chosen is act_server:
            self._cover_overrides[pid] = {"mode": "auto", "path": ov.get("path", "")}
            self._save_cover_overrides()
            self._apply_cover_overrides()
            self._refresh_header_cover(pid, title)
        elif chosen is act_custom:
            path = ov.get("path", "")
            if not path or not Path(str(path)).exists():
                QMessageBox.information(self, "自定义封面",
                                        f"请先为「{title}」选择一张本地图片。")
                self._pick_cover_image(pid)
                return
            self._cover_overrides[pid] = {"mode": "custom", "path": path}
            self._save_cover_overrides()
            self._apply_cover_overrides()
            self._refresh_header_cover(pid, title)

    def _pick_cover_image(self, playlist_id: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择封面图片", "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        pl = next((p for p in self.playlists if p.id == playlist_id), None)
        title = pl.name if pl else "歌单"
        try:
            suffix = Path(path).suffix.lower() or ".jpg"
            dst = self._cover_dir / f"pl_{playlist_id}{suffix}"
            copy2(path, str(dst))
        except OSError as exc:  # noqa: BLE001
            QMessageBox.warning(self, "自定义封面", f"保存图片失败：{exc}")
            return
        self._cover_overrides[playlist_id] = {"mode": "custom", "path": str(dst)}
        self._save_cover_overrides()
        self._apply_cover_overrides()
        self._refresh_header_cover(playlist_id, title)

    def _refresh_header_cover(self, playlist_id: str, title: str) -> None:
        """刷新侧边栏与歌单头部封面显示。"""
        self._pl_view.viewport().update()
        if playlist_id != self.active_playlist_id:
            return
        pix = self._get_override_pixmap(playlist_id, 192)
        if pix is not None:
            self.song_header.cover.set_pixmap(pix)
            return
        # 回退服务器封面
        pl = next((p for p in self.playlists if p.id == playlist_id), None)
        if pl and pl.cover_id:
            sp = self.covers.get(pl.cover_id, 200)
            if sp:
                self.song_header.cover.set_pixmap(sp)

    def _update_playlist_cover(self, playlist_id: str, cover_id: str) -> None:
        items = self._pl_model._items
        for row, it in enumerate(items):
            if len(it) >= 4 and it[0] == playlist_id and not it[3]:
                self._pl_model.update_item(row, (it[0], it[1], it[2], cover_id))
                self._pl_view.viewport().update()
                break

    # ---------- 专辑 ----------
    def show_albums(self) -> None:
        self._set_nav_active(self.nav_album)
        self._album_back_show(False)
        token = self._new_view_token()
        t = DataThread(lambda: self.client.get_albums("newest", 200), self)
        t.result.connect(lambda payload, tk=token: self._on_albums_loaded(payload, tk))
        t.finished.connect(lambda: self._clean_thread(t))
        self._threads.append(t)
        t.start()

    def show_recent_albums(self) -> None:
        self._set_nav_active(self.nav_home)
        self._album_back_show(False)
        token = self._new_view_token()
        t = DataThread(lambda: self.client.get_albums("newest", 60), self)
        t.result.connect(lambda payload, tk=token: self._on_recent_albums_loaded(payload, tk))
        t.finished.connect(lambda: self._clean_thread(t))
        self._threads.append(t)
        t.start()

    def _on_albums_loaded(self, payload, token: int) -> None:
        if token != self._view_token:
            return  # 用户已切到别的视图，丢弃迟到结果
        kind, data = payload
        if kind == "ok":
            self._show_albums(data, "专辑")

    def _on_recent_albums_loaded(self, payload, token: int) -> None:
        if token != self._view_token:
            return
        kind, data = payload
        if kind == "ok":
            self._show_albums(data, "最近专辑")

    def _on_album_clicked(self, index: QModelIndex) -> None:
        album = self.album_model.data(index, Qt.ItemDataRole.UserRole)
        if album:
            token = self._new_view_token()
            t = DataThread(lambda: self.client.get_album(album.id), self)
            t.result.connect(lambda payload, a=album, tk=token: self._on_album_songs(payload, a, tk))
            t.finished.connect(lambda: self._clean_thread(t))
            self._threads.append(t)
            t.start()

    def _on_album_songs(self, payload, album: Album, token: int) -> None:
        if token != self._view_token:
            return
        kind, data = payload
        if kind != "ok":
            return
        meta = f"{album.artist} · {len(data)} 首"
        self._show_songs(data, album.name, meta, album.cover_id)

    def open_album(self, album_id: str, album_name: str, artist: str = "", cover_id: str = "") -> None:
        """从歌曲行点击专辑名：跳到专辑并展示其歌曲。"""
        token = self._new_view_token()
        t = DataThread(lambda: self.client.get_album(album_id), self)
        t.result.connect(lambda payload, an=album_name, ar=artist, cid=cover_id, tk=token:
                         self._on_album_songs_id(payload, an, ar, cid, tk))
        t.finished.connect(lambda: self._clean_thread(t))
        self._threads.append(t)
        t.start()

    def _on_album_songs_id(self, payload, album_name: str, artist: str, cover_id: str, token: int) -> None:
        if token != self._view_token:
            return
        kind, data = payload
        if kind != "ok":
            return
        meta = (f"{artist} · {len(data)} 首") if artist else f"{len(data)} 首"
        self._show_songs(data, album_name, meta, cover_id)

    def open_artist(self, artist_id: str, artist_name: str) -> None:
        """从歌曲行点击歌手名：跳到歌手页，填充并定位左侧列表、选中该歌手，展示其歌曲。"""
        self._pending_artist_id = artist_id
        self._pending_artist_name = artist_name
        self._set_nav_active(self.nav_artist)
        self._album_back_show(False)
        self.content_stack.setCurrentIndex(_VIEW_ARTIST)
        self.list_header.hide()
        if self.artist_model._items:
            self._select_artist_and_load(artist_id, artist_name)
        else:
            # 左侧歌手列表未加载 → 先加载列表再定位
            token = self._new_view_token()
            t = DataThread(self.client.get_artists, self)
            t.result.connect(lambda payload, tk=token: self._on_artists_loaded_for_jump(payload, tk))
            t.finished.connect(lambda: self._clean_thread(t))
            self._threads.append(t)
            t.start()

    def _on_artists_loaded_for_jump(self, payload, token: int) -> None:
        if token != self._view_token:
            return
        kind, data = payload
        if kind != "ok":
            return
        self.artist_model.set_items(list(data))
        self.artist_title.setText(f"歌手（{len(data)}）")
        self.content_stack.setCurrentIndex(_VIEW_ARTIST)
        self.list_header.hide()
        aid = getattr(self, "_pending_artist_id", "")
        name = getattr(self, "_pending_artist_name", "")
        if aid:
            self._select_artist_and_load(aid, name)

    def _select_artist_and_load(self, artist_id: str, artist_name: str) -> None:
        """在左侧列表中定位/选中歌手，并加载其歌曲到右侧。"""
        token = self._new_view_token()
        artist = next((a for a in self.artist_model._items if a.id == artist_id), None)
        if artist is None:
            artist = Artist(id=artist_id, name=artist_name)
        row = self.artist_model._items.index(artist) if artist in self.artist_model._items else 0
        idx = self.artist_model.index(max(0, row), 0)
        self.artist_view.setCurrentIndex(idx)
        self.artist_view.scrollTo(idx)
        self.artist_delegate.set_current(artist_id)
        self.artist_view.viewport().update()
        # 展示该歌手歌曲
        self.artist_header.set_data(artist.name, "正在加载…", "")
        self.artist_song_model.set_songs([])
        t = DataThread(lambda: self.client.get_artist_songs(artist.id), self)
        t.result.connect(lambda payload, a=artist, tk=token: self._on_artist_songs(payload, a, tk))
        t.finished.connect(lambda: self._clean_thread(t))
        self._threads.append(t)
        t.start()

    # ---------- 歌手（双栏） ----------
    def show_artists(self) -> None:
        self._set_nav_active(self.nav_artist)
        self._album_back_show(False)
        token = self._new_view_token()
        t = DataThread(self.client.get_artists, self)
        t.result.connect(lambda payload, tk=token: self._on_artists_loaded(payload, tk))
        t.finished.connect(lambda: self._clean_thread(t))
        self._threads.append(t)
        t.start()

    def _on_artists_loaded(self, payload, token: int) -> None:
        if token != self._view_token:
            return
        kind, data = payload
        if kind != "ok":
            return
        artists = list(data)
        self.artist_model.set_items(artists)
        self.artist_title.setText(f"歌手（{len(artists)}）· 统计歌曲数中…")
        self.content_stack.setCurrentIndex(_VIEW_ARTIST)
        self.list_header.hide()
        # 快速聚合歌曲数（合并多种专辑列表，秒级完成）并按降序重排
        t = DataThread(lambda: self.client.get_artist_counts_fast(artists), self)
        t.result.connect(lambda payload: self._on_artist_counts(payload, artists))
        t.finished.connect(lambda: self._clean_thread(t))
        self._threads.append(t)
        t.start()

    def _on_artist_counts(self, payload, artists) -> None:
        kind, data = payload
        if kind != "ok":
            return
        counts = data
        ranked = sorted(artists, key=lambda a: counts.get(a.id, 0), reverse=True)
        for a in ranked:
            a.album_count = counts.get(a.id, 0)
        self.artist_model.set_items(ranked)
        self.artist_title.setText(f"歌手（{len(artists)}）")

    def _on_artist_clicked(self, index: QModelIndex) -> None:
        artist = self.artist_model.data(index, Qt.ItemDataRole.UserRole)
        if artist:
            token = self._new_view_token()
            self.artist_delegate.set_current(artist.id)
            self.artist_view.viewport().update()
            self.artist_header.set_data(artist.name, f"正在加载…", "")
            self.artist_song_model.set_songs([])
            t = DataThread(lambda: self.client.get_artist_songs(artist.id), self)
            t.result.connect(lambda payload, a=artist, tk=token: self._on_artist_songs(payload, a, tk))
            t.finished.connect(lambda: self._clean_thread(t))
            self._threads.append(t)
            t.start()

    def _on_artist_songs(self, payload, artist: Artist, token: int) -> None:
        if token != self._view_token:
            return  # 用户已切到别的歌手/视图，丢弃迟到结果（否则右侧内容与左侧选中项不一致）
        kind, data = payload
        if kind != "ok":
            self.artist_header.set_data(artist.name, "加载失败", "")
            return
        self.artist_songs = data
        self._base_artist_songs = list(data)
        self.artist_sort_header.reset()
        self.artist_song_model.set_songs(data)
        meta = f"{len(data)} 首" + (f" · 专辑 {artist.album_count}" if artist.album_count else "")
        # 大头像优先用歌手头像，缺失时兜底用第一首歌封面
        cover_id = artist.cover_id or (data[0].cover_id if data else "")
        self.artist_header.set_data(artist.name, meta, cover_id)
        if cover_id:
            pix = self.covers.get(cover_id, 200)
            if pix:
                self.artist_header.cover.set_pixmap(pix)

    def _on_artist_song_double_clicked(self, index: QModelIndex) -> None:
        if self.artist_songs:
            self.player.set_queue(self.artist_songs, index.row())

    def _play_artist_all(self) -> None:
        if self.artist_songs:
            self.player.set_queue(self.artist_songs, 0)

    def _play_artist_random(self) -> None:
        if not self.artist_songs:
            return
        import random as _r

        self.player.set_mode(MODE_RANDOM)
        self.player.set_queue(self.artist_songs, _r.randrange(len(self.artist_songs)))

    def _album_back(self) -> None:
        self.show_artists()

    def _album_back_show(self, on: bool) -> None:
        self.album_back.setVisible(on)

    # ---------- 搜索 ----------
    def focus_search(self) -> None:
        """快捷键入口：聚焦搜索框并全选，方便直接改写关键词。"""
        self.search_box.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_box.selectAll()

    def _on_search_text(self, text: str) -> None:
        if not (text or "").strip():
            self._exit_search()  # 清空输入即退出搜索
            return
        self._search_debounce.start()

    def _run_search(self, force: bool = False) -> None:
        """执行搜索：结果复用歌曲列表视图展示。force=True 时同关键词也重新请求。"""
        query = self.search_box.text().strip()
        if not query:
            self._exit_search()
            return
        if not force and self._search_active and query == self._search_query:
            return  # 关键词未变且已有结果，避免重复请求
        if not self._search_active:
            self._search_active = True
            self._search_prev_nav = self._nav_active  # 记住搜索前的导航，供 Esc 恢复
        self._search_query = query
        self._search_debounce.stop()
        token = self._new_view_token()
        # 立即给出「正在搜索」反馈
        self.current_songs = []
        self._base_songs = []
        self.song_model.set_songs([])
        self.song_header.set_data(f"搜索：{query}", "正在搜索…", "")
        self.list_header.show()
        self.content_stack.setCurrentIndex(_VIEW_SONG)
        t = DataThread(lambda: self.client.search(query), self)
        t.result.connect(lambda payload, tk=token, qq=query: self._on_search_loaded(payload, tk, qq))
        t.finished.connect(lambda: self._clean_thread(t))
        self._threads.append(t)
        t.start()

    def _on_search_loaded(self, payload, token: int, query: str) -> None:
        # 双保险：令牌已变（用户切走）或关键词已被改写 → 丢弃结果
        if token != self._view_token or self.search_box.text().strip() != query:
            return
        kind, data = payload
        if kind != "ok":
            self.song_header.set_data(f"搜索：{query}", "搜索失败", "")
            self._show_placeholder(f"搜索失败：{data}")
            return
        songs, albums, artists = data
        if songs:
            extra = []
            if albums:
                extra.append(f"专辑 {len(albums)}")
            if artists:
                extra.append(f"歌手 {len(artists)}")
            meta = f"{len(songs)} 首" + (" · " + " · ".join(extra) if extra else "")
            self._show_songs(songs, f"搜索：{query}", meta)
        else:
            self._show_placeholder(f"未找到与「{query}」相关的歌曲")

    def _exit_search(self) -> None:
        """退出搜索并回到搜索前的页面（Esc / 清空输入 / 点击左侧图标）。"""
        if not self._search_active:
            return
        nav = self._search_prev_nav
        self._cancel_search_silently()
        self._restore_nav_view(nav)

    def _cancel_search_silently(self) -> None:
        """静默清理搜索状态（不恢复视图，用于用户改点导航/歌单时）。"""
        if not self._search_active:
            return
        self._search_active = False
        self._search_query = ""
        self._search_prev_nav = None
        self._search_debounce.stop()
        if self.search_box.text():
            self.search_box.blockSignals(True)
            self.search_box.clear()
            self.search_box.blockSignals(False)

    def _restore_nav_view(self, nav) -> None:
        """按导航项恢复视图；无导航项时回到当前歌单。"""
        if nav is self.nav_home:
            self.show_recent_albums()
        elif nav is self.nav_starred:
            self.show_starred()
        elif nav is self.nav_recent:
            self.show_play_queue()
        elif nav is self.nav_artist:
            self.show_artists()
        elif nav is self.nav_album:
            self.show_albums()
        elif self.active_playlist_id:
            self.load_playlist(self.active_playlist_id)  # 命中缓存，瞬时恢复
        else:
            self.show_recent_albums()

    # ---------- 收藏 / 最近播放 / 搜索 ----------
    def show_starred(self) -> None:
        self._set_nav_active(self.nav_starred)
        token = self._new_view_token()
        t = DataThread(self.client.get_starred, self)
        t.result.connect(lambda payload, tk=token: self._on_starred_loaded(payload, tk))
        t.finished.connect(lambda: self._clean_thread(t))
        self._threads.append(t)
        t.start()

    def _on_starred_loaded(self, payload, token: int) -> None:
        if token != self._view_token:
            return  # 用户已切到别的视图，丢弃迟到结果
        kind, data = payload
        if kind != "ok":
            return
        if data:
            self._show_songs(data, "收藏", f"{len(data)} 首")
        else:
            self._show_placeholder("暂无收藏的歌曲")

    def show_play_queue(self) -> None:
        self._set_nav_active(self.nav_recent)
        token = self._new_view_token()
        t = DataThread(self.client.get_play_queue, self)
        t.result.connect(lambda payload, tk=token: self._on_play_queue_loaded(payload, tk))
        t.finished.connect(lambda: self._clean_thread(t))
        self._threads.append(t)
        t.start()

    def _on_play_queue_loaded(self, payload, token: int) -> None:
        if token != self._view_token:
            return
        kind, data = payload
        if kind != "ok":
            return
        if data:
            self._show_songs(data, "最近播放", f"{len(data)} 首")
        else:
            self._show_placeholder("暂无最近播放记录")

    # ---------- 排序 ----------
    def _sort_songs(self, col: int, mode: int) -> None:
        self.current_songs = list(self._base_songs) if mode == 0 else _apply_sort(self._base_songs, col, mode)
        self.song_model.set_songs(self.current_songs)

    def _sort_artist_songs(self, col: int, mode: int) -> None:
        self.artist_songs = list(self._base_artist_songs) if mode == 0 else _apply_sort(self._base_artist_songs, col, mode)
        self.artist_song_model.set_songs(self.artist_songs)

    # ---------- 通用展示 ----------
    def _new_view_token(self) -> int:
        """切换内容视图前调用：令牌自增，使仍在飞行中的旧请求结果失效。"""
        self._view_token += 1
        return self._view_token

    def _play_view_fade(self) -> None:
        """B2：视图切换时从底色淡入（只盖内容区，不遮标题栏与播放栏）。"""
        if not hasattr(self, "_veil"):
            return
        rect = self.content_stack.geometry()
        if rect.isValid() and not rect.isEmpty():
            self._veil.play(rect, 130)

    def _show_songs(self, songs: list[Song], title: str, meta: str, cover_id: str = "") -> None:
        self._new_view_token()
        had_rows = self.song_model.rowCount() > 0
        self.current_songs = list(songs)
        self._base_songs = list(songs)
        self.list_header.reset()
        self.song_model.set_songs(self.current_songs)
        if not had_rows:
            self.song_delegate.begin_intro()  # B4：从空列表填充时才逐行入场，避免两段式加载重复动画
        self.song_header.set_data(title, meta, cover_id)
        if cover_id:
            pix = self.covers.get(cover_id, 200)
            if pix:
                self.song_header.cover.set_pixmap(pix)
        self.list_header.show()
        self.content_stack.setCurrentIndex(_VIEW_SONG)
        self._play_view_fade()

    def _show_albums(self, albums: list[Album], title: str) -> None:
        self._new_view_token()
        self.album_model.set_items(list(albums))
        self.album_title.setText(title)
        self.content_stack.setCurrentIndex(_VIEW_ALBUM)
        # 页面切换后触发一次自适应网格（此时视图才有真实尺寸）
        QTimer.singleShot(0, self._resize_album_grid)
        self._play_view_fade()

    def _show_placeholder(self, text: str) -> None:
        self._new_view_token()
        self.placeholder_label.setText(text)
        self.content_stack.setCurrentIndex(_VIEW_PLACEHOLDER)
        self._play_view_fade()

    def set_sidebar_width(self, w: int) -> None:
        """拖动侧边栏右缘：夹取范围后应用并复位拖拽条位置。"""
        w = max(SIDEBAR_MIN_W, min(SIDEBAR_MAX_W, int(w)))
        if w == self._sidebar_w:
            return
        self._sidebar_w = w
        self.sidebar.setFixedWidth(w)
        lay = self.layout()
        if lay is not None:
            lay.activate()  # 立即重排，便于马上按新几何摆放拖拽条
        self._layout_sidebar_handle()

    def save_sidebar_width(self) -> None:
        """松手才落盘（启动时从 config 恢复）。"""
        if int(self.config.player.get("sidebar_width", 0) or 0) == self._sidebar_w:
            return
        self.config.player["sidebar_width"] = self._sidebar_w
        self.config.save()

    def _layout_sidebar_handle(self) -> None:
        """把拖拽条压在侧边栏右缘（宽度变化 / 页面缩放后都要复位）。"""
        sb = getattr(self, "sidebar", None)
        hd = getattr(self, "_sb_resizer", None)
        if sb is None or hd is None:
            return
        hd.setGeometry(sb.x() + sb.width() - SIDEBAR_HANDLE_W // 2, sb.y(),
                       SIDEBAR_HANDLE_W, sb.height())
        hd.raise_()

    def _clean_thread(self, t: QThread) -> None:
        if t in self._threads:
            self._threads.remove(t)
        t.deleteLater()  # 线程已结束，释放对象，避免长期使用累积

    def shutdown(self) -> None:
        """退出前回收后台线程：请求中断并等待结束。

        QThread 若在运行中被父对象连带析构，Qt 会 qFatal 导致进程直接崩溃，
        因此真正退出前必须确保所有线程已结束。全局 STOP_EVENT 已让分页循环提前返回。
        """
        threads = [t for t in self._threads if t.isRunning()]
        for t in threads:
            t.requestInterruption()
        for t in threads:
            if not t.wait(SHUTDOWN_WAIT_MS):
                logging.warning("后台线程未在 %dms 内结束", SHUTDOWN_WAIT_MS)
        self._threads.clear()

    # ---------- 播放相关 ----------
    def _on_song_changed(self, song: Song) -> None:
        self._now_cover_id = song.cover_id
        self.now_title.setText(song.title)
        self.now_artist.setText(f"{song.artist} · {song.album}" if song.album else song.artist)
        self.cover.set_pixmap(self.covers.get(song.cover_id, 120))
        self.like_btn.set_activated(False)
        self.like_btn.icon_name = "heart"
        self.like_btn.update()
        self.song_delegate.set_current(song.id, self.player.state() == STATE_PLAYING)
        self.artist_song_delegate.set_current(song.id, self.player.state() == STATE_PLAYING)
        self.song_view.viewport().update()
        self.artist_song_view.viewport().update()
        self.lyrics.load(song)

    def _on_state_changed(self, state: str) -> None:
        playing = state == "playing"
        self.btn_play.set_playing(playing)
        self.song_delegate.is_playing = playing
        self.artist_song_delegate.is_playing = playing
        if playing:
            if self._should_animate():
                self._anim_timer.start()
        else:
            self._anim_timer.stop()
            self.song_view.viewport().update()
            self.artist_song_view.viewport().update()

    def _should_animate(self) -> bool:
        """四柱律动动画只在「歌曲列表视图可见」时跑（沉浸页/托盘/专辑页都不需要）。"""
        return (self.isVisible()
                and self.content_stack.currentIndex() == _VIEW_SONG
                and not self.song_view.viewport().visibleRegion().isEmpty())

    def _anim_tick(self) -> None:
        if not self._should_animate():
            self._anim_timer.stop()  # 切走/隐藏后停止空转，回到该视图时由 showEvent 重启
            return
        self.song_view.viewport().update()
        self.artist_song_view.viewport().update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # 用“意图状态”而非 media 实际状态：暂停淡出尚未结束时不应重启律动
        if self.player.state() == STATE_PLAYING and self._should_animate():
            self._anim_timer.start()  # 从沉浸页返回/托盘恢复后继续律动

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._anim_timer.stop()

    def _on_position(self, ms: int) -> None:
        self.progress.set_value(ms, notify=False)
        self.time_cur.setText(_fmt_ms(ms))
        self._update_mini_lyrics()

    def _on_duration(self, ms: int) -> None:
        self.progress.set_range(0, ms)
        self.time_tot.setText(_fmt_ms(ms))

    def _on_mode_changed(self, mode: str) -> None:
        self.btn_mode.icon_name = _MODE_ICONS.get(mode, "repeat")
        self.btn_mode.update()

    def _set_nav_active(self, item: NavItem | None) -> None:
        self._cancel_search_silently()  # 用户改点导航/歌单 → 静默退出搜索，由新导航决定视图
        self._nav_active = item
        for nav in (self.nav_home, self.nav_starred,
                    self.nav_recent, self.nav_artist, self.nav_album):
            nav.set_active(nav is item)
        # 导航选中时清除歌单选中（唯一选中）
        if item is not None:
            self._pl_delegate.set_current("")
            self._pl_view.viewport().update()

    def _open_mode_menu(self) -> None:
        menu = QMenu(self.btn_mode)
        current = self.player.mode
        for mode in (MODE_LIST, MODE_RANDOM, MODE_SINGLE, MODE_ORDER):
            act = menu.addAction(_MODE_NAMES[mode])
            act.setCheckable(True)
            act.setChecked(mode == current)
            act.triggered.connect(lambda checked=False, m=mode: self.player.set_mode(m))
        menu.exec(self.btn_mode.mapToGlobal(self.btn_mode.rect().bottomLeft()))

    def _emit_open_immersive(self) -> None:
        pix = self.cover._pix if hasattr(self.cover, "_pix") else None
        if pix is None:
            pix = _placeholder_pixmap(44)
        rect = QRect(self.cover.mapToGlobal(self.cover.rect().topLeft()), self.cover.size())
        self.open_immersive.emit(pix, rect)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # 迷你歌词悬浮层：底部与播放栏顶重合，向上叠在内容区上（顶部全透明渐变）
        if hasattr(self, "_bar") and hasattr(self, "mini_lyrics"):
            bar_top = self._bar.y()
            h = self.mini_lyrics.height()
            self.mini_lyrics.setGeometry(16, bar_top - h, max(0, self.width() - 32), h)
            self.mini_lyrics.raise_()
            # 侧边栏图层高于歌词层，避免歌词盖住左侧
            self.sidebar.raise_()
            self._layout_sidebar_handle()
        # A2：列表缘渐隐跟随视口尺寸
        for fade in (getattr(self, "_song_fade", None), getattr(self, "_pl_fade", None)):
            if fade is not None:
                fade.refresh()
        if getattr(self, "_veil", None) is not None and self._veil.isVisible():
            self._play_view_fade()

    # ---------- 列表封面/歌手/专辑 点击与悬浮（事件过滤） ----------
    def eventFilter(self, obj, event) -> bool:
        if getattr(self, "album_view", None) is obj and event.type() == QEvent.Type.Resize:
            self._resize_album_grid()
            return False
        song_vp = self.song_view.viewport()
        artist_vp = getattr(getattr(self, "artist_song_view", None), "viewport", None)
        artist_vp = artist_vp() if artist_vp else None
        if obj is song_vp or obj is artist_vp:
            try:
                if event.type() == QEvent.Type.MouseMove:
                    self._update_hover(obj, event.position())
                    return False
                if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                    if self._row_click(obj, event.position()):
                        return True
                if event.type() == QEvent.Type.Leave:
                    if obj is self.song_view.viewport():
                        self.song_delegate.hover_row = -1
                        self.song_delegate.cover_hover = -1
                        self.song_delegate.artist_hover = -1
                        self.song_delegate.album_hover = -1
                        self.song_view.viewport().update()
                    else:
                        self.artist_song_delegate.hover_row = -1
                        self.artist_song_delegate.cover_hover = -1
                        self.artist_song_delegate.artist_hover = -1
                        self.artist_song_delegate.album_hover = -1
                        self.artist_song_view.viewport().update()
            except Exception:  # noqa: BLE001
                pass  # 事件处理异常不影响程序运行
        return super().eventFilter(obj, event)

    def _row_at(self, view: QListView, pos) -> int:
        p = pos.toPoint() if hasattr(pos, "toPoint") else pos
        index = view.indexAt(p)
        return index.row() if index.isValid() else -1

    def _resize_album_grid(self) -> None:
        """专辑网格自适应：按视口宽度算列数与格子尺寸，尽量填满消除右侧空隙。

        QListView 中格子实际占位 = gridSize + spacing，因此用 (vw/列数 - spacing) 求 gridSize。
        """
        vw = self.album_view.viewport().width()
        if vw <= 0:
            return
        spacing = 14
        min_tile = 112
        min_cell = min_tile + spacing
        cols = max(3, vw // min_cell)
        cell = vw // cols
        tile = max(min_tile, cell - spacing)
        self.album_delegate.tile = tile
        self.album_view.setGridSize(QSize(tile, tile + self.album_delegate.text_h))
        self.album_view.setSpacing(spacing)
        self.album_view.viewport().update()

    def _update_hover(self, obj, pos) -> None:
        if obj is self.song_view.viewport():
            view, delegate = self.song_view, self.song_delegate
        else:
            view, delegate = self.artist_song_view, self.artist_song_delegate
        row = self._row_at(view, pos)
        cursor = Qt.CursorShape.ArrowCursor
        cover_hover = artist_hover = album_hover = -1
        if row >= 0:
            rect = view.visualRect(view.model().index(row, 0))
            songs = self.current_songs if view is self.song_view else self.artist_songs
            artist_text = songs[row].artist if row < len(songs) and songs[row] else ""
            zone = song_zone(rect, pos.x(), pos.y(), artist_text)
            cover_hover = row if zone == "cover" else -1
            artist_hover = row if zone == "artist" else -1
            album_hover = row if zone == "album" else -1
            if zone in ("cover", "artist", "album"):
                cursor = Qt.CursorShape.PointingHandCursor
        # 只有悬浮状态真变化时才重绘（鼠标移动事件非常密集）
        if (delegate.hover_row, delegate.cover_hover, delegate.artist_hover, delegate.album_hover) != \
                (row, cover_hover, artist_hover, album_hover):
            delegate.hover_row = row
            delegate.cover_hover = cover_hover
            delegate.artist_hover = artist_hover
            delegate.album_hover = album_hover
            view.viewport().update()
        view.viewport().setCursor(cursor)

    def _row_click(self, obj, pos) -> bool:
        if obj is self.song_view.viewport():
            view, songs = self.song_view, self.current_songs
        else:
            view, songs = self.artist_song_view, self.artist_songs
        row = self._row_at(view, pos)
        if row < 0 or not songs:
            return False
        song = songs[row]
        rect = view.visualRect(view.model().index(row, 0))
        zone = song_zone(rect, pos.x(), pos.y(), song.artist)
        if zone == "cover":
            cur = self.player.queue[self.player.current_index] if self.player.queue and self.player.current_index >= 0 else None
            if cur and cur.id == song.id:
                self.player.toggle()
            else:
                self.player.set_queue(songs, row)
            return True
        if zone == "artist" and song.artist_id:
            self.open_artist(song.artist_id, song.artist)
            return True
        if zone == "album" and song.album_id:
            self.open_album(song.album_id, song.album, song.artist, song.cover_id)
            return True
        return False

    # ---------- 列表双击 ----------
    def _on_playlist_clicked(self, index: QModelIndex) -> None:
        item = self._pl_model.data(index, Qt.ItemDataRole.UserRole)
        if item:
            self._set_nav_active(None)  # 歌单选中与上方导航互斥
            self.load_playlist(item[0])

    def _on_playlist_double_clicked(self, index: QModelIndex) -> None:
        """双击侧边栏歌单：加载后直接开始播放全部。"""
        item = self._pl_model.data(index, Qt.ItemDataRole.UserRole)
        if item:
            self._set_nav_active(None)
            self.load_playlist(item[0], play_after=True)

    def _on_song_double_clicked(self, index: QModelIndex) -> None:
        self._play_from(index.row())

    def _play_from(self, row: int) -> None:
        if self.current_songs:
            self.player.set_queue(self.current_songs, row)

    def _play_all(self) -> None:
        if self.current_songs:
            self.player.set_mode(MODE_LIST)  # 播放全部同时切回列表循环
            self.player.set_queue(self.current_songs, 0)

    def _play_random(self) -> None:
        if not self.current_songs:
            return
        import random as _r

        self.player.set_mode(MODE_RANDOM)
        self.player.set_queue(self.current_songs, _r.randrange(len(self.current_songs)))

    def _toggle_like(self) -> None:
        song = self._current_song()
        if not song:
            return
        now_on = not self.like_btn.activated
        self.like_btn.set_activated(now_on)
        self.like_btn.icon_name = "heart_filled" if now_on else "heart"
        self.like_btn.update()
        t = DataThread(lambda: self.client.set_starred(song.id, now_on), self)
        t.finished.connect(lambda: self._clean_thread(t))
        self._threads.append(t)
        t.start()

    def _current_song(self) -> Song | None:
        return self.player.queue[self.player.current_index] if self.player.queue and self.player.current_index >= 0 else None

    def _open_now_artist(self) -> None:
        """点击播放栏歌手名：跳到对应歌手页。"""
        cur = self._current_song()
        if cur and cur.artist_id:
            self.open_artist(cur.artist_id, cur.artist)


# ---------- 音量控件 ----------
class VolumeControl(QWidget):
    """音量图标（点击静音/恢复记忆音量）+ 长滑块（悬浮加宽、调整时显示百分比）。"""

    def __init__(self, parent, player: Player) -> None:
        super().__init__(parent)
        self.player = player
        self._last_volume: int = player.volume
        self._anim = None
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
        self._start(150)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hide_pct()
        pos = self.mapFromGlobal(self.cursor().pos())
        if not self.rect().contains(pos):
            self._start(120)
        super().leaveEvent(event)

    def _start(self, w: int) -> None:
        if self._anim:
            self._anim.stop()
        self._anim.setStartValue(self.slider.width())
        self._anim.setEndValue(w)
        self._anim.start()


def _fmt_dur(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _fmt_ms(ms: int) -> str:
    return _fmt_dur(ms // 1000)


def _placeholder_pixmap(px: int) -> QPixmap:
    pix = QPixmap(px, px)
    pix.fill(QColor("#B9BDF5"))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#6F73E8"))
    p.drawRoundedRect(0, 0, px, px, 12, 12)
    p.end()
    return pix
