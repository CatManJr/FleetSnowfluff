"""Drawable canvas for sticky-note painting tab."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget


class DrawCanvas(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StaticContents, True)
        self._strokes: list[list[QPoint]] = []
        self._current_stroke: list[QPoint] | None = None
        self._pen = QPen(Qt.GlobalColor.black, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)

    def clear_canvas(self) -> None:
        self._strokes.clear()
        self._current_stroke = None
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._current_stroke = [event.position().toPoint()]
            self._strokes.append(self._current_stroke)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._current_stroke is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._current_stroke.append(event.position().toPoint())
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._current_stroke is not None:
            self._current_stroke.append(event.position().toPoint())
            self._current_stroke = None
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.white)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(self._pen)
        for stroke in self._strokes:
            if len(stroke) == 1:
                painter.drawPoint(stroke[0])
                continue
            for i in range(1, len(stroke)):
                painter.drawLine(stroke[i - 1], stroke[i])
