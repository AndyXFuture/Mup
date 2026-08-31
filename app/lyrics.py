"""共享歌词管理器：按当前歌曲异步获取歌词，广播给歌单页迷你歌词与沉浸页，避免重复请求。"""
from __future__ import annotations

import re

from PySide6.QtCore import QObject, QThread, Signal

from app.subsonic_client import LyricLine, SubsonicClient


def parse_lyrics(text: str) -> list[LyricLine]:
    """解析歌词：优先 LRC 时间戳，否则按行拆分纯文本。"""
    if not text:
        return []
    lrc = re.findall(r"\[(\d+):(\d+)(?:[.:](\d+))?\]\s*([^\n\[\]]*)", text)
    if lrc:
        out: list[LyricLine] = []
        for mm, ss, frac, content in lrc:
            content = content.strip()
            if not content:
                continue
            ms = (int(mm) * 60 + int(ss)) * 1000
            if frac:
                ms += int(frac.ljust(2, "0")) * 10 if len(frac) <= 2 else int(frac[:2]) * 10
            out.append(LyricLine(ms, content))
        return out
    return [LyricLine(-1, ln.strip()) for ln in text.splitlines() if ln.strip()]


class LyricsWorker(QThread):
    result = Signal(object)  # list[LyricLine]

    def __init__(self, client: SubsonicClient, song, parent=None) -> None:
        super().__init__(parent)
        self.client = client
        self.song = song

    def run(self) -> None:
        lines: list[LyricLine] = []
        try:
            lines = self.client.get_lyrics_by_song_id(self.song.id)
        except Exception:  # noqa: BLE001
            lines = []
        if not lines:
            try:
                text = self.client.get_lyrics(self.song.artist, self.song.title) or ""
            except Exception:  # noqa: BLE001
                text = ""
            lines = parse_lyrics(text)
        self.result.emit(lines)


class LyricsManager(QObject):
    """缓存 + 广播歌词。loaded 信号带 (song_id, list[LyricLine])。"""

    loaded = Signal(str, object)

    def __init__(self, client: SubsonicClient | None = None, parent=None) -> None:
        super().__init__(parent)
        self.client = client
        self._cache: dict[str, list[LyricLine]] = {}
        self._worker: LyricsWorker | None = None
        self._cur_song_id = ""

    def set_client(self, client) -> None:
        self.client = client
        self._cache.clear()

    def load(self, song) -> None:
        if not self.client:
            return
        self._cur_song_id = song.id
        if song.id in self._cache:
            self.loaded.emit(song.id, self._cache[song.id])
            return
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
        self._worker = LyricsWorker(self.client, song, self)
        self._worker.result.connect(self._on_loaded)
        self._worker.start()

    def _on_loaded(self, lines) -> None:
        self._cache[self._cur_song_id] = lines
        self.loaded.emit(self._cur_song_id, lines)
