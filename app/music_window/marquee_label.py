"""Scrolling marquee label for track title."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPaintEvent, QPainter
from PySide6.QtWidgets import QLabel


class MarqueeLabel(QLabel):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self._full_text = text
        self._offset = 0
        self._gap = 36
        self._scroll_speed_px = 1
        self._timer = QTimer(self)
        self._timer.setInterval(70)
        self._timer.timeout.connect(self._tick)

    def setMarqueeText(self, text: str) -> None:
        self._full_text = text
        self.setToolTip(text if text and text != "-" else "")
        self._offset = 0
        self._update_scroll_state()
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_scroll_state()

    def _tick(self) -> None:
        text_width = self.fontMetrics().horizontalAdvance(self._full_text)
        if text_width <= self.width():
            self._offset = 0
            return
        cycle = text_width + self._gap
        self._offset = (self._offset + self._scroll_speed_px) % cycle
        self.update()

    def _update_scroll_state(self) -> None:
        needs_scroll = self.fontMetrics().horizontalAdvance(self._full_text) > self.width()
        if needs_scroll:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self._offset = 0

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setPen(self.palette().color(self.foregroundRole()))
        rect = self.contentsRect()
        painter.setClipRect(rect)
        fm = self.fontMetrics()
        baseline = rect.y() + (rect.height() + fm.ascent() - fm.descent()) // 2
        text_width = fm.horizontalAdvance(self._full_text)
        if text_width <= rect.width():
            painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._full_text)
            return
        start_x = rect.x() - self._offset
        painter.drawText(start_x, baseline, self._full_text)
        painter.drawText(start_x + text_width + self._gap, baseline, self._full_text)
