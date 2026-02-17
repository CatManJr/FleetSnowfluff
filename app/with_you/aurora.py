"""Pink aurora bands with irregular cadence + white star glints."""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


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
            "left": random.uniform(0.00, 0.20),
            "right": random.uniform(0.00, 0.24),
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
            upper_base = (((1.0 - ratio) * aurora["left"]) + (ratio * aurora["right"])) * h
            wave_a = math.sin((ratio * aurora["freq"] * 2.0 * math.pi) + (t * self._flow_speed) + aurora["shift"])
            wave_b = math.sin((ratio * 6.8) - (t * self._drift_speed) + aurora["shift"] * 1.2)
            wave_c = math.sin((ratio * 11.4) + (t * (self._drift_speed * 0.6)) + aurora["shift"] * 2.1)
            wave_d = math.sin((ratio * 17.0) + (t * (self._drift_speed * 0.24)) + aurora["shift"] * 2.4)
            upper = upper_base + (
                aurora["amp"] * 0.42 * wave_a + 0.015 * wave_b + 0.010 * wave_c + 0.004 * wave_d
            ) * h
            thick_boost = (
                0.22 * (0.5 + 0.5 * math.sin((ratio * 3.4) + (t * 0.006) + aurora["shift"] * 0.8))
                + 0.14 * (0.5 + 0.5 * math.sin((ratio * 6.2) - (t * 0.003)))
                + 0.06 * math.sin((ratio * 11.0) + (t * 0.002))
            )
            thick_ratio = aurora["width"] * (0.58 + thick_boost)
            flow_field = (
                0.1
                + 0.5 * math.sin((ratio * 4.0) + (t * 0.010) + aurora["shift"] * 0.85)
                + 0.24 * math.sin((ratio * 8.6) - (t * 0.006) + aurora["shift"] * 1.7)
                + 0.14 * math.sin((ratio * 14.0) + (t * 0.004))
            )
            flow_norm = max(0.0, min(1.0, flow_field))
            thick = max(0.08 * h, ((0.10 + 0.70 * flow_norm) * h), thick_ratio * h)
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

        if len(self._thick_prev) != len(thick_values):
            self._thick_prev = thick_values[:]
        else:
            for i, current in enumerate(thick_values):
                self._thick_prev[i] = self._thick_prev[i] * 0.72 + current * 0.28
        thick_values = self._thick_prev[:]

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
                factor = 0.22 + 0.10 * math.exp(-exceed / soft_span)
                upper = sky_floor + exceed * factor
            if upper < top_min:
                upper = top_min
            constrained_upper.append(upper)

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
        path = QPainterPath()
        path.moveTo(upper_points[0][0], upper_points[0][1])
        for x, y in upper_points[1:]:
            path.lineTo(x, y)
        for x, y in reversed(lower_points):
            path.lineTo(x, y)
        path.closeSubpath()

        y_min = min(min(y for _, y in upper_points), min(y for _, y in lower_points))
        y_max = max(max(y for _, y in upper_points), max(y for _, y in lower_points))
        grad = QLinearGradient(0.0, y_min, 0.0, y_max)
        grad.setColorAt(0.00, QColor(255, 168, 230, 0))
        grad.setColorAt(0.18, QColor(255, 156, 224, int(alpha_core * 0.48)))
        grad.setColorAt(0.30, QColor(212, 178, 198, int(alpha_core * 0.76)))
        grad.setColorAt(0.56, QColor(173, 255, 204, int(alpha_core * 0.92)))
        grad.setColorAt(0.75, QColor(56, 229, 224, int(alpha_core * 0.57)))
        grad.setColorAt(1.00, QColor(29, 190, 216, 0))
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
