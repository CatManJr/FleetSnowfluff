from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

from PySide6.QtCore import QEvent, QPoint, QSettings, QSignalBlocker
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QCloseEvent,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
)
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)


class TrackInfo(NamedTuple):
    path: Path
    title: str
    artist: str
    album: str


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
        self._timer.setInterval(28)
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
                font-family: Menlo, Monaco, "SF Mono";
                font-size: 12px;
            }
            QListWidget#playlistList {
                border: 1px solid #ffd3e6;
                border-radius: 10px;
                background: #ffffff;
                color: #2a1f2a;
                font-family: Menlo, Monaco, "SF Mono";
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
        self._settings = QSettings("FleetSnowfluff", "MusicWindow")
        self._drag_offset: QPoint | None = None
        self._has_custom_pos = False

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("飞行雪绒电台 - Mini")
        self.resize(460, 70)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.container = QFrame(self)
        self.container.setObjectName("miniCard")
        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(12, 10, 12, 10)
        container_layout.setSpacing(8)

        self.track_label = MarqueeLabel("当前播放：-", self.container)
        self.track_label.setObjectName("miniTitle")
        self.track_label.setMinimumWidth(220)

        self.prev_button = QPushButton("⏮")
        self.prev_button.setObjectName("miniBtn")
        self.prev_button.setToolTip("上一首")
        self.prev_button.clicked.connect(self._on_prev_clicked)

        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("miniBtn")
        self.play_button.setToolTip("播放 / 暂停")
        self.play_button.clicked.connect(self._on_toggle_clicked)

        self.next_button = QPushButton("⏭")
        self.next_button.setObjectName("miniBtn")
        self.next_button.setToolTip("下一首")
        self.next_button.clicked.connect(self._on_next_clicked)

        self.playlist_button = QPushButton("☰")
        self.playlist_button.setObjectName("miniBtn")
        self.playlist_button.setToolTip("播放列表")
        self.playlist_button.clicked.connect(self._show_playlist_menu)

        self.restore_button = QPushButton("▢")
        self.restore_button.setObjectName("miniBtn")
        self.restore_button.setToolTip("展开播放器")
        self.restore_button.clicked.connect(self._restore_main_fn)

        container_layout.addWidget(self.track_label, 1)
        container_layout.addWidget(self.prev_button)
        container_layout.addWidget(self.play_button)
        container_layout.addWidget(self.next_button)
        container_layout.addWidget(self.playlist_button)
        container_layout.addWidget(self.restore_button)
        root.addWidget(self.container)

        self._playlist_panel = MiniPlaylistPanel(
            on_pick_track_fn=self._play_from_menu,
            extract_track_info_fn=self._extract_track_info_fn,
            parent=self,
        )

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(73, 22, 54, 90))
        self.container.setGraphicsEffect(shadow)

        self.setStyleSheet(
            """
            QDialog {
                background: transparent;
                border: none;
            }
            QFrame#miniCard {
                background: rgba(255, 247, 251, 0.95);
                border: 2px solid #ffc2de;
                border-radius: 18px;
            }
            QLabel#miniTitle {
                color: #6c2e4e;
                font-family: Menlo, Monaco, "SF Mono";
                font-size: 13px;
                font-weight: 700;
                padding: 4px 8px;
                background: rgba(255, 239, 247, 0.72);
                border-radius: 10px;
            }
            QPushButton#miniBtn {
                min-width: 36px;
                min-height: 32px;
                border-radius: 10px;
                color: #8d365d;
                font-size: 16px;
                border: 1px solid #ff9dc6;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #fff8fc,
                    stop:1 #ffd4ea
                );
            }
            QPushButton#miniBtn:pressed {
                background: #ffcae4;
            }
            """
        )
        self._restore_saved_position()
        self.set_keep_on_top(True)

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
            label_text = "当前播放：-"
        else:
            info = self._extract_track_info_fn(current)
            label_text = f"{info.title} · {info.artist}"
        self.track_label.setMarqueeText(label_text)
        self.play_button.setText("⏸" if self._is_playing_fn() else "▶")
        self.playlist_button.setEnabled(bool(self._list_tracks_fn()))
        self._update_compact_width(label_text)

    def _update_compact_width(self, label_text: str) -> None:
        metrics = QFontMetrics(self.track_label.font())
        label_target = metrics.horizontalAdvance(label_text) + 22
        control_width = 6 * 42  # 6 icon buttons
        target_width = label_target + control_width + 56
        screen = QGuiApplication.primaryScreen()
        max_width = 840
        if screen is not None:
            max_width = max(420, screen.availableGeometry().width() - 36)
        new_width = max(420, min(max_width, target_width))
        if new_width != self.width():
            self.resize(new_width, self.height())
            self.track_label.setMinimumWidth(max(200, new_width - control_width - 86))

    def _show_playlist_menu(self) -> None:
        tracks = list(self._list_tracks_fn())
        if self._playlist_panel.isVisible():
            self._playlist_panel.hide()
            return
        self._playlist_panel.set_tracks(tracks=tracks, current_track=self._current_track_fn())
        panel_width = min(max(420, self.width()), 620)
        self._playlist_panel.resize(panel_width, 300)
        anchor = self.playlist_button.mapToGlobal(QPoint(0, self.playlist_button.height() + 6))
        self._playlist_panel.move(anchor.x() - panel_width + self.playlist_button.width(), anchor.y())
        self._playlist_panel.show()
        self._playlist_panel.raise_()

    def _play_from_menu(self, track_path: Path) -> None:
        self._play_track_fn(track_path)
        self.refresh_state()

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
        self._playlist_panel.hide()
        super().hideEvent(event)


class MusicWindow(QDialog):
    def __init__(
        self,
        icon_path: Path | None,
        playlist_bg_path: Path | None,
        list_tracks_fn,
        import_tracks_fn,
        start_random_loop_fn,
        play_track_fn,
        play_next_fn,
        play_prev_fn,
        current_track_fn,
        toggle_play_pause_fn,
        is_playing_fn,
        stop_playback_fn,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._icon_path = icon_path
        self._playlist_bg_path = playlist_bg_path
        self._list_tracks_fn = list_tracks_fn
        self._import_tracks_fn = import_tracks_fn
        self._start_random_loop_fn = start_random_loop_fn
        self._play_track_fn = play_track_fn
        self._play_next_fn = play_next_fn
        self._play_prev_fn = play_prev_fn
        self._current_track_fn = current_track_fn
        self._toggle_play_pause_fn = toggle_play_pause_fn
        self._is_playing_fn = is_playing_fn
        self._stop_playback_fn = stop_playback_fn
        self._tracks: list[Path] = []
        self._track_infos: list[TrackInfo] = []
        self._mini_bar: MiniPlayerBar | None = None

        self.setWindowTitle("飞行雪绒电台")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(390, 560)
        self._build_ui()
        self.refresh_tracks()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1200)
        self._refresh_timer.timeout.connect(self._refresh_now_playing)
        self._refresh_timer.start()

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
            )
        return self._mini_bar

    def _show_mini_bar(self) -> None:
        mini = self._ensure_mini_bar()
        mini.set_keep_on_top(True)
        mini.refresh_state()
        if not mini.has_custom_position():
            mini.move_to_default_position()
        mini.show()
        mini.raise_()

    def _hide_mini_bar(self) -> None:
        if self._mini_bar is not None:
            self._mini_bar.set_keep_on_top(False)
            self._mini_bar.hide()

    def _restore_from_mini_bar(self) -> None:
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
        avatar.setFixedSize(42, 42)
        if self._icon_path is not None and self._icon_path.exists():
            pixmap = QPixmap(str(self._icon_path))
            if not pixmap.isNull():
                avatar.setPixmap(
                    pixmap.scaled(
                        42,
                        42,
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

        panel = QFrame(self)
        panel.setObjectName("panelCard")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)
        panel_layout.setSpacing(8)

        self.now_playing = QLabel("当前播放：-")
        self.now_playing.setObjectName("nowPlaying")

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

        ctrl_row1 = QHBoxLayout()
        self.import_button = QPushButton("⤓")
        self.import_button.setObjectName("actionBtn")
        self.import_button.setToolTip("导入曲库")
        self.import_button.clicked.connect(self._on_import_clicked)
        self.random_button = QPushButton("🔀")
        self.random_button.setObjectName("actionBtn")
        self.random_button.setToolTip("随机循环")
        self.random_button.clicked.connect(self._on_random_clicked)
        ctrl_row1.addWidget(self.import_button)
        ctrl_row1.addWidget(self.random_button)

        ctrl_row2 = QHBoxLayout()
        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("actionBtn")
        self.play_button.setToolTip("播放 / 暂停")
        self.play_button.clicked.connect(self._on_toggle_play_pause)
        self.prev_button = QPushButton("⏮")
        self.prev_button.setObjectName("actionBtn")
        self.prev_button.setToolTip("上一首")
        self.prev_button.clicked.connect(self._play_prev_fn)
        self.next_button = QPushButton("⏭")
        self.next_button.setObjectName("actionBtn")
        self.next_button.setToolTip("下一首")
        self.next_button.clicked.connect(self._play_next_fn)
        ctrl_row2.addWidget(self.play_button)
        ctrl_row2.addWidget(self.prev_button)
        ctrl_row2.addWidget(self.next_button)

        panel_layout.addWidget(self.now_playing)
        panel_layout.addWidget(self.track_list, 1)
        panel_layout.addLayout(ctrl_row1)
        panel_layout.addLayout(ctrl_row2)

        root.addWidget(nav)
        root.addWidget(panel, 1)

        track_list_background = "background: transparent;"

        stylesheet = """
            QDialog {
                background: #fff7fb;
                color: #2a1f2a;
            }
            QFrame#navBar {
                background: #ffffff;
                border-bottom: 1px solid #ffd3e6;
            }
            QLabel#avatarBadge {
                min-width: 42px;
                min-height: 42px;
                max-width: 42px;
                max-height: 42px;
                border-radius: 21px;
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
            QFrame#panelCard {
                background: #fff7fb;
                border: none;
            }
            QLabel#nowPlaying {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 238, 247, 0.98),
                    stop:1 rgba(255, 220, 237, 0.98)
                );
                border: 2px solid #ffb7d6;
                border-radius: 12px;
                padding: 8px;
                color: #6c2e4e;
                font-family: Menlo, Monaco, "SF Mono";
                font-size: 13px;
            }
            QTreeWidget#trackList {
                __TRACK_LIST_BACKGROUND__
                border: 2px solid #ffd3e6;
                border-radius: 14px;
                padding: 4px;
                font-family: Menlo, Monaco, "SF Mono";
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
                background: #fff0f7;
                border: none;
                border-bottom: 1px solid #ffd3e6;
                padding: 6px 8px;
                color: #8d365d;
                font-family: Menlo, Monaco, "SF Mono";
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton#actionBtn {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #fff8fc,
                    stop:0.55 #ffdff0,
                    stop:1 #ffc9e5
                );
                border: 2px solid #ff9dc6;
                border-radius: 14px;
                color: #8d365d;
                min-width: 48px;
                min-height: 40px;
                padding: 4px;
                font-family: Menlo, Monaco, "SF Mono";
                font-size: 21px;
                font-weight: 600;
            }
            QPushButton#actionBtn:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #fffafd,
                    stop:0.55 #ffe8f5,
                    stop:1 #ffd5eb
                );
            }
            QPushButton#actionBtn:pressed {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #ffd2e8,
                    stop:1 #ffb7d9
                );
                color: #7a2b4d;
            }
            QPushButton#actionBtn:disabled {
                background: #f2e4eb;
                border: 2px solid #e6ccd8;
                color: #b48ca3;
            }
            """
        self.setStyleSheet(stylesheet.replace("__TRACK_LIST_BACKGROUND__", track_list_background))

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

    def _on_random_clicked(self) -> None:
        self._start_random_loop_fn()
        self._refresh_now_playing()
        self._sync_play_button()

    def _on_toggle_play_pause(self) -> None:
        self._toggle_play_pause_fn()
        self._refresh_now_playing()
        self._sync_play_button()

    def refresh_tracks(self) -> None:
        self._tracks = list(self._list_tracks_fn())
        self.track_list.clear()
        self._track_infos = [self._extract_track_info(p) for p in self._tracks]
        title_font = QFont("Menlo")
        title_font.setBold(True)
        title_font.setPointSize(16)
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
        if current is None:
            self.now_playing.setText("当前播放：-")
            self._sync_current_track_highlight()
            if self._mini_bar is not None:
                self._mini_bar.refresh_state()
            return
        info = self._extract_track_info(current)
        self.now_playing.setText(f"当前播放：{info.title}  ·  {info.artist}")
        self._sync_current_track_highlight()
        if self._mini_bar is not None:
            self._mini_bar.refresh_state()

    def _sync_play_button(self) -> None:
        is_playing = bool(self._is_playing_fn())
        self.play_button.setText("⏸" if is_playing else "▶")

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
        self.random_button.setEnabled(has_tracks)
        self.prev_button.setEnabled(has_tracks)
        self.next_button.setEnabled(has_tracks)
        self.play_button.setEnabled(has_tracks and (has_selected or self._current_track_fn() is not None))

    def _extract_track_info(self, track_path: Path) -> TrackInfo:
        title = track_path.stem
        artist = "未知艺术家"
        album = "未知专辑"
        try:
            from mutagen import File as MutagenFile

            audio = MutagenFile(track_path, easy=True)
            if audio is not None:
                title = self._pick_first(audio.get("title")) or title
                artist = self._normalize_artist_display(audio.get("artist")) or artist
                album = self._pick_first(audio.get("album")) or album
        except Exception:
            pass
        return TrackInfo(path=track_path, title=title, artist=artist, album=album)

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
        self._hide_mini_bar()
        self._stop_playback_fn()
        self._sync_play_button()
        super().closeEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                self._show_mini_bar()
            else:
                self._hide_mini_bar()
                self._refresh_now_playing()
                self._apply_column_widths()
                self._update_control_states()
                self._sync_play_button()
        super().changeEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_column_widths()
