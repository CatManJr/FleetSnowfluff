from __future__ import annotations

import html
import sys
from pathlib import Path

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
    QApplication,
    QDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSlider,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.utils.fluent_compat import apply_icon_button_layout
from app.utils.fluent_compat import FPushButton as QPushButton
from app.utils.fluent_compat import init_fluent_theme
from app.utils.ui_scale import current_app_scale, px

from . import styles
from .marquee_label import MarqueeLabel
from .mini_player_bar import MiniPlayerBar
from .playlist_tree import PlaylistTreeWidget
from .types import TrackInfo
from .utils import load_icon_from_candidates, mirrored_icon

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
        single_repeat_getter=None,
        toggle_single_repeat_fn=None,
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
        self._single_repeat_getter = single_repeat_getter or (lambda: False)
        self._toggle_single_repeat_fn = toggle_single_repeat_fn or (lambda: None)
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
        self._settings = QSettings("FleetSnowfluff", "MusicWindow")
        self._follow_count = 130
        self._is_following = False
        self._load_follow_state()

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
        self._progress_timer.setInterval(350)
        self._progress_timer.timeout.connect(self._update_progress_ui)
        self._progress_timer.start()

    def _ui_scale(self) -> float:
        return current_app_scale(QApplication.instance())

    def _px(self, value: int) -> int:
        return px(value, self._ui_scale())

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
                single_repeat_getter=self._single_repeat_getter,
                toggle_single_repeat_fn=self._toggle_single_repeat_fn,
                icon_dir=self._icon_dir,
            )
        return self._mini_bar

    def _load_jumpout_icon(self) -> QIcon | None:
        return load_icon_from_candidates(self._icon_dir, ("jumpout.png", "jumpout.PNG", "ic_jumpout.png"))

    def _load_main_button_icons(self) -> None:
        specs = {
            "import": ("import.png", "download.png", "ic_import.png"),
            "remove": ("remove.png", "delete.png", "ic_remove.png"),
            "play": ("play.png", "ic_play.png"),
            "pause": ("pause.png", "ic_pause.png"),
            "next": ("skip.png", "next.png", "ic_next.png"),
            "random": ("random.png", "shuffle.png", "ic_random.png"),
            "repeat": ("repeat.png", "repeat_one.png", "loop.png", "ic_repeat.png"),
            "volume": ("volume.png", "ic_volume.png"),
            "expand": ("expand.png", "exitfull.png", "ic_expand.png"),
        }
        for key, names in specs.items():
            icon = load_icon_from_candidates(self._icon_dir, names)
            if icon is not None:
                self._button_icons[key] = icon
        next_icon = self._button_icons.get("next")
        if next_icon is not None:
            prev_icon = mirrored_icon(next_icon)
            if prev_icon is not None:
                self._button_icons["prev"] = prev_icon
        if "prev" not in self._button_icons:
            fallback_prev = load_icon_from_candidates(self._icon_dir, ("prev.png", "previous.png", "ic_prev.png"))
            if fallback_prev is not None:
                self._button_icons["prev"] = fallback_prev

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
        scale = self._ui_scale()
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
        avatar_size = px(64, scale)
        avatar.setFixedSize(avatar_size, avatar_size)
        self.avatar_badge = avatar
        self._refresh_avatar_pixmap(avatar_size)
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
        self.now_playing.setMinimumHeight(px(96, scale))
        self.float_bar_button = QPushButton("")
        self.float_bar_button.setObjectName("navActionBtn")
        self.float_bar_button.setToolTip("切换到迷你播放器")
        self.float_bar_button.setFixedHeight(px(96, scale))
        self.float_bar_button.clicked.connect(self._toggle_mini_bar_from_ui)
        self._jumpout_icon = self._load_jumpout_icon()
        if self._jumpout_icon is not None:
            self.float_bar_button.setIcon(self._jumpout_icon)
            inset = px(4, scale)
            self.float_bar_button.setIconSize(self.float_bar_button.size() - QSize(inset, inset))
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
        self.volume_popup.resize(px(54, scale), px(170, scale))
        self._sync_volume_ui(max(0, min(100, int(self._get_volume_percent_fn()))))

        # Keep playlist visuals stable in fullscreen: avoid image letterboxing/stretching.
        self.track_list = PlaylistTreeWidget(None, panel)
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
        self.repeat_button = QPushButton("")
        self.repeat_button.setObjectName("actionBtn")
        self.repeat_button.setToolTip("单曲循环")
        self.repeat_button.clicked.connect(self._on_repeat_clicked)

        ctrl_row.addWidget(self.import_button)
        ctrl_row.addWidget(self.remove_button)
        ctrl_row.addStretch(1)
        ctrl_row.addWidget(self.prev_button)
        ctrl_row.addWidget(self.play_button)
        ctrl_row.addWidget(self.next_button)
        ctrl_row.addWidget(self.repeat_button)
        ctrl_row.addStretch(1)
        ctrl_row.addWidget(self.random_button)

        panel_layout.addLayout(now_playing_row)
        panel_layout.addLayout(progress_row)
        panel_layout.addWidget(self.track_list, 1)
        panel_layout.addLayout(ctrl_row)

        root.addWidget(nav)
        root.addWidget(panel, 1)

        self._track_list_background = (
            "background: qlineargradient("
            "x1:0, y1:0, x2:1, y2:1,"
            "stop:0 rgba(244, 249, 255, 0.78),"
            "stop:1 rgba(231, 241, 253, 0.68)"
            ");"
        )
        self._apply_main_stylesheet()
        self._load_main_button_icons()
        self._apply_main_button_icons()
        # Ensure volume icon state uses freshly loaded assets immediately.
        self._sync_volume_ui(self._get_volume_percent_fn())

    def _apply_main_stylesheet(self) -> None:
        scale = self._ui_scale()
        stylesheet = styles.build_main_stylesheet(scale, self._track_list_background)
        self.setStyleSheet(stylesheet)
        action_w = px(48, scale)
        action_h = px(40, scale)
        main_btn = px(48, scale)
        for btn in (self.import_button, self.remove_button, self.prev_button, self.next_button, self.repeat_button, self.random_button):
            btn.setFixedSize(action_w, action_h)
        self.play_button.setFixedSize(main_btn, main_btn)

    def _refresh_avatar_pixmap(self, avatar_size: int) -> None:
        self.avatar_badge.clearMask()
        if self._icon_path is not None and self._icon_path.exists():
            pixmap = QPixmap(str(self._icon_path))
            if not pixmap.isNull():
                self.avatar_badge.setPixmap(
                    pixmap.scaled(
                        avatar_size,
                        avatar_size,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self.avatar_badge.setScaledContents(True)
                return
        self.avatar_badge.setPixmap(QPixmap())
        self.avatar_badge.setText("飞")

    def _apply_scaled_ui(self) -> None:
        scale = self._ui_scale()
        avatar_size = px(64, scale)
        self.avatar_badge.setFixedSize(avatar_size, avatar_size)
        self._refresh_avatar_pixmap(avatar_size)
        self.now_playing.setMinimumHeight(px(96, scale))
        self.float_bar_button.setFixedHeight(px(96, scale))
        if self._jumpout_icon is not None:
            self.float_bar_button.setIcon(self._jumpout_icon)
            inset = px(4, scale)
            self.float_bar_button.setIconSize(self.float_bar_button.size() - QSize(inset, inset))
        self.volume_popup.resize(px(54, scale), px(170, scale))
        self._apply_main_stylesheet()
        self._apply_main_button_icons()
        self._sync_play_button()
        if self._last_now_playing_key is not None:
            self._refresh_now_playing(force=True)

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

    def _on_repeat_clicked(self) -> None:
        self._toggle_single_repeat_fn()

    def _sync_repeat_button(self) -> None:
        on = self._single_repeat_getter()
        self.repeat_button.setDown(on)
        self.repeat_button.setToolTip("单曲循环 (开)" if on else "单曲循环")

    def refresh_repeat_button(self) -> None:
        self._sync_repeat_button()

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
            icon_size = max(self._px(22), min(self.float_bar_button.width(), self.float_bar_button.height()) - self._px(14))
            apply_icon_button_layout(self.float_bar_button, icon_size=icon_size, edge_padding=18, min_edge=self.float_bar_button.height(), set_fixed=False)
        elif self._jumpout_icon is not None:
            self.float_bar_button.setIcon(self._jumpout_icon)
            self.float_bar_button.setText("")
            icon_size = max(self._px(22), min(self.float_bar_button.width(), self.float_bar_button.height()) - self._px(14))
            apply_icon_button_layout(self.float_bar_button, icon_size=icon_size, edge_padding=18, min_edge=self.float_bar_button.height(), set_fixed=False)
        else:
            self.float_bar_button.setIcon(QIcon())
            self.float_bar_button.setProperty("iconOnly", False)
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
            apply_icon_button_layout(self.volume_button, icon_size=self._px(20), edge_padding=12, min_edge=self._px(28), set_fixed=False)
        elif clamped == 0:
            self.volume_button.setIcon(QIcon())
            self.volume_button.setProperty("iconOnly", False)
            self.volume_button.setText("🔇")
        elif clamped < 45:
            self.volume_button.setIcon(QIcon())
            self.volume_button.setProperty("iconOnly", False)
            self.volume_button.setText("🔉")
        else:
            self.volume_button.setIcon(QIcon())
            self.volume_button.setProperty("iconOnly", False)
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

    def _refresh_now_playing(self, force: bool = False) -> None:
        current = self._current_track_fn()
        is_playing = bool(self._is_playing_fn())
        now_playing_key = (str(current) if current is not None else "", is_playing)
        if (not force) and now_playing_key == self._last_now_playing_key:
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
        icon_size = self._px(24)
        if is_playing and pause_icon is not None:
            self.play_button.setIcon(pause_icon)
            self.play_button.setText("")
            apply_icon_button_layout(self.play_button, icon_size=icon_size, edge_padding=16, min_edge=self.play_button.height(), set_fixed=False)
            return
        if (not is_playing) and play_icon is not None:
            self.play_button.setIcon(play_icon)
            self.play_button.setText("")
            apply_icon_button_layout(self.play_button, icon_size=icon_size, edge_padding=16, min_edge=self.play_button.height(), set_fixed=False)
            return
        self.play_button.setIcon(QIcon())
        self.play_button.setProperty("iconOnly", False)
        self.play_button.setText("⏸" if is_playing else "▶")

    def _update_follow_ui(self) -> None:
        self.follow_count_label.setText(f"已关注：{self._follow_count}")
        self.follow_button.setText("已关注" if self._is_following else "关注")

    def _load_follow_state(self) -> None:
        raw_following = self._settings.value("follow/is_following", self._is_following)
        if isinstance(raw_following, bool):
            self._is_following = raw_following
        elif isinstance(raw_following, (int, float)):
            self._is_following = bool(raw_following)
        elif isinstance(raw_following, str):
            self._is_following = raw_following.strip().lower() in {"1", "true", "yes", "on"}

        raw_count = self._settings.value("follow/count", self._follow_count)
        if isinstance(raw_count, int):
            self._follow_count = max(0, raw_count)
        elif isinstance(raw_count, float):
            self._follow_count = max(0, int(raw_count))
        elif isinstance(raw_count, str):
            try:
                self._follow_count = max(0, int(raw_count.strip()))
            except ValueError:
                pass

    def _save_follow_state(self) -> None:
        self._settings.setValue("follow/is_following", self._is_following)
        self._settings.setValue("follow/count", self._follow_count)

    def _on_follow_clicked(self) -> None:
        if self._is_following:
            self._is_following = False
            self._follow_count = max(0, self._follow_count - 1)
        else:
            self._is_following = True
            self._follow_count += 1
        self._update_follow_ui()
        self._save_follow_state()

    def _apply_main_button_icons(self) -> None:
        icon_size = self._px(24)

        def apply(button: QPushButton, key: str, fallback: str, size: int = 24) -> None:
            icon = self._button_icons.get(key)
            if icon is not None:
                button.setIcon(icon)
                button.setText("")
                resolved = icon_size if size == 24 else self._px(size)
                apply_icon_button_layout(button, icon_size=resolved, edge_padding=16, min_edge=max(button.height(), self._px(38)), set_fixed=False)
            else:
                button.setIcon(QIcon())
                button.setProperty("iconOnly", False)
                button.setText(fallback)

        apply(self.import_button, "import", "⤓")
        apply(self.remove_button, "remove", "⌫")
        apply(self.prev_button, "prev", "⏮")
        apply(self.next_button, "next", "⏭")
        apply(self.repeat_button, "repeat", "🔁")
        apply(self.random_button, "random", "🔀")
        self._sync_play_button()
        self._sync_repeat_button()

    def _set_now_playing_text(self, title: str, artist: str, album: str) -> None:
        title_html = html.escape((title or "-").strip() or "-")
        artist_html = html.escape((artist or "-").strip() or "-")
        album_html = html.escape((album or "-").strip() or "-")
        title_size = self._px(19)
        artist_size = self._px(13)
        album_size = self._px(12)
        self.now_playing.setText(
            (
                "<div style='line-height:1.08;'>"
                f"<div style='font-size:{title_size}px; font-weight:800; color:#c13c83;'>{title_html}</div>"
                f"<div style='margin-top:2px; font-size:{artist_size}px; color:#ff5b9d;'>{artist_html}</div>"
                f"<div style='margin-top:1px; font-size:{album_size}px; color:#5f5f5f;'>{album_html}</div>"
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
        self._save_follow_state()
        if self.volume_popup.isVisible():
            self.volume_popup.hide()
        self._hide_mini_bar()
        self._stop_playback_fn()
        self._sync_play_button()
        self._sync_float_bar_button()
        super().closeEvent(event)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ScreenChangeInternal:
            self._apply_scaled_ui()
        return super().event(event)

    def showEvent(self, event) -> None:
        self._apply_scaled_ui()
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