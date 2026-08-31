"""播放核心：基于 QMediaPlayer 的队列播放器，支持随机/顺序/单曲/列表循环。"""
from __future__ import annotations

import random

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

# 播放模式
MODE_LIST = "list"      # 列表循环
MODE_RANDOM = "random"  # 随机播放
MODE_SINGLE = "single"  # 单曲循环
MODE_ORDER = "order"    # 顺序播放
PLAY_MODES = (MODE_LIST, MODE_RANDOM, MODE_SINGLE, MODE_ORDER)

STATE_STOPPED = "stopped"
STATE_PLAYING = "playing"
STATE_PAUSED = "paused"


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

        self.queue: list = []
        self.current_index = -1
        self.mode = MODE_LIST
        self.volume = 80
        self._history: list[int] = []  # 用于随机模式的上一曲

        self.audio.setVolume(self.volume / 100.0)
        self.media.positionChanged.connect(self.position_changed.emit)
        self.media.durationChanged.connect(self.duration_changed.emit)
        self.media.playbackStateChanged.connect(self._on_state)
        self.media.mediaStatusChanged.connect(self._on_status)
        self.media.errorOccurred.connect(self._on_error)

    # ---------- 对外 API ----------
    def set_client(self, client) -> None:
        self.client = client

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
        song = self.queue[index]
        self.media.setSource(QUrl(self.client.stream_url(song.id)))
        self.media.play()
        self.song_changed.emit(song)

    def restore(self, song, position_ms: int = 0) -> None:
        """启动恢复：加载上次歌曲用于显示，不自动播放（可选恢复进度）。"""
        if not self.client:
            return
        self.queue = [song]
        self.current_index = 0
        self._history.clear()
        self.media.setSource(QUrl(self.client.stream_url(song.id)))
        self.media.pause()
        self.song_changed.emit(song)
        if position_ms > 0:
            self.media.setPosition(int(position_ms))

    def toggle(self) -> None:
        if self.media.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media.pause()
        else:
            self.media.play()

    def play(self) -> None:
        self.media.play()

    def pause(self) -> None:
        self.media.pause()

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
        self.audio.setVolume(self.volume / 100.0)
        self.volume_changed.emit(self.volume)

    def stop(self) -> None:
        self.media.stop()

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
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.mode == MODE_SINGLE:
                self.media.setPosition(0)
                self.media.play()
            else:
                self.next(manual=False)

    def _on_state(self, state) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.state_changed.emit(STATE_PLAYING)
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.state_changed.emit(STATE_PAUSED)
        else:
            self.state_changed.emit(STATE_STOPPED)

    def _on_error(self, error, error_string: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            self.error_occurred.emit(error_string or "播放失败")
