"""Playlist tree widget with optional background image."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import QTreeWidget


class PlaylistTreeWidget(QTreeWidget):
    def __init__(self, bg_path: Path | None, parent=None) -> None:
        super().__init__(parent)
        self._bg_pixmap: QPixmap | None = None
        if bg_path is not None and bg_path.exists():
            pixmap = QPixmap(str(bg_path))
            if not pixmap.isNull():
                self._bg_pixmap = pixmap

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        viewport_rect = self.viewport().rect()
        if self._bg_pixmap is not None and not self._bg_pixmap.isNull():
            src_size = self._bg_pixmap.size()
            if src_size.width() > 0 and src_size.height() > 0:
                scale_w = viewport_rect.width() / src_size.width()
                scale_h = viewport_rect.height() / src_size.height()
                scale = min(scale_w, scale_h)
                target_w = max(1, int(src_size.width() * scale))
                target_h = max(1, int(src_size.height() * scale))
                scaled = self._bg_pixmap.scaled(
                    target_w,
                    target_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                x = viewport_rect.x() + (viewport_rect.width() - scaled.width()) // 2
                y = viewport_rect.y() + (viewport_rect.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
        super().paintEvent(event)
