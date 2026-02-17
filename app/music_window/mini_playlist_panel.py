"""Mini playlist popup panel for track selection."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QDialog, QFrame, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from app.utils.ui_scale import current_app_scale

from . import styles
from .types import TrackInfo


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

        self._apply_scaled_stylesheet()

    def _ui_scale(self) -> float:
        return current_app_scale(QApplication.instance())

    def _apply_scaled_stylesheet(self) -> None:
        scale = self._ui_scale()
        self.setStyleSheet(styles.build_mini_playlist_stylesheet(scale))

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ScreenChangeInternal:
            self._apply_scaled_stylesheet()
        return super().event(event)

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
