from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from PySide6.QtCore import QEvent, QSignalBlocker
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QCloseEvent, QColor, QFont, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
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
            painter.drawTiledPixmap(viewport_rect, self._bg_pixmap)
        super().paintEvent(event)


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

        self.setWindowTitle("飞讯播放器")
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
        title = QLabel("飞讯播放器")
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
            return
        info = self._extract_track_info(current)
        self.now_playing.setText(f"当前播放：{info.title}  ·  {info.artist}")
        self._sync_current_track_highlight()

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
                artist = self._pick_first(audio.get("artist")) or artist
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

    def closeEvent(self, event: QCloseEvent) -> None:
        self._stop_playback_fn()
        self._sync_play_button()
        super().closeEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.WindowStateChange and not self.isMinimized():
            self._refresh_now_playing()
            self._apply_column_widths()
            self._update_control_states()
            self._sync_play_button()
        super().changeEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_column_widths()
