"""Floating mini player bar with playlist and volume popups."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QSettings, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.utils.fluent_compat import apply_icon_button_layout
from app.utils.ui_scale import current_app_scale, px

from . import styles
from .marquee_label import MarqueeLabel
from .mini_playlist_panel import MiniPlaylistPanel
from .utils import load_icon_from_candidates, mirrored_icon


class MiniPlayerBar(QDialog):
    def __init__(
        self,
        toggle_play_pause_fn,
        play_prev_fn,
        play_next_fn,
        restore_main_fn,
        current_track_fn,
        list_tracks_fn,
        play_track_fn,
        extract_track_info_fn,
        is_playing_fn,
        get_position_ms_fn,
        get_duration_ms_fn,
        seek_position_ms_fn,
        get_volume_percent_fn,
        set_volume_percent_fn,
        single_repeat_getter=None,
        toggle_single_repeat_fn=None,
        icon_dir: Path | None = None,
    ) -> None:
        super().__init__(None)
        self._toggle_play_pause_fn = toggle_play_pause_fn
        self._play_prev_fn = play_prev_fn
        self._play_next_fn = play_next_fn
        self._restore_main_fn = restore_main_fn
        self._current_track_fn = current_track_fn
        self._list_tracks_fn = list_tracks_fn
        self._play_track_fn = play_track_fn
        self._extract_track_info_fn = extract_track_info_fn
        self._is_playing_fn = is_playing_fn
        self._get_position_ms_fn = get_position_ms_fn
        self._get_duration_ms_fn = get_duration_ms_fn
        self._seek_position_ms_fn = seek_position_ms_fn
        self._get_volume_percent_fn = get_volume_percent_fn
        self._set_volume_percent_fn = set_volume_percent_fn
        self._single_repeat_getter = single_repeat_getter or (lambda: False)
        self._toggle_single_repeat_fn = toggle_single_repeat_fn or (lambda: None)
        self._icon_dir = icon_dir
        self._settings = QSettings("FleetSnowfluff", "MusicWindow")
        self._drag_offset: QPoint | None = None
        self._has_custom_pos = False
        self._is_scrubbing = False
        self._icons: dict[str, QIcon] = {}

        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("飞行雪绒电台 - Mini")
        self.setWindowOpacity(1.0)
        self.resize(360, 60)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.container = QFrame(self)
        self.container.setObjectName("miniCard")
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(10, 8, 10, 8)
        container_layout.setSpacing(5)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(4)

        self.track_label = MarqueeLabel("-", self.container)
        self.track_label.setObjectName("miniTitle")
        self.track_label.setFixedWidth(78)

        self.prev_button = QPushButton("")
        self.prev_button.setObjectName("miniBtn")
        self.prev_button.setToolTip("上一首")
        self.prev_button.clicked.connect(self._on_prev_clicked)

        self.play_button = QPushButton("")
        self.play_button.setObjectName("miniBtn")
        self.play_button.setToolTip("播放 / 暂停")
        self.play_button.clicked.connect(self._on_toggle_clicked)

        self.next_button = QPushButton("")
        self.next_button.setObjectName("miniBtn")
        self.next_button.setToolTip("下一首")
        self.next_button.clicked.connect(self._on_next_clicked)

        self.repeat_button = QPushButton("")
        self.repeat_button.setObjectName("miniBtn")
        self.repeat_button.setToolTip("单曲循环")
        self.repeat_button.clicked.connect(self._on_repeat_clicked)

        self.playlist_button = QPushButton("")
        self.playlist_button.setObjectName("miniBtn")
        self.playlist_button.setToolTip("播放列表")
        self.playlist_button.clicked.connect(self._show_playlist_menu)

        self.volume_button = QPushButton("")
        self.volume_button.setObjectName("miniBtn")
        self.volume_button.setToolTip("音量")
        self.volume_button.clicked.connect(self._toggle_volume_popup)

        self.restore_button = QPushButton("")
        self.restore_button.setObjectName("miniBtnExpand")
        self.restore_button.setToolTip("展开到完整播放器")
        self.restore_button.clicked.connect(self._restore_main_fn)

        self.volume_popup = QWidget(self)
        self.volume_popup.setObjectName("miniVolumePopup")
        self.volume_popup.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        volume_popup_layout = QVBoxLayout(self.volume_popup)
        volume_popup_layout.setContentsMargins(8, 8, 8, 8)
        volume_popup_layout.setSpacing(6)
        self.volume_value_label = QLabel("70%")
        self.volume_value_label.setObjectName("miniVolumeValue")
        self.volume_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.volume_slider = QSlider(Qt.Orientation.Vertical)
        self.volume_slider.setObjectName("miniVolumeSlider")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        volume_popup_layout.addWidget(self.volume_value_label)
        volume_popup_layout.addWidget(self.volume_slider, 1)
        self.volume_popup.resize(54, 170)
        self._sync_volume_ui(max(0, min(100, int(self._get_volume_percent_fn()))))

        self.progress_slider = QSlider(Qt.Orientation.Horizontal, self.container)
        self.progress_slider.setObjectName("miniProgressSlider")
        self.progress_slider.setRange(0, 0)
        self.progress_slider.setEnabled(False)
        self.progress_slider.sliderPressed.connect(self._on_progress_pressed)
        self.progress_slider.sliderReleased.connect(self._on_progress_released)

        top_row.addWidget(self.track_label)
        top_row.addWidget(self.prev_button)
        top_row.addWidget(self.play_button)
        top_row.addWidget(self.next_button)
        top_row.addWidget(self.repeat_button)
        top_row.addWidget(self.playlist_button)
        top_row.addWidget(self.volume_button)
        top_row.addWidget(self.restore_button)
        container_layout.addLayout(top_row)
        container_layout.addWidget(self.progress_slider)
        root.addWidget(self.container)

        self._playlist_panel = MiniPlaylistPanel(
            on_pick_track_fn=self._play_from_menu,
            extract_track_info_fn=self._extract_track_info_fn,
            parent=self,
        )

        self.container.setGraphicsEffect(None)
        self._apply_scaled_ui()
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(220)
        self._progress_timer.timeout.connect(self._update_progress_ui)
        self._progress_timer.start()
        self._restore_saved_position()
        self.set_keep_on_top(True)
        self._load_button_icons()

    def _ui_scale(self) -> float:
        return current_app_scale(QApplication.instance())

    def _px(self, value: int) -> int:
        return px(value, self._ui_scale())

    def _apply_scaled_ui(self) -> None:
        scale = self._ui_scale()
        popup_w = px(54, scale)
        popup_h = px(170, scale)
        self.volume_popup.resize(popup_w, popup_h)
        self.setStyleSheet(styles.build_mini_player_bar_stylesheet(scale))

    def _load_button_icons(self) -> None:
        icon_size = self._px(24)
        icon_specs = {
            "play": ("play.png", "ic_play.png"),
            "pause": ("pause.png", "ic_pause.png"),
            "next": ("skip.png", "next.png", "ic_next.png"),
            "repeat": ("repeat.png", "repeat_one.png", "loop.png", "ic_repeat.png"),
            "playlist": ("playlist.png", "list.png", "menu.png", "ic_playlist.png"),
            "volume": ("volume.png", "ic_volume.png"),
            "expand": ("expand.png", "exitfull.png", "ic_expand.png"),
        }
        for key, filenames in icon_specs.items():
            icon = load_icon_from_candidates(self._icon_dir, filenames)
            if icon is not None:
                self._icons[key] = icon
        next_icon = self._icons.get("next")
        if next_icon is not None:
            prev_icon = mirrored_icon(next_icon)
            if prev_icon is not None:
                self._icons["prev"] = prev_icon
        if "prev" not in self._icons:
            fallback_prev = load_icon_from_candidates(self._icon_dir, ("prev.png", "previous.png", "ic_prev.png"))
            if fallback_prev is not None:
                self._icons["prev"] = fallback_prev

        if "prev" in self._icons:
            self.prev_button.setIcon(self._icons["prev"])
            apply_icon_button_layout(self.prev_button, icon_size=icon_size, edge_padding=22, min_edge=self._px(44), set_fixed=False)
        else:
            self.prev_button.setProperty("iconOnly", False)
            self.prev_button.setText("⏮")
        if "next" in self._icons:
            self.next_button.setIcon(self._icons["next"])
            apply_icon_button_layout(self.next_button, icon_size=icon_size, edge_padding=22, min_edge=self._px(44), set_fixed=False)
        else:
            self.next_button.setProperty("iconOnly", False)
            self.next_button.setText("⏭")
        if "repeat" in self._icons:
            self.repeat_button.setIcon(self._icons["repeat"])
            apply_icon_button_layout(self.repeat_button, icon_size=icon_size, edge_padding=22, min_edge=self._px(44), set_fixed=False)
        else:
            self.repeat_button.setProperty("iconOnly", False)
            self.repeat_button.setText("🔁")
        self._sync_repeat_button()
        if "playlist" in self._icons:
            self.playlist_button.setIcon(self._icons["playlist"])
            apply_icon_button_layout(self.playlist_button, icon_size=icon_size, edge_padding=22, min_edge=self._px(44), set_fixed=False)
        else:
            self.playlist_button.setProperty("iconOnly", False)
            self.playlist_button.setText("☰")
        if "volume" in self._icons:
            self.volume_button.setIcon(self._icons["volume"])
            apply_icon_button_layout(self.volume_button, icon_size=icon_size, edge_padding=22, min_edge=self._px(44), set_fixed=False)
        else:
            self.volume_button.setProperty("iconOnly", False)
            self.volume_button.setText("🔊")
        if "expand" in self._icons:
            self.restore_button.setIcon(self._icons["expand"])
            apply_icon_button_layout(self.restore_button, icon_size=icon_size, edge_padding=20, min_edge=self._px(42), set_fixed=False)
        else:
            self.restore_button.setProperty("iconOnly", False)
            self.restore_button.setText("⤢")

    def _on_toggle_clicked(self) -> None:
        self._toggle_play_pause_fn()
        self.refresh_state()

    def _on_prev_clicked(self) -> None:
        self._play_prev_fn()
        self.refresh_state()

    def _on_next_clicked(self) -> None:
        self._play_next_fn()
        self.refresh_state()

    def _on_repeat_clicked(self) -> None:
        self._toggle_single_repeat_fn()
        self._sync_repeat_button()

    def _sync_repeat_button(self) -> None:
        on = self._single_repeat_getter()
        self.repeat_button.setDown(on)
        self.repeat_button.setToolTip("单曲循环 (开)" if on else "单曲循环")

    def refresh_state(self) -> None:
        current = self._current_track_fn()
        if current is None:
            label_text = "-"
        else:
            info = self._extract_track_info_fn(current)
            label_text = f"{info.title} · {info.artist}"
        self.track_label.setMarqueeText(label_text)
        self._sync_repeat_button()
        is_playing = self._is_playing_fn()
        if is_playing and "pause" in self._icons:
            self.play_button.setIcon(self._icons["pause"])
            self.play_button.setText("")
            icon_size = self._px(24)
            apply_icon_button_layout(self.play_button, icon_size=icon_size, edge_padding=22, min_edge=self._px(44), set_fixed=False)
        elif not is_playing and "play" in self._icons:
            self.play_button.setIcon(self._icons["play"])
            self.play_button.setText("")
            icon_size = self._px(24)
            apply_icon_button_layout(self.play_button, icon_size=icon_size, edge_padding=22, min_edge=self._px(44), set_fixed=False)
        else:
            self.play_button.setIcon(QIcon())
            self.play_button.setProperty("iconOnly", False)
            self.play_button.setText("⏸" if is_playing else "▶")
        self.playlist_button.setEnabled(bool(self._list_tracks_fn()))
        self._sync_volume_ui(self._get_volume_percent_fn())
        self._update_compact_width(label_text)
        self._update_progress_ui(force=True)

    def _update_compact_width(self, label_text: str) -> None:
        _ = label_text
        compact_width = 430
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            compact_width = min(compact_width, max(360, screen.availableGeometry().width() - 24))
        if compact_width != self.width():
            self.resize(compact_width, self.height())
        self.track_label.setFixedWidth(78)

    def _on_progress_pressed(self) -> None:
        self._is_scrubbing = True

    def _on_progress_released(self) -> None:
        self._is_scrubbing = False
        self._seek_position_ms_fn(int(self.progress_slider.value()))
        self._update_progress_ui(force=True)

    def _update_progress_ui(self, force: bool = False) -> None:
        duration = max(0, int(self._get_duration_ms_fn()))
        position = max(0, int(self._get_position_ms_fn()))
        if duration <= 0:
            self.progress_slider.setEnabled(False)
            self.progress_slider.setRange(0, 0)
            return
        self.progress_slider.setEnabled(True)
        self.progress_slider.setRange(0, duration)
        if not self._is_scrubbing or force:
            self.progress_slider.setValue(min(position, duration))

    def _show_playlist_menu(self) -> None:
        tracks = list(self._list_tracks_fn())
        if self._playlist_panel.isVisible():
            self._playlist_panel.hide()
            return
        self._playlist_panel.set_tracks(tracks=tracks, current_track=self._current_track_fn())
        panel_width = min(max(420, self.width()), 620)
        self._playlist_panel.resize(panel_width, 300)
        self._place_popup_near_button(
            popup=self._playlist_panel,
            button=self.playlist_button,
            prefer_above=False,
            align_right=True,
            gap=6,
        )
        self._playlist_panel.show()
        self._playlist_panel.raise_()

    def _play_from_menu(self, track_path: Path) -> None:
        self._play_track_fn(track_path)
        self.refresh_state()

    def _on_volume_changed(self, value: int) -> None:
        clamped = max(0, min(100, int(value)))
        self._sync_volume_ui(clamped)
        self._set_volume_percent_fn(clamped)

    def _sync_volume_ui(self, volume_percent: int) -> None:
        clamped = max(0, min(100, int(volume_percent)))
        with QSignalBlocker(self.volume_slider):
            self.volume_slider.setValue(clamped)
        self.volume_value_label.setText(f"{clamped}%")

    def _toggle_volume_popup(self) -> None:
        if self.volume_popup.isVisible():
            self.volume_popup.hide()
            return
        self._sync_volume_ui(self._get_volume_percent_fn())
        self._place_popup_near_button(
            popup=self.volume_popup,
            button=self.volume_button,
            prefer_above=True,
            align_right=False,
            gap=6,
        )
        self.volume_popup.show()
        self.volume_popup.raise_()

    def _place_popup_near_button(
        self,
        popup: QWidget,
        button: QWidget,
        *,
        prefer_above: bool,
        align_right: bool,
        gap: int = 6,
    ) -> None:
        popup_w = popup.width()
        popup_h = popup.height()
        top_left = button.mapToGlobal(QPoint(0, 0))
        btn_w = button.width()
        btn_h = button.height()
        screen = QGuiApplication.screenAt(top_left) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x_centered = top_left.x() + (btn_w - popup_w) // 2
        x_right_aligned = top_left.x() + btn_w - popup_w
        x = x_right_aligned if align_right else x_centered
        x = max(area.left(), min(x, area.right() - popup_w + 1))

        y_above = top_left.y() - popup_h - gap
        y_below = top_left.y() + btn_h + gap
        fits_above = y_above >= area.top()
        fits_below = y_below + popup_h <= area.bottom() + 1
        if prefer_above:
            y = y_above if fits_above or not fits_below else y_below
        else:
            y = y_below if fits_below or not fits_above else y_above
        y = max(area.top(), min(y, area.bottom() - popup_h + 1))
        popup.move(x, y)

    def has_custom_position(self) -> bool:
        return self._has_custom_pos

    def set_keep_on_top(self, keep_on_top: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, keep_on_top)
        if sys.platform == "darwin":
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, keep_on_top)
        if self.isVisible():
            self.show()

    def move_to_default_position(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = area.left() + (area.width() - self.width()) // 2
        y = area.bottom() - self.height() - 18
        self.move(x, y)

    def _restore_saved_position(self) -> None:
        point = self._settings.value("mini_bar/pos", None, type=QPoint)
        if point is None:
            return
        self.move(point)
        self._has_custom_pos = True

    def _save_position(self) -> None:
        self._settings.setValue("mini_bar/pos", self.pos())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            self._has_custom_pos = True
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            if self._has_custom_pos:
                self._save_position()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def hideEvent(self, event) -> None:
        self.volume_popup.hide()
        self._playlist_panel.hide()
        self._progress_timer.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        self._apply_scaled_ui()
        self._load_button_icons()
        if not self._progress_timer.isActive():
            self._progress_timer.start()
        super().showEvent(event)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ScreenChangeInternal:
            self._apply_scaled_ui()
            self._load_button_icons()
            self.refresh_state()
        return super().event(event)
