"""音珏 Mup - 通过 Subsonic 协议连接飞牛音乐的轻量 Windows 音乐播放器。"""
from __future__ import annotations

import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QSharedMemory, Qt, qInstallMessageHandler
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import APP_NAME, APP_VERSION, APP_DIR, Config, LOG_DIR, RESOURCE_DIR
from ui.windows import MainWindow


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    handler = RotatingFileHandler(LOG_DIR / "mup.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler],
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _excepthook(exc_type, exc_value, exc_tb) -> None:
    """Python 层未捕获异常：写日志并提示。"""
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logging.critical("未处理异常:\n%s", text)
    try:
        QMessageBox.critical(None, "音珏 - Mup 出错", f"发生未处理的异常：\n{exc_value}\n\n详细信息已写入 logs/mup.log")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(1)


def _qt_message_handler(mode, context, message) -> None:
    """Qt（C++）层消息记录到日志。"""
    if mode >= Qt.MsgType.WarningMsg:
        logging.warning("[Qt] %s", message)


def main() -> int:
    setup_logging()
    sys.excepthook = _excepthook
    qInstallMessageHandler(_qt_message_handler)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setFont(QFont("Microsoft YaHei UI", 9.5))
    icon_path = RESOURCE_DIR / "app_icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # 单实例
    shm = QSharedMemory("MupSingleInstance_v1")
    if not shm.create(1):
        QMessageBox.information(None, APP_NAME, "程序已在运行中。")
        return 0

    config = Config()
    win = MainWindow(config)
    win.show()

    if os.environ.get("MUP_SMOKE") == "1":
        # 冒烟测试：2 秒后自动退出
        from PySide6.QtCore import QTimer

        QTimer.singleShot(2000, app.quit)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
