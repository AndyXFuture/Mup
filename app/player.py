"""播放核心：基于 QMediaPlayer 的队列播放器，支持随机/顺序/单曲/列表循环。"""
from __future__ import annotations

import random
import time

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from app.stream_cache import StreamCache

# 播放模式
MODE_LIST = "list"      # 列表循环
MODE_RANDOM = "random"  # 随机播放
MODE_SINGLE = "single"  # 单曲循环
MODE_ORDER = "order"    # 顺序播放
PLAY_MODES = (MODE_LIST, MODE_RANDOM, MODE_SINGLE, MODE_ORDER)

STATE_STOPPED = "stopped"
STATE_PLAYING = "playing"
STATE_PAUSED = "paused"

FADE_MS = 3000       # 播放淡入时长
FADE_OUT_MS = 2000   # 暂停淡出时长（图标立即切换，声音在 2 秒内渐弱后暂停）
FADE_TICK = 30   # 淡化定时器间隔(ms)


class Player(QObject):
    """管理媒体源、队列与播放模式。所有方法在主线程调用。"""

    song_changed = Signal(object)   # Song
    position_changed = Signal(int)  # ms
    duration_changed = Signal(int)  # ms
    state_changed = Signal(str)     # STATE_*
    mode_changed = Signal(str)
    volume_changed = Signal(int)
    error_occurred = Signal(str)

    def __init__(self, client, parent=None) -> None:
        super().__init__(parent)
        self.client = client
        self.media = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.media.setAudioOutput(self.audio)
        self.stream_cache = StreamCache(client, self)
        self.stream_cache.downloaded.connect(self._on_downloaded)
        self.stream_cache.download_failed.connect(self._on_download_failed)

        self.queue: list = []
        self.current_index = -1
        self.mode = MODE_LIST
        self.volume = 80
        self._history: list[int] = []  # 用于随机模式的上一曲
        self._preparing_id: str = ""    # 正在准备(下载中/待播)的歌曲 id，用于下载完成回叫
        self._restore_only = False      # 恢复场景：下载完成后只加载不自动播放
        self._restore_pos = 0
        # 待应用的恢复位置：QMediaPlayer 在媒体加载完成前 setPosition 会被静默忽略，
        # 必须等 LoadedMedia/BufferedMedia 后再设置（_on_status 里应用）
        self._pending_position = 0
        self._last_state = STATE_STOPPED  # 最近一次发出的状态（去重 + 供 UI 查询"意图状态"）
        self._intent_play = False         # 用户意图：True=播放，False=暂停/停止（下载完成后据此决定是否自动播）

        # 播放/暂停淡入淡出：反复切换时从当前音量续接渐变，不跳变
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(FADE_TICK)
        self._fade_timer.timeout.connect(self._fade_tick)
        self._fade_start_ms = 0.0
        self._fade_start_level = 0.0
        self._fade_target = 1.0
        self._fade_duration_ms = float(FADE_MS)
        self._fade_pending_pause = False  # 淡出完成后是否暂停

        self.audio.setVolume(self.volume / 100.0)
        self.media.positionChanged.connect(self.position_changed.emit)
        self.media.durationChanged.connect(self.duration_changed.emit)
        self.media.playbackStateChanged.connect(self._on_state)
        self.media.mediaStatusChanged.connect(self._on_status)
        self.media.errorOccurred.connect(self._on_error)

    # ---------- 对外 API ----------
    def set_client(self, client) -> None:
        self.client = client
        self.stream_cache.set_client(client)

    def set_queue(self, songs: list, start_index: int = 0) -> None:
        self.queue = list(songs)
        self._history.clear()
        self.current_index = -1
        if self.queue and 0 <= start_index < len(self.queue):
            self.play_index(start_index)

    def play_index(self, index: int) -> None:
        if not self.queue or not (0 <= index < len(self.queue)):
            return
        self.current_index = index
        self._history.append(index)
        if len(self._history) > 500:
            self._history.pop(0)
        self._prepare(self.queue[index])

    def _prepare(self, song) -> None:
        """边下边播：优先播放本地缓存，未缓存则下载完成后再播；失败降级网络流。"""
        self._cancel_fade(restore_volume=True)  # 切歌恢复设定音量，避免淡出后音量滞留为0
        self._pending_position = 0  # 切歌清掉上曲遗留的恢复位置，避免套用到新曲
        self.media.stop()
        self.song_changed.emit(song)
        self._preparing_id = song.id
        self._restore_only = False
        self._intent_play = True
        local = self.stream_cache.local_path(song.id)
        if local:
            self._play_local(local)
        else:
            self.stream_cache.download(song.id)  # 完成后经 _on_downloaded 播放
        self._prefetch_next()

    def _play_local(self, path) -> None:
        self.media.setSource(QUrl.fromLocalFile(str(path)))
        self.media.play()

    def _play_stream(self, song) -> None:
        self.media.setSource(QUrl(self.client.stream_url(song.id)))
        self.media.play()

    def _on_downloaded(self, song_id: str) -> None:
        if song_id != self._preparing_id:
            return  # 已切歌，缓存留给下次点击直接播
        p = self.stream_cache.local_path(song_id)
        if not p:
            return
        self.media.setSource(QUrl.fromLocalFile(str(p)))
        if self._restore_only:
            self.media.pause()
            self._pending_position = self._restore_pos  # 媒体加载完成后再定位（见 _on_status）
            self._restore_only = False
        elif self._intent_play:
            self.media.play()
        else:
            self.media.pause()  # 用户已暂停：只加载不自动播放，避免暂停被下载完成覆盖

    def _on_download_failed(self, song_id: str, _err: str) -> None:
        if song_id != self._preparing_id:
            return
        if self.queue and 0 <= self.current_index < len(self.queue):
            self._play_stream(self.queue[self.current_index])  # 降级网络流

    def _prefetch_next(self) -> None:
        """后台预取下一首，缩短切换等待。"""
        nxt = self._next_index(manual=True)
        if nxt is None or nxt == self.current_index:
            return
        song = self.queue[nxt]
        if not self.stream_cache.local_path(song.id):
            self.stream_cache.download(song.id)

    def restore(self, songs: list, song, position_ms: int = 0) -> None:
        """启动恢复：用完整列表 songs 作为队列并定位到 song 用于显示，不自动播放（可选恢复进度）。

        队列必须是完整播放列表，否则自动/手动下一曲会在单曲队列里原地循环。
        有本地缓存优先缓存文件，否则下载完成后加载（仍不自动播放）。
        """
        if not self.client or not songs:
            return
        self._cancel_fade(restore_volume=True)  # 恢复启动加载时结束可能残留的淡化
        self.queue = list(songs)
        self.current_index = self.queue.index(song) if song in self.queue else 0
        self._history.clear()
        cur = self.queue[self.current_index]
        self._preparing_id = cur.id
        self._restore_only = True
        self._intent_play = False
        self._restore_pos = int(position_ms)
        self._pending_position = int(position_ms)  # 媒体加载完成后应用（见 _on_status）
        self.song_changed.emit(cur)
        local = self.stream_cache.local_path(cur.id)
        if local:
            self.media.setSource(QUrl.fromLocalFile(str(local)))
            self.media.pause()
        else:
            self.stream_cache.download(cur.id)  # 完成后 _on_downloaded 加载但不播放

    def toggle(self) -> None:
        """播放/暂停：按用户意图切换，暂停立即生效（图标与声音同步）。"""
        if self._last_state == STATE_PLAYING:
            self.pause()
        else:
            self.play()

    def play(self) -> None:
        self._intent_play = True
        self._fade_pending_pause = False
        # 全新播放（无淡化进行中）从静音淡入；淡出中途续播则从当前音量淡回，避免跳变
        if not self._fade_timer.isActive():
            self.audio.setVolume(0.0)
        self.media.play()
        # 立即上报“正在播放”：淡出中途续播时 Qt 不会重新发 Playing，图标会滞后
        self._emit_state(STATE_PLAYING)
        self._start_fade(self.volume / 100.0)

    def pause(self) -> None:
        """暂停：图标立即切换为暂停态，声音在 2 秒内淡出后再真正暂停。"""
        self._intent_play = False
        if self.media.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            # 从当前音量续接淡出（淡入中途按暂停也不会跳变），淡出结束后暂停
            self._start_fade(0.0, pending_pause=True, duration_ms=FADE_OUT_MS)
        else:
            # 尚未真正开始播放：无需淡出，直接置为暂停态
            self._cancel_fade(restore_volume=True)
            self.media.pause()
        # 立即上报暂停，图标与用户操作同步（不等 2 秒淡出结束）
        self._emit_state(STATE_PAUSED)

    def _emit_state(self, state: str) -> None:
        """状态去重后广播（意图状态与 Qt 实际状态可能先后到达同一值）。"""
        if state != self._last_state:
            self._last_state = state
            self.state_changed.emit(state)

    def state(self) -> str:
        """当前对外状态：反映用户意图（暂停时淡出尚未结束也算已暂停）。"""
        return self._last_state

    def _start_fade(self, target: float, pending_pause: bool = False,
                    duration_ms: float = FADE_MS) -> None:
        """从当前音量线性渐变到 target；pending_pause 表示渐变完成后暂停。"""
        self._fade_target = max(0.0, min(1.0, float(target)))
        self._fade_pending_pause = pending_pause
        self._fade_duration_ms = max(1.0, float(duration_ms))
        self._fade_start_level = self.audio.volume()
        self._fade_start_ms = time.monotonic()
        if not self._fade_timer.isActive():
            self._fade_timer.start()

    def _fade_tick(self) -> None:
        elapsed = (time.monotonic() - self._fade_start_ms) * 1000.0
        t = min(1.0, elapsed / self._fade_duration_ms)
        level = self._fade_start_level + (self._fade_target - self._fade_start_level) * t
        self.audio.setVolume(max(0.0, min(1.0, level)))
        if t >= 1.0:
            self._fade_timer.stop()
            if self._fade_pending_pause:
                self._fade_pending_pause = False
                self.media.pause()

    def _cancel_fade(self, restore_volume: bool = False) -> None:
        """取消进行中的淡化。restore_volume=True 时把音量恢复为设定音量。"""
        self._fade_pending_pause = False
        if self._fade_timer.isActive():
            self._fade_timer.stop()
        if restore_volume:
            self.audio.setVolume(self.volume / 100.0)

    def next(self, manual: bool = True) -> None:
        if not self.queue:
            return
        n = self._next_index(manual)
        if n is not None:
            self.play_index(n)

    def prev(self) -> None:
        if not self.queue:
            return
        # 播放超过 3 秒则回到本曲开头
        if self.media.position() > 3000:
            self.media.setPosition(0)
            return
        if self._history:
            self._history.pop()  # 当前
            prev = self._history.pop() if self._history else self.current_index
            self.play_index(prev)
        else:
            self.play_index(self.current_index)

    def seek(self, ms: int) -> None:
        self.media.setPosition(max(0, int(ms)))

    def set_mode(self, mode: str) -> None:
        if mode not in PLAY_MODES:
            return
        self.mode = mode
        self.mode_changed.emit(mode)

    def set_volume(self, vol: int) -> None:
        self.volume = max(0, min(100, int(vol)))
        # 暂停淡出进行中时不要打断它，仅记录新音量供下次播放使用
        if not self._fade_pending_pause:
            self._cancel_fade(restore_volume=True)  # 用户调音量优先，结束淡化直接生效
            self.audio.setVolume(self.volume / 100.0)
        self.volume_changed.emit(self.volume)

    def stop(self) -> None:
        self._intent_play = False
        self._cancel_fade(restore_volume=True)
        self.media.stop()
        self._emit_state(STATE_STOPPED)

    def is_playing(self) -> bool:
        return self.media.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    # ---------- 内部 ----------
    def _next_index(self, manual: bool):
        n = len(self.queue)
        if n == 0:
            return None
        if self.mode == MODE_RANDOM:
            candidates = [i for i in range(n) if i != self.current_index]
            return random.choice(candidates) if candidates else self.current_index
        nxt = self.current_index + 1
        if nxt >= n:
            if self.mode == MODE_ORDER:
                return 0 if manual else None  # 顺序模式自动播完则停止
            return 0  # list / single 手动切歌时循环回第一首
        return nxt

    def _on_status(self, status) -> None:
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self._apply_pending_position()
            return
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.mode == MODE_SINGLE:
                self.media.setPosition(0)
                self.media.play()
            else:
                self.next(manual=False)

    def _apply_pending_position(self) -> None:
        """媒体加载完成后才应用恢复进度：加载前 setPosition 会被 QMediaPlayer 静默忽略。"""
        if self._pending_position > 0:
            self.media.setPosition(self._pending_position)
            self._pending_position = 0

    def _on_state(self, state) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._emit_state(STATE_PLAYING)
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self._emit_state(STATE_PAUSED)
        else:
            self._emit_state(STATE_STOPPED)

    def _on_error(self, error, error_string: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            self.error_occurred.emit(error_string or "播放失败")
