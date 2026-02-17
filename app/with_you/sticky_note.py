"""Sticky note dialog with text and draw tabs."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QPushButton, QTabWidget, QTextEdit, QVBoxLayout

from app.ui_scale import current_app_scale

from . import styles
from .draw_canvas import DrawCanvas


class StickyNoteWindow(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("便利贴")
        self.resize(340, 380)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.Tool)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        tabs = QTabWidget(self)
        self._text = QTextEdit(self)
        self._text.setPlaceholderText("在这里记录想法...")
        self._draw = DrawCanvas(self)
        tabs.addTab(self._text, "文字")
        tabs.addTab(self._draw, "绘画")
        root.addWidget(tabs, 1)

        btn_row = QHBoxLayout()
        clear_btn = QPushButton("清除", self)
        clear_btn.setToolTip("清除文字与绘画内容")
        clear_btn.clicked.connect(self._clear_all_content)
        btn_row.addStretch(1)
        btn_row.addWidget(clear_btn)
        root.addLayout(btn_row)

        app = QApplication.instance()
        scale = current_app_scale(app) if app is not None else 1.0
        self.setStyleSheet(styles.build_sticky_note_stylesheet(scale))

    def _clear_all_content(self) -> None:
        self._text.clear()
        self._draw.clear_canvas()
