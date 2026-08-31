"""封面异步加载与缓存（内存 LRU），不阻塞 UI 线程。"""
from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

MAX_CACHE = 240


class CoverManager(QObject):
    """按 cover_id + size 缓存 QPixmap。加载完成后发出 loaded 信号。"""

    loaded = Signal(str, QPixmap)  # cover_id, pixmap（缩略图或大图）

    def __init__(self, client, parent=None) -> None:
        super().__init__(parent)
        self.client = client
        self._nam = QNetworkAccessManager(self)
        self._cache: OrderedDict[tuple, QPixmap] = OrderedDict()
        self._pending: set = set()

    def set_client(self, client) -> None:
        self.client = client
        self._cache.clear()
        self._pending.clear()

    def get(self, cover_id: str, size: int = 160) -> QPixmap | None:
        """同步取缓存；未命中则发起异步请求并返回 None。"""
        if not cover_id:
            return None
        key = (cover_id, size)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        self._request(cover_id, size)
        return None

    def _request(self, cover_id: str, size: int) -> None:
        key = (cover_id, size)
        if key in self._pending:
            return
        if not self.client:
            return
        self._pending.add(key)
        req = QNetworkRequest(QUrl(self.client.cover_url(cover_id, size)))
        reply = self._nam.get(req)
        reply.finished.connect(lambda r=reply, k=key, cid=cover_id: self._on_finish(r, k, cid))

    def _on_finish(self, reply: QNetworkReply, key: tuple, cover_id: str) -> None:
        self._pending.discard(key)
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pix = QPixmap()
            pix.loadFromData(bytes(reply.readAll()))
            if not pix.isNull():
                self._cache[key] = pix
                self._cache.move_to_end(key)
                while len(self._cache) > MAX_CACHE:
                    self._cache.popitem(last=False)
                self.loaded.emit(cover_id, pix)
        reply.deleteLater()
