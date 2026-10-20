"""封面异步加载与缓存（内存 LRU + 磁盘缓存），不阻塞 UI 线程。

磁盘缓存使启动时封面可立即显示（无需等待网络），同时后台向服务器刷新保持最新。
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from app.config import APP_DIR

MAX_CACHE = 240
CACHE_DIR = APP_DIR / "covers" / "cache"
MAX_DISK_FILES = 500


class CoverManager(QObject):
    """按 cover_id + size 缓存 QPixmap。加载完成后发出 loaded 信号。"""

    loaded = Signal(str, QPixmap)  # cover_id, pixmap（缩略图或大图）

    def __init__(self, client, parent=None) -> None:
        super().__init__(parent)
        self.client = client
        self._nam = QNetworkAccessManager(self)
        self._cache: OrderedDict[tuple, QPixmap] = OrderedDict()
        self._pending: set = set()
        self._failed: set[str] = set()  # 取不到封面的 cover_id（占位不再做扫光，避免无限重绘）
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._trim_disk_cache()
        except OSError:  # noqa: BLE001
            pass

    def set_client(self, client) -> None:
        self.client = client
        self._cache.clear()
        self._pending.clear()
        self._failed.clear()

    def is_failed(self, cover_id: str) -> bool:
        """该封面是否已确认取不到（用于占位不再扫光，避免无限刷新）。"""
        return cover_id in self._failed

    def get(self, cover_id: str, size: int = 160) -> QPixmap | None:
        """取缓存；未命中则先读磁盘缓存（立即返回）并后台刷新，否则发起异步请求。

        目标尺寸无缓存时回退到其它已缓存尺寸放大显示（如侧边栏 120px 供头部 200px 用），
        保证点开歌单时封面立即可见，同时后台拉取目标尺寸后升级。
        """
        if not cover_id:
            return None
        key = (cover_id, size)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        pix = self._load_disk(cover_id, size)
        if pix is not None:
            self._cache[key] = pix
            # 磁盘命中：先返回旧图，同时后台向服务器刷新，保证与服务器封面同步
            self._request(cover_id, size)
            return pix
        # 回退：用其它已缓存尺寸立即显示（优先更大的提升画质）
        fallback = self._load_disk_fallback(cover_id, size)
        if fallback is not None:
            self._cache[key] = fallback
            self._request(cover_id, size)
            return fallback
        self._request(cover_id, size)
        return None

    def _load_disk_fallback(self, cover_id: str, size: int) -> QPixmap | None:
        for s in (size * 3, 600, 300, 160, 120, 96, size // 2):
            if s == size or s <= 0:
                continue
            pix = self._load_disk(cover_id, s)
            if pix is not None:
                return pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                  Qt.TransformationMode.SmoothTransformation)
        return None

    # ---------- 磁盘缓存 ----------
    def _disk_path(self, cover_id: str, size: int) -> Path:
        safe = str(cover_id).replace("/", "_").replace("\\", "_")
        return CACHE_DIR / f"{safe}_{size}.png"

    def _load_disk(self, cover_id: str, size: int) -> QPixmap | None:
        path = self._disk_path(cover_id, size)
        if not path.exists():
            return None
        pix = QPixmap(str(path))
        return pix if not pix.isNull() else None

    def _save_disk(self, cover_id: str, size: int, pix: QPixmap) -> None:
        try:
            path = self._disk_path(cover_id, size)
            path.parent.mkdir(parents=True, exist_ok=True)
            pix.save(str(path), "PNG")
        except OSError:  # noqa: BLE001
            pass

    def _trim_disk_cache(self) -> None:
        """磁盘缓存文件过多时整体清空重建，避免长期累积。"""
        try:
            files = [p for p in CACHE_DIR.glob("*.png")]
            if len(files) > MAX_DISK_FILES:
                for f in files:
                    f.unlink(missing_ok=True)
        except OSError:  # noqa: BLE001
            pass

    # ---------- 网络请求 ----------
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
                size = key[1]
                self._cache[key] = pix
                self._cache.move_to_end(key)
                while len(self._cache) > MAX_CACHE:
                    self._cache.popitem(last=False)
                self._save_disk(cover_id, size, pix)
                self._failed.discard(cover_id)
                self.loaded.emit(cover_id, pix)
                reply.deleteLater()
                return
        self._failed.add(cover_id)  # 记下来：占位不再扫光，避免无休止重绘
        reply.deleteLater()
