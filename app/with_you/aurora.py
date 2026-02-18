"""
极光：从 0 实现。
一条固定的下边界曲线，沿下边界布置竖线，类似录音波形的流动动态。
"""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QWidget

# 配色：红-玫红-粉-绿-深绿（改极光为自定义色系）
_AURORA_COLORS = [
    (255, 76, 76),     # 红色 Red
    (232, 70, 125),    # 玫红 Rose Red
    (255, 186, 243),   # 粉色 Pink
    (113, 248, 206),   # 绿色 Green
    (4, 153, 76),      # 深绿色 Dark Green
]

# 夜空背景渐变（自上而下）
_NIGHT_SKY_TOP = (8, 12, 28)       # 顶部：深蓝黑
_NIGHT_SKY_MID = (18, 25, 52)      # 中上
_NIGHT_SKY_LOWER = (28, 38, 72)    # 中下
_NIGHT_SKY_BOTTOM = (35, 45, 85)   # 底部：略亮、偏蓝

# 极光范围（可改这里）
# 下边界基准：水平线高度（北半球极光弧倾斜与观测方向有关，无固定左高/右高，这里取中性水平）
AURORA_BASE_TOP = 0.58   # 基准线占画面高度比例（0.5~0.7 均可）
AURORA_BASE_SLOPE = 0.0  # 左右倾斜：0=水平；>0 右端更低（原 0.28）；<0 左端更低
AURORA_RAY_HEIGHT = 0.65  # 竖线最大高度占画面比例（_stroke_height 的 base_h）
AURORA_X_MARGIN_LEFT = 0.01  # 水平范围：左边界（相对宽度，负值表示超出左边）
AURORA_X_MARGIN_RIGHT = 0.99  # 水平范围：右边界（相对宽度，>1 表示超出右边）

# 变化频率（可改这里，<1 更慢/更疏）
AURORA_TIME_FREQ = 0.2  # 时间：波动速度（1=原速）
AURORA_SPATIAL_FREQ = 0.6  # 空间：沿 x 的波浪疏密（1=原样，越小波浪越少）

# 竖线明带：窄→调大粗细；密→减小根数
AURORA_STROKE_WIDTH = 8   # 竖线/明带粗细（越大越宽，如 12～18）
AURORA_STROKE_COUNT = 316  # 竖线根数（越小越疏，如 120～180）

# 竖线间距分布（决定疏密沿 x 怎么变）
AURORA_SPACING_AMP1 = 0.05   # 第一层扰动振幅（越大疏密差异越大）
AURORA_SPACING_AMP2 = 0.01   # 第二层扰动振幅
AURORA_SPACING_FREQ1 = 2   # 第一层频率（整屏约几个疏密周期）
AURORA_SPACING_FREQ2 = 2.5   # 第二层频率
AURORA_SPACING_SMOOTH = 3    # 间距平滑半径（0=不平滑，越大变化越缓、越均匀， 正整数）

# 流星：一颗颗，粉色轨迹，朝左下飞，半分钟一次
METEOR_SPEED = 2.2
METEOR_LENGTH = 200
METEOR_PEN_WIDTH = 3
METEOR_INTERVAL_TICKS = 600  # 33ms 一 tick，约 20 秒
_METEOR_PINK = (255, 182, 213)  # 粉色轨迹

class Aurora(QWidget):
    """极光：下边界曲线 + 沿边界竖线 + 波形流动。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # 不挡住下方按钮：鼠标事件穿透、不抢焦点
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._t = 0.0
        self._star_count = 72
        self._stars: list[dict[str, float]] = []
        self._meteor: dict[str, float] | None = None
        self._meteor_next_spawn = 0.0
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
        self._update_meteors()
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.trigger_meteor_now()

    def trigger_meteor_now(self) -> None:
        """立即出现一颗流星，下一颗隔 30 秒。进入（极光）页面时调用。"""
        self._meteor = None
        self._spawn_meteor()
        self._meteor_next_spawn = self._t + METEOR_INTERVAL_TICKS

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._seed_stars()
        if self._meteor is None and self._meteor_next_spawn <= self._t:
            self._meteor_next_spawn = self._t + METEOR_INTERVAL_TICKS * 0.3

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

    def _spawn_meteor(self) -> None:
        w = max(1, self.width())
        h = max(1, self.height())
        if w < 40 or h < 40:
            return
        # 从右上角飞出，朝左下飞
        self._meteor = {
            "x": w + METEOR_LENGTH * 0.3,
            "y": -METEOR_LENGTH * 0.4,
            "len": METEOR_LENGTH * (0.8 + random.random() * 0.4),
            "speed": METEOR_SPEED,
            "alpha": 255,
        }

    def _update_meteors(self) -> None:
        w = max(1, self.width())
        h = max(1, self.height())
        if w < 40 or h < 40:
            return
        if self._meteor is None:
            if self._t >= self._meteor_next_spawn:
                self._spawn_meteor()
            return
        m = self._meteor
        # 从顶部朝左下飞：x 减，y 增
        m["x"] -= m["speed"] * 0.85
        m["y"] += m["speed"] * 0.53
        if m["x"] < -METEOR_LENGTH * 2 or m["y"] > h + METEOR_LENGTH:
            self._meteor = None
            self._meteor_next_spawn = self._t + METEOR_INTERVAL_TICKS

    def _lower_boundary(self, x: float, w: float, h: float) -> float:
        """下边界：大波打底 + 多几条中频波，形成多个 S 型。"""
        nx = x / max(1, w)  # 归一化 x in [0, 1]，左→右
        t = self._t * AURORA_TIME_FREQ
        base = h * (AURORA_BASE_TOP + AURORA_BASE_SLOPE * nx)
        sf = AURORA_SPATIAL_FREQ
        # 大波长打底（改 0.068、0.052 可调大波幅度，越大起伏越大）
        wave1 = 0.08 * h * math.sin(0.9 * sf * math.pi * nx - t * 0.03)
        wave2 = 0.07 * h * math.sin(1.4 * sf * math.pi * (nx + 0.2) + t * 0.02)
        # 多几条中频波 → 多几个 S 型（约 2~4 个周期跨屏）
        wave3 = 0.032 * h * math.sin(2.2 * sf * math.pi * nx + t * 0.025)
        wave4 = 0.026 * h * math.sin(2.8 * sf * math.pi * (nx - 0.15) - t * 0.02)
        wave5 = 0.02 * h * math.sin(3.5 * sf * math.pi * nx + 0.4 + t * 0.03)
        wave6 = 0.016 * h * math.sin(4.0 * sf * math.pi * (nx + 0.1) - t * 0.018)
        center_peak = 0.08 * h * math.exp(-((nx - 0.5) ** 2) / 0.12)
        center_peak += 0.02 * h * math.sin(0.8 * sf * math.pi * nx + t * 0.025)
        envelope = 0.025 * h * math.sin(0.6 * sf * math.pi * nx - 0.2 - t * 0.02)
        return base + wave1 + wave2 + wave3 + wave4 + wave5 + wave6 + center_peak + envelope

    def _stroke_gradient(
        self, y_top: float, y_bottom: float, x: float, peak_alpha: int
    ) -> QLinearGradient:
        """单条竖线的辉光渐变：光带处（y_bottom）最亮，向上渐隐。peak_alpha 为光带处透明度 [96,196]。"""
        grad = QLinearGradient(x, y_top, x, y_bottom)
        # 自上而下：完全透明 -> 极淡 -> 渐亮 -> 光带处最亮（peak_alpha）
        scale = peak_alpha / 160
        grad.setColorAt(0.00, QColor(_AURORA_COLORS[0][0], _AURORA_COLORS[0][1], _AURORA_COLORS[0][2], 20))
        grad.setColorAt(0.10, QColor(_AURORA_COLORS[1][0], _AURORA_COLORS[1][1], _AURORA_COLORS[1][2], int(58 * scale)))
        grad.setColorAt(0.45, QColor(_AURORA_COLORS[2][0], _AURORA_COLORS[2][1], _AURORA_COLORS[2][2], int(85 * scale)))
        grad.setColorAt(0.65, QColor(_AURORA_COLORS[3][0], _AURORA_COLORS[3][1], _AURORA_COLORS[3][2], int(120 * scale)))
        grad.setColorAt(0.90, QColor(_AURORA_COLORS[4][0], _AURORA_COLORS[4][1], _AURORA_COLORS[4][2], int(160 * scale)))
        grad.setColorAt(1.00, QColor(_AURORA_COLORS[4][0], _AURORA_COLORS[4][1], _AURORA_COLORS[4][2], min(196, peak_alpha)))
        return grad

    def _stroke_height(self, x: float, w: float, h: float) -> float:
        """竖线高度：上边界狂野——多频率、大振幅变化，形成参差尖峰。"""
        nx = x / max(1, w)
        t = self._t
        base_h = h * AURORA_RAY_HEIGHT
        tf, sf = AURORA_TIME_FREQ, AURORA_SPATIAL_FREQ
        # 多组高、中、低频叠加，振幅拉大，让上缘起伏剧烈
        a = 0.30 + 0.28 * math.sin(4.0 * sf * math.pi * nx - t * 0.04 * tf)
        a += 0.22 * math.sin(7.2 * sf * math.pi * nx + t * 0.03 * tf)
        a += 0.18 * math.sin(12.0 * sf * math.pi * nx - t * 0.025 * tf)
        a += 0.12 * math.sin(2.2 * sf * math.pi * nx + t * 0.05 * tf)
        a += 0.10 * math.sin(15.0 * sf * math.pi * (nx - 0.1) + t * 0.02 * tf)
        a += 0.06 * math.sin(8.5 * sf * math.pi * (nx + 0.3) - t * 0.035 * tf)
        # 归一到 [0.18, 1.0]，拉大高低差，上边界更狂野
        mod = 0.18 + 0.82 * (0.5 + 0.5 * max(-1, min(1, a)))
        return base_h * mod

    def paintEvent(self, _event) -> None:
        w = float(max(1, self.width()))
        h = float(max(1, self.height()))
        if w < 40 or h < 40:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 0) 夜空渐变色背景
        bg = QLinearGradient(0.0, 0.0, 0.0, h)
        bg.setColorAt(0.0, QColor(*_NIGHT_SKY_TOP))
        bg.setColorAt(0.35, QColor(*_NIGHT_SKY_MID))
        bg.setColorAt(0.7, QColor(*_NIGHT_SKY_LOWER))
        bg.setColorAt(1.0, QColor(*_NIGHT_SKY_BOTTOM))
        painter.fillRect(0, 0, int(w), int(h), QBrush(bg))

        t = self._t
        n_samples = AURORA_STROKE_COUNT
        x_start = w * AURORA_X_MARGIN_LEFT
        x_end = w * AURORA_X_MARGIN_RIGHT

        # 1) 沿下边界布置竖线：粗细、间距见顶部 AURORA_STROKE_*
        painter.setPen(Qt.PenStyle.NoPen)
        core_pen_w = AURORA_STROKE_WIDTH
        tf = AURORA_TIME_FREQ
        tt = self._t * 0.02 * tf
        # 间距分布：raw 用正弦扰动，再算 dx、平滑，得到 x_norm_list（见顶部 AURORA_SPACING_*）
        raw = []
        for i in range(n_samples + 1):
            t = i / n_samples
            x = t + AURORA_SPACING_AMP1 * math.sin(2.0 * math.pi * AURORA_SPACING_FREQ1 * t + tt)
            x += AURORA_SPACING_AMP2 * math.sin(2.0 * math.pi * AURORA_SPACING_FREQ2 * t - tt * 0.7)
            raw.append(max(0.0, min(1.0, x)))
        dx = [raw[i + 1] - raw[i] for i in range(n_samples)]
        r = int(max(0, AURORA_SPACING_SMOOTH))
        dx_smooth = []
        for i in range(n_samples):
            lo = max(0, i - r)
            hi = min(n_samples, i + r + 1)
            span = hi - lo
            dx_smooth.append(sum(dx[lo:hi]) / span if span > 0 else dx[i])
        total = sum(dx_smooth)
        if total < 1e-6:
            total = 1.0
        x_norm_list = [0.0]
        for i in range(n_samples):
            x_norm_list.append(x_norm_list[-1] + dx_smooth[i] / total)
        x_norm_list[-1] = 1.0  # 避免浮点误差
        # 景深：先算极光带上下范围，再按竖线位置算“远近”
        stroke_data = []
        for i in range(n_samples + 1):
            x_norm = x_norm_list[i]
            x = x_start + (x_end - x_start) * x_norm
            y_bottom = self._lower_boundary(x, w, h)
            stroke_h = self._stroke_height(x, w, h)
            y_top = y_bottom - stroke_h
            # 不把 y_top 截断为 0，保留真实顶端，绘制时由裁剪处理，避免“平顶”
            stroke_data.append((x, y_top, y_bottom))
        # 最大波峰不越过 1/2 高度：若下边界最高点超过中线则整体下移（不硬截断）
        min_y_bottom = min(s[2] for s in stroke_data)
        half_h = h * 0.5
        shift = max(0.0, half_h - min_y_bottom)
        if shift > 0:
            stroke_data = [(x, y_top + shift, y_bottom + shift) for (x, y_top, y_bottom) in stroke_data]
        y_band_top = min(s[1] for s in stroke_data)
        y_band_bottom = max(s[2] for s in stroke_data)
        band_h = max(1e-6, y_band_bottom - y_band_top)

        for (x, y_top, y_bottom) in stroke_data:
            # 景深：上缘=远（暗、细），下缘=近（亮、粗）
            y_center = (y_top + y_bottom) * 0.5
            depth = (y_center - y_band_top) / band_h
            depth = max(0.0, min(1.0, depth))
            depth_bright = 0.5 + 0.5 * depth  # 远 0.5x ~ 近 1x
            depth_width = 0.65 + 0.35 * depth  # 远更细、近更粗
            peak_alpha = int(96 * depth_bright)
            pen_w = core_pen_w * depth_width
            grad = self._stroke_gradient(y_top, y_bottom, x, max(40, peak_alpha))
            for pass_alpha, pass_width in [(0.10, 2.0), (0.28, 1.0)]:
                pen = QPen(QBrush(grad), pen_w * pass_width)
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                painter.setPen(pen)
                painter.setOpacity(pass_alpha * depth_bright)
                painter.drawLine(int(x), int(y_bottom), int(x), int(y_top))
            painter.setOpacity(1.0)
            painter.setOpacity(0.82 * depth_bright)
            pen = QPen(QBrush(grad), pen_w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(int(x), int(y_bottom), int(x), int(y_top))
            painter.setOpacity(1.0)
        painter.setPen(Qt.PenStyle.NoPen)

        # 2) 星星：正常白色、四芒星（Screen 混合避免被极光压黑）
        if not self._stars:
            self._seed_stars()
        old_mode = painter.compositionMode()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for s in self._stars:
            a = int(s["alpha"] * (0.6 + 0.4 * math.sin(t * 0.05 + s["phase"]) * s["twinkle"]))
            if a < 10:
                continue
            cx, cy = s["x"], s["y"]
            r = max(1.0, s["r"])
            painter.setPen(QPen(QColor(255, 255, 255, a), max(1, int(r * 0.5))))
            for angle in (0.0, math.pi / 2, math.pi, math.pi * 1.5):
                ex = cx + r * math.cos(angle)
                ey = cy + r * math.sin(angle)
                painter.drawLine(QPointF(cx, cy), QPointF(ex, ey))
        painter.setCompositionMode(old_mode)

        # 3) 流星：头白尾粉、尾迹渐隐（头在左前，尾在右后）
        if self._meteor is not None:
            m = self._meteor
            xh, yh = m["x"], m["y"]
            L = m["len"]
            xt = xh + L * 0.85
            yt = yh - L * 0.53
            grad = QLinearGradient(xh, yh, xt, yt)
            pr, pg, pb = _METEOR_PINK
            grad.setColorAt(0.0, QColor(255, 255, 255, 255))
            grad.setColorAt(0.15, QColor(255, 250, 255, 240))
            grad.setColorAt(0.4, QColor(pr, pg, pb, 200))
            grad.setColorAt(0.7, QColor(pr, pg, pb, 100))
            grad.setColorAt(1.0, QColor(pr, pg, pb, 0))
            painter.setPen(QPen(QBrush(grad), METEOR_PEN_WIDTH))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QPointF(xh, yh), QPointF(xt, yt))
        painter.setPen(Qt.PenStyle.NoPen)
