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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWindowOpacity(1.0)
        self.resize(320, 320)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._frame_label = QLabel(self)
        self._frame_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(self._frame_label)
        self._apply_scene_visual_mode(desktop_scene_mode=False)

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
        if desktop_scene_mode:
            # Use normal frameless window (not Tool) to avoid macOS titlebar-space
            # quirks and ensure the top area below status bar is fully black-filled.
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.Window
                | Qt.WindowType.WindowStaysOnTopHint
            )
        else:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowStaysOnTopHint
            )
        self._frame_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self._apply_scene_visual_mode(desktop_scene_mode=desktop_scene_mode)
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(media_path)))
        if desktop_scene_mode:
            # Native macOS fullscreen cutscene mode.
            self.showFullScreen()
        else:
            self.setGeometry(target_geometry)
            self.show()
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
        # Horizontal-fill strategy with centered letterbox:
        # 1) scale by window width
        # 2) keep aspect ratio
        # 3) center vertically, leaving black bars top/bottom when needed.
        target_w = max(1, self.width())
        scaled = self._last_frame_pixmap.scaledToWidth(
            target_w,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Guard for very tall sources: never crop.
        if scaled.height() > self.height():
            scaled = self._last_frame_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._frame_label.setPixmap(scaled)

    def _apply_scene_visual_mode(self, desktop_scene_mode: bool) -> None:
        if desktop_scene_mode:
            # Real cinematic black bars require an opaque black backing layer.
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
            self._frame_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self.setStyleSheet("background-color: #000000;")
            self._frame_label.setStyleSheet("background-color: #000000;")
            return
        # Keep transparent composition for non-desktop transform overlay mode.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._frame_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self._frame_label.setStyleSheet("background: transparent;")

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
