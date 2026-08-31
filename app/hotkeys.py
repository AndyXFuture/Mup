"""全局快捷键：自定义组合键(RegisterHotKey) + 系统媒体键(WH_KEYBOARD_LL 低级钩子)。

媒体键（播放/暂停、上/下一曲等）在 Windows 上通过按键事件分发，用低级键盘钩子可全局捕获，
不依赖窗口焦点，与 QQ 音乐/potplayer 行为一致。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312

# 系统媒体键虚拟键码
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF

_MEDIA_KEY_MAP = {
    "media_play_pause": VK_MEDIA_PLAY_PAUSE,
    "media_next": VK_MEDIA_NEXT_TRACK,
    "media_prev": VK_MEDIA_PREV_TRACK,
    "media_stop": VK_MEDIA_STOP,
    "media_volume_up": VK_VOLUME_UP,
    "media_volume_down": VK_VOLUME_DOWN,
    "media_volume_mute": VK_VOLUME_MUTE,
}
_VK_TO_ACTION = {vk: act for act, vk in _MEDIA_KEY_MAP.items()}

_MOD_NAME = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}
_VK_NAMES = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
}


def parse_combo(text: str):
    """解析 "Ctrl+Alt+P" 形式的组合键，返回 (modifiers, vk)；失败返回 None。"""
    parts = [p.strip().lower() for p in (text or "").split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    key = None
    for p in parts:
        if p in _MOD_NAME:
            mods |= _MOD_NAME[p]
        elif p in _VK_NAMES:
            key = _VK_NAMES[p]
        elif p.startswith("f") and p[1:].isdigit():
            n = int(p[1:])
            if 1 <= n <= 24:
                key = 0x70 + n - 1
        elif len(p) == 1 and p.isprintable():
            key = ord(p.upper())
        elif p.startswith("vk") and p[2:].isdigit():
            key = int(p[2:])
    if key is None:
        return None
    return mods | MOD_NOREPEAT, key


# ---------- 低级键盘钩子（媒体键） ----------
class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulonglong)),
    ]


_WH_KEYBOARD_LL = 13
_WM_KEYDOWN = 0x0100
_WM_SYSKEYDOWN = 0x0104
_WM_APPCOMMAND = 0x0319
_HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

# APPCOMMAND 常量（媒体键的另一种分发方式，作兜底）
APPCOMMAND_MEDIA_PLAY_PAUSE = 0xE
APPCOMMAND_MEDIA_NEXTTRACK = 0xB
APPCOMMAND_MEDIA_PREVIOUSTRACK = 0xC
APPCOMMAND_MEDIA_STOP = 0xD
APPCOMMAND_VOLUME_UP = 0xA
APPCOMMAND_VOLUME_DOWN = 0x9
APPCOMMAND_VOLUME_MUTE = 0x8
_APPCOMMAND_TO_ACTION = {
    APPCOMMAND_MEDIA_PLAY_PAUSE: "media_play_pause",
    APPCOMMAND_MEDIA_NEXTTRACK: "media_next",
    APPCOMMAND_MEDIA_PREVIOUSTRACK: "media_prev",
    APPCOMMAND_MEDIA_STOP: "media_stop",
    APPCOMMAND_VOLUME_UP: "media_volume_up",
    APPCOMMAND_VOLUME_DOWN: "media_volume_down",
    APPCOMMAND_VOLUME_MUTE: "media_volume_mute",
}


class MediaKeyHook:
    """低级键盘钩子：全局捕获媒体键与音量键，不依赖窗口焦点。"""

    def __init__(self, on_action) -> None:
        self._on_action = on_action
        self._handle = None
        self._callback = _HOOKPROC(self._proc)  # 持有引用防止被回收
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        user32.CallNextHookEx.restype = ctypes.c_long
        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]

    def _proc(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code >= 0 and w_param in (_WM_KEYDOWN, _WM_SYSKEYDOWN):
            kbd = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            action = _VK_TO_ACTION.get(int(kbd.vkCode))
            if action:
                self._on_action(action)
                return 1  # 吞掉该键，避免其他应用重复响应
        return user32.CallNextHookEx(self._handle, n_code, w_param, l_param)

    def install(self) -> bool:
        if self._handle:
            return True
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        module = kernel32.GetModuleHandleW(None)
        self._handle = user32.SetWindowsHookExW(_WH_KEYBOARD_LL, self._callback, module, 0)
        if not self._handle:
            print(f"[hotkeys] 低级键盘钩子安装失败，GetLastError={ctypes.get_last_error() or ctypes.windll.kernel32.GetLastError()}")
        return bool(self._handle)

    def uninstall(self) -> None:
        if self._handle:
            user32.UnhookWindowsHookEx(self._handle)
            self._handle = None


# ---------- RegisterHotKey / WM_APPCOMMAND 原生事件过滤 ----------
class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback, appcmd_callback) -> None:
        super().__init__()
        self._callback = callback
        self._appcmd = appcmd_callback

    def nativeEventFilter(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self._callback(int(msg.wParam))
            elif msg.message == _WM_APPCOMMAND:
                cmd = (msg.lParam >> 16) & ~0xF000
                action = _APPCOMMAND_TO_ACTION.get(int(cmd))
                if action:
                    self._appcmd(action)
                    return (True, 1)  # 已处理
        return False, 0


class GlobalHotkeys(QObject):
    """注册与分发全局快捷键。triggered 信号携带动作名。"""

    triggered = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._ids: dict[int, str] = {}
        self._next_id = 0x8000
        self._filter = _HotkeyFilter(self._on_hotkey, self._on_media)
        QCoreApplication.instance().installNativeEventFilter(self._filter)
        self._media_hook = MediaKeyHook(self._on_media)

    def _on_hotkey(self, hotkey_id: int) -> None:
        action = self._ids.get(hotkey_id)
        if action:
            self.triggered.emit(action)

    def _on_media(self, action: str) -> None:
        self.triggered.emit(action)

    def register(self, action: str, mods: int, vk: int) -> bool:
        ok = user32.RegisterHotKey(None, self._next_id, mods, vk)
        if ok:
            self._ids[self._next_id] = action
            self._next_id += 1
        return bool(ok)

    def register_combo(self, action: str, combo: str) -> bool:
        parsed = parse_combo(combo)
        if not parsed:
            return False
        return self.register(action, *parsed)

    def install_media_hook(self) -> bool:
        """安装媒体键低级钩子（代替 RegisterHotKey 注册媒体键）。"""
        return self._media_hook.install()

    def unregister_all(self) -> None:
        for hid in self._ids:
            user32.UnregisterHotKey(None, hid)
        self._ids.clear()
        self._media_hook.uninstall()
