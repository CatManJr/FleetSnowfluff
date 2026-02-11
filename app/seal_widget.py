from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QMouseEvent, QMovie
from PySide6.QtWidgets import QLabel


class SealWidget(QLabel):
    def __init__(
        self,
        movie_path: Path,
        geometry: QRect,
        on_closed: Callable[["SealWidget"], None],
    ) -> None:
        super().__init__()
        self._on_closed = on_closed
        self._movie = QMovie(str(movie_path))
        self._movie.setScaledSize(QSize(100, 100))
        self.setMovie(self._movie)
        self._movie.start()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        if sys.platform == "darwin":
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.resize(QSize(100, 100))
        self._place_randomly(geometry)
        self.show()
        self.raise_()

    def _place_randomly(self, geometry: QRect) -> None:
        max_x = max(geometry.left(), geometry.right() - self.width())
        max_y = max(geometry.top(), geometry.bottom() - self.height())
        x = random.randint(geometry.left(), max_x)
        y = random.randint(geometry.top(), max_y)
        self.move(x, y)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.close()
            event.accept()
            return
        super().mousePressEvent(event)

    def closeEvent(self, event) -> None:
        self._movie.stop()
        self._on_closed(self)
        super().closeEvent(event)
