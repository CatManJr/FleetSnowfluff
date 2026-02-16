from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QPushButton, QSizePolicy

from .design_tokens import brand_palette

FLUENT_AVAILABLE = False

try:
    from qfluentwidgets import PushButton as _FluentPushButton
    from qfluentwidgets import Theme, setTheme, setThemeColor
    from qfluentwidgets import FluentIcon as FIF

    FLUENT_AVAILABLE = True
except Exception:  # noqa: BLE001
    _FluentPushButton = QPushButton
    Theme = None
    setTheme = None
    setThemeColor = None
    FIF = None


class FPushButton(_FluentPushButton):
    """Unified button type with Fluent fallback."""


def init_fluent_theme() -> None:
    if not FLUENT_AVAILABLE or setTheme is None or setThemeColor is None or Theme is None:
        return
    p = brand_palette()
    try:
        setTheme(Theme.AUTO)
        setThemeColor(QColor(p["accent_blue"]))
    except Exception:  # noqa: BLE001
        # Theme setup should never block window construction.
        return


def fluent_icon(*names: str) -> QIcon | None:
    if not FLUENT_AVAILABLE or FIF is None:
        return None
    for name in names:
        try:
            icon_enum = getattr(FIF, name)
        except AttributeError:
            continue
        try:
            icon = icon_enum.icon()
        except Exception:  # noqa: BLE001
            continue
        if isinstance(icon, QIcon) and not icon.isNull():
            return icon
    return None


def apply_icon_button_layout(
    button: QPushButton,
    *,
    icon_size: int,
    edge_padding: int = 12,
    min_edge: int = 28,
    set_fixed: bool = True,
) -> None:
    edge = max(icon_size + edge_padding, min_edge)
    button.setProperty("iconOnly", True)
    if set_fixed:
        button.setMinimumSize(edge, edge)
        button.setMaximumSize(edge, edge)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    button.setIconSize(QSize(icon_size, icon_size))
    button.setStyleSheet("padding: 0px; margin: 0px; text-align: center;")


def rounded_icon(icon: QIcon, *, edge: int = 18, radius_ratio: float = 0.28) -> QIcon:
    """Return a rounded-corner icon variant for compact surfaces (e.g. tray)."""
    if icon.isNull() or edge <= 0:
        return icon
    source = icon.pixmap(QSize(edge, edge))
    if source.isNull():
        return icon

    scaled = source.scaled(
        edge,
        edge,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    canvas = QPixmap(edge, edge)
    canvas.fill(Qt.GlobalColor.transparent)
    radius = max(3.0, edge * radius_ratio)

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    clip = QPainterPath()
    clip.addRoundedRect(0.5, 0.5, float(edge - 1), float(edge - 1), radius, radius)
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    return QIcon(canvas)
