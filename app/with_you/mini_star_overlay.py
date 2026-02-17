"""Subtle star glints for MiniCallBar."""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class MiniStarOverlay(QWidget):
    """Subtle star glints for MiniCallBar."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._stars: list[dict[str, float]] = []
        self._star_count = 26
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    def _on_tick(self) -> None:
        self._phase += 1.0
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._seed_stars(force=True)

    def _seed_stars(self, *, force: bool = False) -> None:
        w = float(max(1, self.width()))
        h = float(max(1, self.height()))
        if (not force) and len(self._stars) == self._star_count:
            return
        self._stars = []
        for _ in range(self._star_count):
            self._stars.append(
                {
                    "x": random.random() * w,
                    "y": random.random() * h,
                    "r": 0.35 + random.random() * 0.95,
                    "alpha": 55 + random.random() * 125,
                    "twinkle": 0.8 + random.random() * 1.8,
                    "phase": random.random() * math.pi * 2.0,
                }
            )

    def paintEvent(self, _event) -> None:
        if not self._stars:
            self._seed_stars()
        w = self.width()
        h = self.height()
        if w <= 2 or h <= 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        clip = QPainterPath()
        clip.addRoundedRect(self.rect(), 20.0, 20.0)
        painter.setClipPath(clip)
        t = self._phase
        for star in self._stars:
            twinkle = 0.46 + 0.54 * (0.5 + 0.5 * math.sin((t * 0.070 * star["twinkle"]) + star["phase"]))
            alpha = int(star["alpha"] * twinkle)
            if alpha < 10:
                continue
            x = star["x"]
            y = star["y"]
            r = star["r"]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(246, 252, 255, alpha))
            painter.drawEllipse(QPoint(int(x), int(y)), max(1, int(r)), max(1, int(r)))
            if twinkle > 0.84:
                pen = QPen(QColor(255, 255, 255, int(alpha * 0.52)))
                pen.setWidthF(0.75)
                painter.setPen(pen)
                painter.drawLine(QPoint(int(x - r * 1.6), int(y)), QPoint(int(x + r * 1.6), int(y)))
                painter.drawLine(QPoint(int(x), int(y - r * 1.6)), QPoint(int(x), int(y + r * 1.6)))
