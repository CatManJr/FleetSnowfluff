from __future__ import annotations

import html
import sys
from pathlib import Path
from typing import NamedTuple

from PySide6.QtCore import QEvent, QPoint, QSettings, QSignalBlocker, QSize, Signal
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QCloseEvent,
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
)
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class TrackInfo(NamedTuple):
    path: Path
    title: str
    artist: str
    album: str


def _load_icon_from_candidates(icon_dir: Path | None, filenames: tuple[str, ...]) -> QIcon | None:
    if icon_dir is None:
        return None
    for filename in filenames:
        candidate = icon_dir / filename
        if not candidate.exists():
            continue
        icon = QIcon(str(candidate))
        if not icon.isNull():
            return icon
    return None


class PlaylistTreeWidget(QTreeWidget):
    def __init__(self, bg_path: Path | None, parent=None) -> None:
        super().__init__(parent)
        self._bg_pixmap: QPixmap | None = None
        if bg_path is not None and bg_path.exists():
            pixmap = QPixmap(str(bg_path))
            if not pixmap.isNull():
                self._bg_pixmap = pixmap

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        viewport_rect = self.viewport().rect()
        if self._bg_pixmap is not None and not self._bg_pixmap.isNull():
            src_size = self._bg_pixmap.size()
            if src_size.width() > 0 and src_size.height() > 0:
                scale_w = viewport_rect.width() / src_size.width()
                scale_h = viewport_rect.height() / src_size.height()
                scale = min(scale_w, scale_h)
                target_w = max(1, int(src_size.width() * scale))
                target_h = max(1, int(src_size.height() * scale))
                scaled = self._bg_pixmap.scaled(
                    target_w,
                    target_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                x = viewport_rect.x() + (viewport_rect.width() - scaled.width()) // 2
                y = viewport_rect.y() + (viewport_rect.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
        super().paintEvent(event)


class MarqueeLabel(QLabel):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self._full_text = text
        self._offset = 0
        self._gap = 36
        self._scroll_speed_px = 1
        self._timer = QTimer(self)
        self._timer.setInterval(50)
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


class MiniPlaylistPanel(QDialog):
    def __init__(self, on_pick_track_fn, extract_track_info_fn, parent=None) -> None:
        super().__init__(parent)
        self._on_pick_track_fn = on_pick_track_fn
        self._extract_track_info_fn = extract_track_info_fn
        self._entries: list[tuple[Path, TrackInfo]] = []
        self._current_path: str = ""

        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(430, 280)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame(self)
        card.setObjectName("playlistCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(8)

        self.search_input = QLineEdit(card)
        self.search_input.setObjectName("playlistSearch")
        self.search_input.setPlaceholderText("搜索歌名 / 歌手 / 专辑")
        self.search_input.textChanged.connect(self._apply_filter)

        self.list_widget = QListWidget(card)
        self.list_widget.setObjectName("playlistList")
        self.list_widget.itemClicked.connect(self._on_item_clicked)

        card_layout.addWidget(self.search_input)
        card_layout.addWidget(self.list_widget, 1)
        root.addWidget(card)

        self.setStyleSheet(
            """
            QFrame#playlistCard {
                background: rgba(255, 247, 251, 0.97);
                border: 2px solid #ffc2de;
                border-radius: 14px;
            }
            QLineEdit#playlistSearch {
                border: 1px solid #ffb7d6;
                border-radius: 8px;
                padding: 6px 8px;
                background: #fff8fc;
                color: #6c2e4e;
                font-size: 12px;
            }
            QListWidget#playlistList {
                border: 1px solid #ffd3e6;
                border-radius: 10px;
                background: #ffffff;
                color: #2a1f2a;
                font-size: 12px;
                padding: 3px;
            }
            QListWidget#playlistList::item {
                padding: 5px 8px;
                border-radius: 6px;
            }
            QListWidget#playlistList::item:selected {
                background: rgba(255, 224, 240, 0.8);
                color: #8d365d;
            }
            """
        )

    def set_tracks(self, tracks: list[Path], current_track: Path | None) -> None:
        self._entries = [(track, self._extract_track_info_fn(track)) for track in tracks]
        self._current_path = str(current_track) if current_track is not None else ""
        self._apply_filter(self.search_input.text())

    def _apply_filter(self, query: str) -> None:
        keyword = query.strip().lower()
        self.list_widget.clear()
        for track, info in self._entries:
            candidate = f"{info.title} {info.artist} {info.album}".lower()
            if keyword and keyword not in candidate:
                continue
            text = f"{info.title} · {info.artist}"
            if str(track) == self._current_path:
                text = f"♪ {text}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, str(track))
            self.list_widget.addItem(item)
        if self.list_widget.count() == 0:
            empty = QListWidgetItem("未找到匹配曲目")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(empty)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        raw_path = item.data(Qt.ItemDataRole.UserRole)
        if not raw_path:
            return
        self._on_pick_track_fn(Path(raw_path))
        self.hide()


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
        icon_dir: Path | None,
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
        self._icon_dir = icon_dir
        self._settings = QSettings("FleetSnowfluff", "MusicWindow")
        self._drag_offset: QPoint | None = None
        self._has_custom_pos = False
        self._is_scrubbing = False
        self._icons: dict[str, QIcon] = {}

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
        )
        self.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("飞行雪绒电台 - Mini")
        # Avoid macOS alpha-compositing fringe around rounded corners.
        # Keep window fully opaque at compositor level and control translucency
        # via the card gradient alpha only.
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
        # Keep title viewport compact to mimic Apple Music mini-player.
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

        self.setStyleSheet(
            """
            QDialog {
                background: transparent;
                border: none;
            }
            QFrame#miniCard {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.62),
                    stop:0.18 rgba(255, 252, 255, 0.50),
                    stop:0.52 rgba(255, 245, 252, 0.40),
                    stop:1 rgba(255, 228, 244, 0.34)
                );
                border: none;
                border-radius: 18px;
            }
            QLabel#miniTitle {
                color: #6a2f4f;
                font-size: 14px;
                font-weight: 700;
                padding: 2px 7px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.40),
                    stop:1 rgba(255, 238, 248, 0.26)
                );
                border: none;
                border-radius: 9px;
            }
            QPushButton#miniBtn {
                min-width: 56px;
                max-width: 56px;
                min-height: 48px;
                max-height: 48px;
                border-radius: 14px;
                color: #5d1f3f;
                font-size: 24px;
                border: none;
                background: transparent;
            }
            QPushButton#miniBtn:hover {
                background: rgba(255, 231, 246, 0.32);
            }
            QPushButton#miniBtn:pressed {
                background: rgba(255, 208, 231, 0.52);
                color: #4f1935;
            }
            QPushButton#miniBtn:disabled {
                color: rgba(93, 31, 63, 0.35);
                background: transparent;
            }
            QPushButton#miniBtnExpand {
                min-width: 50px;
                max-width: 50px;
                min-height: 50px;
                max-height: 50px;
                border-radius: 14px;
                color: #4f1935;
                font-size: 25px;
                border: none;
                background: transparent;
            }
            QPushButton#miniBtnExpand:hover {
                background: rgba(255, 231, 246, 0.35);
            }
            QPushButton#miniBtnExpand:pressed {
                background: rgba(255, 208, 231, 0.56);
            }
            QWidget#miniVolumePopup {
                background: rgba(255, 247, 251, 0.96);
                border: 1px solid rgba(255, 197, 224, 0.85);
                border-radius: 12px;
            }
            QLabel#miniVolumeValue {
                color: #8d365d;
                font-size: 11px;
                font-weight: 700;
            }
            QSlider#miniVolumeSlider::groove:vertical {
                width: 8px;
                border-radius: 4px;
                background: rgba(255, 221, 238, 0.52);
            }
            QSlider#miniVolumeSlider::sub-page:vertical {
                border-radius: 4px;
                background: qlineargradient(
                    x1:0, y1:1, x2:0, y2:0,
                    stop:0 rgba(255, 231, 243, 0.86),
                    stop:1 rgba(255, 208, 230, 0.78)
                );
            }
            QSlider#miniVolumeSlider::add-page:vertical {
                border-radius: 4px;
                background: qlineargradient(
                    x1:0, y1:1, x2:0, y2:0,
                    stop:0 rgba(255, 119, 176, 0.96),
                    stop:1 rgba(255, 153, 197, 0.96)
                );
            }
            QSlider#miniVolumeSlider::handle:vertical {
                height: 14px;
                margin: 0 -4px;
                border-radius: 7px;
                border: none;
                background: rgba(255, 248, 252, 0.98);
            }
            QSlider#miniProgressSlider::groove:horizontal {
                height: 4px;
                border-radius: 2px;
                background: rgba(255, 207, 229, 0.44);
            }
            QSlider#miniProgressSlider::sub-page:horizontal {
                border-radius: 2px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 143, 190, 0.92),
                    stop:1 rgba(255, 112, 171, 0.92)
                );
            }
            QSlider#miniProgressSlider::handle:horizontal {
                width: 10px;
                margin: -4px 0;
                border-radius: 5px;
                border: none;
                background: rgba(255, 247, 252, 0.96);
            }
            """
        )
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(220)
        self._progress_timer.timeout.connect(self._update_progress_ui)
        self._progress_timer.start()
        self._restore_saved_position()
        self.set_keep_on_top(True)
        self._load_button_icons()

    def _load_button_icons(self) -> None:
        icon_specs = {
            "prev": ("prev.png", "previous.png", "ic_prev.png"),
            "play": ("play.png", "ic_play.png"),
            "pause": ("pause.png", "ic_pause.png"),
            "next": ("next.png", "ic_next.png"),
            "playlist": ("playlist.png", "list.png", "menu.png", "ic_playlist.png"),
            "volume": ("volume.png", "ic_volume.png"),
            "expand": ("expand.png", "exitfull.png", "ic_expand.png"),
        }
        for key, filenames in icon_specs.items():
            icon = _load_icon_from_candidates(self._icon_dir, filenames)
            if icon is not None:
                self._icons[key] = icon

        if "prev" in self._icons:
            self.prev_button.setIcon(self._icons["prev"])
            self.prev_button.setIconSize(QSize(24, 24))
        else:
            self.prev_button.setText("⏮")
        if "next" in self._icons:
            self.next_button.setIcon(self._icons["next"])
            self.next_button.setIconSize(QSize(24, 24))
        else:
            self.next_button.setText("⏭")
        if "playlist" in self._icons:
            self.playlist_button.setIcon(self._icons["playlist"])
            self.playlist_button.setIconSize(QSize(24, 24))
        else:
            self.playlist_button.setText("☰")
        if "volume" in self._icons:
            self.volume_button.setIcon(self._icons["volume"])
            self.volume_button.setIconSize(QSize(24, 24))
        else:
            self.volume_button.setText("🔊")
        if "expand" in self._icons:
            self.restore_button.setIcon(self._icons["expand"])
            self.restore_button.setIconSize(QSize(24, 24))
        else:
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

    def refresh_state(self) -> None:
        current = self._current_track_fn()
        if current is None:
            label_text = "-"
        else:
            info = self._extract_track_info_fn(current)
            label_text = f"{info.title} · {info.artist}"
        self.track_label.setMarqueeText(label_text)
        is_playing = self._is_playing_fn()
        if is_playing and "pause" in self._icons:
            self.play_button.setIcon(self._icons["pause"])
            self.play_button.setText("")
            self.play_button.setIconSize(QSize(24, 24))
        elif not is_playing and "play" in self._icons:
            self.play_button.setIcon(self._icons["play"])
            self.play_button.setText("")
            self.play_button.setIconSize(QSize(24, 24))
        else:
            self.play_button.setIcon(QIcon())
            self.play_button.setText("⏸" if is_playing else "▶")
        self.playlist_button.setEnabled(bool(self._list_tracks_fn()))
        self._sync_volume_ui(self._get_volume_percent_fn())
        self._update_compact_width(label_text)
        self._update_progress_ui(force=True)

    def _update_compact_width(self, label_text: str) -> None:
        _ = label_text  # keep signature stable
        # Always keep mini player in the tightest compact layout.
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
        x_left = top_left.x()
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
        if not self._progress_timer.isActive():
            self._progress_timer.start()
        super().showEvent(event)


class MusicWindow(QDialog):
    readyForPlayback = Signal()
    def __init__(
        self,
        icon_path: Path | None,
        playlist_bg_path: Path | None,
        list_tracks_fn,
        import_tracks_fn,
        remove_track_fn,
        start_random_loop_fn,
        play_track_fn,
        play_next_fn,
        play_prev_fn,
        current_track_fn,
        toggle_play_pause_fn,
        is_playing_fn,
        get_position_ms_fn,
        get_duration_ms_fn,
        seek_position_ms_fn,
        get_volume_percent_fn,
        set_volume_percent_fn,
        stop_playback_fn,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._icon_path = icon_path
        self._playlist_bg_path = playlist_bg_path
        self._list_tracks_fn = list_tracks_fn
        self._import_tracks_fn = import_tracks_fn
        self._remove_track_fn = remove_track_fn
        self._start_random_loop_fn = start_random_loop_fn
        self._play_track_fn = play_track_fn
        self._play_next_fn = play_next_fn
        self._play_prev_fn = play_prev_fn
        self._current_track_fn = current_track_fn
        self._toggle_play_pause_fn = toggle_play_pause_fn
        self._is_playing_fn = is_playing_fn
        self._get_position_ms_fn = get_position_ms_fn
        self._get_duration_ms_fn = get_duration_ms_fn
        self._seek_position_ms_fn = seek_position_ms_fn
        self._get_volume_percent_fn = get_volume_percent_fn
        self._set_volume_percent_fn = set_volume_percent_fn
        self._stop_playback_fn = stop_playback_fn
        self._tracks: list[Path] = []
        self._track_infos: list[TrackInfo] = []
        self._mini_bar: MiniPlayerBar | None = None
        self._track_info_cache: dict[Path, tuple[int, int, TrackInfo]] = {}
        self._last_now_playing_key: tuple[str, bool] | None = None
        self._is_scrubbing = False
        self._ready_emitted = False
        self._pending_enter_mini_mode = False
        self._jumpout_icon: QIcon | None = None
        self._icon_dir = self._icon_path.parent / "icon" if self._icon_path is not None else None
        self._button_icons: dict[str, QIcon] = {}
        self._follow_count = 130
        self._is_following = False

        self.setWindowTitle("飞行雪绒电台")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowOpacity(0.95)
        self.resize(390, 560)
        self._build_ui()
        self.refresh_tracks()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(2500)
        self._refresh_timer.timeout.connect(self._refresh_now_playing)
        self._refresh_timer.start()

        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(220)
        self._progress_timer.timeout.connect(self._update_progress_ui)
        self._progress_timer.start()

    def is_ready_for_playback(self) -> bool:
        return self._ready_emitted

    def _ensure_mini_bar(self) -> MiniPlayerBar:
        if self._mini_bar is None:
            self._mini_bar = MiniPlayerBar(
                toggle_play_pause_fn=self._on_toggle_play_pause,
                play_prev_fn=self._play_prev_fn,
                play_next_fn=self._play_next_fn,
                restore_main_fn=self._restore_from_mini_bar,
                current_track_fn=self._current_track_fn,
                list_tracks_fn=self._list_tracks_fn,
                play_track_fn=self._play_track_fn,
                extract_track_info_fn=self._extract_track_info,
                is_playing_fn=self._is_playing_fn,
                get_position_ms_fn=self._get_position_ms_fn,
                get_duration_ms_fn=self._get_duration_ms_fn,
                seek_position_ms_fn=self._seek_position_ms_fn,
                get_volume_percent_fn=self._get_volume_percent_fn,
                set_volume_percent_fn=self._set_volume_percent_fn,
                icon_dir=self._icon_dir,
            )
        return self._mini_bar

    def _load_jumpout_icon(self) -> QIcon | None:
        return _load_icon_from_candidates(self._icon_dir, ("jumpout.png", "jumpout.PNG", "ic_jumpout.png"))

    def _load_main_button_icons(self) -> None:
        specs = {
            "import": ("import.png", "download.png", "ic_import.png"),
            "remove": ("remove.png", "delete.png", "ic_remove.png"),
            "prev": ("prev.png", "previous.png", "ic_prev.png"),
            "play": ("play.png", "ic_play.png"),
            "pause": ("pause.png", "ic_pause.png"),
            "next": ("next.png", "ic_next.png"),
            "random": ("random.png", "shuffle.png", "ic_random.png"),
            "volume": ("volume.png", "ic_volume.png"),
            "expand": ("expand.png", "exitfull.png", "ic_expand.png"),
        }
        for key, names in specs.items():
            icon = _load_icon_from_candidates(self._icon_dir, names)
            if icon is not None:
                self._button_icons[key] = icon

    def _show_mini_bar(self) -> None:
        mini = self._ensure_mini_bar()
        mini.set_keep_on_top(True)
        mini.refresh_state()
        if not mini.has_custom_position():
            mini.move_to_default_position()
        mini.show()
        mini.raise_()
        self._sync_float_bar_button()

    def _hide_mini_bar(self) -> None:
        if self._mini_bar is not None:
            self._mini_bar.set_keep_on_top(False)
            self._mini_bar.hide()
        self._sync_float_bar_button()

    def capture_visibility_state(self) -> dict[str, bool]:
        return {
            "main_visible": self.isVisible(),
            "mini_visible": self._mini_bar is not None and self._mini_bar.isVisible(),
        }

    def hide_for_transform(self) -> None:
        if self.volume_popup.isVisible():
            self.volume_popup.hide()
        if self.isVisible():
            self.hide()
        self._hide_mini_bar()

    def restore_after_transform(self, state: dict[str, bool] | None) -> None:
        if not state:
            return
        was_mini_visible = bool(state.get("mini_visible", False))
        was_main_visible = bool(state.get("main_visible", False))
        if was_mini_visible:
            self._show_mini_bar()
            self.hide()
            return
        if was_main_visible:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _restore_from_mini_bar(self) -> None:
        if self.volume_popup.isVisible():
            self.volume_popup.hide()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self._hide_mini_bar()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        nav = QFrame(self)
        nav.setObjectName("navBar")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(12, 8, 12, 8)
        nav_layout.setSpacing(8)

        avatar = QLabel("")
        avatar.setObjectName("avatarBadge")
        avatar.setFixedSize(56, 56)
        if self._icon_path is not None and self._icon_path.exists():
            pixmap = QPixmap(str(self._icon_path))
            if not pixmap.isNull():
                avatar.setPixmap(
                    pixmap.scaled(
                        56,
                        56,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                avatar.setScaledContents(True)
        else:
            avatar.setText("飞")
        title = QLabel("飞行雪绒电台")
        title.setObjectName("navTitle")
        nav_layout.addWidget(avatar)
        nav_layout.addWidget(title, 1)
        self.follow_count_label = QLabel("")
        self.follow_count_label.setObjectName("followCount")
        self.follow_button = QPushButton("关注")
        self.follow_button.setObjectName("followBtn")
        self.follow_button.setToolTip("关注飞行雪绒")
        self.follow_button.clicked.connect(self._on_follow_clicked)
        self._update_follow_ui()
        nav_layout.addWidget(self.follow_count_label)
        nav_layout.addWidget(self.follow_button)

        panel = QFrame(self)
        panel.setObjectName("panelCard")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)
        panel_layout.setSpacing(8)

        now_playing_row = QHBoxLayout()
        now_playing_row.setContentsMargins(0, 0, 0, 0)
        now_playing_row.setSpacing(8)
        self.now_playing = QLabel("当前播放：-")
        self.now_playing.setObjectName("nowPlaying")
        self.now_playing.setTextFormat(Qt.TextFormat.RichText)
        self.now_playing.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.now_playing.setMinimumHeight(72)
        self.float_bar_button = QPushButton("")
        self.float_bar_button.setObjectName("navActionBtn")
        self.float_bar_button.setToolTip("切换到迷你播放器")
        self.float_bar_button.setFixedHeight(72)
        self.float_bar_button.clicked.connect(self._toggle_mini_bar_from_ui)
        self._jumpout_icon = self._load_jumpout_icon()
        if self._jumpout_icon is not None:
            self.float_bar_button.setIcon(self._jumpout_icon)
            self.float_bar_button.setIconSize(self.float_bar_button.size() - QSize(4, 4))
        else:
            self.float_bar_button.setText("⤡")
        now_playing_row.addWidget(self.now_playing, 1)
        now_playing_row.addWidget(self.float_bar_button)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)
        self.current_time_label = QLabel("00:00")
        self.current_time_label.setObjectName("timeLabel")
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setObjectName("progressSlider")
        self.progress_slider.setRange(0, 0)
        self.progress_slider.setEnabled(False)
        self.progress_slider.sliderPressed.connect(self._on_progress_pressed)
        self.progress_slider.sliderReleased.connect(self._on_progress_released)
        self.progress_slider.valueChanged.connect(self._on_progress_value_changed)
        self.total_time_label = QLabel("00:00")
        self.total_time_label.setObjectName("timeLabel")
        progress_row.addWidget(self.current_time_label)
        progress_row.addWidget(self.progress_slider, 1)
        progress_row.addWidget(self.total_time_label)
        self.volume_button = QPushButton("")
        self.volume_button.setObjectName("volumeToggleBtn")
        self.volume_button.setToolTip("音量")
        self.volume_button.clicked.connect(self._toggle_volume_popup)
        progress_row.addWidget(self.volume_button)

        self.volume_popup = QWidget(self)
        self.volume_popup.setObjectName("volumePopup")
        self.volume_popup.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        popup_layout = QVBoxLayout(self.volume_popup)
        popup_layout.setContentsMargins(8, 8, 8, 8)
        popup_layout.setSpacing(6)
        self.volume_popup_value = QLabel("70%")
        self.volume_popup_value.setObjectName("volumePopupValue")
        self.volume_popup_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.volume_popup_slider = QSlider(Qt.Orientation.Vertical)
        self.volume_popup_slider.setObjectName("volumePopupSlider")
        self.volume_popup_slider.setRange(0, 100)
        self.volume_popup_slider.setInvertedAppearance(False)
        self.volume_popup_slider.valueChanged.connect(self._on_volume_changed)
        popup_layout.addWidget(self.volume_popup_value)
        popup_layout.addWidget(self.volume_popup_slider, 1)
        self.volume_popup.resize(54, 170)
        self._sync_volume_ui(max(0, min(100, int(self._get_volume_percent_fn()))))

        self.track_list = PlaylistTreeWidget(self._playlist_bg_path, panel)
        self.track_list.setObjectName("trackList")
        self.track_list.setColumnCount(3)
        self.track_list.setHeaderLabels(["歌名", "作者", "专辑"])
        self.track_list.setRootIsDecorated(False)
        self.track_list.setUniformRowHeights(True)
        self.track_list.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
        self.track_list.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.track_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.track_list.itemSelectionChanged.connect(self._update_control_states)
        header = self.track_list.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)
        self.import_button = QPushButton("")
        self.import_button.setObjectName("actionBtn")
        self.import_button.setToolTip("导入曲库")
        self.import_button.clicked.connect(self._on_import_clicked)
        self.remove_button = QPushButton("")
        self.remove_button.setObjectName("actionBtn")
        self.remove_button.setToolTip("移除选中曲目")
        self.remove_button.clicked.connect(self._on_remove_clicked)
        self.prev_button = QPushButton("")
        self.prev_button.setObjectName("actionBtn")
        self.prev_button.setToolTip("上一首")
        self.prev_button.clicked.connect(self._play_prev_fn)
        self.play_button = QPushButton("")
        self.play_button.setObjectName("actionMainBtn")
        self.play_button.setToolTip("播放 / 暂停")
        self.play_button.clicked.connect(self._on_toggle_play_pause)
        self.next_button = QPushButton("")
        self.next_button.setObjectName("actionBtn")
        self.next_button.setToolTip("下一首")
        self.next_button.clicked.connect(self._play_next_fn)
        self.random_button = QPushButton("")
        self.random_button.setObjectName("actionBtn")
        self.random_button.setToolTip("重新随机排序")
        self.random_button.clicked.connect(self._on_random_clicked)

        ctrl_row.addWidget(self.import_button)
        ctrl_row.addWidget(self.remove_button)
        ctrl_row.addStretch(1)
        ctrl_row.addWidget(self.prev_button)
        ctrl_row.addWidget(self.play_button)
        ctrl_row.addWidget(self.next_button)
        ctrl_row.addStretch(1)
        ctrl_row.addWidget(self.random_button)

        panel_layout.addLayout(now_playing_row)
        panel_layout.addLayout(progress_row)
        panel_layout.addWidget(self.track_list, 1)
        panel_layout.addLayout(ctrl_row)

        root.addWidget(nav)
        root.addWidget(panel, 1)

        track_list_background = "background: transparent;"

        stylesheet = """
            QDialog {
                background: rgba(255, 247, 251, 0.78);
                color: #2a1f2a;
            }
            QFrame#navBar {
                background: rgba(255, 255, 255, 0.46);
                border-bottom: 1px solid rgba(255, 211, 230, 0.36);
            }
            QLabel#avatarBadge {
                min-width: 56px;
                min-height: 56px;
                max-width: 56px;
                max-height: 56px;
                border-radius: 28px;
                background: #ff5fa2;
                color: #ffffff;
                font-weight: 700;
                qproperty-alignment: AlignCenter;
                border: 2px solid #ffc2de;
            }
            QLabel#navTitle {
                font-size: 18px;
                font-weight: 700;
                color: #221626;
            }
            QLabel#followCount {
                color: #8d365d;
                font-size: 12px;
                font-weight: 700;
                padding: 0 2px;
            }
            QPushButton#followBtn {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 112, 178, 0.95),
                    stop:1 rgba(255, 139, 193, 0.92)
                );
                border: none;
                border-radius: 12px;
                color: #ffffff;
                min-width: 56px;
                min-height: 32px;
                padding: 0 10px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton#followBtn:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 124, 185, 0.98),
                    stop:1 rgba(255, 154, 202, 0.95)
                );
            }
            QPushButton#followBtn:pressed {
                background: rgba(255, 105, 170, 0.88);
            }
            QPushButton#navActionBtn {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.42),
                    stop:1 rgba(255, 235, 247, 0.30)
                );
                border: none;
                border-radius: 14px;
                color: #7a3658;
                min-width: 56px;
                max-width: 56px;
                min-height: 72px;
                max-height: 72px;
                padding: 0px;
                font-size: 34px;
                font-weight: 600;
            }
            QPushButton#navActionBtn:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.98),
                    stop:1 rgba(255, 227, 243, 0.95)
                );
            }
            QPushButton#navActionBtn:pressed {
                background: rgba(255, 211, 233, 0.38);
            }
            QFrame#panelCard {
                background: rgba(255, 247, 251, 0.34);
                border: none;
                border-radius: 16px;
            }
            QLabel#nowPlaying {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 238, 247, 0.62),
                    stop:1 rgba(255, 220, 237, 0.52)
                );
                border: none;
                border-radius: 12px;
                padding: 8px;
                color: #6c2e4e;
                font-size: 13px;
            }
            QLabel#timeLabel {
                color: #8a4a69;
                min-width: 44px;
                font-size: 11px;
                font-weight: 600;
            }
            QSlider#progressSlider::groove:horizontal {
                height: 6px;
                border-radius: 3px;
                background: rgba(255, 205, 228, 0.52);
            }
            QSlider#progressSlider::sub-page:horizontal {
                border-radius: 3px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 143, 190, 0.95),
                    stop:1 rgba(255, 110, 170, 0.95)
                );
            }
            QSlider#progressSlider::handle:horizontal {
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
                border: none;
                background: rgba(255, 248, 252, 0.96);
            }
            QSlider#progressSlider::handle:horizontal:hover {
                background: rgba(255, 255, 255, 0.98);
            }
            QPushButton#volumeToggleBtn {
                min-width: 34px;
                max-width: 34px;
                min-height: 28px;
                max-height: 28px;
                border-radius: 10px;
                border: none;
                background: rgba(255, 255, 255, 0.36);
                color: #7a3658;
                font-size: 16px;
                font-weight: 700;
            }
            QPushButton#volumeToggleBtn:hover {
                background: rgba(255, 255, 255, 0.56);
            }
            QPushButton#volumeToggleBtn:pressed {
                background: rgba(255, 220, 239, 0.64);
            }
            QWidget#volumePopup {
                background: rgba(255, 247, 251, 0.96);
                border: 1px solid rgba(255, 197, 224, 0.85);
                border-radius: 12px;
            }
            QLabel#volumePopupValue {
                color: #8d365d;
                font-size: 11px;
                font-weight: 700;
            }
            QSlider#volumePopupSlider::groove:vertical {
                width: 8px;
                border-radius: 4px;
                background: rgba(255, 221, 238, 0.52);
            }
            QSlider#volumePopupSlider::sub-page:vertical {
                border-radius: 4px;
                background: qlineargradient(
                    x1:0, y1:1, x2:0, y2:0,
                    stop:0 rgba(255, 231, 243, 0.86),
                    stop:1 rgba(255, 208, 230, 0.78)
                );
            }
            QSlider#volumePopupSlider::add-page:vertical {
                border-radius: 4px;
                background: qlineargradient(
                    x1:0, y1:1, x2:0, y2:0,
                    stop:0 rgba(255, 119, 176, 0.96),
                    stop:1 rgba(255, 153, 197, 0.96)
                );
            }
            QSlider#volumePopupSlider::handle:vertical {
                height: 14px;
                margin: 0 -4px;
                border-radius: 7px;
                border: none;
                background: rgba(255, 248, 252, 0.98);
            }
            QSlider#volumePopupSlider::handle:vertical:hover {
                background: rgba(255, 255, 255, 1.0);
            }
            QTreeWidget#trackList {
                __TRACK_LIST_BACKGROUND__
                border: none;
                border-radius: 14px;
                padding: 4px;
                font-size: 14px;
                color: #2a1f2a;
            }
            QTreeWidget#trackList::item {
                height: 28px;
                padding: 2px 6px;
                background: transparent;
                margin: 1px 2px;
            }
            QTreeWidget#trackList::item:selected {
                background: rgba(255, 234, 244, 0.35);
                color: #6c2e4e;
            }
            QHeaderView::section {
                background: rgba(255, 240, 247, 0.58);
                border: none;
                border-bottom: 1px solid rgba(255, 211, 230, 0.34);
                padding: 6px 8px;
                color: #8d365d;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton#actionBtn {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.34),
                    stop:0.58 rgba(255, 239, 249, 0.28),
                    stop:1 rgba(255, 217, 238, 0.24)
                );
                border: none;
                border-radius: 15px;
                color: #7b3356;
                min-width: 48px;
                min-height: 40px;
                padding: 4px;
                font-size: 20px;
                font-weight: 600;
            }
            QPushButton#actionBtn:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.56),
                    stop:0.55 rgba(255, 245, 251, 0.46),
                    stop:1 rgba(255, 226, 243, 0.40)
                );
            }
            QPushButton#actionBtn:pressed {
                background: rgba(255, 207, 231, 0.36);
                color: #6f2d4d;
            }
            QPushButton#actionBtn:disabled {
                background: rgba(245, 237, 242, 0.18);
                border: none;
                color: #b995ab;
            }
            QPushButton#actionMainBtn {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.42),
                    stop:0.5 rgba(255, 230, 245, 0.35),
                    stop:1 rgba(255, 198, 227, 0.30)
                );
                border: none;
                border-radius: 24px;
                color: #6f2a4a;
                min-width: 48px;
                max-width: 48px;
                min-height: 48px;
                max-height: 48px;
                padding: 0px;
                font-size: 21px;
                font-weight: 700;
            }
            QPushButton#actionMainBtn:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.64),
                    stop:1 rgba(255, 214, 238, 0.52)
                );
            }
            QPushButton#actionMainBtn:pressed {
                background: rgba(255, 185, 220, 0.42);
                color: #662640;
            }
            QPushButton#actionMainBtn:disabled {
                background: rgba(245, 237, 242, 0.18);
                border: none;
                color: #b995ab;
            }
            """
        self.setStyleSheet(stylesheet.replace("__TRACK_LIST_BACKGROUND__", track_list_background))
        self._load_main_button_icons()
        self._apply_main_button_icons()
        # Ensure volume icon state uses freshly loaded assets immediately.
        self._sync_volume_ui(self._get_volume_percent_fn())

    def _on_item_double_clicked(self, _item, _column: int) -> None:
        self._on_play_selected()
        self._sync_play_button()

    def _on_play_selected(self) -> None:
        item = self.track_list.currentItem()
        if item is None:
            return
        row = self.track_list.indexOfTopLevelItem(item)
        if row < 0 or row >= len(self._track_infos):
            return
        self._play_track_fn(self._track_infos[row].path)
        self._refresh_now_playing()
        self._sync_play_button()

    def _on_import_clicked(self) -> None:
        self._import_tracks_fn()
        self.refresh_tracks()

    def _on_remove_clicked(self) -> None:
        item = self.track_list.currentItem()
        if item is None:
            QMessageBox.information(self, "未选择曲目", "请先在列表中选择要移除的歌曲。")
            return
        row = self.track_list.indexOfTopLevelItem(item)
        if row < 0 or row >= len(self._track_infos):
            return
        target = self._track_infos[row]
        confirm = QMessageBox.question(
            self,
            "移除曲目",
            f"确认移除：\n{target.title}\n\n此操作会删除容器中的该音频文件。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        if not self._remove_track_fn(target.path):
            QMessageBox.warning(self, "移除失败", "无法删除该曲目，请检查文件权限。")
            return
        self.refresh_tracks()

    def _on_random_clicked(self) -> None:
        self._start_random_loop_fn()
        self._refresh_now_playing()
        self._sync_play_button()

    def _on_toggle_play_pause(self) -> None:
        self._toggle_play_pause_fn()
        self._refresh_now_playing()
        self._sync_play_button()

    def _toggle_mini_bar_from_ui(self) -> None:
        if self._mini_bar is not None and self._mini_bar.isVisible():
            self._restore_from_mini_bar()
            return
        if self.volume_popup.isVisible():
            self.volume_popup.hide()
        if self.isFullScreen():
            self._pending_enter_mini_mode = True
            self.showNormal()
            QTimer.singleShot(0, self._enter_mini_mode_after_fullscreen)
            return
        self._enter_mini_mode_after_fullscreen()

    def _enter_mini_mode_after_fullscreen(self) -> None:
        if self.isFullScreen():
            QTimer.singleShot(40, self._enter_mini_mode_after_fullscreen)
            return
        self._pending_enter_mini_mode = False
        self._show_mini_bar()
        self._hide_main_window_for_mini_mode()

    def _hide_main_window_for_mini_mode(self) -> None:
        # On macOS, avoid minimize-to-dock when mini bar is active.
        # Keep window normal, push it back, then hide after a short delay
        # to prevent transient ghost frame artifacts.
        if sys.platform == "darwin":
            self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
            self.showNormal()
            self.lower()
            QTimer.singleShot(90, self.hide)
            return
        # Apple Music-like mode switch: hide full player when mini player opens.
        self.hide()

    def _sync_float_bar_button(self) -> None:
        is_visible = self._mini_bar is not None and self._mini_bar.isVisible()
        expand_icon = self._button_icons.get("expand")
        if is_visible and expand_icon is not None:
            self.float_bar_button.setIcon(expand_icon)
            self.float_bar_button.setText("")
            self.float_bar_button.setIconSize(self.float_bar_button.size() - QSize(8, 8))
        elif self._jumpout_icon is not None:
            self.float_bar_button.setIcon(self._jumpout_icon)
            self.float_bar_button.setText("")
            self.float_bar_button.setIconSize(self.float_bar_button.size() - QSize(4, 4))
        else:
            self.float_bar_button.setIcon(QIcon())
            self.float_bar_button.setText("⤢" if is_visible else "⤡")
        self.float_bar_button.setToolTip("返回完整播放器" if is_visible else "切换到迷你播放器")

    @staticmethod
    def _format_ms(ms: int) -> str:
        total = max(0, int(ms)) // 1000
        minute = total // 60
        second = total % 60
        return f"{minute:02d}:{second:02d}"

    def _on_progress_pressed(self) -> None:
        self._is_scrubbing = True

    def _on_progress_released(self) -> None:
        self._is_scrubbing = False
        self._seek_position_ms_fn(int(self.progress_slider.value()))
        self._update_progress_ui(force=True)

    def _on_progress_value_changed(self, value: int) -> None:
        if self._is_scrubbing:
            self.current_time_label.setText(self._format_ms(value))

    def _on_volume_changed(self, value: int) -> None:
        clamped = max(0, min(100, int(value)))
        self._sync_volume_ui(clamped)
        self._set_volume_percent_fn(clamped)

    def _sync_volume_ui(self, volume_percent: int) -> None:
        clamped = max(0, min(100, int(volume_percent)))
        with QSignalBlocker(self.volume_popup_slider):
            self.volume_popup_slider.setValue(clamped)
        self.volume_popup_value.setText(f"{clamped}%")
        volume_icon = self._button_icons.get("volume")
        if volume_icon is not None:
            self.volume_button.setIcon(volume_icon)
            self.volume_button.setText("")
            self.volume_button.setIconSize(QSize(20, 20))
        elif clamped == 0:
            self.volume_button.setIcon(QIcon())
            self.volume_button.setText("🔇")
        elif clamped < 45:
            self.volume_button.setIcon(QIcon())
            self.volume_button.setText("🔉")
        else:
            self.volume_button.setIcon(QIcon())
            self.volume_button.setText("🔊")

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

    def _update_progress_ui(self, force: bool = False) -> None:
        duration = max(0, int(self._get_duration_ms_fn()))
        position = max(0, int(self._get_position_ms_fn()))
        if duration <= 0:
            self.progress_slider.setEnabled(False)
            self.progress_slider.setRange(0, 0)
            if force or not self._is_scrubbing:
                self.current_time_label.setText("00:00")
            self.total_time_label.setText("00:00")
            return

        self.progress_slider.setEnabled(True)
        self.progress_slider.setRange(0, duration)
        self.total_time_label.setText(self._format_ms(duration))
        if not self._is_scrubbing or force:
            self.progress_slider.setValue(min(position, duration))
            self.current_time_label.setText(self._format_ms(position))

    def refresh_tracks(self) -> None:
        self._tracks = list(self._list_tracks_fn())
        self.track_list.clear()
        self._track_infos = [self._extract_track_info(p) for p in self._tracks]
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(14)
        for info in self._track_infos:
            item = QTreeWidgetItem([info.title, info.artist, info.album])
            item.setToolTip(0, str(info.path))
            item.setData(0, Qt.ItemDataRole.UserRole, str(info.path))
            item.setFont(0, title_font)
            self.track_list.addTopLevelItem(item)
        self._apply_column_widths()
        self._refresh_now_playing()
        self._update_control_states()
        self._sync_current_track_highlight()
        self._sync_play_button()

    def _apply_column_widths(self) -> None:
        total_width = max(1, self.track_list.viewport().width())
        # Prioritize title readability; keep artist/album informative but bounded.
        artist_width = min(170, max(100, int(total_width * 0.2)))
        album_width = min(190, max(110, int(total_width * 0.22)))
        reserved = artist_width + album_width
        title_width = max(180, total_width - reserved - 16)
        self.track_list.setColumnWidth(0, title_width)
        self.track_list.setColumnWidth(1, artist_width)
        self.track_list.setColumnWidth(2, album_width)

    def _refresh_now_playing(self) -> None:
        current = self._current_track_fn()
        is_playing = bool(self._is_playing_fn())
        now_playing_key = (str(current) if current is not None else "", is_playing)
        if now_playing_key == self._last_now_playing_key:
            # Avoid repeated metadata I/O and repaint work when state is unchanged.
            self._update_control_states()
            self._sync_play_button()
            return
        self._last_now_playing_key = now_playing_key
        if current is None:
            self._set_now_playing_text(title="-", artist="-", album="-")
            self._sync_current_track_highlight()
            if self._mini_bar is not None:
                self._mini_bar.refresh_state()
            self._update_control_states()
            self._sync_play_button()
            return
        info = self._extract_track_info(current)
        self._set_now_playing_text(title=info.title, artist=info.artist, album=info.album)
        self._sync_current_track_highlight()
        if self._mini_bar is not None:
            self._mini_bar.refresh_state()
        self._update_control_states()
        self._sync_play_button()
        self._sync_float_bar_button()

    def refresh_now_playing(self) -> None:
        """
        Fast-path refresh for external playback state changes.
        """
        self._refresh_now_playing()
        self._update_progress_ui(force=True)

    def _sync_play_button(self) -> None:
        is_playing = bool(self._is_playing_fn())
        pause_icon = self._button_icons.get("pause")
        play_icon = self._button_icons.get("play")
        if is_playing and pause_icon is not None:
            self.play_button.setIcon(pause_icon)
            self.play_button.setText("")
            self.play_button.setIconSize(QSize(24, 24))
            return
        if (not is_playing) and play_icon is not None:
            self.play_button.setIcon(play_icon)
            self.play_button.setText("")
            self.play_button.setIconSize(QSize(24, 24))
            return
        self.play_button.setIcon(QIcon())
        self.play_button.setText("⏸" if is_playing else "▶")

    def _update_follow_ui(self) -> None:
        self.follow_count_label.setText(f"已关注：{self._follow_count}")
        self.follow_button.setText("已关注" if self._is_following else "关注")

    def _on_follow_clicked(self) -> None:
        if self._is_following:
            self._is_following = False
            self._follow_count = max(0, self._follow_count - 1)
        else:
            self._is_following = True
            self._follow_count += 1
        self._update_follow_ui()

    def _apply_main_button_icons(self) -> None:
        def apply(button: QPushButton, key: str, fallback: str, size: int = 24) -> None:
            icon = self._button_icons.get(key)
            if icon is not None:
                button.setIcon(icon)
                button.setText("")
                button.setIconSize(QSize(size, size))
            else:
                button.setIcon(QIcon())
                button.setText(fallback)

        apply(self.import_button, "import", "⤓")
        apply(self.remove_button, "remove", "⌫")
        apply(self.prev_button, "prev", "⏮")
        apply(self.next_button, "next", "⏭")
        apply(self.random_button, "random", "🔀")
        self._sync_play_button()

    def _set_now_playing_text(self, title: str, artist: str, album: str) -> None:
        title_html = html.escape((title or "-").strip() or "-")
        artist_html = html.escape((artist or "-").strip() or "-")
        album_html = html.escape((album or "-").strip() or "-")
        self.now_playing.setText(
            (
                "<div style='line-height:1.08;'>"
                f"<div style='font-size:19px; font-weight:800; color:#c13c83;'>{title_html}</div>"
                f"<div style='margin-top:2px; font-size:13px; color:#ff5b9d;'>{artist_html}</div>"
                f"<div style='margin-top:1px; font-size:12px; color:#b78da3;'>{album_html}</div>"
                "</div>"
            )
        )

    def _sync_current_track_highlight(self) -> None:
        current = self._current_track_fn()
        now_playing_path = str(current) if current is not None else ""
        matched_item: QTreeWidgetItem | None = None
        normal_fg = QBrush(QColor("#2a1f2a"))
        playing_fg = QBrush(QColor("#8d365d"))
        playing_bg = QBrush(QColor(255, 224, 240, 180))
        transparent_bg = QBrush(QColor(0, 0, 0, 0))

        for i in range(self.track_list.topLevelItemCount()):
            item = self.track_list.topLevelItem(i)
            is_playing = item.data(0, Qt.ItemDataRole.UserRole) == now_playing_path
            item.setText(0, f"♪ {self._track_infos[i].title}" if is_playing else self._track_infos[i].title)
            for col in range(3):
                item.setForeground(col, playing_fg if is_playing else normal_fg)
                item.setBackground(col, playing_bg if is_playing else transparent_bg)
            if is_playing:
                matched_item = item

        if current is None or matched_item is None:
            return
        with QSignalBlocker(self.track_list):
            self.track_list.setCurrentItem(matched_item)
        self.track_list.scrollToItem(matched_item)

    def _update_control_states(self) -> None:
        has_tracks = bool(self._track_infos)
        has_selected = self.track_list.currentItem() is not None
        self.remove_button.setEnabled(has_selected)
        self.random_button.setEnabled(has_tracks)
        self.prev_button.setEnabled(has_tracks)
        self.next_button.setEnabled(has_tracks)
        self.play_button.setEnabled(has_tracks and (has_selected or self._current_track_fn() is not None))

    def _extract_track_info(self, track_path: Path) -> TrackInfo:
        title = track_path.stem
        artist = "未知艺术家"
        album = "未知专辑"
        stat_mtime_ns = 0
        stat_size = 0
        try:
            stat = track_path.stat()
            stat_mtime_ns = stat.st_mtime_ns
            stat_size = stat.st_size
            cached = self._track_info_cache.get(track_path)
            if cached is not None and cached[0] == stat_mtime_ns and cached[1] == stat_size:
                return cached[2]
        except OSError:
            pass
        try:
            from mutagen import File as MutagenFile

            audio = MutagenFile(track_path, easy=True)
            if audio is not None:
                title = self._pick_first(audio.get("title")) or title
                artist = self._normalize_artist_display(audio.get("artist")) or artist
                album = self._pick_first(audio.get("album")) or album
        except Exception:
            pass
        info = TrackInfo(path=track_path, title=title, artist=artist, album=album)
        self._track_info_cache[track_path] = (stat_mtime_ns, stat_size, info)
        return info

    @staticmethod
    def _pick_first(value) -> str:
        if not value:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (list, tuple)):
            for entry in value:
                text = str(entry).strip()
                if text:
                    return text
        return ""

    @staticmethod
    def _normalize_artist_display(value) -> str:
        preferred = "飞行雪绒"
        if not value:
            return ""

        raw_entries: list[str] = []
        if isinstance(value, str):
            raw_entries = [value]
        elif isinstance(value, (list, tuple)):
            raw_entries = [str(v) for v in value if str(v).strip()]
        else:
            raw_entries = [str(value)]

        artists: list[str] = []
        for raw in raw_entries:
            parts = MusicWindow._split_artist_tokens(raw)
            for part in parts:
                if part not in artists:
                    artists.append(part)

        if not artists:
            return ""

        artists.sort(key=lambda name: (0 if preferred in name else 1, name))
        return ", ".join(artists)

    @staticmethod
    def _split_artist_tokens(text: str) -> list[str]:
        normalized = text
        for sep in ["、", ";", "|", "&", "/", "，"]:
            normalized = normalized.replace(sep, ",")
        return [token.strip() for token in normalized.split(",") if token.strip()]

    def closeEvent(self, event: QCloseEvent) -> None:
        self._progress_timer.stop()
        self._pending_enter_mini_mode = False
        if self.volume_popup.isVisible():
            self.volume_popup.hide()
        self._hide_mini_bar()
        self._stop_playback_fn()
        self._sync_play_button()
        self._sync_float_bar_button()
        super().closeEvent(event)

    def showEvent(self, event) -> None:
        if not self._ready_emitted:
            self._ready_emitted = True
            self.readyForPlayback.emit()
        super().showEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                if self.volume_popup.isVisible():
                    self.volume_popup.hide()
                self._refresh_timer.stop()
                self._progress_timer.stop()
            else:
                if not self._refresh_timer.isActive():
                    self._refresh_timer.start()
                if not self._progress_timer.isActive():
                    self._progress_timer.start()
                self._refresh_now_playing()
                self._update_progress_ui(force=True)
                self._apply_column_widths()
                self._update_control_states()
                self._sync_play_button()
            self._sync_float_bar_button()
        super().changeEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_column_widths()
