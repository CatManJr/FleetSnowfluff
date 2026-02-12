from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QKeyEvent, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout


class TransformWindow(QDialog):
    playbackFinished = Signal()
    playbackFailed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._emitted_finished = False
        self._desktop_scene_mode = False
        self._last_frame_pixmap: QPixmap | None = None
        self.setWindowTitle("爱弥斯，变身！")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.resize(320, 320)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._frame_label = QLabel(self)
        self._frame_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._frame_label.setStyleSheet("background: transparent;")
        self._frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._frame_label)

        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(1.0)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self._video_sink = QVideoSink(self)
        self._video_sink.videoFrameChanged.connect(self._on_video_frame_changed)
        self._player.setVideoOutput(self._video_sink)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._player.errorOccurred.connect(self._on_playback_error)

    def play_media(self, media_path: Path, target_geometry, desktop_scene_mode: bool = False) -> None:
        self._emitted_finished = False
        self._desktop_scene_mode = desktop_scene_mode
        self._last_frame_pixmap = None
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, not desktop_scene_mode)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnBottomHint, desktop_scene_mode)
        if desktop_scene_mode:
            self._frame_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        else:
            self._frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(media_path)))
        self.setGeometry(target_geometry)
        self.show()
        if not desktop_scene_mode:
            self.raise_()
            self.activateWindow()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self._player.play()

    def _on_media_status_changed(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.close()
            return
        if status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._emit_failure("视频解码失败（媒体无效）")
            self.close()

    def _on_playback_error(self, _error, error_string: str) -> None:
        self._emit_failure(error_string or "视频播放失败")
        self.close()

    def _on_video_frame_changed(self, frame) -> None:
        if not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return
        self._last_frame_pixmap = pixmap
        self._apply_frame_pixmap()

    def _apply_frame_pixmap(self) -> None:
        if self._last_frame_pixmap is None or self._last_frame_pixmap.isNull():
            return
        # Keep original aspect ratio in both modes (no crop/stretch).
        mode = Qt.AspectRatioMode.KeepAspectRatio
        scaled = self._last_frame_pixmap.scaled(
            self.size(),
            mode,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._frame_label.setPixmap(scaled)

    def _emit_failure(self, message: str) -> None:
        if self._emitted_finished:
            return
        self._emitted_finished = True
        self.playbackFailed.emit(message)
        self.playbackFinished.emit()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_frame_pixmap()

    def closeEvent(self, event) -> None:
        self._player.stop()
        self._frame_label.clear()
        self._last_frame_pixmap = None
        if not self._emitted_finished:
            self._emitted_finished = True
            self.playbackFinished.emit()
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)
