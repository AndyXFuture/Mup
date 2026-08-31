"""配置管理：服务器参数、播放设置、快捷键、主题，持久化到 config.json。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

APP_NAME = "音珏 - Mup"
APP_VERSION = "0.3.2"

# 打包（PyInstaller 单文件）后 __file__ 指向临时解压目录，需要分别处理：
#   APP_DIR       → exe 所在目录（config.json / logs 写在这里，持久化）
#   RESOURCE_DIR  → 资源目录（打包后在 _MEIPASS 临时目录，正常在项目 resources/）
if getattr(sys, "frozen", False):  # PyInstaller 冻结运行
    APP_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)) / "resources"
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    RESOURCE_DIR = APP_DIR / "resources"

CONFIG_PATH = APP_DIR / "config.json"
LOG_DIR = APP_DIR / "logs"

DEFAULT_CONFIG: dict = {
    "server": {"protocol": "http", "host": "", "port": 14040, "username": "", "password": ""},
    "player": {"volume": 80, "mode": "list", "last_playlist_id": "", "last_song_id": "", "last_position": 0,
               "window_size": [1080, 720]},
    "theme": "system",
    "hotkeys": {
        "play_pause": "Ctrl+Alt+P",
        "next": "Ctrl+Alt+Right",
        "prev": "Ctrl+Alt+Left",
        "volume_up": "Ctrl+Alt+Up",
        "volume_down": "Ctrl+Alt+Down",
    },
}


class Config:
    """读取/保存全局配置。"""

    def __init__(self) -> None:
        self.data: dict = json.loads(json.dumps(DEFAULT_CONFIG))
        self.load()

    def load(self) -> None:
        if not CONFIG_PATH.exists():
            return
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for key in self.data:
                if key in raw:
                    if isinstance(self.data[key], dict) and isinstance(raw[key], dict):
                        self.data[key].update(raw[key])
                    else:
                        self.data[key] = raw[key]
        except Exception as exc:  # noqa: BLE001
            print(f"读取配置失败: {exc}")

    def save(self) -> None:
        try:
            CONFIG_PATH.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            print(f"保存配置失败: {exc}")

    def __getitem__(self, key: str):
        return self.data[key]

    def __setitem__(self, key: str, value) -> None:
        self.data[key] = value

    @property
    def server(self) -> dict:
        return self.data["server"]

    @property
    def player(self) -> dict:
        return self.data["player"]

    @property
    def hotkeys(self) -> dict:
        return self.data["hotkeys"]

    @property
    def theme(self) -> str:
        return self.data["theme"]
