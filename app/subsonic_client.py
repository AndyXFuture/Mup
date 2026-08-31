"""Subsonic / OpenSubsonic 客户端：通过「音桥」连接飞牛音乐。

认证采用 Subsonic token+salt 方式（p=enc:md5(password+salt)）。
所有 JSON 响应包裹在 subsonic-response 根节点中，child 元素转成 dict 且属性以 '@' 开头。
"""
from __future__ import annotations

import hashlib
import secrets
import threading
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlencode

import requests

API_VERSION = "1.16.1"
CLIENT_NAME = "mup"


def _as_list(value: Any):
    """Subsonic 对单元素直接返回 dict，统一转成 list。"""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


@dataclass
class Song:
    id: str = ""
    title: str = ""
    artist: str = ""
    artist_id: str = ""
    album: str = ""
    duration: int = 0
    cover_id: str = ""
    track: int = 0
    year: int = 0
    album_id: str = ""


@dataclass
class Playlist:
    id: str = ""
    name: str = ""
    song_count: int = 0
    duration: int = 0
    cover_id: str = ""
    comment: str = ""


@dataclass
class Album:
    id: str = ""
    name: str = ""
    artist: str = ""
    cover_id: str = ""
    song_count: int = 0


@dataclass
class Artist:
    id: str = ""
    name: str = ""
    cover_id: str = ""
    album_count: int = 0


@dataclass
class LyricLine:
    time_ms: int = -1  # -1 表示无时间戳（纯文本歌词）
    text: str = ""


def _get(node: dict, *keys: str, default=""):
    """兼容两种键风格：音桥原生 JSON 用纯键，标准 Subsonic XML→JSON 用 '@' 前缀键。"""
    if not isinstance(node, dict):
        return default
    for k in keys:
        if k in node and node[k] is not None:
            return node[k]
    return default


def _parse_song(node: dict) -> Song:
    return Song(
        id=str(_get(node, "id", "@id", default="")),
        title=_get(node, "title", "@title", "#text"),
        artist=_get(node, "artist", "@artist"),
        artist_id=str(_get(node, "artistId", "@artistId", default="")),
        album=_get(node, "album", "@album"),
        duration=int(_get(node, "duration", "@duration", default=0) or 0),
        cover_id=str(_get(node, "coverArt", "@coverArt", default="")),
        track=int(_get(node, "track", "@track", default=0) or 0),
        year=int(_get(node, "year", "@year", default=0) or 0),
        album_id=str(_get(node, "albumId", "@albumId", default="")),
    )


def _parse_playlist(node: dict) -> Playlist:
    return Playlist(
        id=str(_get(node, "id", "@id", default="")),
        name=_get(node, "name", "@name"),
        song_count=int(_get(node, "songCount", "@songCount", default=0) or 0),
        duration=int(_get(node, "duration", "@duration", default=0) or 0),
        cover_id=str(_get(node, "coverArt", "@coverArt", default="")),
        comment=_get(node, "comment", "@comment"),
    )


def _parse_album(node: dict) -> Album:
    return Album(
        id=str(_get(node, "id", "@id", default="")),
        name=_get(node, "name", "@name"),
        artist=_get(node, "artist", "@artist"),
        cover_id=str(_get(node, "coverArt", "@coverArt", default="")),
        song_count=int(_get(node, "songCount", "@songCount", default=0) or 0),
    )


def _parse_artist(node: dict) -> Artist:
    return Artist(
        id=str(_get(node, "id", "@id", default="")),
        name=_get(node, "name", "@name"),
        cover_id=str(_get(node, "coverArt", "@coverArt", default="")),
        album_count=int(_get(node, "albumCount", "@albumCount", default=0) or 0),
    )


class SubsonicClient:
    """Subsonic REST 客户端。非线程安全的同步实现，网络调用请放到后台线程。"""

    def __init__(self, host: str, port: int, username: str, password: str, protocol: str = "http") -> None:
        self.base = f"{protocol}://{host}:{port}/rest"
        self.base_root = f"{protocol}://{host}:{port}"
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers["User-Agent"] = f"{CLIENT_NAME}/{API_VERSION}"
        self._auth = self._auth_params()
        self._jf_lock = threading.Lock()
        self._jf_cache: tuple | None = None  # (token, userId) Jellyfin 登录缓存

    # ---------- 认证 ----------
    def _auth_params(self) -> dict:
        salt = secrets.token_hex(8)
        token = hashlib.md5((self.password + salt).encode("utf-8")).hexdigest()
        return {"u": self.username, "t": token, "s": salt, "v": API_VERSION, "c": CLIENT_NAME, "f": "json"}

    def _get(self, view: str, timeout: float = 15, **params: Any) -> dict:
        req = dict(self._auth)
        req.update(params)
        resp = self.session.get(f"{self.base}/{view}", params=req, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        body = data.get("subsonic-response") or data
        if body.get("status") != "ok":
            err = body.get("error", {}) or {}
            raise ConnectionError(f"Subsonic 错误: {err.get('message', '未知错误')}")
        return body

    # ---------- 基础 ----------
    def ping(self) -> bool:
        try:
            self._get("ping", timeout=8)
            return True
        except Exception:
            return False

    # ---------- 歌单 ----------
    def get_playlists(self) -> list[Playlist]:
        body = self._get("getPlaylists")
        return [_parse_playlist(n) for n in _as_list((body.get("playlists") or {}).get("playlist"))]

    def get_playlist_songs(self, playlist_id: str, page_size: int = 500, max_pages: int = 80, jellyfin: bool = True) -> list[Song]:
        """分页感知加载歌单歌曲。

        服务器若支持 offset/count 则逐页取完；若不支持分页（如音桥固定返回前 50 首）则自动停止。
        遇到返回数量被服务器压缩（返回数 < 请求数）时，自动把页大小收缩为该数量，保证 offset 步进与页大小一致。
        若服务端硬性截断（忽略分页），再用 Jellyfin 协议补全完整歌单（jellyfin=False 时跳过，用于快速首屏）。
        """
        songs: list[Song] = []
        seen: set[str] = set()
        capped = False
        step = page_size
        offset = 0
        while offset < max_pages * step and len(songs) < max_pages * page_size:
            body = self._get("getPlaylist", id=playlist_id, offset=offset, count=step)
            page = [_parse_song(n) for n in _as_list((body.get("playlist") or {}).get("entry"))]
            if not page:
                break
            new_ids = [s.id for s in page if s.id not in seen]
            if offset > 0 and not new_ids:
                capped = True  # 服务器忽略分页，返回相同内容
                break
            for s in page:
                seen.add(s.id)
                songs.append(s)
            if len(page) < step:
                if len(page) < page_size:
                    if step == len(page):
                        break  # 页大小已收缩到服务端上限，无法再推进
                    step = len(page)  # 服务端有返回上限，收缩页大小继续尝试
                else:
                    break
                if step <= 0:
                    break
            offset += step
        # 服务端硬性截断 → 改用 Jellyfin 协议取完整歌单（jellyfin=False 时保留被截断的结果，用于快速首屏）
        if capped and jellyfin:
            full = self.get_playlist_songs_jellyfin(playlist_id)
            if len(full) > len(songs):
                songs = full
        return songs

    # ---------- Jellyfin 补全（音桥等把 getPlaylist 截断在 50 首时的兜底协议） ----------
    def _jf_login(self) -> tuple | None:
        try:
            resp = self.session.post(
                f"{self.base_root}/Users/AuthenticateByName",
                json={"Username": self.username, "Pw": self.password},
                headers={"Authorization": 'MediaBrowser Client="mup", Device="pc", DeviceId="mup001", Version="1.0"',
                         "Content-Type": "application/json"},
                timeout=12,
            )
            d = resp.json()
            tok = d.get("AccessToken")
            uid = d.get("User", {}).get("Id")
            return (tok, uid) if tok and uid else None
        except Exception:  # noqa: BLE001
            return None

    def _jf_ready(self) -> tuple | None:
        with self._jf_lock:
            if self._jf_cache is None:
                self._jf_cache = self._jf_login()
            return self._jf_cache

    @staticmethod
    def _strip_prefix(value: str, prefix: str) -> str:
        value = str(value or "")
        return value[len(prefix):] if value.startswith(prefix) else value

    def _jf_to_song(self, item: dict) -> Song:
        item_id = str(item.get("Id") or "")
        artists = item.get("Artists") or []
        artist = ", ".join(a for a in artists if a) or item.get("AlbumArtist") or ""
        ai = item.get("ArtistItems") or []
        artist_id = self._strip_prefix(str(ai[0].get("Id") or ""), "fnm-artist-") if ai else ""
        return Song(
            id=self._strip_prefix(item_id, "fnm-track-"),
            title=str(item.get("Name") or ""),
            artist=artist,
            artist_id=artist_id,
            album=str(item.get("Album") or ""),
            duration=int((item.get("RunTimeTicks") or 0) // 10_000_000),
            cover_id=item_id,  # 用 Jellyfin 条目 id 走 Jellyfin 图片接口取封面
            album_id=self._strip_prefix(str(item.get("AlbumId") or ""), "fnm-album-"),
        )

    def get_playlist_songs_jellyfin(self, playlist_id: str, limit: int = 200, max_items: int = 20000) -> list[Song]:
        """通过 Jellyfin 协议分页取完整歌单（音桥同时暴露 Subsonic/Jellyfin/Ampache）。"""
        creds = self._jf_ready()
        if not creds:
            return []
        tok, uid = creds
        headers = {"X-Emby-Token": tok}
        jf_pid = f"fnm-playlist-{playlist_id}"
        songs: list[Song] = []
        start = 0
        while start < max_items:
            try:
                resp = self.session.get(
                    f"{self.base_root}/Playlists/{jf_pid}/Items",
                    params={"userId": uid, "StartIndex": start, "Limit": limit},
                    headers=headers,
                    timeout=25,
                )
                body = resp.json()
            except Exception:  # noqa: BLE001
                break
            items = body.get("Items") or []
            if not items:
                break
            for item in items:
                song = self._jf_to_song(item)
                if song.id:
                    songs.append(song)
            total = int(body.get("TotalRecordCount") or 0)
            start += limit
            if len(items) < limit or (total and len(songs) >= total):
                break
        return songs

    def get_playlist_counts(self, playlists: list) -> dict[str, int]:
        """读取每个歌单的真实歌曲数（部分服务端 getPlaylists 不带 songCount，需按歌单查询）。"""
        counts: dict[str, int] = {}
        for pl in playlists:
            count = int(pl.song_count or 0)
            try:
                body = self._get("getPlaylist", id=pl.id)
                node = body.get("playlist") or {}
                count = int(_get(node, "songCount", "@songCount", default=count) or 0)
            except Exception:  # noqa: BLE001
                pass
            counts[pl.id] = count
        return counts

    # ---------- 收藏 ----------
    def get_starred(self) -> list[Song]:
        body = self._get("getStarred2")
        return [_parse_song(n) for n in _as_list((body.get("starred2") or {}).get("song"))]

    def set_starred(self, song_id: str, starred: bool) -> bool:
        try:
            self._get("star", id=song_id) if starred else self._get("unstar", id=song_id)
            return True
        except Exception:
            return False

    # ---------- 专辑 ----------
    def get_albums(self, list_type: str = "newest", size: int = 200) -> list[Album]:
        body = self._get("getAlbumList2", type=list_type, size=size)
        return [_parse_album(n) for n in _as_list((body.get("albumList2") or {}).get("album"))]

    def get_album(self, album_id: str) -> list[Song]:
        body = self._get("getAlbum", id=album_id)
        return [_parse_song(n) for n in _as_list((body.get("album") or {}).get("song"))]

    # ---------- 歌手 ----------
    def get_artists(self) -> list[Artist]:
        body = self._get("getArtists")
        artists: list[Artist] = []
        for index in _as_list((body.get("artists") or {}).get("index")):
            for node in _as_list(index.get("artist")):
                artists.append(_parse_artist(node))
        return artists

    def get_artist_albums(self, artist_id: str) -> list[Album]:
        body = self._get("getArtist", id=artist_id)
        return [_parse_album(n) for n in _as_list((body.get("artist") or {}).get("album"))]

    def get_artist_songs(self, artist_id: str) -> list[Song]:
        """取某歌手的全部歌曲（逐专辑合并，后台线程调用）。"""
        songs: list[Song] = []
        for album in self.get_artist_albums(artist_id):
            try:
                songs.extend(self.get_album(album.id))
            except Exception:  # noqa: BLE001
                continue
        return songs

    def get_artist_song_counts(self, artists: list) -> dict[str, int]:
        """并发统计每位歌手的曲库歌曲数（按专辑 songCount 求和）。"""
        from concurrent.futures import ThreadPoolExecutor

        def one(artist) -> tuple[str, int]:
            try:
                return artist.id, sum(a.song_count for a in self.get_artist_albums(artist.id))
            except Exception:  # noqa: BLE001
                return artist.id, 0

        with ThreadPoolExecutor(max_workers=12) as ex:
            return dict(ex.map(one, artists))

    def get_artist_counts_fast(self, artists: list) -> dict[str, int]:
        """快速聚合：合并多种 getAlbumList2 类型（各 500 张专辑）按歌手聚合歌曲数。

        单次请求级开销即可得到较好的"歌曲数排序"，避免对每位歌手逐次请求。
        """
        artist_counts: dict[str, int] = {}
        for list_type in ("newest", "alphabeticalByName", "alphabeticalByArtist"):
            try:
                body = self._get("getAlbumList2", type=list_type, size=500)
                for node in _as_list((body.get("albumList2") or {}).get("album")):
                    aid = str(_get(node, "artistId", "@artistId", default=""))
                    if not aid:
                        continue
                    artist_counts[aid] = artist_counts.get(aid, 0) + int(_get(node, "songCount", "@songCount", default=0) or 0)
            except Exception:  # noqa: BLE001
                continue
        return {a.id: artist_counts.get(a.id, 0) for a in artists}

    # ---------- 搜索 ----------
    def search(self, query: str) -> tuple[list[Song], list[Album], list[Artist]]:
        body = self._get("search3", query=query, songCount=200, albumCount=60, artistCount=60)
        res = body.get("searchResult3") or {}
        songs = [_parse_song(n) for n in _as_list(res.get("song"))]
        albums = [_parse_album(n) for n in _as_list(res.get("album"))]
        artists = [_parse_artist(n) for n in _as_list(res.get("artist"))]
        return songs, albums, artists

    # ---------- 播放队列 / 最近播放 ----------
    def get_play_queue(self) -> list[Song]:
        body = self._get("getPlayQueue")
        return [_parse_song(n) for n in _as_list((body.get("playQueue") or {}).get("entry"))]

    # ---------- 歌词 ----------
    def get_lyrics(self, artist: str, title: str) -> str:
        """返回原始歌词文本；可能为 LRC 或纯文本。找不到返回空串。"""
        try:
            body = self._get("getLyrics", artist=artist or "", title=title or "")
            lyr = (body.get("lyrics") or {}).get("lyric", "")
            return lyr or ""
        except Exception:
            return ""

    def get_lyrics_by_song_id(self, song_id: str) -> list[LyricLine]:
        """OpenSubsonic 结构化歌词（带 start 时间轴）；无则返回空列表。"""
        try:
            body = self._get("getLyricsBySongId", id=song_id)
            lst = body.get("lyricsList") or {}
            out: list[LyricLine] = []
            for sl in _as_list(lst.get("structuredLyrics")):
                for line in _as_list(sl.get("line")):
                    start = int(_get(line, "start", default=-1))
                    value = _get(line, "value", default="")
                    if value:
                        out.append(LyricLine(start, value))
            return out
        except Exception:
            return []

    # ---------- URL 构造 ----------
    def stream_url(self, song_id: str) -> str:
        return f"{self.base}/stream.view?" + urlencode({**self._auth, "id": song_id})

    def cover_url(self, cover_id: str, size: int = 160) -> str:
        cover_id = str(cover_id or "")
        # Jellyfin 条目 id（fnm- 前缀）→ 走 Jellyfin 图片接口（公开、无需鉴权）
        if cover_id.startswith("fnm-"):
            return f"{self.base_root}/Items/{cover_id}/Images/Primary?maxHeight={size}&maxWidth={size}"
        return f"{self.base}/getCoverArt.view?" + urlencode({**self._auth, "id": cover_id, "size": size})

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SubsonicClient {self.host}:{self.port}>"
