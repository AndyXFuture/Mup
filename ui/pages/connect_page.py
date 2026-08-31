"""连接服务器页：填写 Subsonic 服务器参数并验证连接。"""
from __future__ import annotations

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.config import Config
from app.subsonic_client import SubsonicClient
from ui import icons, theme
from ui.widgets import NeuButton, NeuFrame, NeuLineEdit


class PingThread(QThread):
    """后台线程验证 Subsonic 连接。"""

    done = Signal(bool, str)

    def __init__(self, client: SubsonicClient, parent=None) -> None:
        super().__init__(parent)
        self.client = client

    def run(self) -> None:
        try:
            ok = self.client.ping()
            self.done.emit(ok, "" if ok else "无法连接服务器，请检查地址与端口")
        except Exception as exc:  # noqa: BLE001
            self.done.emit(False, str(exc))


class _Logo(QWidget):
    """靛蓝圆角 Logo。"""

    def __init__(self, parent=None, px: int = 62) -> None:
        super().__init__(parent)
        self.px = px
        self.setFixedSize(px, px)

    def paintEvent(self, event) -> None:
        pal = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(pal["primary"]))
        r = self.rect().adjusted(1, 1, -1, -1)
        p.drawRoundedRect(r, 22, 22)
        ip = icons.pixmap("note", pal["on_primary"], 30, stroke=1.6)
        p.drawPixmap((self.width() - 30) // 2, (self.height() - 30) // 2, ip)


class ConnectPage(QWidget):
    """首启/重连页面。连接成功后发出 connected(client)。"""

    connected = Signal(object)

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._ping: PingThread | None = None
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        card = NeuFrame(self, radius=22)
        card.setFixedWidth(360)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(35, 38, 35, 34)
        card_layout.setSpacing(0)

        self._logo = _Logo()
        card_layout.addWidget(self._logo, 0, Qt.AlignmentFlag.AlignHCenter)
        title = QLabel("连接到音乐服务器")
        f = QFont("Microsoft YaHei UI")
        f.setPointSizeF(13)
        f.setWeight(QFont.Weight.DemiBold)
        title.setFont(f)
        card_layout.addSpacing(12)
        card_layout.addWidget(title, 0, Qt.AlignmentFlag.AlignHCenter)

        sub = QLabel("通过 Subsonic 协议接入「音桥 · 飞牛音乐」")
        fs = QFont("Microsoft YaHei UI")
        fs.setPointSizeF(9)
        sub.setFont(fs)
        sub.setStyleSheet(f"color: {theme.CURRENT['text_muted']};")
        card_layout.addSpacing(5)
        card_layout.addWidget(sub, 0, Qt.AlignmentFlag.AlignHCenter)
        card_layout.addSpacing(20)

        srv = self.config.server
        self.host = NeuLineEdit(srv.get("host", ""), "例如 192.168.0.116")
        self.port = NeuLineEdit(str(srv.get("port", 14040)), "端口")
        self.user = NeuLineEdit(srv.get("username", ""), "用户名")
        self.pwd = NeuLineEdit(srv.get("password", ""), "密码", password=True)

        card_layout.addWidget(self._field("服务器地址", self.host))
        pr = QHBoxLayout()
        pr.setSpacing(12)
        pr.addWidget(self._field("端口", self.port))
        pr.addWidget(self._field("用户名", self.user))
        card_layout.addLayout(pr)
        card_layout.addWidget(self._field("密码", self.pwd))
        card_layout.addSpacing(18)

        self.btn = NeuButton("连 接", accent=True)
        self.btn.setMinimumHeight(42)
        self.btn.clicked.connect(self._on_connect)
        card_layout.addWidget(self.btn)

        self.status = QLabel("")
        fs2 = QFont("Microsoft YaHei UI")
        fs2.setPointSizeF(9)
        self.status.setFont(fs2)
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addSpacing(10)
        card_layout.addWidget(self.status)

        hint = QLabel("首次启动需填写连接参数，连接成功后自动保存，\n可在「设置」中重新填写")
        hint.setFont(fs2)
        hint.setStyleSheet(f"color: {theme.CURRENT['text_muted']};")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addSpacing(14)
        card_layout.addWidget(hint)
        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

    def _field(self, label: str, edit: NeuLineEdit) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 10)
        v.setSpacing(4)
        lb = QLabel(label)
        ff = QFont("Microsoft YaHei UI")
        ff.setPointSizeF(8.5)
        lb.setFont(ff)
        lb.setStyleSheet(f"color: {theme.CURRENT['text_muted']};")
        v.addWidget(lb)
        v.addWidget(edit)
        return wrap

    def _on_connect(self) -> None:
        host = self.host.text().strip()
        try:
            port = int(self.port.text().strip() or 14040)
        except ValueError:
            self._show_status("端口格式不正确", error=True)
            return
        user = self.user.text().strip()
        pwd = self.pwd.text()
        if not host or not user:
            self._show_status("请填写服务器地址与用户名", error=True)
            return
        client = SubsonicClient(host, port, user, pwd)
        self.btn.setEnabled(False)
        self._show_status("正在连接…")
        self._ping = PingThread(client, self)
        self._ping.done.connect(self._on_done)
        self._ping.start()

    def _on_done(self, ok: bool, msg: str) -> None:
        self.btn.setEnabled(True)
        if ok:
            srv = self.config.server
            srv["host"] = self.host.text().strip()
            srv["port"] = int(self.port.text().strip() or 14040)
            srv["username"] = self.user.text().strip()
            srv["password"] = self.pwd.text()
            self.config.save()
            self._show_status("连接成功", error=False, ok=True)
            client = SubsonicClient(srv["host"], srv["port"], srv["username"], srv["password"])
            self.connected.emit(client)
        else:
            self._show_status(msg or "连接失败", error=True)

    def _show_status(self, text: str, error: bool = False, ok: bool = False) -> None:
        pal = theme.CURRENT
        color = pal["ok"] if ok else (pal["danger"] if error else pal["text_muted"])
        self.status.setStyleSheet(f"color: {color};")
        self.status.setText(text)
