from __future__ import annotations

import json
import math
import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Union, cast

from PySide6.QtCore import QPoint, QSettings, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QCloseEvent, QColor, QIcon, QKeyEvent, QLinearGradient, QMouseEvent, QPainter, QPen, QPixmap, QPainterPath, QRegion
from PySide6.QtMultimedia import QAudioDevice, QAudioOutput, QMediaPlayer, QMediaDevices, QVideoSink
try:
    from PySide6.QtMultimediaWidgets import QVideoWidget as _QVideoWidget
except Exception:  # noqa: BLE001
    _QVideoWidget = None
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QGraphicsDropShadowEffect,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QSystemTrayIcon,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .design_tokens import focus_theme_base_tokens
from .fluent_compat import apply_icon_button_layout
from .fluent_compat import FPushButton as QPushButton
from .fluent_compat import init_fluent_theme
from .ui_scale import current_app_scale, px

HAS_QVIDEO_WIDGET = _QVideoWidget is not None


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


class Aurora(QWidget):
    """Pink aurora bands with irregular cadence + white star glints."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self._phase = 0.0
        self._flow_speed = 0.020
        self._drift_speed = 0.008
        # Use a gentle startup state to avoid first-open single spikes.
        self._aurora_current = self._make_aurora_state(gentle=True)
        self._aurora_target = self._make_aurora_state(gentle=True)
        self._target_hold_frames = random.randint(140, 220)
        self._star_count = 72
        self._stars: list[dict[str, float]] = []
        self._thick_prev: list[float] = []
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    @staticmethod
    def _make_aurora_state(*, gentle: bool = False) -> dict[str, float]:
        if gentle:
            return {
                "left": random.uniform(0.03, 0.14),
                "right": random.uniform(0.04, 0.16),
                "width": random.uniform(0.44, 0.64),
                "amp": random.uniform(0.052, 0.082),
                "freq": random.uniform(0.72, 0.98),
                "shift": random.uniform(0.0, math.pi * 2.0),
                "alpha": random.uniform(116.0, 168.0),
            }
        return {
            # Upper-edge anchor in sky region.
            "left": random.uniform(0.00, 0.20),
            "right": random.uniform(0.00, 0.24),
            # Ribbon width and motion parameters.
            "width": random.uniform(0.30, 0.80),
            "amp": random.uniform(0.050, 0.125),
            "freq": random.uniform(0.60, 1.20),
            "shift": random.uniform(0.0, math.pi * 2.0),
            "alpha": random.uniform(96.0, 196.0),
        }

    def set_animating(self, enabled: bool) -> None:
        if enabled:
            if not self._timer.isActive():
                self._timer.start()
            return
        self._timer.stop()

    def _on_tick(self) -> None:
        self._phase += 1.0
        self._target_hold_frames -= 1
        if self._target_hold_frames <= 0:
            self._aurora_target = self._make_aurora_state()
            self._target_hold_frames = random.randint(110, 220)
        # Smoothly chase the next wind state.
        follow = 0.016
        for k, v in self._aurora_target.items():
            self._aurora_current[k] += (v - self._aurora_current[k]) * follow
        self._update_stars()
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._thick_prev = []
        self._seed_stars(force=True)

    def _seed_stars(self, *, force: bool = False) -> None:
        w = float(max(1, self.width()))
        h = float(max(1, self.height()))
        if w < 40 or h < 40:
            self._stars = []
            return
        if (not force) and self._stars and len(self._stars) == self._star_count:
            return
        self._stars = []
        for _ in range(self._star_count):
            self._stars.append(
                {
                    "x": random.random() * w,
                    "y": random.random() * h,
                    "vy": 0.22 + random.random() * 0.75,
                    "r": 0.50 + random.random() * 1.75,
                    "alpha": 70 + random.random() * 155,
                    "twinkle": 0.7 + random.random() * 1.9,
                    "phase": random.random() * math.pi * 2.0,
                }
            )

    def _update_stars(self) -> None:
        if not self._stars:
            self._seed_stars()
        w = float(max(1, self.width()))
        h = float(max(1, self.height()))
        if w < 40 or h < 40:
            return
        for star in self._stars:
            star["y"] += star["vy"]
            star["x"] += math.sin((self._phase * 0.010) + star["phase"]) * 0.24
            if star["y"] > h + 8.0:
                star["y"] = -8.0
                star["x"] = random.random() * w
                star["alpha"] = 70 + random.random() * 155
                star["r"] = 0.50 + random.random() * 1.75

    def paintEvent(self, _event) -> None:
        w = float(max(1, self.width()))
        h = float(max(1, self.height()))
        if w < 40 or h < 40:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        t = self._phase
        samples = 120
        x_start = -0.08 * w
        x_span = 1.16 * w
        # Hard boundary: aurora upper edge must NEVER enter setting-panel area.
        top_min = 0.0
        panel_top_boundary = h * 0.24
        host = self.parent()
        if host is not None and hasattr(host, "_middle_stack"):
            try:
                middle_stack = host._middle_stack  # type: ignore[attr-defined]
                panel_top_boundary = max(6.0, min(h - 2.0, float(middle_stack.geometry().top())))
            except Exception:
                pass

        aurora = self._aurora_current
        x_points: list[float] = []
        upper_raw: list[float] = []
        thick_values: list[float] = []
        sky_floors: list[float] = []
        for i in range(samples + 1):
            ratio = i / samples
            x = x_start + x_span * ratio
            # Treat aurora as a hanging strip: anchor from sky (top), then fall downward.
            upper_base = (((1.0 - ratio) * aurora["left"]) + (ratio * aurora["right"])) * h
            wave_a = math.sin((ratio * aurora["freq"] * 2.0 * math.pi) + (t * self._flow_speed) + aurora["shift"])
            wave_b = math.sin((ratio * 6.8) - (t * self._drift_speed) + aurora["shift"] * 1.2)
            wave_c = math.sin((ratio * 11.4) + (t * (self._drift_speed * 0.6)) + aurora["shift"] * 2.1)
            wave_d = math.sin((ratio * 17.0) + (t * (self._drift_speed * 0.24)) + aurora["shift"] * 2.4)
            upper = upper_base + (
                aurora["amp"] * 0.42 * wave_a + 0.015 * wave_b + 0.010 * wave_c + 0.004 * wave_d
            ) * h
            # Use lower-frequency envelope so thickened areas become wider curtains.
            thick_boost = (
                0.22 * (0.5 + 0.5 * math.sin((ratio * 3.4) + (t * 0.006) + aurora["shift"] * 0.8))
                + 0.14 * (0.5 + 0.5 * math.sin((ratio * 6.2) - (t * 0.003)))
                + 0.06 * math.sin((ratio * 11.0) + (t * 0.002))
            )
            thick_ratio = aurora["width"] * (0.58 + thick_boost)
            # Coherent flowing thickness field: random-like, but with temporal continuity.
            flow_field = (
                0.1
                + 0.5 * math.sin((ratio * 4.0) + (t * 0.010) + aurora["shift"] * 0.85)
                + 0.24 * math.sin((ratio * 8.6) - (t * 0.006) + aurora["shift"] * 1.7)
                + 0.14 * math.sin((ratio * 14.0) + (t * 0.004))
            )
            flow_norm = max(0.0, min(1.0, flow_field))
            thick = max(0.08 * h, ((0.10 + 0.70 * flow_norm) * h), thick_ratio * h)
            # Keep upper edge within sky area (above setting panel), but with a more irregular, organic cap.
            cap_wave = (
                4.0
                + 6.0 * (0.5 + 0.5 * math.sin((ratio * 4.3) + (t * 0.006) + aurora["shift"]))
                + 3.5 * (0.5 + 0.5 * math.sin((ratio * 12.7) - (t * 0.003) + aurora["shift"] * 1.9))
                + 2.0 * (0.5 + 0.5 * math.sin((ratio * 27.0) + (t * 0.002)))
                + 1.2 * (0.5 + 0.5 * math.sin((ratio * 16.2) + t * 0.012 + math.cos(ratio * 8.7)))
            )
            sky_floor = panel_top_boundary - cap_wave
            x_points.append(x)
            upper_raw.append(upper)
            thick_values.append(thick)
            sky_floors.append(sky_floor)

        # Temporal smoothing for random thickness: keep organic variation,
        # but avoid frame-to-frame flicker.
        if len(self._thick_prev) != len(thick_values):
            self._thick_prev = thick_values[:]
        else:
            for i, current in enumerate(thick_values):
                self._thick_prev[i] = self._thick_prev[i] * 0.72 + current * 0.28
        thick_values = self._thick_prev[:]

        # Smooth upper edge to avoid narrow pointy crests.
        upper_smooth = upper_raw[:]
        for _ in range(2):
            pass_result = upper_smooth[:]
            for i in range(1, len(upper_smooth) - 1):
                pass_result[i] = (
                    upper_smooth[i - 1] * 0.20
                    + upper_smooth[i] * 0.60
                    + upper_smooth[i + 1] * 0.20
                )
            upper_smooth = pass_result

        # Smooth sky floor as well, so boundary compression won't create single-point needles.
        sky_floor_smooth = sky_floors[:]
        for _ in range(2):
            floor_pass = sky_floor_smooth[:]
            for i in range(1, len(sky_floor_smooth) - 1):
                floor_pass[i] = (
                    sky_floor_smooth[i - 1] * 0.20
                    + sky_floor_smooth[i] * 0.60
                    + sky_floor_smooth[i + 1] * 0.20
                )
            sky_floor_smooth = floor_pass

        # Lower-edge spikes mainly come from abrupt thickness changes.
        # Smooth thickness independently so lower boundary becomes curtain-like.
        thick_smooth = thick_values[:]
        for _ in range(2):
            thick_pass = thick_smooth[:]
            for i in range(1, len(thick_smooth) - 1):
                thick_pass[i] = (
                    thick_smooth[i - 1] * 0.22
                    + thick_smooth[i] * 0.56
                    + thick_smooth[i + 1] * 0.22
                )
            thick_smooth = thick_pass

        soft_span = max(8.0, h * 0.085)
        constrained_upper: list[float] = []
        for upper, sky_floor in zip(upper_smooth, sky_floor_smooth):
            if upper > sky_floor:
                exceed = upper - sky_floor
                # Continuous soft compression: smooth boundary without sharp break.
                factor = 0.22 + 0.10 * math.exp(-exceed / soft_span)
                upper = sky_floor + exceed * factor
            if upper < top_min:
                upper = top_min
            constrained_upper.append(upper)

        # Widen local sharp peaks: spikes can exist, but should appear as a cluster.
        widened_upper = constrained_upper[:]
        sharp_threshold = max(1.8, h * 0.010)
        for i in range(2, len(constrained_upper) - 2):
            cur = constrained_upper[i]
            second_diff = abs(constrained_upper[i - 1] - 2.0 * cur + constrained_upper[i + 1])
            if second_diff < sharp_threshold:
                continue
            band = (
                constrained_upper[i - 2] * 0.10
                + constrained_upper[i - 1] * 0.25
                + constrained_upper[i] * 0.30
                + constrained_upper[i + 1] * 0.25
                + constrained_upper[i + 2] * 0.10
            )
            widened_upper[i - 1] = widened_upper[i - 1] * 0.70 + band * 0.30
            widened_upper[i] = widened_upper[i] * 0.55 + band * 0.45
            widened_upper[i + 1] = widened_upper[i + 1] * 0.70 + band * 0.30

        upper_points: list[tuple[float, float]] = []
        lower_points: list[tuple[float, float]] = []
        for x, upper, thick in zip(x_points, widened_upper, thick_smooth):
            lower = upper + thick
            upper_points.append((x, upper))
            lower_points.append((x, lower))

        alpha_breath = 0.42 + 0.58 * (0.5 + 0.5 * math.sin((t * 0.010) + aurora["shift"] * 1.2))
        alpha_core = int(aurora["alpha"] * alpha_breath)
        # Single continuous aurora strip.
        path = QPainterPath()
        path.moveTo(upper_points[0][0], upper_points[0][1])
        for x, y in upper_points[1:]:
            path.lineTo(x, y)
        for x, y in reversed(lower_points):
            path.lineTo(x, y)
        path.closeSubpath()

        y_min = min(min(y for _, y in upper_points), min(y for _, y in lower_points))
        y_max = max(max(y for _, y in upper_points), max(y for _, y in lower_points))
        # Aurora hue by wavelength feeling: top pink, bottom green.
        grad = QLinearGradient(0.0, y_min, 0.0, y_max)
        grad.setColorAt(0.00, QColor(255, 168, 230, 0))  # 顶部透明粉色
        grad.setColorAt(0.18, QColor(255, 156, 224, int(alpha_core * 0.48)))  # 上部粉色
        grad.setColorAt(0.30, QColor(212, 178, 198, int(alpha_core * 0.76)))  # 过渡到绿色的粉色
        grad.setColorAt(0.56, QColor(173, 255, 204, int(alpha_core * 0.92)))  # 中部清新绿，贴近极光
        grad.setColorAt(0.75, QColor(56, 229, 224, int(alpha_core * 0.57)))   # 绿色-青色（真实极光主色）
        grad.setColorAt(1.00, QColor(29, 190, 216, 0))   # 底部透明蓝青，真实极光底部淡出
        painter.fillPath(path, grad)

        halo_pen = QPen(QColor(255, 180, 232, int(alpha_core * 0.22)))
        halo_pen.setWidthF(1.3)
        halo_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        halo_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(halo_pen)
        edge = QPainterPath()
        edge.moveTo(upper_points[0][0], upper_points[0][1])
        for x, y in upper_points[1:]:
            edge.lineTo(x, y)
        painter.drawPath(edge)
        painter.setPen(Qt.PenStyle.NoPen)

        # White star glints across full window.
        for star in self._stars:
            twinkle = 0.52 + 0.48 * (0.5 + 0.5 * math.sin((t * 0.055 * star["twinkle"]) + star["phase"]))
            alpha = int(star["alpha"] * twinkle)
            if alpha < 10:
                continue
            x = star["x"]
            y = star["y"]
            r = star["r"]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(247, 252, 255, alpha))
            painter.drawEllipse(QPoint(int(x), int(y)), max(1, int(r)), max(1, int(r)))
            if twinkle > 0.83:
                pen = QPen(QColor(255, 255, 255, int(alpha * 0.55)))
                pen.setWidthF(0.8)
                painter.setPen(pen)
                painter.drawLine(QPoint(int(x - r * 1.8), int(y)), QPoint(int(x + r * 1.8), int(y)))
                painter.drawLine(QPoint(int(x), int(y - r * 1.8)), QPoint(int(x), int(y + r * 1.8)))


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

        self.setStyleSheet(
            """
            QDialog {
                background: #fff7fb;
                color: #2a1f2a;
            }
            QTabWidget::pane {
                border: 1px solid #ffd3e6;
                border-radius: 10px;
                background: #ffffff;
            }
            QTabBar::tab {
                background: #fff0f7;
                border: 1px solid #ffbfdc;
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 5px 10px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #ffdced;
            }
            QTextEdit {
                border: none;
                background: #fffdfd;
                color: #2a1f2a;
                font-size: %dpx;
            }
            QPushButton {
                background: #fff0f7;
                border: 1px solid #ffb7d6;
                border-radius: 9px;
                color: #8d365d;
                padding: 6px 10px;
            }
            """
            % px(14, scale)
        )

    def _clear_all_content(self) -> None:
        self._text.clear()
        self._draw.clear_canvas()


class MiniCallBar(QDialog):
    expandRequested = Signal()
    chatRequested = Signal()
    pauseRequested = Signal()
    hangupRequested = Signal()

    def __init__(self, parent=None, theme_tokens: dict[str, str] | None = None) -> None:
        super().__init__(parent)
        self._theme_tokens = dict(theme_tokens or self._default_theme_tokens())
        self._drag_offset: QPoint | None = None
        self.setWindowTitle("通话悬浮条")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        if sys.platform == "darwin":
            # Keep tool windows visible across Spaces/fullscreen scenes on macOS.
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

        self.setStyleSheet(self._build_stylesheet(scale))

    @staticmethod
    def _default_theme_tokens() -> dict[str, str]:
        return {
            "mini_panel_a": "rgba(18, 30, 52, 0.92)",
            "mini_panel_b": "rgba(34, 53, 82, 0.92)",
            "mini_panel_border": "rgba(176, 207, 246, 0.58)",
            "mini_text": "#D7E9FF",
            "mini_focus": "#89E4C0",
            "mini_break": "#F9D188",
            "mini_pause": "#C0D5EE",
            "mini_config": "#B8CCE5",
            "mini_hangup": "#FFB8CF",
            "mini_timer": "#F0C9FF",
            "mini_btn_a": "rgba(240, 232, 255, 0.62)",
            "mini_btn_b": "rgba(220, 236, 255, 0.56)",
            "mini_btn_border": "rgba(175, 205, 240, 0.60)",
            "mini_btn_text": "#1B2A42",
            "mini_btn_hover": "rgba(212, 228, 248, 0.88)",
            "mini_btn_pressed": "rgba(183, 205, 233, 0.92)",
            "mini_danger_a": "rgba(255, 223, 236, 0.74)",
            "mini_danger_b": "rgba(244, 206, 227, 0.68)",
            "mini_danger_border": "rgba(226, 167, 200, 0.86)",
            "mini_danger_text": "#3A2540",
            "mini_danger_hover_a": "rgba(255, 232, 242, 0.84)",
            "mini_danger_hover_b": "rgba(248, 214, 232, 0.80)",
            "mini_danger_pressed_a": "rgba(247, 211, 230, 0.86)",
            "mini_danger_pressed_b": "rgba(239, 197, 220, 0.82)",
            "font_family": '"SF Pro Rounded", "PingFang SC", "Helvetica Neue", sans-serif',
        }

    def _build_stylesheet(self, scale: float) -> str:
        t = self._theme_tokens
        return f"""
            QFrame#miniPanel {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["mini_panel_a"]}, stop:1 {t["mini_panel_b"]});
                border: none;
                border-radius: 20px;
            }}
            QLabel#miniStatus, QLabel#miniTimer, QPushButton {{
                font-family: {t["font_family"]};
            }}
            QLabel#miniStatus {{
                color: {t["mini_text"]};
                font-size: {px(12, scale)}px;
                font-weight: 700;
            }}
            QLabel#miniStatus[miniState="focus"] {{ color: {t["mini_focus"]}; }}
            QLabel#miniStatus[miniState="break"] {{ color: {t["mini_break"]}; }}
            QLabel#miniStatus[miniState="pause"] {{ color: {t["mini_pause"]}; }}
            QLabel#miniStatus[miniState="config"] {{ color: {t["mini_config"]}; }}
            QLabel#miniStatus[miniState="hangup"] {{ color: {t["mini_hangup"]}; }}
            QLabel#miniTimer {{
                color: {t["mini_timer"]};
                font-size: {px(16, scale)}px;
                font-weight: 800;
            }}
            QPushButton#miniBtn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["mini_btn_a"]}, stop:1 {t["mini_btn_b"]});
                border: 1px solid {t["mini_btn_border"]};
                border-radius: 12px;
                color: {t["mini_btn_text"]};
                min-width: 44px;
                min-height: 28px;
                padding: 2px 8px;
            }}
            QPushButton#miniBtn:hover {{ border-color: {t["mini_btn_hover"]}; }}
            QPushButton#miniBtn:pressed {{ background: {t["mini_btn_pressed"]}; }}
            QPushButton#miniDanger {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["mini_danger_a"]}, stop:1 {t["mini_danger_b"]});
                border: 1px solid {t["mini_danger_border"]};
                border-radius: 12px;
                color: {t["mini_danger_text"]};
                min-width: 44px;
                min-height: 28px;
                padding: 2px 8px;
                font-weight: 700;
            }}
            QPushButton#miniDanger:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["mini_danger_hover_a"]}, stop:1 {t["mini_danger_hover_b"]});
            }}
            QPushButton#miniDanger:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["mini_danger_pressed_a"]}, stop:1 {t["mini_danger_pressed_b"]});
            }}
        """

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

class WithYouWindow(QDialog):
    callStarted = Signal()
    callEnded = Signal()
    chatRequested = Signal()

    def __init__(
        self,
        resources_dir: Path,
        config_dir: Path | None = None,
        shared_tray: QSystemTrayIcon | None = None,
        shared_tray_default_menu: QMenu | None = None,
        shared_tray_default_tooltip: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        init_fluent_theme()
        self._resources_dir = resources_dir
        self._config_dir = config_dir
        self._settings_json_path = (config_dir / "settings.json") if config_dir is not None else None
        self._shared_tray = shared_tray
        self._shared_tray_default_menu = shared_tray_default_menu
        self._shared_tray_default_tooltip = shared_tray_default_tooltip or "飞行雪绒：主控菜单"
        self._status_tray_active = False
        self._call_dir = resources_dir / "Call"
        self._note_window: StickyNoteWindow | None = None
        self._phase = "idle"  # idle / answering / config / running / hangup
        self._loop_video = False
        self._active_video_widget: QWidget | None = None
        self._active_video_label: QLabel | None = None
        self._last_frame: QPixmap | None = None
        self._total_rounds = 1
        self._current_round = 1
        self._round_seconds = 25 * 60
        self._remaining_seconds = self._round_seconds
        self._withyou_width = 1440
        self._withyou_height = 1790
        self._mini_bar: MiniCallBar | None = None
        self._status_tray: QSystemTrayIcon | None = None
        self._status_tray_menu: QMenu | None = None
        self._status_tray_stage_action: QAction | None = None
        self._call_active = False
        self._is_break_phase = False
        self._is_paused = False
        self._break_seconds = 5 * 60
        self._resume_state: dict[str, int | bool] | None = None
        self._break_intro_playing = False
        self._start_intro_playing = False
        self._end_outro_playing = False
        self._cinematic_fill_mode = False
        self._current_media_source = ""
        self._last_frame_render_ts = 0.0
        self._frame_interval_s = 1.0 / 20.0
        self._fallback_frame_interval_normal_s = 1.0 / 20.0
        self._fallback_frame_interval_bgm_priority_s = 1.0 / 8.0
        self._bgm_ducking_ratio = 0.35
        self._background_audio_paused_for_voice = False
        self._resume_ambient_after_voice = False
        self._resume_bgm_after_voice = False

        self._answer_path = self._pick_media(("answering.mov", "answering.mp4", "answering.MOV", "answering.MP4"))
        self._hangup_path = self._pick_media(("hangup.mov", "hangup.mp4", "hangup.MOV", "hangup.MP4"))
        self._break_paths = self._pick_media_candidates(
            (
                "break1.mov",
                "break1.mp4",
                "break1.MOV",
                "break1.MP4",
                "break2.mov",
                "break2.mp4",
                "break2.MOV",
                "break2.MP4",
                "break3.mov",
                "break3.mp4",
                "break3.MOV",
                "break3.MP4",
            )
        )
        self._start1_path = self._pick_media(("start1.mov", "start1.mp4", "start1.MOV", "start1.MP4"))
        self._start2_path = self._pick_media(("start2.mov", "start2.mp4", "start2.MOV", "start2.MP4"))
        self._end_paths = self._pick_media_candidates(
            (
                "end.mov",
                "end.mp4",
                "end.MOV",
                "end.MP4",
                "end2.mov",
                "end2.mp4",
                "end2.MOV",
                "end2.MP4",
            )
        )
        self._start_sfx_path = self._pick_media(("start.mp3", "start.MP3", "start.wav", "start.WAV"))
        self._withyou_path = self._pick_media(
            ("withyou.mov", "withyou.mp4", "with_you.mov", "with_you.mp4", "withyou.MOV", "withyou.MP4")
        )
        self._noise_dir = self._call_dir / "noise"
        self._bgm_dir = self._call_dir / "bgm"
        self._noise_path: Path | None = self._first_audio_in_dir(self._noise_dir)
        self._with_you_settings = QSettings("FleetSnowfluff", "WithYou")
        self._config_opacity = self._load_config_opacity()
        self._last_focus_date, self._companion_days, self._companion_streak_days = self._load_companion_stats()
        self._bgm_playlist: list[str] = []
        self._bgm_index = 0
        self._bgm_seek_block = False
        self._bgm_resume_position_ms = 0
        self._bgm_pending_seek_ms = 0
        self._bgm_switching_source = False

        self.setWindowTitle("通话中")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.Tool)
        self.setObjectName("withYouWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.resize(375, 812)  # 5.8-inch class
        self.setFixedSize(375, 812)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._stack = QStackedWidget(self)
        root.addWidget(self._stack, 1)

        # Cinematic page: answering/hangup only (full window, no controls)
        self._cinematic_page = QFrame(self)
        cine_layout = QVBoxLayout(self._cinematic_page)
        cine_layout.setContentsMargins(0, 0, 0, 0)
        if HAS_QVIDEO_WIDGET and _QVideoWidget is not None:
            self._cinematic_video = _QVideoWidget(self._cinematic_page)
            self._cinematic_video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        else:
            self._cinematic_video = QLabel(self._cinematic_page)
            self._cinematic_video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cinematic_video.setStyleSheet("background:#000000;")
        cine_layout.addWidget(self._cinematic_video, 1)
        self._stack.addWidget(self._cinematic_page)

        # Interactive page: top/middle/bottom three bands
        self._interactive_page = QFrame(self)
        self._interactive_page.setObjectName("interactivePage")
        interactive_root = QVBoxLayout(self._interactive_page)
        interactive_root.setContentsMargins(0, 0, 0, 0)
        interactive_root.setSpacing(0)
        self._ribbon_overlay = Aurora(self)
        self._ribbon_overlay.setGeometry(self.rect())
        self._ribbon_overlay.hide()

        # Top: 上栏按内容自适应，保证轮次计数器不被挤压
        self._top_bar = QFrame(self._interactive_page)
        self._top_bar.setObjectName("topBar")
        self._top_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        top_box = QVBoxLayout(self._top_bar)
        top_box.setContentsMargins(8, 6, 8, 6)
        top_box.setSpacing(4)
        self._last_focus_label = QLabel("")
        self._last_focus_label.setObjectName("companionInfoTopLabel")
        self._companion_days_label = QLabel("")
        self._companion_days_label.setObjectName("companionInfoTopLabel")
        top_box.addWidget(self._last_focus_label)
        top_box.addWidget(self._companion_days_label)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)
        self.status_label = QLabel("番茄钟设置")
        self.status_label.setObjectName("statusLabel")
        self.round_label = QLabel("第 0/0 轮")
        self.round_label.setObjectName("roundLabel")
        self.settings_btn = QPushButton("设置")
        self.settings_btn.setObjectName("ghostBtn")
        self.settings_btn.setToolTip("返回番茄钟设置")
        self.settings_btn.clicked.connect(self._back_to_settings)
        self.chat_btn = QPushButton("聊天窗口")
        self.chat_btn.setObjectName("chocoBtn")
        self.chat_btn.setToolTip("呼出飞讯聊天窗口")
        self.chat_btn.clicked.connect(self._request_chat_window)
        self.mini_btn = QPushButton("悬浮条")
        self.mini_btn.setObjectName("ghostBtn")
        self.mini_btn.setToolTip("收缩为悬浮条")
        self.mini_btn.clicked.connect(self._enter_mini_mode)
        self.exit_btn = QPushButton("退出")
        self.exit_btn.setObjectName("dangerBtn")
        self.exit_btn.setToolTip("结束当前通话")
        self.exit_btn.clicked.connect(self._start_hangup)
        top_row.addWidget(self.status_label)
        top_row.addStretch(1)
        top_btn_row = QHBoxLayout()
        top_btn_row.setContentsMargins(0, 0, 0, 0)
        top_btn_row.setSpacing(6)
        ui_scale = self._ui_scale()
        self.mini_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.settings_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.exit_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        top_btn_h = px(40, ui_scale)
        top_btn_w = px(44, ui_scale)
        self.mini_btn.setMinimumHeight(top_btn_h)
        self.settings_btn.setMinimumHeight(top_btn_h)
        self.exit_btn.setMinimumHeight(top_btn_h)
        self.mini_btn.setFixedWidth(top_btn_w)
        self.settings_btn.setFixedWidth(top_btn_w)
        self.exit_btn.setFixedWidth(top_btn_w)
        top_btn_row.addWidget(self.mini_btn, 1)
        top_btn_row.addWidget(self.settings_btn, 1)
        top_btn_row.addWidget(self.exit_btn, 1)
        top_row.addLayout(top_btn_row)
        round_row = QHBoxLayout()
        round_row.setContentsMargins(0, 0, 0, 0)
        round_row.addStretch(1)
        round_row.addWidget(self.round_label)
        round_row.addStretch(1)
        top_box.addLayout(top_row)
        top_box.addLayout(round_row)

        # Middle: 中间播片/设置，占据剩余空间，高度由 _sync_middle_height 保证不重叠
        # Middle: settings panel OR withyou video panel
        self._middle_stack = QStackedWidget(self._interactive_page)

        self._settings_panel = QFrame(self._interactive_page)
        self._settings_panel.setObjectName("settingsContentPanel")
        settings_layout = QVBoxLayout(self._settings_panel)
        settings_layout.setContentsMargins(14, 14, 14, 14)
        settings_layout.setSpacing(10)
        settings_rows = QVBoxLayout()
        settings_rows.setContentsMargins(0, 0, 0, 0)
        settings_rows.setSpacing(10)

        rounds_card = QFrame(self._settings_panel)
        rounds_card.setObjectName("settingCard")
        rounds_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        rounds_card_layout = QVBoxLayout(rounds_card)
        rounds_card_layout.setContentsMargins(10, 8, 10, 8)
        rounds_card_layout.setSpacing(6)
        rounds_row = QHBoxLayout()
        rounds_row.setContentsMargins(0, 0, 0, 0)
        rounds_row.setSpacing(6)
        rounds_label = QLabel("轮次")
        rounds_label.setObjectName("settingFieldLabel")
        rounds_label.setObjectName("roundsFieldLabel")
        rounds_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.rounds_spin = QSpinBox(self._settings_panel)
        self.rounds_spin.setRange(1, 20)
        self.rounds_spin.setValue(4)
        self.rounds_spin.setObjectName("roundsFieldSpin")
        rounds_row.addWidget(rounds_label)
        rounds_row.addWidget(self.rounds_spin, 1)
        rounds_card_layout.addLayout(rounds_row)

        focus_card = QFrame(self._settings_panel)
        focus_card.setObjectName("settingCard")
        focus_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        focus_card_layout = QVBoxLayout(focus_card)
        focus_card_layout.setContentsMargins(10, 8, 10, 8)
        focus_card_layout.setSpacing(6)
        focus_label = QLabel("专注时长")
        focus_label.setObjectName("settingFieldLabel")
        focus_label.setObjectName("timeFieldLabel")
        focus_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        focus_time_row = QHBoxLayout()
        focus_time_row.setContentsMargins(0, 0, 0, 0)
        focus_time_row.setSpacing(6)
        self.focus_min_spin = QSpinBox(self._settings_panel)
        self.focus_min_spin.setRange(0, 120)
        self.focus_min_spin.setValue(25)
        self.focus_min_spin.setObjectName("timeFieldSpin")
        self.focus_sec_spin = QSpinBox(self._settings_panel)
        self.focus_sec_spin.setRange(0, 59)
        self.focus_sec_spin.setValue(0)
        self.focus_sec_spin.setObjectName("timeFieldSpin")
        focus_min_label = QLabel("分")
        focus_min_label.setObjectName("unitLabel")
        focus_sec_label = QLabel("秒")
        focus_sec_label.setObjectName("unitLabel")
        focus_time_row.addWidget(self.focus_min_spin, 1)
        focus_time_row.addWidget(focus_min_label)
        focus_time_row.addWidget(self.focus_sec_spin, 1)
        focus_time_row.addWidget(focus_sec_label)
        focus_card_layout.addWidget(focus_label)
        focus_card_layout.addLayout(focus_time_row)

        break_card = QFrame(self._settings_panel)
        break_card.setObjectName("settingCard")
        break_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        break_card_layout = QVBoxLayout(break_card)
        break_card_layout.setContentsMargins(10, 8, 10, 8)
        break_card_layout.setSpacing(6)
        break_label = QLabel("休息时长")
        break_label.setObjectName("settingFieldLabel")
        break_label.setObjectName("timeFieldLabel")
        break_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        break_time_row = QHBoxLayout()
        break_time_row.setContentsMargins(0, 0, 0, 0)
        break_time_row.setSpacing(6)
        self.break_min_spin = QSpinBox(self._settings_panel)
        self.break_min_spin.setRange(0, 60)
        self.break_min_spin.setValue(5)
        self.break_min_spin.setObjectName("timeFieldSpin")
        self.break_sec_spin = QSpinBox(self._settings_panel)
        self.break_sec_spin.setRange(0, 59)
        self.break_sec_spin.setValue(0)
        self.break_sec_spin.setObjectName("timeFieldSpin")
        break_min_label = QLabel("分")
        break_min_label.setObjectName("unitLabel")
        break_sec_label = QLabel("秒")
        break_sec_label.setObjectName("unitLabel")
        break_time_row.addWidget(self.break_min_spin, 1)
        break_time_row.addWidget(break_min_label)
        break_time_row.addWidget(self.break_sec_spin, 1)
        break_time_row.addWidget(break_sec_label)
        break_card_layout.addWidget(break_label)
        break_card_layout.addLayout(break_time_row)
        settings_rows.addWidget(rounds_card, 1)
        settings_rows.addWidget(focus_card, 1)
        settings_rows.addWidget(break_card, 1)
        opacity_card = QFrame(self._settings_panel)
        opacity_card.setObjectName("settingCard")
        opacity_card_layout = QVBoxLayout(opacity_card)
        opacity_card_layout.setContentsMargins(10, 8, 10, 8)
        opacity_card_layout.setSpacing(6)
        opacity_label = QLabel("设置窗口透明度")
        opacity_label.setObjectName("settingFieldLabel")
        opacity_row = QHBoxLayout()
        opacity_row.setContentsMargins(0, 0, 0, 0)
        opacity_row.setSpacing(6)
        self._config_opacity_slider = QSlider(Qt.Orientation.Horizontal, self._settings_panel)
        self._config_opacity_slider.setRange(80, 100)
        self._config_opacity_slider.setValue(self._config_opacity)
        self._config_opacity_slider.valueChanged.connect(self._on_config_opacity_changed)
        self._config_opacity_value_label = QLabel(f"{self._config_opacity}%")
        self._config_opacity_value_label.setObjectName("settingFieldLabel")
        self._config_opacity_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        opacity_row.addWidget(self._config_opacity_slider, 1)
        opacity_row.addWidget(self._config_opacity_value_label)
        opacity_card_layout.addWidget(opacity_label)
        opacity_card_layout.addLayout(opacity_row)
        settings_rows.addWidget(opacity_card, 1)
        self._refresh_companion_labels()

        self.start_btn = QPushButton("开始专注")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.setToolTip("开始番茄钟计时")
        self.start_btn.clicked.connect(self._start_focus)
        self.return_btn = QPushButton("返回")
        self.return_btn.setObjectName("ghostBtn")
        self.return_btn.setToolTip("返回当前计时进度（不应用本次修改）")
        self.return_btn.clicked.connect(self._return_to_running_without_changes)
        self.return_btn.setVisible(False)
        settings_layout.addLayout(settings_rows, 1)
        settings_actions = QHBoxLayout()
        settings_actions.setContentsMargins(0, 0, 0, 0)
        settings_actions.setSpacing(10)
        self.return_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.start_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        action_btn_h = px(42, ui_scale)
        self.return_btn.setMinimumHeight(action_btn_h)
        self.start_btn.setMinimumHeight(action_btn_h)
        settings_actions.addWidget(self.return_btn, 1)
        settings_actions.addWidget(self.start_btn, 1)
        settings_layout.addLayout(settings_actions)

        self._settings_scroll = QScrollArea(self._interactive_page)
        self._settings_scroll.setObjectName("settingsScroll")
        self._settings_scroll.setWidgetResizable(True)
        self._settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._settings_scroll.setWidget(self._settings_panel)

        self._withyou_panel = QFrame(self._interactive_page)
        self._withyou_panel.setObjectName("withyouPanel")
        withyou_layout = QVBoxLayout(self._withyou_panel)
        withyou_layout.setContentsMargins(0, 0, 0, 0)
        if HAS_QVIDEO_WIDGET and _QVideoWidget is not None:
            self._withyou_video = _QVideoWidget(self._withyou_panel)
            self._withyou_video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatioByExpanding)
        else:
            self._withyou_video = QLabel(self._withyou_panel)
            self._withyou_video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._withyou_video.setStyleSheet("background: transparent; border-radius: 18px;")
        withyou_layout.addWidget(self._withyou_video, 1)

        self._middle_stack.addWidget(self._settings_scroll)
        self._middle_stack.addWidget(self._withyou_panel)

        # Bottom: 噪声 | 计时器 | BGM，下方为操作按钮；下栏按内容自适应
        bottom_bar = QFrame(self._interactive_page)
        bottom_bar.setObjectName("bottomBar")
        bottom_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        bottom_box = QVBoxLayout(bottom_bar)
        bottom_box.setContentsMargins(12, 8, 12, 8)
        bottom_box.setSpacing(8)
        self.countdown_label = QLabel("00:00")
        self.countdown_label.setObjectName("countdownLabel")
        self._noise_btn = QPushButton("噪声", bottom_bar)
        self._noise_btn.setObjectName("ghostBtn")
        self._noise_btn.setToolTip("背景噪声开关与音量")
        self._noise_btn.clicked.connect(self._open_noise_popup)
        self._bgm_btn = QPushButton("BGM", bottom_bar)
        self._bgm_btn.setObjectName("ghostBtn")
        self._bgm_btn.setToolTip("背景音乐开关与音量")
        self._bgm_btn.clicked.connect(self._open_bgm_popup)
        self.note_btn = QPushButton("便利贴")
        self.note_btn.setObjectName("chocoBtn")
        self.note_btn.setToolTip("打开便利贴")
        self.note_btn.clicked.connect(self._open_note_window)
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setObjectName("chocoBtn")
        self.pause_btn.setToolTip("暂停或继续计时")
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.skip_btn = QPushButton("跳过")
        self.skip_btn.setObjectName("chocoBtn")
        self.skip_btn.setToolTip("跳过当前环节")
        self.skip_btn.clicked.connect(self._skip_current_stage)
        timer_wrap = QWidget(bottom_bar)
        timer_row = QHBoxLayout(timer_wrap)
        timer_row.setContentsMargins(0, 0, 0, 0)
        timer_row.setSpacing(8)
        timer_row.addWidget(self._noise_btn)
        timer_row.addStretch(1)
        timer_row.addWidget(self.countdown_label)
        timer_row.addStretch(1)
        timer_row.addWidget(self._bgm_btn)

        buttons_grid = QGridLayout()
        buttons_grid.setContentsMargins(2, 2, 2, 2)
        buttons_grid.setHorizontalSpacing(8)
        buttons_grid.setVerticalSpacing(8)
        self.chat_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.pause_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.skip_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.note_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        choco_h = px(44, ui_scale)
        self.chat_btn.setMinimumHeight(choco_h)
        self.pause_btn.setMinimumHeight(choco_h)
        self.skip_btn.setMinimumHeight(choco_h)
        self.note_btn.setMinimumHeight(choco_h)
        buttons_grid.addWidget(self.chat_btn, 0, 0)
        buttons_grid.addWidget(self.pause_btn, 0, 1)
        buttons_grid.addWidget(self.skip_btn, 1, 0)
        buttons_grid.addWidget(self.note_btn, 1, 1)
        buttons_grid.setColumnStretch(0, 1)
        buttons_grid.setColumnStretch(1, 1)
        bottom_box.addWidget(timer_wrap)
        bottom_box.addLayout(buttons_grid)

        self._bottom_bar = bottom_bar
        interactive_root.addWidget(self._top_bar)
        interactive_root.addWidget(self._middle_stack, 1)
        interactive_root.addWidget(self._bottom_bar)
        self._stack.addWidget(self._interactive_page)
        self._sync_middle_height()

        self._audio = QAudioOutput(self)
        self._audio.setVolume(1.0)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio)
        self._sfx_audio = QAudioOutput(self)
        self._sfx_audio.setVolume(1.0)
        self._sfx_player = QMediaPlayer(self)
        self._sfx_player.setAudioOutput(self._sfx_audio)
        self._ambient_audio = QAudioOutput(self)
        _default_out = QMediaDevices.defaultAudioOutput()
        if not _default_out.isNull():
            self._ambient_audio.setDevice(_default_out)
        self._ambient_player = QMediaPlayer(self)
        self._ambient_player.setAudioOutput(self._ambient_audio)
        self._ambient_player.mediaStatusChanged.connect(self._on_ambient_status_changed)
        self._bgm_audio = QAudioOutput(self)
        if not _default_out.isNull():
            self._bgm_audio.setDevice(_default_out)
        self._bgm_player = QMediaPlayer(self)
        self._bgm_player.setAudioOutput(self._bgm_audio)
        self._bgm_player.positionChanged.connect(self._on_bgm_position_changed)
        self._bgm_player.durationChanged.connect(self._on_bgm_duration_changed)
        self._bgm_player.mediaStatusChanged.connect(self._on_bgm_media_status_changed)
        self._sink: QVideoSink | None = None
        if HAS_QVIDEO_WIDGET:
            self._player.setVideoOutput(self._withyou_video)
            self._active_video_widget = self._withyou_video
        else:
            sink = QVideoSink(self)
            sink.videoFrameChanged.connect(self._on_video_frame_changed)
            self._sink = sink
            self._player.setVideoOutput(sink)
            self._active_video_label = cast(QLabel, self._withyou_video)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._player.errorOccurred.connect(self._on_media_error)
        self._player.playbackStateChanged.connect(self._on_video_playback_state_changed)
        self._refresh_video_priority_for_bgm()

        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._on_tick)
        self._apply_icon_buttons()
        app = QApplication.instance()
        scale = current_app_scale(app) if app is not None else 1.0
        self._apply_soft_shadow(rounds_card, px(22, scale), px(2, scale), alpha=30)
        self._apply_soft_shadow(focus_card, px(22, scale), px(2, scale), alpha=30)
        self._apply_soft_shadow(break_card, px(22, scale), px(2, scale), alpha=30)

        self.setStyleSheet(self._build_focus_stylesheet(scale))
        self._build_noise_popup()
        self._build_bgm_popup()
        self._set_view_mode("config")
        self._load_ambient_state()
        self._load_bgm_state()

    def _ui_scale(self) -> float:
        app = QApplication.instance()
        return current_app_scale(app) if app is not None else 1.0

    def _load_ambient_state(self) -> None:
        enabled = self._with_you_settings.value("ambient/enabled", True)
        if isinstance(enabled, bool):
            self._ambient_enabled_cb.setChecked(enabled)
        else:
            self._ambient_enabled_cb.setChecked(enabled not in (0, "0", "false", "no"))
        vol = self._with_you_settings.value("ambient/volume", 50)
        v = 50
        try:
            if vol is not None:
                v = int(cast(Union[int, str], vol))
        except (TypeError, ValueError):
            pass
        self._ambient_volume_slider.setValue(max(0, min(100, v)))
        self._on_ambient_volume_changed(self._ambient_volume_slider.value())

    def _save_ambient_state(self) -> None:
        self._with_you_settings.setValue("ambient/enabled", self._ambient_enabled_cb.isChecked())
        self._with_you_settings.setValue("ambient/volume", self._ambient_volume_slider.value())

    def _load_bgm_state(self) -> None:
        self._refresh_bgm_playlist()
        enabled_bgm = self._with_you_settings.value("bgm/enabled", True)
        if isinstance(enabled_bgm, bool):
            self._bgm_enabled_cb.setChecked(enabled_bgm)
        else:
            self._bgm_enabled_cb.setChecked(enabled_bgm not in (0, "0", "false", "no"))
        vol_bgm = self._with_you_settings.value("bgm/volume", 60)
        v_bgm = 60
        try:
            if vol_bgm is not None:
                v_bgm = int(cast(Union[int, str], vol_bgm))
        except (TypeError, ValueError):
            pass
        self._bgm_volume_slider.setValue(max(0, min(100, v_bgm)))
        self._on_bgm_volume_changed(self._bgm_volume_slider.value())
        loop = self._with_you_settings.value("bgm/loop", True)
        self._bgm_loop_cb.setChecked(loop if isinstance(loop, bool) else str(loop).lower() not in ("0", "false", "no"))
        idx_raw = self._with_you_settings.value("bgm/index", 0)
        idx_int = 0
        try:
            if idx_raw is not None:
                idx_int = int(cast(Union[int, str], idx_raw))
        except (TypeError, ValueError):
            pass
        self._bgm_index = max(0, min(len(self._bgm_playlist) - 1, idx_int))
        pos_raw = self._with_you_settings.value("bgm/position_ms", 0)
        pos_int = 0
        try:
            if pos_raw is not None:
                pos_int = int(cast(Union[int, str], pos_raw))
        except (TypeError, ValueError):
            pos_int = 0
        self._bgm_resume_position_ms = max(0, pos_int)
        if self._bgm_playlist:
            self._bgm_list.blockSignals(True)
            self._bgm_list.setCurrentRow(self._bgm_index)
            self._bgm_list.blockSignals(False)

    def _save_bgm_state(self) -> None:
        self._with_you_settings.setValue("bgm/enabled", self._bgm_enabled_cb.isChecked())
        self._with_you_settings.setValue("bgm/volume", self._bgm_volume_slider.value())
        self._with_you_settings.setValue("bgm/loop", self._bgm_loop_cb.isChecked())
        self._with_you_settings.setValue("bgm/index", self._bgm_index)
        current_pos = self._bgm_player.position()
        self._with_you_settings.setValue("bgm/position_ms", max(0, current_pos if current_pos > 0 else self._bgm_resume_position_ms))

    def _load_config_opacity(self) -> int:
        raw = self._with_you_settings.value("window/config_opacity", 100)
        value = 100
        try:
            if raw is not None:
                value = int(cast(Union[int, str], raw))
        except (TypeError, ValueError):
            value = 100
        return max(80, min(100, value))

    def _on_config_opacity_changed(self, value: int) -> None:
        self._config_opacity = max(80, min(100, int(value)))
        self._config_opacity_value_label.setText(f"{self._config_opacity}%")
        self._with_you_settings.setValue("window/config_opacity", self._config_opacity)
        if self.property("viewMode") == "config":
            self.setWindowOpacity(self._config_opacity / 100.0)

    def _load_companion_stats(self) -> tuple[str, int, int]:
        if self._settings_json_path is None or not self._settings_json_path.exists():
            return "", 0, 0
        try:
            raw = self._settings_json_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                return "", 0, 0
            last_focus_date = str(data.get("with_you_last_focus_date", "") or "").strip()
            companion_days_raw = data.get("with_you_companion_days", 0)
            companion_days = int(companion_days_raw) if companion_days_raw is not None else 0
            companion_streak_raw = data.get("with_you_companion_streak_days", companion_days)
            companion_streak_days = int(companion_streak_raw) if companion_streak_raw is not None else companion_days
            if companion_days < 0:
                companion_days = 0
            if companion_streak_days < 0:
                companion_streak_days = 0
            return last_focus_date, companion_days, companion_streak_days
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return "", 0, 0

    def _save_companion_stats(self) -> None:
        if self._settings_json_path is None:
            return
        data: dict[str, object] = {}
        try:
            if self._settings_json_path.exists():
                raw = self._settings_json_path.read_text(encoding="utf-8")
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    data = dict(parsed)
        except (OSError, json.JSONDecodeError):
            data = {}
        data["with_you_last_focus_date"] = self._last_focus_date
        data["with_you_companion_days"] = int(max(0, self._companion_days))
        data["with_you_companion_streak_days"] = int(max(0, self._companion_streak_days))
        try:
            self._settings_json_path.parent.mkdir(parents=True, exist_ok=True)
            self._settings_json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            return

    def _refresh_companion_labels(self) -> None:
        if not hasattr(self, "_last_focus_label"):
            return
        date_text = self._last_focus_date if self._last_focus_date else "--"
        self._last_focus_label.setText(f"上次小爱陪你专注：{date_text}")
        streak = max(0, self._companion_streak_days)
        streak_emoji = "🔥" if streak > 7 else "🌱"
        self._companion_days_label.setText(
            f"小爱同学已陪伴你 {max(0, self._companion_days)} 天（连续 {streak} 天 {streak_emoji}）"
        )

    def _record_focus_companion_completion(self) -> None:
        today = date.today().isoformat()
        if self._last_focus_date == today:
            return
        previous_date = None
        if self._last_focus_date:
            try:
                previous_date = date.fromisoformat(self._last_focus_date)
            except ValueError:
                previous_date = None
        if previous_date is not None and previous_date + timedelta(days=1) == date.today():
            self._companion_streak_days = max(1, self._companion_streak_days + 1)
        else:
            self._companion_streak_days = 1
        self._last_focus_date = today
        self._companion_days = max(0, self._companion_days) + 1
        self._save_companion_stats()
        self._refresh_companion_labels()

    def _on_ambient_enabled_changed(self, _state: int) -> None:
        self._save_ambient_state()
        if self._ambient_enabled_cb.isChecked():
            if self._phase == "running":
                self._start_ambient()
        else:
            self._stop_ambient()

    def _on_ambient_volume_changed(self, value: int) -> None:
        self._ambient_audio.setVolume(value / 100.0)
        self._with_you_settings.setValue("ambient/volume", value)

    def _on_ambient_status_changed(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            self._ambient_player.play()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._ambient_player.setPosition(0)
            self._ambient_player.play()

    def _build_noise_popup(self) -> None:
        self._noise_popup = QDialog(self)
        self._noise_popup.setObjectName("noisePopup")
        self._noise_popup.setWindowTitle("背景噪声")
        self._noise_popup.setModal(False)
        self._noise_popup.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
        )
        self._noise_popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        root = QVBoxLayout(self._noise_popup)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        panel = QFrame(self._noise_popup)
        panel.setObjectName("noisePopupPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        header_row.addWidget(QLabel("背景噪声", panel))
        header_row.addStretch(1)
        close_btn = QPushButton("关闭", panel)
        close_btn.setObjectName("ghostBtn")
        close_btn.setToolTip("关闭噪声设置面板")
        close_btn.clicked.connect(self._noise_popup.hide)
        header_row.addWidget(close_btn)
        layout.addLayout(header_row)
        self._ambient_enabled_cb = QCheckBox("播放噪声（雪夜炉火）", panel)
        self._ambient_enabled_cb.stateChanged.connect(self._on_ambient_enabled_changed)
        layout.addWidget(self._ambient_enabled_cb)
        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("音量", panel))
        self._ambient_volume_slider = QSlider(Qt.Orientation.Horizontal, panel)
        self._ambient_volume_slider.setRange(0, 100)
        self._ambient_volume_slider.setValue(50)
        self._ambient_volume_slider.valueChanged.connect(self._on_ambient_volume_changed)
        vol_row.addWidget(self._ambient_volume_slider, 1)
        layout.addLayout(vol_row)
        root.addWidget(panel)
        self._noise_popup.setStyleSheet(self._build_focus_stylesheet(self._ui_scale()))

    def _build_bgm_popup(self) -> None:
        self._bgm_popup = QDialog(self)
        self._bgm_popup.setObjectName("bgmPopup")
        self._bgm_popup.setWindowTitle("背景音乐")
        self._bgm_popup.setModal(False)
        self._bgm_popup.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
        )
        self._bgm_popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        root = QVBoxLayout(self._bgm_popup)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        panel = QFrame(self._bgm_popup)
        panel.setObjectName("bgmPopupPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        header_row.addWidget(QLabel("背景音乐", panel))
        header_row.addStretch(1)
        close_btn = QPushButton("关闭", panel)
        close_btn.setObjectName("ghostBtn")
        close_btn.setToolTip("关闭 BGM 设置面板")
        close_btn.clicked.connect(self._bgm_popup.hide)
        header_row.addWidget(close_btn)
        layout.addLayout(header_row)
        self._bgm_enabled_cb = QCheckBox("播放 BGM", panel)
        self._bgm_enabled_cb.stateChanged.connect(self._on_bgm_enabled_changed)
        layout.addWidget(self._bgm_enabled_cb)
        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("音量", panel))
        self._bgm_volume_slider = QSlider(Qt.Orientation.Horizontal, panel)
        self._bgm_volume_slider.setRange(0, 100)
        self._bgm_volume_slider.setValue(60)
        self._bgm_volume_slider.valueChanged.connect(self._on_bgm_volume_changed)
        vol_row.addWidget(self._bgm_volume_slider, 1)
        layout.addLayout(vol_row)
        self._bgm_loop_cb = QCheckBox("单曲循环", panel)
        self._bgm_loop_cb.stateChanged.connect(self._on_bgm_loop_changed)
        layout.addWidget(self._bgm_loop_cb)
        self._bgm_list = QListWidget(panel)
        self._bgm_list.setObjectName("chatTimeline")
        self._bgm_list.setMaximumHeight(px(100, self._ui_scale()))
        self._bgm_list.currentRowChanged.connect(self._on_bgm_list_selection_changed)
        layout.addWidget(self._bgm_list)
        self._bgm_seek_slider = QSlider(Qt.Orientation.Horizontal, panel)
        self._bgm_seek_slider.setRange(0, 0)
        self._bgm_seek_slider.sliderMoved.connect(self._on_bgm_seek_moved)
        self._bgm_seek_slider.sliderPressed.connect(lambda: setattr(self, "_bgm_seek_block", True))
        self._bgm_seek_slider.sliderReleased.connect(lambda: setattr(self, "_bgm_seek_block", False))
        layout.addWidget(self._bgm_seek_slider)
        self._bgm_time_label = QLabel("0:00 / 0:00", panel)
        layout.addWidget(self._bgm_time_label)
        ctrl_row = QHBoxLayout()
        self._bgm_prev_btn = QPushButton("上一首", panel)
        self._bgm_prev_btn.setObjectName("ghostBtn")
        self._bgm_prev_btn.clicked.connect(self._bgm_prev_track)
        self._bgm_next_btn = QPushButton("下一首", panel)
        self._bgm_next_btn.setObjectName("ghostBtn")
        self._bgm_next_btn.clicked.connect(self._bgm_next_track)
        ctrl_row.addWidget(self._bgm_prev_btn)
        ctrl_row.addWidget(self._bgm_next_btn)
        ctrl_row.addStretch(1)
        layout.addLayout(ctrl_row)
        root.addWidget(panel)
        self._bgm_popup.setStyleSheet(self._build_focus_stylesheet(self._ui_scale()))

    def _reposition_noise_popup(self) -> None:
        btn_top_left = self._noise_btn.mapToGlobal(self._noise_btn.rect().topLeft())
        x = max(0, btn_top_left.x())
        y = btn_top_left.y() - self._noise_popup.height() - 4
        self._noise_popup.move(x, max(0, y))

    def _reposition_bgm_popup(self) -> None:
        btn_top_right = self._bgm_btn.mapToGlobal(self._bgm_btn.rect().topRight())
        x = btn_top_right.x() - self._bgm_popup.width()
        y = btn_top_right.y() - self._bgm_popup.height() - 4
        self._bgm_popup.move(x, max(0, y))

    @staticmethod
    def _apply_popup_rounded_mask(widget: QWidget, radius: int = 14) -> None:
        """圆角窗口遮罩，避免系统绘制直角阴影。"""
        path = QPainterPath()
        path.addRoundedRect(widget.rect(), radius, radius)
        poly = path.toFillPolygon().toPolygon()
        widget.setMask(QRegion(poly))  # type: ignore[call-arg]

    def _open_noise_popup(self) -> None:
        if self._noise_popup.isVisible():
            self._noise_popup.hide()
            return
        self._noise_popup.adjustSize()
        self._apply_popup_rounded_mask(self._noise_popup)
        self._reposition_noise_popup()
        self._noise_popup.show()

    def _open_bgm_popup(self) -> None:
        if self._bgm_popup.isVisible():
            self._bgm_popup.hide()
            return
        self._bgm_popup.adjustSize()
        self._apply_popup_rounded_mask(self._bgm_popup)
        self._reposition_bgm_popup()
        self._bgm_popup.show()

    def _start_focus_audio(self) -> None:
        """点击开始专注后自动播放：根据勾选状态启动背景噪声与 BGM。"""
        if self._phase != "running":
            return
        if self._ambient_enabled_cb.isChecked():
            self._start_ambient()
        if self._bgm_enabled_cb.isChecked():
            self._start_bgm()

    def _start_ambient(self) -> None:
        if not self._ambient_enabled_cb.isChecked() or self._noise_path is None:
            return
        self._ambient_audio.setVolume(self._ambient_volume_slider.value() / 100.0)
        self._ambient_player.stop()
        self._ambient_player.setSource(QUrl())
        self._ambient_player.setSource(QUrl.fromLocalFile(str(self._noise_path.resolve())))
        self._ambient_player.play()
        QTimer.singleShot(400, self._ambient_player.play)

    def _on_bgm_media_status_changed(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            self._bgm_switching_source = False
            if self._bgm_pending_seek_ms > 0:
                self._bgm_player.setPosition(self._bgm_pending_seek_ms)
                self._bgm_pending_seek_ms = 0
            self._bgm_player.play()
            self._refresh_video_priority_for_bgm()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            # Guard against transient EndOfMedia events emitted during
            # stop/setSource switching, which can cause accidental next-track jumps.
            if self._bgm_switching_source:
                return
            if self._bgm_loop_cb.isChecked():
                self._bgm_resume_position_ms = 0
                self._bgm_player.setPosition(0)
                self._bgm_player.play()
            else:
                next_idx = (self._bgm_index + 1) % len(self._bgm_playlist) if self._bgm_playlist else 0
                if next_idx != self._bgm_index:
                    self._bgm_index = next_idx
                    self._bgm_list.setCurrentRow(self._bgm_index)
                    self._bgm_play_index(self._bgm_index, start_position_ms=0)
                else:
                    self._bgm_resume_position_ms = 0
                    self._bgm_player.setPosition(0)
                    self._bgm_player.play()
            self._refresh_video_priority_for_bgm()

    def _bgm_play_index(self, index: int, *, start_position_ms: int = 0) -> None:
        if index < 0 or index >= len(self._bgm_playlist):
            self._stop_bgm()
            return
        if not self._bgm_enabled_cb.isChecked():
            self._stop_bgm()
            return
        path = self._bgm_playlist[index]
        self._apply_bgm_ducking_volume()
        self._bgm_pending_seek_ms = max(0, start_position_ms)
        self._bgm_resume_position_ms = self._bgm_pending_seek_ms
        self._bgm_switching_source = True
        self._bgm_player.stop()
        self._bgm_player.setSource(QUrl())
        self._bgm_player.setSource(QUrl.fromLocalFile(path))
        self._bgm_player.play()
        QTimer.singleShot(400, self._bgm_player.play)

    def _stop_ambient(self) -> None:
        self._ambient_player.stop()
        self._ambient_player.setSource(QUrl())

    def _on_bgm_volume_changed(self, value: int) -> None:
        self._apply_bgm_ducking_volume()
        self._with_you_settings.setValue("bgm/volume", value)

    def _on_bgm_enabled_changed(self, _state: int) -> None:
        self._save_bgm_state()
        if self._bgm_enabled_cb.isChecked():
            if self._phase in ("running", "config"):
                self._start_bgm()
        else:
            self._stop_bgm()

    def _on_bgm_loop_changed(self, _state: int) -> None:
        self._save_bgm_state()

    def _on_bgm_list_selection_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._bgm_playlist):
            return
        self._bgm_index = row
        self._with_you_settings.setValue("bgm/index", row)
        self._bgm_resume_position_ms = 0
        self._with_you_settings.setValue("bgm/position_ms", 0)
        if self._phase in ("running", "config") and self._bgm_enabled_cb.isChecked():
            self._bgm_play_index(self._bgm_index, start_position_ms=0)

    def _on_bgm_seek_moved(self, position: int) -> None:
        self._bgm_resume_position_ms = max(0, position)
        self._with_you_settings.setValue("bgm/position_ms", self._bgm_resume_position_ms)
        self._bgm_player.setPosition(position)

    def _bgm_prev_track(self) -> None:
        if not self._bgm_playlist:
            return
        self._bgm_index = (self._bgm_index - 1) % len(self._bgm_playlist)
        self._bgm_list.setCurrentRow(self._bgm_index)
        self._with_you_settings.setValue("bgm/index", self._bgm_index)
        self._bgm_resume_position_ms = 0
        self._with_you_settings.setValue("bgm/position_ms", 0)
        self._bgm_play_index(self._bgm_index, start_position_ms=0)

    def _bgm_next_track(self) -> None:
        if not self._bgm_playlist:
            return
        self._bgm_index = (self._bgm_index + 1) % len(self._bgm_playlist)
        self._bgm_list.setCurrentRow(self._bgm_index)
        self._with_you_settings.setValue("bgm/index", self._bgm_index)
        self._bgm_resume_position_ms = 0
        self._with_you_settings.setValue("bgm/position_ms", 0)
        self._bgm_play_index(self._bgm_index, start_position_ms=0)

    def _on_bgm_position_changed(self, position: int) -> None:
        if getattr(self, "_bgm_seek_block", False):
            return
        self._bgm_resume_position_ms = max(0, position)
        self._with_you_settings.setValue("bgm/position_ms", self._bgm_resume_position_ms)
        self._bgm_seek_slider.setMaximum(max(self._bgm_player.duration(), 1))
        self._bgm_seek_slider.setValue(position)
        d = self._bgm_player.duration()
        self._bgm_time_label.setText(f"{position // 1000 // 60}:{position // 1000 % 60:02d} / {d // 1000 // 60}:{d // 1000 % 60:02d}" if d > 0 else "0:00 / 0:00")

    def _on_bgm_duration_changed(self, duration: int) -> None:
        self._bgm_seek_slider.setRange(0, max(0, duration))

    def _start_bgm(self) -> None:
        if not self._bgm_enabled_cb.isChecked() or not self._bgm_playlist:
            return
        self._bgm_index = min(self._bgm_index, len(self._bgm_playlist) - 1)
        self._bgm_play_index(self._bgm_index, start_position_ms=self._bgm_resume_position_ms)

    def _stop_bgm(self) -> None:
        self._bgm_resume_position_ms = max(0, self._bgm_player.position())
        self._with_you_settings.setValue("bgm/position_ms", self._bgm_resume_position_ms)
        self._bgm_switching_source = False
        self._bgm_player.stop()
        self._bgm_player.setSource(QUrl())
        self._bgm_seek_slider.setRange(0, 0)
        self._bgm_time_label.setText("0:00 / 0:00")
        self._refresh_video_priority_for_bgm()

    def _on_video_playback_state_changed(self, _state) -> None:
        self._refresh_video_priority_for_bgm()

    def _is_video_audio_active(self) -> bool:
        return (
            not self._player.source().isEmpty()
            and self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )

    def _apply_bgm_ducking_volume(self) -> None:
        if not hasattr(self, "_bgm_volume_slider"):
            return
        base = max(0.0, min(1.0, self._bgm_volume_slider.value() / 100.0))
        target = base
        if self._is_video_audio_active():
            target = base * self._bgm_ducking_ratio
        self._bgm_audio.setVolume(max(0.0, min(1.0, target)))

    def _refresh_video_priority_for_bgm(self) -> None:
        if not hasattr(self, "_bgm_enabled_cb"):
            self._player.setAudioOutput(self._audio)
            self._audio.setVolume(1.0)
            self._frame_interval_s = self._fallback_frame_interval_normal_s
            return
        self._player.setAudioOutput(self._audio)
        self._audio.setVolume(1.0)
        bgm_playing = (
            self._bgm_enabled_cb.isChecked()
            and self._bgm_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        self._apply_bgm_ducking_volume()
        if bgm_playing:
            self._frame_interval_s = self._fallback_frame_interval_bgm_priority_s
            return
        self._frame_interval_s = self._fallback_frame_interval_normal_s

    @staticmethod
    def _focus_theme_tokens() -> dict[str, str]:
        tokens = {
            "bg_dialog": "#0f141b",
            "text_light": "#e6edf3",
            "panel_grad_a": "rgba(10, 18, 36, 1)",
            "panel_grad_b": "rgba(34, 56, 86, 1)",
            "panel_border": "#ffffff",
            "settings_bg": "#eef2f6",
            "focus_window_bg": "#fdf0f4",
            "config_window_bg": "#eef2f6",
            "settings_panel_bg": "#ffeadc",
            "status_text": "#EAF5FF",
            "round_text": "#CFE8FF",
            "tip_text": "#DDEBFF",
            "settings_text": "#EAF3FF",
            "unit_text": "#C8DBF7",
            "divider": "rgba(180, 203, 233, 0.45)",
            # Frosted cards over night-sky background.
            "card_bg_a": "rgba(237, 245, 255, 0.30)",
            "card_bg_b": "rgba(224, 236, 252, 0.20)",
            "card_border": "rgba(191, 219, 255, 0.38)",
            "countdown": "#DDF1FF",
            "input_bg": "rgba(246, 251, 255, 0.42)",
            "input_border": "rgba(197, 220, 246, 0.50)",
            "input_focus": "rgba(211, 230, 252, 0.72)",
            "input_focus_bg": "rgba(250, 253, 255, 0.62)",
            "btn_pink_top": "rgba(241, 233, 255, 0.55)",
            "btn_pink_bottom": "rgba(222, 238, 255, 0.50)",
            "btn_pink_border": "rgba(184, 206, 238, 0.55)",
            "btn_pink_border_pressed": "rgba(160, 184, 220, 0.60)",
            "btn_pink_hover_top": "#f8fbff",
            "btn_pink_hover_bottom": "#e9f2ff",
            "text_dark": "#1B2A40",
            "font_family":" 'Source Han Sans SC', 'PingFang SC'",
            "mini_panel_a": "rgba(18, 30, 52, 0.92)",
            "mini_panel_b": "rgba(34, 53, 82, 0.92)",
            "mini_panel_border": "rgba(176, 207, 246, 0.58)",
            "mini_text": "#D7E9FF",
            "mini_focus": "#89E4C0",
            "mini_break": "#F9D188",
            "mini_pause": "#C0D5EE",
            "mini_config": "#B8CCE5",
            "mini_hangup": "#FFB8CF",
            "mini_timer": "#F0C9FF",
            "mini_btn_a": "rgba(240, 232, 255, 0.62)",
            "mini_btn_b": "rgba(220, 236, 255, 0.56)",
            "mini_btn_border": "rgba(175, 205, 240, 0.60)",
            "mini_btn_text": "#1B2A42",
            "mini_btn_hover": "rgba(212, 228, 248, 0.88)",
            "mini_btn_pressed": "rgba(183, 205, 233, 0.92)",
            "mini_danger_a": "rgba(255, 223, 236, 0.74)",
            "mini_danger_b": "rgba(244, 206, 227, 0.68)",
            "mini_danger_border": "rgba(226, 167, 200, 0.86)",
            "mini_danger_text": "#3A2540",
            "mini_danger_hover_a": "rgba(255, 232, 242, 0.84)",
            "mini_danger_hover_b": "rgba(248, 214, 232, 0.80)",
            "mini_danger_pressed_a": "rgba(247, 211, 230, 0.86)",
            "mini_danger_pressed_b": "rgba(239, 197, 220, 0.82)",
            "focus_bg_cream": "#fdf0f4",
            "macaron_pink": "#E8D0E6",
            "popup_bg": "#EAF2FF",
        }
        tokens.update(focus_theme_base_tokens())
        # Keep high contrast for the focus-mode gradient background.
        tokens["status_text"] = "#EAF5FF"
        tokens["round_text"] = "#CFE8FF"
        tokens["countdown"] = "#DDF1FF"
        tokens["macaron_pink"] = "#E8D0E6"
        return tokens

    def _build_focus_stylesheet(self, scale: float) -> str:
        t = self._focus_theme_tokens()
        return f"""
            QDialog {{
                background: {t["bg_dialog"]};
                color: {t["text_light"]};
            }}
            QDialog#noisePopup, QDialog#bgmPopup {{
                background: transparent;
                border: none;
            }}
            QDialog#withYouWindow {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {t["panel_grad_a"]}, stop:1 {t["panel_grad_b"]});
                border: none;
            }}
            QFrame#noisePopupPanel, QFrame#bgmPopupPanel {{
                background: {t["popup_bg"]};
                border: 1px solid {t["card_border"]};
                border-radius: 14px;
                border-image: none;
            }}
            QFrame#noisePopupPanel QLabel, QFrame#bgmPopupPanel QLabel {{
                color: {t["macaron_pink"]};
            }}
            QFrame#noisePopupPanel QCheckBox, QFrame#bgmPopupPanel QCheckBox {{
                color: {t["macaron_pink"]};
            }}
            QDialog#withYouWindow[viewMode="config"] {{
                color: {t["settings_text"]};
            }}
            QLabel#statusLabel, QLabel#roundLabel, QLabel#countdownLabel, QPushButton {{
                font-family: {t["font_family"]};
            }}
            QDialog#withYouWindow QFrame#interactivePage,
            QDialog#withYouWindow QFrame#topBar,
            QDialog#withYouWindow QFrame#bottomBar,
            QDialog#withYouWindow QScrollArea#settingsScroll,
            QDialog#withYouWindow QScrollArea#settingsScroll > QWidget#qt_scrollarea_viewport,
            QDialog#withYouWindow QFrame#withyouPanel {{
                background: transparent;
                border: none;
            }}
            QDialog#withYouWindow QFrame#interactivePage {{
                background: rgba(9, 18, 34, 0.28);
            }}
            QDialog#withYouWindow QFrame#settingsContentPanel {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(28, 44, 68, 0.34),
                    stop:1 rgba(41, 62, 92, 0.28)
                );
                border: none;
                border-radius: 0px;
            }}
            QDialog#withYouWindow QFrame#topBar,
            QDialog#withYouWindow QFrame#bottomBar {{
                background: rgba(9, 17, 34, 0.34);
                border: none;
                border-radius: 0px;
            }}
            QDialog#withYouWindow[viewMode="config"] QFrame#topBar,
            QDialog#withYouWindow[viewMode="config"] QFrame#bottomBar {{
                background: rgba(9, 17, 34, 0.42);
                border: none;
            }}
            QLabel#statusLabel {{ font-size: {px(17, scale)}px; font-weight: 700; color: {t["status_text"]}; }}
            QLabel#roundLabel {{ font-size: {px(32, scale)}px; font-weight: 700; color: {t["round_text"]}; }}
            QDialog[viewMode="config"] QLabel#statusLabel {{ color: {t["settings_text"]}; }}
            QDialog[viewMode="config"] QLabel#roundLabel {{ color: {t["unit_text"]}; }}
            QLabel#tipLabel {{ font-size: {px(13, scale)}px; color: {t["tip_text"]}; padding: 2px 4px; }}
            QCheckBox {{ color: #b8c4d3; font-size: {px(26, scale)}px; font-weight: 700; }}
            QLabel#settingFieldLabel, QLabel#roundsFieldLabel, QLabel#timeFieldLabel {{
                font-size: {px(14, scale)}px; color: {t["settings_text"]};
            }}
            QLabel#unitLabel {{ font-size: {px(28, scale)}px; color: {t["unit_text"]}; }}
            QFrame#settingsDivider {{ background: {t["divider"]}; border-radius: 1px; margin-bottom: 2px; }}
            QFrame#settingCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["card_bg_a"]}, stop:1 {t["card_bg_b"]});
                border: 1px solid {t["card_border"]};
                border-radius: 14px;
            }}
            QLabel#companionInfoTopLabel {{
                font-size: {px(16, scale)}px;
                color: {t["status_text"]};
                font-weight: 700;
            }}
            QDialog[viewMode="config"] QLabel#companionInfoTopLabel {{
                color: {t["settings_text"]};
            }}
            QLabel#countdownLabel {{
                font-size: {px(56, scale)}px;
                font-weight: 800;
                color: {t["countdown"]};
                letter-spacing: 1px;
            }}
            QFrame {{ border: none; }}
            QSpinBox {{
                background: {t["input_bg"]};
                border: 1px solid {t["input_border"]};
                border-radius: 10px;
                padding: 4px 8px;
                min-height: {px(34, scale)}px;
                color: {t["text_dark"]};
                font-size: {px(12, scale)}px;
            }}
            QSpinBox:focus {{
                border: 2px solid {t["input_focus"]};
                background: {t["input_focus_bg"]};
            }}
            QSpinBox#roundsFieldSpin, QSpinBox#timeFieldSpin {{
                font-size: {px(24, scale)}px;
            }}
            QPushButton#primaryBtn, QPushButton#ghostBtn, QPushButton#chocoBtn, QPushButton#dangerBtn {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {t["btn_pink_top"]}, stop:1 {t["btn_pink_bottom"]});
                border: 1px solid {t["btn_pink_border"]};
                border-bottom: 2px solid {t["btn_pink_border_pressed"]};
                color: {t["text_dark"]};
                font-weight: 700;
            }}
            QPushButton#primaryBtn {{
                border-radius: 16px;
                min-height: {px(44, scale)}px;
                font-size: {px(15, scale)}px;
                padding: 6px 10px;
            }}
            QPushButton#ghostBtn {{
                border-radius: 16px;
                min-height: {px(36, scale)}px;
                min-width: {px(66, scale)}px;
                font-size: {px(13, scale)}px;
                padding: 6px 10px;
            }}
            QPushButton#chocoBtn {{
                border-radius: 14px;
                min-height: {px(30, scale)}px;
                min-width: 0px;
                margin: 2px;
                padding: 6px 8px;
                font-size: {px(13, scale)}px;
            }}
            QPushButton#dangerBtn {{
                border-radius: 16px;
                min-height: {px(36, scale)}px;
                min-width: {px(66, scale)}px;
                font-size: {px(13, scale)}px;
                padding: 6px 10px;
            }}
            QPushButton#primaryBtn:hover, QPushButton#ghostBtn:hover, QPushButton#chocoBtn:hover, QPushButton#dangerBtn:hover {{
                border-color: #e2a7c2;
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {t["btn_pink_hover_top"]},
                    stop:1 {t["btn_pink_hover_bottom"]}
                );
            }}
            QPushButton#primaryBtn:pressed, QPushButton#ghostBtn:pressed, QPushButton#chocoBtn:pressed, QPushButton#dangerBtn:pressed {{
                border-bottom: 1px solid {t["btn_pink_border_pressed"]};
                padding-top: 7px;
                padding-bottom: 5px;
            }}
            QPushButton[iconOnly="true"] {{
                padding: 0px;
                margin: 0px;
                min-width: 0px;
                min-height: 0px;
                text-align: center;
            }}
        """

    def _set_view_mode(self, mode: str) -> None:
        self.setProperty("viewMode", mode)
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        if mode == "focus":
            self.setWindowOpacity(1.0)
        elif mode == "config":
            self.setWindowOpacity(self._config_opacity / 100.0)
        else:
            self.setWindowOpacity(1.0)
        self.update()

    def open_call(self) -> None:
        # Re-read companion stats so external/manual settings.json edits
        # are reflected each time the call window is reopened.
        self._last_focus_date, self._companion_days, self._companion_streak_days = self._load_companion_stats()
        self._refresh_companion_labels()
        if self._mini_bar is not None and self._mini_bar.isVisible():
            self._mini_bar.hide()
        self.show()
        self.raise_()
        self.activateWindow()
        if not self._call_active:
            self._call_active = True
            self.callStarted.emit()
        if self._answer_path is None:
            self._enter_config()
            return
        self._phase = "answering"
        self._set_cinematic_mode()
        self._play_media(self._answer_path, loop=False)

    def _pick_media(self, names: tuple[str, ...]) -> Path | None:
        for name in names:
            p = self._call_dir / name
            if p.exists():
                return p
        return None

    @staticmethod
    def _audio_extensions() -> tuple[str, ...]:
        return (".mp3", ".m4a", ".wav", ".flac", ".ogg", ".MP3", ".M4A", ".WAV", ".FLAC", ".OGG")

    def _scan_audio_dir(self, directory: Path) -> list[Path]:
        if not directory.is_dir():
            return []
        exts = self._audio_extensions()
        return sorted(
            (p for p in directory.resolve().iterdir() if p.is_file() and p.suffix in exts),
            key=lambda p: p.name.lower(),
        )

    def _first_audio_in_dir(self, directory: Path) -> Path | None:
        files = self._scan_audio_dir(directory)
        return files[0] if files else None

    def _refresh_bgm_playlist(self) -> None:
        """从 resources/Call/bgm 扫描音频，只显示歌名。"""
        self._bgm_playlist = [str(p.resolve()) for p in self._scan_audio_dir(self._bgm_dir)]
        if not hasattr(self, "_bgm_list") or self._bgm_list is None:
            return
        self._bgm_list.clear()
        for path in self._bgm_playlist:
            self._bgm_list.addItem(QListWidgetItem(Path(path).name))
        self._bgm_index = max(0, min(self._bgm_index, len(self._bgm_playlist) - 1))
        if self._bgm_playlist:
            self._bgm_list.blockSignals(True)
            self._bgm_list.setCurrentRow(self._bgm_index)
            self._bgm_list.blockSignals(False)

    def _pick_media_candidates(self, names: tuple[str, ...]) -> list[Path]:
        candidates: list[Path] = []
        for name in names:
            p = self._call_dir / name
            if p.exists():
                candidates.append(p)
        return candidates

    def _apply_soft_shadow(self, widget: QWidget, blur_radius: int, y_offset: int, *, alpha: int = 36) -> None:
        effect = QGraphicsDropShadowEffect(widget)
        effect.setBlurRadius(max(8, int(blur_radius)))
        effect.setOffset(0, int(y_offset))
        effect.setColor(QColor(23, 36, 51, max(0, min(255, alpha))))
        widget.setGraphicsEffect(effect)

    def _play_media(self, media_path: Path, *, loop: bool) -> None:
        resolved = str(media_path.resolve())
        if (
            self._current_media_source == resolved
            and self._loop_video == loop
            and self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        ):
            return
        if loop:
            self._restore_background_audio_after_voice(resume=True)
        else:
            self._pause_background_audio_for_voice()
        self._loop_video = loop
        if hasattr(self._player, "setLoops"):
            loops = QMediaPlayer.Loops.Infinite if loop else 1
            self._player.setLoops(loops)
        self._player.stop()
        # Force-detach previous stream before switching to new media.
        self._player.setSource(QUrl())
        self._current_media_source = resolved
        self._player.setSource(QUrl.fromLocalFile(resolved))
        self._player.play()

    def _stop_all_playback(self) -> None:
        self._loop_video = False
        if hasattr(self._player, "setLoops"):
            self._player.setLoops(1)
        self._player.stop()
        self._player.setSource(QUrl())
        self._current_media_source = ""
        self._sfx_player.stop()
        self._restore_background_audio_after_voice(resume=False)
        self._stop_ambient()
        self._stop_bgm()

    def _stop_transition_playback(self) -> None:
        """Stop only cinematic/video/sfx playback, keep ambient+BGM running."""
        self._loop_video = False
        if hasattr(self._player, "setLoops"):
            self._player.setLoops(1)
        self._player.stop()
        self._player.setSource(QUrl())
        self._current_media_source = ""
        self._sfx_player.stop()
        self._restore_background_audio_after_voice(resume=True)

    def _pause_background_audio_for_voice(self) -> None:
        if self._background_audio_paused_for_voice:
            return
        self._background_audio_paused_for_voice = True
        self._resume_ambient_after_voice = (
            self._ambient_enabled_cb.isChecked()
            and self._ambient_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        self._resume_bgm_after_voice = (
            self._bgm_enabled_cb.isChecked()
            and self._bgm_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        if self._resume_ambient_after_voice:
            self._ambient_player.pause()
        if self._resume_bgm_after_voice:
            self._bgm_player.pause()
        self._refresh_video_priority_for_bgm()

    def _restore_background_audio_after_voice(self, *, resume: bool) -> None:
        if not self._background_audio_paused_for_voice:
            return
        should_resume_ambient = resume and self._resume_ambient_after_voice and self._ambient_enabled_cb.isChecked()
        should_resume_bgm = resume and self._resume_bgm_after_voice and self._bgm_enabled_cb.isChecked()
        self._background_audio_paused_for_voice = False
        self._resume_ambient_after_voice = False
        self._resume_bgm_after_voice = False
        if should_resume_ambient:
            self._ambient_player.play()
        if should_resume_bgm:
            self._bgm_player.play()
        self._refresh_video_priority_for_bgm()

    def _play_start_sfx(self) -> None:
        if self._start_sfx_path is None:
            return
        self._sfx_player.stop()
        self._sfx_player.setSource(QUrl.fromLocalFile(str(self._start_sfx_path)))
        self._sfx_player.play()

    def _play_focus_entry_media(self) -> None:
        self._start_intro_playing = False
        starts = [p for p in (self._start1_path, self._start2_path) if p is not None]
        if starts:
            self._start_intro_playing = True
            self._set_cinematic_mode(fill=True)
            self._play_media(random.choice(starts), loop=False)
            return
        self._play_start_sfx()
        self._set_interactive_mode()
        self._middle_stack.setCurrentWidget(self._withyou_panel)
        self._activate_withyou_video_output()
        if self._withyou_path is not None:
            self._play_media(self._withyou_path, loop=True)

    def _finish_all_rounds(self) -> None:
        self._tick.stop()
        self._player.stop()
        self._break_intro_playing = False
        self._start_intro_playing = False
        self._record_focus_companion_completion()
        if self._end_paths:
            self._end_outro_playing = True
            self._set_cinematic_mode(fill=True)
            self._play_media(random.choice(self._end_paths), loop=False)
            return
        self._enter_config(preserve_progress=False)

    def _set_cinematic_mode(self, *, fill: bool = False) -> None:
        self._stack.setCurrentWidget(self._cinematic_page)
        if hasattr(self, "_ribbon_overlay"):
            self._ribbon_overlay.hide()
            self._ribbon_overlay.set_animating(False)
        self._activate_cinematic_video_output(fill=fill)

    def _set_interactive_mode(self) -> None:
        self._stack.setCurrentWidget(self._interactive_page)
        if hasattr(self, "_ribbon_overlay"):
            self._ribbon_overlay.show()
            self._ribbon_overlay.raise_()
            self._ribbon_overlay.set_animating(True)

    def _activate_cinematic_video_output(self, *, fill: bool) -> None:
        self._cinematic_fill_mode = fill
        if HAS_QVIDEO_WIDGET and _QVideoWidget is not None and isinstance(self._cinematic_video, _QVideoWidget):
            mode = Qt.AspectRatioMode.KeepAspectRatioByExpanding if fill else Qt.AspectRatioMode.KeepAspectRatio
            self._cinematic_video.setAspectRatioMode(mode)
            self._active_video_widget = self._cinematic_video
            self._player.setVideoOutput(self._cinematic_video)
            return
        self._active_video_label = cast(QLabel, self._cinematic_video)
        self._active_video_label.setPixmap(QPixmap())

    def _activate_withyou_video_output(self) -> None:
        self._cinematic_fill_mode = False
        if HAS_QVIDEO_WIDGET and _QVideoWidget is not None and isinstance(self._withyou_video, _QVideoWidget):
            self._withyou_video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatioByExpanding)
            self._active_video_widget = self._withyou_video
            self._player.setVideoOutput(self._withyou_video)
            return
        self._active_video_label = cast(QLabel, self._withyou_video)

    def _enter_config(self, *, preserve_progress: bool = False) -> None:
        self._phase = "config"
        self._set_view_mode("config")
        self._set_interactive_mode()
        self._middle_stack.setCurrentWidget(self._settings_scroll)
        self._active_video_widget = None
        self._active_video_label = None
        self._break_intro_playing = False
        self._start_intro_playing = False
        self._end_outro_playing = False
        if preserve_progress:
            self._is_paused = True
            self.status_label.setText("设置中（进度已保留）")
            self._sync_round_ui()
            self._sync_countdown_ui()
            self.return_btn.setVisible(True)
        else:
            self._is_break_phase = False
            self._is_paused = False
            self.status_label.setText("番茄钟设置")
            self.round_label.setText("第 0/0 轮")
            self.countdown_label.setText("00:00")
            self.return_btn.setVisible(False)
        self.start_btn.setEnabled(True)
        self.rounds_spin.setEnabled(True)
        self.focus_min_spin.setEnabled(True)
        self.focus_sec_spin.setEnabled(True)
        self.break_min_spin.setEnabled(True)
        self.break_sec_spin.setEnabled(True)
        self.settings_btn.setEnabled(False)
        self.chat_btn.setVisible(False)
        self.mini_btn.setVisible(False)
        self.settings_btn.setVisible(False)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setVisible(False)
        self.skip_btn.setEnabled(False)
        self.skip_btn.setVisible(False)
        self._set_pause_button_state()
        self._update_mini_bar_state()

    def _back_to_settings(self) -> None:
        if self._phase != "running":
            return
        self._resume_state = {
            "total_rounds": self._total_rounds,
            "current_round": self._current_round,
            "round_seconds": self._round_seconds,
            "break_seconds": self._break_seconds,
            "remaining_seconds": self._remaining_seconds,
            "is_break_phase": self._is_break_phase,
            "was_paused": self._is_paused,
        }
        self._tick.stop()
        self._player.stop()
        self._enter_config(preserve_progress=True)

    def _start_focus(self) -> None:
        self._resume_state = None
        self._phase = "running"
        self._set_view_mode("focus")
        self._set_interactive_mode()
        self._middle_stack.setCurrentWidget(self._withyou_panel)
        self._activate_withyou_video_output()
        self._total_rounds = max(1, int(self.rounds_spin.value()))
        self._current_round = 1
        focus_total_seconds = int(self.focus_min_spin.value()) * 60 + int(self.focus_sec_spin.value())
        break_total_seconds = int(self.break_min_spin.value()) * 60 + int(self.break_sec_spin.value())
        self._round_seconds = max(1, focus_total_seconds)
        self._break_seconds = max(1, break_total_seconds)
        self._remaining_seconds = self._round_seconds
        self._is_break_phase = False
        self._is_paused = False
        self._break_intro_playing = False
        self._start_intro_playing = False
        self._end_outro_playing = False
        self.rounds_spin.setEnabled(False)
        self.focus_min_spin.setEnabled(False)
        self.focus_sec_spin.setEnabled(False)
        self.break_min_spin.setEnabled(False)
        self.break_sec_spin.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.settings_btn.setEnabled(True)
        self.chat_btn.setVisible(True)
        self.mini_btn.setVisible(True)
        self.settings_btn.setVisible(True)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setVisible(True)
        self.skip_btn.setEnabled(True)
        self.skip_btn.setVisible(True)
        self._set_pause_button_state()
        self.status_label.setText("专注中")
        self._sync_round_ui()
        self._sync_countdown_ui()
        self._tick.start()
        self._update_mini_bar_state()
        self._play_focus_entry_media()
        # 点击开始专注后自动播放：界面切换完成后再启动背景噪声与 BGM，避免设备未就绪
        QTimer.singleShot(150, self._start_focus_audio)

        if self._withyou_path is None and not self._start_intro_playing:
            QMessageBox.information(self, "缺少素材", "未找到 withyou 视频素材，将仅保留计时。")

    def _return_to_running_without_changes(self) -> None:
        if not self._resume_state:
            return
        self._total_rounds = int(self._resume_state.get("total_rounds", self._total_rounds))
        self._current_round = int(self._resume_state.get("current_round", self._current_round))
        self._round_seconds = int(self._resume_state.get("round_seconds", self._round_seconds))
        self._break_seconds = int(self._resume_state.get("break_seconds", self._break_seconds))
        self._remaining_seconds = int(self._resume_state.get("remaining_seconds", self._remaining_seconds))
        self._is_break_phase = bool(self._resume_state.get("is_break_phase", False))
        self._is_paused = bool(self._resume_state.get("was_paused", False))
        self._resume_state = None

        self._phase = "running"
        self._set_view_mode("focus")
        self._set_interactive_mode()
        self._middle_stack.setCurrentWidget(self._withyou_panel)
        self._activate_withyou_video_output()
        self.start_btn.setEnabled(False)
        self.rounds_spin.setEnabled(False)
        self.focus_min_spin.setEnabled(False)
        self.focus_sec_spin.setEnabled(False)
        self.break_min_spin.setEnabled(False)
        self.break_sec_spin.setEnabled(False)
        self.settings_btn.setEnabled(True)
        self.chat_btn.setVisible(True)
        self.mini_btn.setVisible(True)
        self.settings_btn.setVisible(True)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setVisible(True)
        self.skip_btn.setEnabled(True)
        self.skip_btn.setVisible(True)
        self.return_btn.setVisible(False)

        if self._is_paused:
            self.status_label.setText("已暂停")
            self._tick.stop()
            self._player.stop()
        else:
            self.status_label.setText("休息中" if self._is_break_phase else "专注中")
            self._tick.start()
            # Resuming from "返回" should keep current stage directly,
            # without replaying start intro clips.
            self._start_intro_playing = False
            self._break_intro_playing = False
            if self._withyou_path is not None:
                self._play_media(self._withyou_path, loop=True)
        self._sync_round_ui()
        self._sync_countdown_ui()
        self._set_pause_button_state()
        self._update_mini_bar_state()

    def _start_hangup(self) -> None:
        self._tick.stop()
        self._stop_ambient()
        self._stop_bgm()
        self._phase = "hangup"
        self._set_view_mode("focus")
        self._update_mini_bar_state()
        if self._hangup_path is None:
            self.close()
            return
        self._set_cinematic_mode()
        self._play_media(self._hangup_path, loop=False)

    def _sync_round_ui(self) -> None:
        stage = "休息" if self._is_break_phase else "专注"
        self.round_label.setText(
            f'第 {self._current_round}/{self._total_rounds} 轮 · '
            f'<span style="font-size:32px;">{stage}</span>'
        )

    def _sync_countdown_ui(self) -> None:
        sec = max(0, int(self._remaining_seconds))
        text = f"{sec // 60:02d}:{sec % 60:02d}"
        self.countdown_label.setText(text)
        if self._mini_bar is not None:
            self._mini_bar.set_countdown(text)
        self._update_status_tray_state()

    def _sync_middle_height(self) -> None:
        if self._withyou_width <= 0 or self._withyou_height <= 0:
            return
        target_h = int(round(self.width() * (self._withyou_height / self._withyou_width)))
        top_h = max(64, self._top_bar.sizeHint().height())
        bottom_h = max(64, self._bottom_bar.sizeHint().height())
        available = self.height() - top_h - bottom_h
        max_h = max(120, available)
        self._middle_stack.setFixedHeight(min(target_h, max_h))

    def _on_tick(self) -> None:
        if self._phase != "running":
            return
        if self._is_paused:
            return
        self._remaining_seconds -= 1
        stage_changed = False
        if self._remaining_seconds <= 0:
            if self._is_break_phase:
                if self._current_round >= self._total_rounds:
                    self._finish_all_rounds()
                    return
                self._is_break_phase = False
                stage_changed = True
                self._current_round += 1
                self._remaining_seconds = self._round_seconds
                self.status_label.setText("专注中")
                self._play_focus_entry_media()
            else:
                self._is_break_phase = True
                stage_changed = True
                self._remaining_seconds = self._break_seconds
                self.status_label.setText("休息中")
                if self._break_paths:
                    self._break_intro_playing = True
                    self._set_cinematic_mode(fill=True)
                    self._play_media(random.choice(self._break_paths), loop=False)
            self._sync_round_ui()
        if stage_changed:
            self._update_mini_bar_state()
        self._sync_countdown_ui()

    def _toggle_pause(self) -> None:
        if self._phase != "running":
            return
        self._is_paused = not self._is_paused
        if self._is_paused:
            self.status_label.setText("已暂停")
        else:
            self.status_label.setText("休息中" if self._is_break_phase else "专注中")
        self._set_pause_button_state()
        self._update_mini_bar_state()

    def _skip_current_stage(self) -> None:
        if self._phase != "running":
            return
        self._is_paused = False
        if self._is_break_phase:
            if self._current_round >= self._total_rounds:
                self._finish_all_rounds()
                return
            self._is_break_phase = False
            self._break_intro_playing = False
            self._current_round += 1
            self._remaining_seconds = self._round_seconds
            self.status_label.setText("专注中")
            self._play_focus_entry_media()
        else:
            self._is_break_phase = True
            self._remaining_seconds = self._break_seconds
            self.status_label.setText("休息中")
            if self._break_paths:
                self._break_intro_playing = True
                self._set_cinematic_mode(fill=True)
                self._play_media(random.choice(self._break_paths), loop=False)
        self._sync_round_ui()
        self._sync_countdown_ui()
        self._set_pause_button_state()
        self._update_mini_bar_state()

    def _on_video_frame_changed(self, frame) -> None:
        if HAS_QVIDEO_WIDGET:
            return
        now = time.monotonic()
        if (now - self._last_frame_render_ts) < self._frame_interval_s:
            return
        self._last_frame_render_ts = now
        if frame is None or not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        pix = QPixmap.fromImage(image)
        if pix.isNull():
            return
        self._last_frame = pix
        self._render_frame()

    def _render_frame(self) -> None:
        if HAS_QVIDEO_WIDGET:
            return
        if self._last_frame is None or self._last_frame.isNull() or self._active_video_label is None:
            return
        mode = Qt.AspectRatioMode.KeepAspectRatio
        if self._active_video_label is self._withyou_video:
            mode = Qt.AspectRatioMode.KeepAspectRatioByExpanding
        if self._active_video_label is self._cinematic_video and self._cinematic_fill_mode:
            mode = Qt.AspectRatioMode.KeepAspectRatioByExpanding
        scaled = self._last_frame.scaled(
            self._active_video_label.size(),
            mode,
            Qt.TransformationMode.FastTransformation,
        )
        self._active_video_label.setPixmap(scaled)

    def _on_media_status_changed(self, status) -> None:
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        if self._loop_video and self._phase == "running":
            if not hasattr(self._player, "setLoops"):
                self._player.setPosition(0)
                self._player.play()
            return
        if self._break_intro_playing and self._phase == "running" and self._is_break_phase:
            self._restore_background_audio_after_voice(resume=True)
            self._break_intro_playing = False
            self._set_interactive_mode()
            self._middle_stack.setCurrentWidget(self._withyou_panel)
            self._activate_withyou_video_output()
            if self._withyou_path is not None:
                self._play_media(self._withyou_path, loop=True)
            return
        if self._start_intro_playing and self._phase == "running" and not self._is_break_phase:
            self._restore_background_audio_after_voice(resume=True)
            self._start_intro_playing = False
            self._set_interactive_mode()
            self._middle_stack.setCurrentWidget(self._withyou_panel)
            self._activate_withyou_video_output()
            if self._withyou_path is not None:
                self._play_media(self._withyou_path, loop=True)
            return
        if self._end_outro_playing:
            self._restore_background_audio_after_voice(resume=True)
            self._end_outro_playing = False
            self._enter_config(preserve_progress=False)
            return
        if self._phase == "answering":
            self._restore_background_audio_after_voice(resume=True)
            self._enter_config()
            return
        if self._phase == "hangup":
            self._restore_background_audio_after_voice(resume=False)
            self.close()

    def _on_media_error(self, _err, _msg: str) -> None:
        if self._end_outro_playing:
            self._restore_background_audio_after_voice(resume=True)
            self._end_outro_playing = False
            self._enter_config(preserve_progress=False)
            return
        if self._phase == "answering":
            self._restore_background_audio_after_voice(resume=True)
            self._enter_config()
            return
        if self._phase == "hangup":
            self._restore_background_audio_after_voice(resume=False)
            self.close()

    def _open_note_window(self) -> None:
        if self._note_window is None:
            self._note_window = StickyNoteWindow(self)
        self._note_window.show()
        self._note_window.raise_()
        self._note_window.activateWindow()

    def handle_escape_animation(self) -> bool:
        if self._phase == "answering":
            self._stop_transition_playback()
            self._enter_config()
            return True
        if self._start_intro_playing and self._phase == "running" and not self._is_break_phase:
            self._stop_transition_playback()
            self._start_intro_playing = False
            self._set_interactive_mode()
            self._middle_stack.setCurrentWidget(self._withyou_panel)
            self._activate_withyou_video_output()
            if self._withyou_path is not None:
                self._play_media(self._withyou_path, loop=True)
            return True
        if self._break_intro_playing and self._phase == "running" and self._is_break_phase:
            self._stop_transition_playback()
            self._break_intro_playing = False
            self._set_interactive_mode()
            self._middle_stack.setCurrentWidget(self._withyou_panel)
            self._activate_withyou_video_output()
            if self._withyou_path is not None:
                self._play_media(self._withyou_path, loop=True)
            return True
        if self._end_outro_playing:
            self._stop_transition_playback()
            self._end_outro_playing = False
            self._enter_config(preserve_progress=False)
            return True
        if self._phase == "hangup":
            self._stop_transition_playback()
            self._enter_config(preserve_progress=False)
            return True
        return False

    def _ensure_mini_bar(self) -> MiniCallBar:
        if self._mini_bar is None:
            self._mini_bar = MiniCallBar(parent=None, theme_tokens=self._focus_theme_tokens())
            self._mini_bar.expandRequested.connect(self._exit_mini_mode)
            self._mini_bar.chatRequested.connect(self._request_chat_window)
            self._mini_bar.pauseRequested.connect(self._toggle_pause)
            self._mini_bar.hangupRequested.connect(self._start_hangup)
            self._apply_mini_bar_icons()
        return self._mini_bar

    def _enter_mini_mode(self) -> None:
        if self._phase in ("answering", "hangup"):
            return
        bar = self._ensure_mini_bar()
        self._update_mini_bar_state()
        if not bar.isVisible():
            x = self.x() + max(0, self.width() - bar.width() - 8)
            y = self.y() + 12
            bar.move(x, y)
            bar.show()
            bar.raise_()
        self._set_status_tray_visible(True)
        self.hide()

    def _exit_mini_mode(self) -> None:
        if self._mini_bar is not None and self._mini_bar.isVisible():
            self._mini_bar.hide()
        self._set_status_tray_visible(False)
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def _ensure_status_tray(self) -> QSystemTrayIcon | None:
        if self._status_tray is not None:
            return self._status_tray
        if self._shared_tray is not None:
            tray = self._shared_tray
        elif not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        else:
            tray = QSystemTrayIcon(self)
            tray.setToolTip("专注计时器（点击展开）")

            icon = self._load_icon(("icon.webp", "icon.png", "icon.PNG"))
            if icon is None or icon.isNull():
                root_icon = self._resources_dir / "icon.webp"
                if root_icon.exists():
                    icon = QIcon(str(root_icon))
            if icon is not None and not icon.isNull():
                tray.setIcon(icon)

        menu = QMenu()
        menu_font = menu.font()
        if menu_font.pointSize() > 0:
            menu_font.setPointSize(menu_font.pointSize() + 2)
        elif menu_font.pixelSize() > 0:
            menu_font.setPixelSize(menu_font.pixelSize() + 2)
        menu.setFont(menu_font)
        stage_action = QAction("当前环节：设置中 · 00:00", menu)
        stage_action.setEnabled(False)
        expand_action = QAction("展开计时器", menu)
        expand_action.triggered.connect(self._exit_mini_mode)
        chat_action = QAction("打开聊天窗口", menu)
        chat_action.triggered.connect(self._request_chat_window)
        hangup_action = QAction("结束通话", menu)
        hangup_action.triggered.connect(self._start_hangup)
        menu.addAction(stage_action)
        menu.addSeparator()
        menu.addAction(expand_action)
        menu.addAction(chat_action)
        menu.addSeparator()
        menu.addAction(hangup_action)
        if self._shared_tray is None:
            tray.setContextMenu(menu)
            tray.activated.connect(self._on_status_tray_activated)

        self._status_tray = tray
        self._status_tray_menu = menu
        self._status_tray_stage_action = stage_action
        self._update_status_tray_state()
        return tray

    def _set_status_tray_visible(self, visible: bool) -> None:
        tray = self._ensure_status_tray()
        if tray is None:
            return
        if visible:
            self._status_tray_active = True
            self._update_status_tray_state()
            if self._status_tray_menu is not None:
                tray.setContextMenu(self._status_tray_menu)
            tray.setToolTip(f"专注计时器：{self._current_stage_and_countdown()[0]} · {self._current_stage_and_countdown()[1]}")
            if self._shared_tray is None:
                tray.show()
        else:
            self._status_tray_active = False
            if self._shared_tray is not None:
                if self._shared_tray_default_menu is not None:
                    tray.setContextMenu(self._shared_tray_default_menu)
                tray.setToolTip(self._shared_tray_default_tooltip)
            else:
                tray.hide()

    def _on_status_tray_activated(self, reason) -> None:
        # Keep tray icon passive: no auto-expand on click.
        _ = reason

    def _current_stage_and_countdown(self) -> tuple[str, str]:
        stage = "通话中"
        if self._phase == "running":
            if self._is_paused:
                stage = "已暂停"
            elif self._is_break_phase:
                stage = "休息中"
            else:
                stage = "专注中"
        elif self._phase == "config":
            stage = "设置中"
        elif self._phase == "hangup":
            stage = "结束中"
        countdown = self.countdown_label.text() if hasattr(self, "countdown_label") else "00:00"
        return stage, countdown

    def call_stage_line(self) -> str | None:
        if not self._call_active:
            return None
        stage, countdown = self._current_stage_and_countdown()
        return f"{stage} · {countdown}"

    def _update_status_tray_state(self) -> None:
        stage, countdown = self._current_stage_and_countdown()
        line = f"{stage} · {countdown}"
        if self._status_tray_stage_action is not None:
            self._status_tray_stage_action.setText(f"当前环节：{line}")
        if self._status_tray is not None and (self._shared_tray is None or self._status_tray_active):
            self._status_tray.setToolTip(f"专注计时器：{line}")

    def _request_chat_window(self) -> None:
        self.chatRequested.emit()

    def _load_icon(self, candidates: tuple[str, ...]) -> QIcon | None:
        icon_dir = self._resources_dir / "icon"
        for name in candidates:
            candidate = icon_dir / name
            if candidate.exists():
                icon = QIcon(str(candidate))
                if not icon.isNull():
                    return icon
        return None

    def _apply_icon_to_button(
        self,
        button: QPushButton,
        tip: str,
        candidates: tuple[str, ...],
        size: int = 20,
    ) -> None:
        button.setToolTip(tip)
        icon = self._load_icon(candidates)
        if icon is None:
            return
        button.setIcon(icon)
        button.setText("")
        apply_icon_button_layout(button, icon_size=size, edge_padding=14, min_edge=30, set_fixed=False)

    def _apply_icon_buttons(self) -> None:
        self._apply_icon_to_button(
            self.chat_btn,
            "聊天窗口",
            ("chat.png", "chat.PNG", "jumpout.png"),
        )
        self._apply_icon_to_button(
            self.mini_btn,
            "悬浮条",
            ("exitfull.png", "expand.png", "fullscreen.jpeg"),
        )
        self._apply_icon_to_button(
            self.settings_btn,
            "设置",
            ("setting.png", "setting.PNG"),
        )
        self._apply_icon_to_button(
            self.return_btn,
            "返回当前进度",
            ("return.png", "return.PNG"),
        )
        self._apply_icon_to_button(
            self.exit_btn,
            "退出",
            ("exit", "exit.png", "exit.PNG", "exitfull.png"),
        )
        self._apply_icon_to_button(
            self.note_btn,
            "便利贴",
            ("post-it.png", "post-it.PNG", "notepad.png", "notepad.PNG"),
        )
        self._apply_icon_to_button(
            self.skip_btn,
            "跳过当前环节",
            ("skip.png", "skip.PNG", "next.png", "next.PNG"),
        )
        self._set_pause_button_state()

    def _apply_mini_bar_icons(self) -> None:
        if self._mini_bar is None:
            return
        self._apply_icon_to_button(
            self._mini_bar.chat_btn,
            "聊天窗口",
            ("chat.png", "chat.PNG", "jumpout.png"),
            size=18,
        )
        self._apply_icon_to_button(
            self._mini_bar.expand_btn,
            "展开",
            ("expand.png", "fullscreen.jpeg"),
            size=18,
        )
        self._apply_icon_to_button(
            self._mini_bar.exit_btn,
            "退出",
            ("exit", "exit.png", "exit.PNG", "exitfull.png"),
            size=18,
        )
        self._set_pause_button_state()

    def _set_pause_button_visual(self, button: QPushButton, *, paused: bool, mini: bool = False) -> None:
        icon_size = 18 if mini else 20
        if paused:
            tip = "继续"
            text = "继续"
            icon_names = ("play.png", "play.PNG", "ic_play.png")
        else:
            tip = "暂停"
            text = "暂停"
            icon_names = ("pause.png", "pause.PNG", "ic_pause.png")
        button.setToolTip(tip if mini else ("继续计时" if paused else "暂停计时"))
        icon = self._load_icon(icon_names)
        if icon is None:
            button.setIcon(QIcon())
            button.setProperty("iconOnly", False)
            button.setText(text)
            return
        button.setIcon(icon)
        button.setText("")
        apply_icon_button_layout(button, icon_size=icon_size, edge_padding=14, min_edge=30, set_fixed=False)

    def _set_pause_button_state(self) -> None:
        self._set_pause_button_visual(self.pause_btn, paused=self._is_paused, mini=False)
        if self._mini_bar is not None:
            self._set_pause_button_visual(self._mini_bar.pause_btn, paused=self._is_paused, mini=True)

    def _update_mini_bar_state(self) -> None:
        if self._mini_bar is None:
            self._update_status_tray_state()
            return
        self._mini_bar.pause_btn.setEnabled(self._phase == "running")
        if self._phase == "running":
            if self._is_paused:
                self._mini_bar.set_status("● 已暂停")
            elif self._is_break_phase:
                self._mini_bar.set_status("● 休息中")
            else:
                self._mini_bar.set_status("● 专注中")
        elif self._phase == "config":
            self._mini_bar.set_status("● 设置中")
        elif self._phase == "hangup":
            self._mini_bar.set_status("● 结束中")
        else:
            self._mini_bar.set_status("● 通话中")
        self._update_status_tray_state()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_ribbon_overlay"):
            self._ribbon_overlay.setGeometry(self.rect())
            if self._stack.currentWidget() is self._interactive_page:
                self._ribbon_overlay.raise_()
        self._sync_middle_height()
        self._render_frame()
        self._reposition_audio_popups_if_shown()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self.handle_escape_animation():
                event.accept()
                return
            # Keep ESC from closing dialogs/windows.
            event.accept()
            return
        super().keyPressEvent(event)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._reposition_audio_popups_if_shown()

    def _reposition_audio_popups_if_shown(self) -> None:
        if self._noise_popup.isVisible():
            self._reposition_noise_popup()
        if self._bgm_popup.isVisible():
            self._reposition_bgm_popup()

    def closeEvent(self, event: QCloseEvent) -> None:
        was_call_active = self._call_active
        self._tick.stop()
        self._stop_all_playback()
        self._call_active = False
        if self._mini_bar is not None and self._mini_bar.isVisible():
            self._mini_bar.close()
        self._set_status_tray_visible(False)
        if self._note_window is not None and self._note_window.isVisible():
            self._note_window.close()
        if self._noise_popup.isVisible():
            self._noise_popup.close()
        if self._bgm_popup.isVisible():
            self._bgm_popup.close()
        if was_call_active:
            self.callEnded.emit()
        super().closeEvent(event)
