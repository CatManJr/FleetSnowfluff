"""
极光：从 0 实现。
一条固定的下边界曲线，沿下边界布置竖线，类似录音波形的流动动态。
"""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

# 配色：上粉下绿
_PINK = (255, 168, 230)
_GREEN = (83, 229, 166)

# 极光范围（可改这里）
AURORA_BASE_TOP = 0.50  # 下边界基准：顶部占画面高度比例（越小越靠上）
AURORA_BASE_BOTTOM = 0.28  # 下边界基准：从左到右再下降的比例（base = h * (AURORA_BASE_TOP + AURORA_BASE_BOTTOM * nx)）
AURORA_RAY_HEIGHT = 0.70  # 竖线最大高度占画面比例（_stroke_height 的 base_h）
AURORA_X_MARGIN_LEFT = -0.0  # 水平范围：左边界（相对宽度，负值表示超出左边）
AURORA_X_MARGIN_RIGHT = 1.0  # 水平范围：右边界（相对宽度，>1 表示超出右边）

# 变化频率（可改这里，<1 更慢/更疏）
AURORA_TIME_FREQ = 0.1  # 时间：竖线高度、线宽随时间的波动速度（1=原速）
AURORA_SPATIAL_FREQ = 1  # 空间：下边界和竖线沿 x 的波浪疏密（1=原样，越小波浪越少）

class Aurora(QWidget):
    """极光：下边界曲线 + 沿边界竖线 + 波形流动。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self._t = 0.0
        self._star_count = 72
        self._stars: list[dict[str, float]] = []
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    def set_animating(self, enabled: bool) -> None:
        if enabled:
            if not self._timer.isActive():
                self._timer.start()
            return
        self._timer.stop()

    def _on_tick(self) -> None:
        self._t += 1.0
        self._update_stars()
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._seed_stars()

    def _seed_stars(self) -> None:
        w = max(1, self.width())
        h = max(1, self.height())
        if w < 40 or h < 40:
            self._stars = []
            return
        self._stars = []
        for _ in range(self._star_count):
            self._stars.append({
                "x": random.uniform(0, w),
                "y": random.uniform(0, h),
                "vy": 0.2 + random.random() * 0.6,
                "r": 0.5 + random.random() * 1.5,
                "alpha": 80 + random.random() * 140,
                "twinkle": 0.8 + random.random() * 1.5,
                "phase": random.uniform(0, math.pi * 2),
            })

    def _update_stars(self) -> None:
        if not self._stars:
            return
        w = max(1, self.width())
        h = max(1, self.height())
        for s in self._stars:
            s["y"] += s["vy"]
            s["x"] += 0.2 * math.sin(self._t * 0.01 + s["phase"])
            if s["y"] > h + 10:
                s["y"] = -5
                s["x"] = random.uniform(0, w)

    def _lower_boundary(self, x: float, w: float, h: float) -> float:
        """与参考图一致的静态复杂下边界：左帘下弯、中帘主峰、右帘波浪。"""
        nx = x / max(1, w)  # 归一化 x in [0, 1]，左→右
        base = h * (AURORA_BASE_TOP + AURORA_BASE_BOTTOM * nx)
        sf = AURORA_SPATIAL_FREQ
        # 左帘：从左上向内弯下（左侧略高，向右下弯）
        left_curtain = 0.06 * h * (1.0 - nx) * math.sin(2.5 * sf * math.pi * nx)
        # 中帘：明显主峰（中心处下边界下凸，形成一条主光带峰）
        center_peak = 0.12 * h * math.exp(-((nx - 0.48) ** 2) / 0.08)
        center_peak += 0.04 * h * math.sin(5.0 * sf * math.pi * (nx - 0.1))
        # 右帘：波浪形（多频率叠加，有机感）
        right_curtain = 0.05 * h * math.sin(7.0 * sf * math.pi * nx + 0.3)
        right_curtain += 0.03 * h * math.sin(11.0 * sf * math.pi * nx - 0.5)
        right_curtain += 0.025 * h * math.sin(4.0 * sf * math.pi * (nx - 0.2))
        # 整体再叠一层大波长起伏
        envelope = 0.035 * h * math.sin(2.0 * sf * math.pi * nx - 0.2)
        envelope += 0.02 * h * math.sin(3.3 * sf * math.pi * nx + 0.7)
        return base + left_curtain + center_peak + right_curtain + envelope

    def _stroke_gradient(
        self, y_top: float, y_bottom: float, x: float, peak_alpha: int
    ) -> QLinearGradient:
        """单条竖线的辉光渐变：光带处（y_bottom）最亮，向上渐隐。peak_alpha 为光带处透明度 [96,196]。"""
        grad = QLinearGradient(x, y_top, x, y_bottom)
        # 自上而下：完全透明 -> 极淡 -> 渐亮 -> 光带处最亮（peak_alpha）
        scale = peak_alpha / 160
        grad.setColorAt(0.00, QColor(_PINK[0], _PINK[1], _PINK[2], 20))
        grad.setColorAt(0.20, QColor(_PINK[0], _PINK[1], _PINK[2], int(58 * scale)))
        grad.setColorAt(0.45, QColor(_PINK[0], _PINK[1], _PINK[2], int(85 * scale)))
        grad.setColorAt(0.65, QColor(_GREEN[0], _GREEN[1], _GREEN[2], int(120 * scale)))
        grad.setColorAt(0.80, QColor(_GREEN[0], _GREEN[1], _GREEN[2], int(160 * scale)))
        grad.setColorAt(1.00, QColor(_GREEN[0], _GREEN[1], _GREEN[2], min(196, peak_alpha)))
        return grad

    def _stroke_height(self, x: float, w: float, h: float) -> float:
        """竖线高度：不整齐地变化（多频率叠加 + 轻微随机感）。"""
        nx = x / max(1, w)
        t = self._t
        base_h = h * AURORA_RAY_HEIGHT
        tf, sf = AURORA_TIME_FREQ, AURORA_SPATIAL_FREQ
        # 多组不同频率、相位，使高度参差不齐
        a = 0.35 + 0.25 * math.sin(4.0 * sf * math.pi * nx - t * 0.04 * tf)
        a += 0.18 * math.sin(6.7 * sf * math.pi * nx + t * 0.03 * tf)
        a += 0.12 * math.sin(11.2 * sf * math.pi * nx - t * 0.02 * tf)
        a += 0.08 * math.sin(2.3 * sf * math.pi * nx + t * 0.05 * tf)
        # 归一到 [0.25, 1.0] 使长短不一
        mod = 0.25 + 0.75 * (0.5 + 0.5 * max(-1, min(1, a)))
        return base_h * mod

    def paintEvent(self, _event) -> None:
        w = float(max(1, self.width()))
        h = float(max(1, self.height()))
        if w < 40 or h < 40:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        t = self._t
        n_samples = 100  # 竖线数量，少一些更柔和、不刺眼
        x_start = w * AURORA_X_MARGIN_LEFT
        x_end = w * AURORA_X_MARGIN_RIGHT

        # 1) 沿下边界布置竖线，带辉光：多层绘制（先粗淡再细亮）+ 单条竖线自上而下渐隐
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(n_samples + 1):
            x = x_start + (x_end - x_start) * (i / n_samples)
            y_bottom = self._lower_boundary(x, w, h)
            stroke_h = self._stroke_height(x, w, h)
            y_top = y_bottom - stroke_h
            if y_top < 0:
                y_top = 0
            core_pen_w = 1.8 + 0.8 * math.sin(
                3.0 * AURORA_SPATIAL_FREQ * x / w + t * 0.02 * AURORA_TIME_FREQ
            )
            peak_alpha = random.randint(70, 160)
            grad = self._stroke_gradient(y_top, y_bottom, x, peak_alpha)
            # 辉光层：降低不透明度与层数，避免刺眼
            for pass_alpha, pass_width in [(0.04, 10.0), (0.10, 4.0), (0.28, 2.0)]:
                pen = QPen(QBrush(grad), core_pen_w * pass_width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.setOpacity(pass_alpha)
                painter.drawLine(int(x), int(y_bottom), int(x), int(y_top))
            painter.setOpacity(1.0)
            # 核心亮线（整体压暗一点）
            painter.setOpacity(0.82)
            pen = QPen(QBrush(grad), core_pen_w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(int(x), int(y_bottom), int(x), int(y_top))
            painter.setOpacity(1.0)
        painter.setPen(Qt.PenStyle.NoPen)

        # 2) 星星
        if not self._stars:
            self._seed_stars()
        twinkle = 0.5 + 0.5 * math.sin(t * 0.055)
        for s in self._stars:
            a = int(s["alpha"] * (0.6 + 0.4 * math.sin(t * 0.05 + s["phase"]) * s["twinkle"]))
            if a < 10:
                continue
            painter.setBrush(QColor(247, 252, 255, a))
            painter.setPen(Qt.PenStyle.NoPen)
            r = max(1, int(s["r"]))
            painter.drawEllipse(QPoint(int(s["x"]), int(s["y"])), r, r)
