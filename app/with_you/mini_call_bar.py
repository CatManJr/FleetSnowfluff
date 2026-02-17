"""Floating mini call bar with timer and actions."""
from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from app.ui_scale import current_app_scale, px

from . import styles
from .mini_star_overlay import MiniStarOverlay


class MiniCallBar(QDialog):
    expandRequested = Signal()
    chatRequested = Signal()
    pauseRequested = Signal()
    hangupRequested = Signal()

    def __init__(self, parent=None, theme_tokens: dict[str, str] | None = None) -> None:
        super().__init__(parent)
        self._theme_tokens = dict(theme_tokens or styles.mini_call_bar_theme_tokens())
        self._drag_offset: QPoint | None = None
        self.setWindowTitle("通话悬浮条")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        if sys.platform == "darwin":
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        self.setFixedSize(300, 92)

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        panel = QFrame(self)
        self._panel = panel
        panel.setObjectName("miniPanel")
        box = QVBoxLayout(panel)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        self.status_label = QLabel("通话中", panel)
        self.status_label.setObjectName("miniStatus")
        self.timer_label = QLabel("00:00", panel)
        self.timer_label.setObjectName("miniTimer")
        self.chat_btn = QPushButton("聊天", panel)
        self.chat_btn.setObjectName("miniBtn")
        self.chat_btn.setToolTip("打开聊天窗口")
        self.chat_btn.clicked.connect(self.chatRequested.emit)
        self.expand_btn = QPushButton("展开", panel)
        self.expand_btn.setObjectName("miniBtn")
        self.expand_btn.setToolTip("展开完整通话窗口")
        self.expand_btn.clicked.connect(self.expandRequested.emit)
        self.pause_btn = QPushButton("暂停", panel)
        self.pause_btn.setObjectName("miniBtn")
        self.pause_btn.setToolTip("暂停或继续计时")
        self.pause_btn.clicked.connect(self.pauseRequested.emit)
        self.exit_btn = QPushButton("退出", panel)
        self.exit_btn.setObjectName("miniDanger")
        self.exit_btn.setToolTip("结束通话")
        self.exit_btn.clicked.connect(self.hangupRequested.emit)

        self.timer_label.setFixedWidth(66)
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.addWidget(self.status_label)
        top_row.addStretch(1)
        top_row.addWidget(self.timer_label)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)
        self.chat_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.expand_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.pause_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.exit_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_row.addWidget(self.chat_btn, 1)
        btn_row.addWidget(self.expand_btn, 1)
        btn_row.addWidget(self.pause_btn, 1)
        btn_row.addWidget(self.exit_btn, 1)

        self._star_overlay = MiniStarOverlay(panel)
        self._star_overlay.setGeometry(panel.rect())
        self._star_overlay.lower()

        box.addLayout(top_row)
        box.addLayout(btn_row)
        root.addWidget(panel, 1)

        app = QApplication.instance()
        scale = current_app_scale(app) if app is not None else 1.0
        self._scale = scale
        panel_shadow = QGraphicsDropShadowEffect(panel)
        panel_shadow.setBlurRadius(px(26, scale))
        panel_shadow.setOffset(0, px(3, scale))
        panel_shadow.setColor(QColor(31, 44, 59, 38))
        panel.setGraphicsEffect(panel_shadow)

        self.setStyleSheet(styles.build_mini_call_bar_stylesheet(scale, self._theme_tokens))

    def set_countdown(self, text: str) -> None:
        self.timer_label.setText(text)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)
        state = "config"
        if "专注" in text:
            state = "focus"
        elif "休息" in text:
            state = "break"
        elif "暂停" in text:
            state = "pause"
        elif "结束" in text:
            state = "hangup"
        self.status_label.setProperty("miniState", state)
        style = self.status_label.style()
        if style is not None:
            style.unpolish(self.status_label)
            style.polish(self.status_label)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_star_overlay") and hasattr(self, "_panel"):
            self._star_overlay.setGeometry(self._panel.rect())
            self._star_overlay.lower()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            return
        super().keyPressEvent(event)
