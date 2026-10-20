"""统一动效驱动：全局单 ticker + 过渡量工具。

设计约束（保证低占用，改动时请勿破坏）：
- 全应用**只有一个 QTimer**；没有任何进行中的过渡时自动 stop → 静止时零开销
- 过渡进度由「起始时刻 + 时长」计算，不做帧累加：掉帧只会少画几帧，不会变慢/拖尾
- 只重绘「参与过渡的控件（可指定 rect）」，**绝不整窗 update**
- 控件不可见时跳过重绘（计时照常结束）
- 「减少动效」开启时所有时长归零 → 全部退化为瞬时切换
"""
from __future__ import annotations

import time
import weakref
from typing import Optional

from PySide6.QtCore import QObject, QRect, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

TICK_MS = 16        # 全局节拍，约 60fps
HOVER_MS = 130      # 悬浮过渡
PRESS_MS = 90       # 按压/回弹过渡
EASE_MS = 140       # 数值追赶（进度条等）
SHIMMER_MS = 60      # 封面占位扫光：单次请求的持续时长
SHIMMER_EVERY_MS = 40  # 扫光刷新间隔（约 25fps，避免大面积高频重绘）
STAGGER_STEP_MS = 22  # 列表入场每行错开
STAGGER_DUR_MS = 220  # 单行入场时长

_reduced = False


def set_reduced_motion(on: bool) -> None:
    """「减少动效」：开启后所有过渡时长归零（瞬时完成）。"""
    global _reduced
    _reduced = bool(on)


def reduced_motion() -> bool:
    return _reduced


def dur(ms: int) -> int:
    """按「减少动效」折算实际时长。"""
    return 0 if _reduced else int(ms)


def ease_out_cubic(t: float) -> float:
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return 1.0 - (1.0 - t) ** 3


def clamp01(t: float) -> float:
    return 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)


def mix(c1: QColor, c2: QColor, t: float) -> QColor:
    """两色线性插值（t=0 → c1，t=1 → c2），返回新对象，不改入参。"""
    t = clamp01(t)
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue() + (c2.blue() - c1.blue()) * t),
        int(c1.alpha() + (c2.alpha() - c1.alpha()) * t),
    )


class _Ticker(QObject):
    """全局节拍器：按请求持续刷新若干控件/区域，队列空了自动停止。"""

    def __init__(self) -> None:
        super().__init__()
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        # key = (weakref(widget), x, y, w, h)（全 0 表示整控件）→ (结束时刻, 刷新间隔, 下次到期)
        self._entries: dict[tuple, tuple] = {}

    def request(self, widget: QWidget, ms: int, rect: Optional[QRect] = None,
                every_ms: int = 0) -> None:
        """请求在接下来 ms 毫秒内持续刷新该控件；rect 非空时只刷该区域。

        every_ms 为该条目的刷新间隔（默认跟随全局节拍）；扫光这类大面积动效
        可以调大它以显著降低重绘量。
        """
        if ms <= 0:
            return
        if not isinstance(widget, QWidget):  # 防误用：非控件入队会让整个 ticker 卡死
            return
        ref = weakref.ref(widget)
        if rect is None or rect.isEmpty():
            key = (ref, 0, 0, 0, 0)
        else:
            key = (ref, rect.x(), rect.y(), rect.width(), rect.height())
        now = time.monotonic()
        self._entries[key] = (now + ms / 1000.0 + TICK_MS / 1000.0,
                              max(TICK_MS, every_ms or TICK_MS), 0.0)
        if not self._timer.isActive():
            self._timer.start()

    def busy(self) -> bool:
        return bool(self._entries)

    def _tick(self) -> None:
        now = time.monotonic()
        for key, (deadline, every, next_due) in list(self._entries.items()):
            widget = key[0]()
            if widget is None:
                self._entries.pop(key, None)
                continue
            if now >= next_due:
                try:
                    if widget.isVisible():
                        _, x, y, w, h = key
                        if w or h:
                            widget.update(QRect(x, y, w, h))
                        else:
                            widget.update()
                except Exception:  # noqa: BLE001 C++ 对象已销毁/异常都不能让 ticker 卡死
                    self._entries.pop(key, None)
                    continue
                next_due = now + every / 1000.0
            if now >= deadline:
                # 结束前补一次最终重绘，保证动画落在目标值上
                try:
                    if widget.isVisible() and (key[3] or key[4]):
                        widget.update(QRect(key[1], key[2], key[3], key[4]))
                    elif widget.isVisible():
                        widget.update()
                except Exception:  # noqa: BLE001
                    pass
                self._entries.pop(key, None)
                continue
            self._entries[key] = (deadline, every, next_due)
        if not self._entries:
            self._timer.stop()


_ticker_cache: Optional[_Ticker] = None


def ticker() -> _Ticker:
    """取全局 ticker（懒创建：首次调用须在 QApplication 之后）。"""
    global _ticker_cache
    if _ticker_cache is None:
        _ticker_cache = _Ticker()
    return _ticker_cache


def request(widget: QWidget, ms: int, rect: Optional[QRect] = None, every_ms: int = 0) -> None:
    """请求持续刷新；every_ms 可单独放慢该条目的刷新频率。"""
    ticker().request(widget, dur(ms), rect, every_ms)


class Motion:
    """一个 0..1 过渡量：控件持有它，paint 时读 `value()`，无需自己管定时器。"""

    __slots__ = ("_owner", "_ms", "_from", "_to", "_t0")

    def __init__(self, owner: QWidget, ms: int = HOVER_MS, value: float = 0.0) -> None:
        self._owner = owner
        self._ms = ms
        self._from = float(value)
        self._to = float(value)
        self._t0 = 0.0

    def to(self, target: float) -> None:
        """平滑过渡到 target（0..1）。"""
        target = clamp01(target)
        if target == self._to:
            return
        cur = self.value()
        self._from = cur
        self._to = target
        self._t0 = time.monotonic()
        ms = dur(self._ms)
        if ms <= 0 or cur == target:
            self._from = self._to
            self._owner.update()
            return
        request(self._owner, ms)

    def set(self, value: float) -> None:
        """直接设定（不产生过渡）。"""
        self._from = self._to = clamp01(value)
        self._owner.update()

    def value(self) -> float:
        if self._from == self._to or self._ms <= 0:
            return self._to
        t = (time.monotonic() - self._t0) * 1000.0 / self._ms
        if t >= 1.0:
            return self._to
        return self._from + (self._to - self._from) * ease_out_cubic(t)

    def animating(self) -> bool:
        return self._from != self._to


def staggered_t(start_ms: float, index: int, dur_ms: int = STAGGER_DUR_MS,
                step_ms: int = STAGGER_STEP_MS) -> float:
    """列表「逐行入场」进度：第 index 行延后 index*step_ms 开始，返回 0..1 已缓动值。"""
    if reduced_motion():
        return 1.0
    el = (time.monotonic() - start_ms) * 1000.0 - index * step_ms
    if el <= 0.0:
        return 0.0
    return ease_out_cubic(el / max(1.0, float(dur_ms)))