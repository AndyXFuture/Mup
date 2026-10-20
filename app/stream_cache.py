"""本地音频缓存：边下边播（Stream-Cache）。

切歌时先把整首下载到本地磁盘，下载完成后用本地文件播放——播放过程不依赖网络，
系统（磁盘/网络/Explorer）卡顿时音频继续播放，效果接近 QQ 音乐。

缓存上限 100MB（约 3 首歌），超出按最旧优先清理；扩展名通过响应头/文件头嗅探。
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from app.config import APP_DIR

STREAM_CACHE_DIR = APP_DIR / "stream_cache"
MAX_BYTES = 100 * 1024 * 1024  # 100MB

# 常见音频文件头 → 扩展名
_MAGIC = (
    (b"ID3", "mp3"), (b"\xff\xfb", "mp3"), (b"\xff\xf3", "mp3"), (b"\xff\xf2", "mp3"),
    (b"fLaC", "flac"), (b"OggS", "ogg"),
)


def _safe(song_id: str) -> str:
    return str(song_id).replace("/", "_").replace("\\", "_")


class StreamCache(QObject):
    """下载歌曲到本地目录；下载完成后发 downloaded(song_id)。"""

    downloaded = Signal(str)                    # song_id 下载成功
    download_failed = Signal(str, str)          # song_id, error 信息

    def __init__(self, client, parent=None) -> None:
        super().__init__(parent)
        self.client = client
        self._nam = QNetworkAccessManager(self)
        self._nam.setRedirectPolicy(QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        self._pending: dict[str, QNetworkReply] = {}  # song_id → reply
        try:
            STREAM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._prune()
        except OSError:  # noqa: BLE001
            pass

    def set_client(self, client) -> None:
        self.client = client

    # ---------- 查询 ----------
    def local_path(self, song_id: str, with_ext: bool = False) -> Path | None:
        """返回已缓存歌曲的本地路径；未缓存/文件损坏返回 None。"""
        if not song_id:
            return None
        base = STREAM_CACHE_DIR / _safe(song_id)
        if with_ext:
            base = base.with_suffix(".bin")
        for p in base.parent.glob(f"{base.name}.*"):
            if p.suffix == ".partial":
                continue  # 未完成的下载残留，不能当缓存
            if p.is_file() and p.stat().st_size > 0:
                return p
        return None

    # ---------- 下载 ----------
    def download(self, song_id: str) -> bool:
        """异步下载 song_id；已在下载返回 False；已有缓存直接发 downloaded。"""
        if not song_id or not self.client or song_id in self._pending:
            return False
        if self.local_path(song_id):
            self.downloaded.emit(song_id)
            return False
        url = QUrl(self.client.stream_url(song_id))
        req = QNetworkRequest(url)
        reply = self._nam.get(req)
        self._pending[song_id] = reply
        # 临时文件先写到 .partial，完成后再改名，避免半截文件被当成有效缓存
        tmp = STREAM_CACHE_DIR / f"{_safe(song_id)}.partial"
        reply.readyRead.connect(lambda: self._on_ready(reply, tmp))
        reply.finished.connect(lambda r=reply, s=song_id, t=tmp: self._on_finish(r, s, t))
        return True

    def _on_ready(self, reply: QNetworkReply, tmp: Path) -> None:
        try:
            with tmp.open("ab") as f:
                f.write(reply.readAll().data())
        except OSError:  # noqa: BLE001
            pass

    def _on_finish(self, reply: QNetworkReply, song_id: str, tmp: Path) -> None:
        self._pending.pop(song_id, None)
        try:
            with tmp.open("ab") as f:
                f.write(reply.readAll().data())
        except OSError:  # noqa: BLE001
            pass
        err = reply.error()
        reply.deleteLater()
        if err != QNetworkReply.NetworkError.NoError or tmp.stat().st_size == 0:
            tmp.unlink(missing_ok=True)
            self.download_failed.emit(song_id, reply.errorString())
            return
        ext = self._detect_ext(tmp, reply)
        final = STREAM_CACHE_DIR / f"{_safe(song_id)}.{ext}"
        try:
            final.unlink(missing_ok=True)
            tmp.rename(final)
        except OSError:  # noqa: BLE001
            tmp.unlink(missing_ok=True)
            self.download_failed.emit(song_id, "无法写入缓存")
            return
        self._prune()
        self.downloaded.emit(song_id)

    @staticmethod
    def _detect_ext(path: Path, reply: QNetworkReply | None = None) -> str:
        """扩展名：响应头文件名后缀 → 文件头嗅探 → mp3。"""
        if reply:
            cd = bytes(reply.rawHeader("Content-Disposition")).decode("utf-8", "ignore")
            if "*" in cd and "''" in cd:
                name = cd.split("''", 1)[-1].split(";")[0].strip('"')
                if "." in name:
                    return name.rsplit(".", 1)[-1].lower()
        try:
            with path.open("rb") as f:
                head = f.read(12)
        except OSError:  # noqa: BLE001
            return "mp3"
        for magic, ext in _MAGIC:
            if head.startswith(magic):
                return ext
        return "mp3"

    # ---------- 缓存清理 ----------
    def _prune(self) -> None:
        """清理中断残留的 .partial，并在总大小超上限时按修改时间删除最旧文件。

        注意：**只删除已无对应下载任务的 .partial**。正在下载的文件由 _pending 持有，
        若在此处删掉，写入方会以追加模式新建空文件继续写，导致先前写入的字节全部丢失
        （表现为当前播放曲的缓存被截断）。
        """
        active = {f"{_safe(song_id)}.partial" for song_id in self._pending}
        try:
            files = [p for p in STREAM_CACHE_DIR.iterdir() if p.is_file()]
        except OSError:  # noqa: BLE001
            return
        for p in files:
            if p.suffix == ".partial" and p.name not in active:
                try:
                    p.unlink(missing_ok=True)  # 上次运行残留的未完成下载，直接删除
                except OSError:  # noqa: BLE001
                    pass
        files = [p for p in files if p.suffix != ".partial"]
        total = sum(p.stat().st_size for p in files)
        if total <= MAX_BYTES:
            return
        limit = MAX_BYTES * 9 // 10
        for p in sorted(files, key=lambda q: q.stat().st_mtime):
            if total <= limit:
                break
            try:
                total -= p.stat().st_size
                p.unlink(missing_ok=True)
            except OSError:  # noqa: BLE001
                continue

    def cancel_all(self) -> None:
        for reply in self._pending.values():
            reply.abort()
        self._pending.clear()