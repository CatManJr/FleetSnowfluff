from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QCoreApplication, QObject, QTimer
from PySide6.QtGui import QFont, QGuiApplication, QScreen
from PySide6.QtWidgets import QApplication

_BASE_DPI = 96.0
_MIN_SCALE = 0.85
_MAX_SCALE = 2.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def screen_scale(screen: QScreen | None) -> float:
    if screen is None:
        return 1.0
    try:
        logical_dpi = float(screen.logicalDotsPerInch())
    except RuntimeError:
        # Screen can be destroyed during monitor/window transitions.
        return 1.0
    if logical_dpi <= 0:
        try:
            dpr = float(screen.devicePixelRatio()) or 1.0
        except RuntimeError:
            return 1.0
        return _clamp(dpr, _MIN_SCALE, _MAX_SCALE)
    return _clamp(logical_dpi / _BASE_DPI, _MIN_SCALE, _MAX_SCALE)


def current_app_scale(app: QCoreApplication | None) -> float:
    if app is None:
        primary = QGuiApplication.primaryScreen()
        return screen_scale(primary)
    raw = app.property("ui_scale_factor")
    if isinstance(raw, (int, float)):
        return _clamp(float(raw), _MIN_SCALE, _MAX_SCALE)
    primary = QGuiApplication.primaryScreen()
    return screen_scale(primary)


def px(value: int, scale: float) -> int:
    return max(1, int(round(value * scale)))


class AppScaleController(QObject):
    """
    Keeps app font in sync with active screen DPI and exposes scale via app property.
    """

    def __init__(self, app: QApplication, base_font: QFont) -> None:
        super().__init__(app)
        self._app = app
        self._base_font = QFont(base_font)
        self._base_point_size = float(base_font.pointSizeF() if base_font.pointSizeF() > 0 else 12.0)
        self._restylers: list[Callable[[float], None]] = []
        self._refresh_scheduled = False
        self._bind_screen_signals()
        app.screenAdded.connect(self._on_screen_added)
        app.screenRemoved.connect(self._schedule_refresh)
        app.focusWindowChanged.connect(self._schedule_refresh)
        self._refresh_now()

    def register_restyler(self, restyler: Callable[[float], None]) -> None:
        self._restylers.append(restyler)
        restyler(current_app_scale(self._app))

    def _bind_screen_signals(self) -> None:
        for screen in self._app.screens():
            screen.logicalDotsPerInchChanged.connect(self._schedule_refresh)
            screen.geometryChanged.connect(self._schedule_refresh)

    def _on_screen_added(self, screen: QScreen) -> None:
        screen.logicalDotsPerInchChanged.connect(self._schedule_refresh)
        screen.geometryChanged.connect(self._schedule_refresh)
        self._schedule_refresh()

    def _schedule_refresh(self, *_args) -> None:
        if self._refresh_scheduled:
            return
        self._refresh_scheduled = True
        QTimer.singleShot(0, self._refresh_now)

    def _pick_reference_screen(self) -> QScreen | None:
        active = self._app.activeWindow()
        if active is not None and active.windowHandle() is not None:
            screen = active.windowHandle().screen()
            if screen is not None:
                return screen
        return QGuiApplication.primaryScreen()

    def _refresh_now(self) -> None:
        self._refresh_scheduled = False
        try:
            scale = screen_scale(self._pick_reference_screen())
        except RuntimeError:
            # Defensive fallback against transient Qt object lifetimes.
            scale = 1.0
        self._app.setProperty("ui_scale_factor", scale)
        scaled_font = QFont(self._base_font)
        scaled_font.setPointSizeF(self._base_point_size * scale)
        self._app.setFont(scaled_font)
        for restyler in self._restylers:
            restyler(scale)


def install_app_scale_controller(app: QApplication, base_font: QFont) -> AppScaleController:
    controller = AppScaleController(app, base_font)
    app.setProperty("ui_scale_controller", controller)
    return controller
