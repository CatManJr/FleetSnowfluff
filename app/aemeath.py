from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QCursor, QGuiApplication, QMouseEvent, QMovie, QPixmap, QTransform
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QMessageBox

from .chat_window import ChatWindow
from .seal_widget import SealWidget
from .settings_dialog import SettingsDialog


class Aemeath(QLabel):
    def __init__(self, resources_dir: Path) -> None:
        super().__init__()
        self.resources_dir = resources_dir
        self._config_path = self._resolve_config_path()
        self._api_key = ""
        self.idle_ids = [1, 2, 3, 4, 5, 6, 7]
        self.hover_id = 4
        self.seal_id = 8

        self._drag_offset: QPoint | None = None
        self._mouse_pressed_global: QPoint | None = None
        self._has_dragged = False
        self._right_click_pending = False
        self._is_hovering = False
        self._current_movie_id: int | None = None
        self._current_movie: QMovie | None = None
        self._mirror_h = False
        self._seal_widgets: list[SealWidget] = []
        self._terminal_open = False
        self._visibility_suppressed = False
        self._last_fullscreen_state = False
        self._last_fullscreen_checked_at = 0.0
        self._chat_window: ChatWindow | None = None

        self._movies = {}
        self._load_movies()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        if sys.platform == "darwin":
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        self.setMouseTracking(True)

        self._set_movie(random.choice(self.idle_ids))
        self._place_initial_position()
        self.show()

        self.idle_switch_timer = QTimer(self)
        self.idle_switch_timer.setInterval(4500)
        self.idle_switch_timer.timeout.connect(self._switch_idle_animation)
        self.idle_switch_timer.start()

        self._load_config()
        self._setup_audio()
        self._setup_menu()
        # Keep it simple: pin topmost once at startup, no runtime stack polling.
        QTimer.singleShot(0, self._pin_topmost_once)
        QTimer.singleShot(300, self._pin_topmost_once)

    def _resolve_config_path(self) -> Path:
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "Aemeath" / "settings.json"
        if sys.platform.startswith("win"):
            appdata = os.environ.get("APPDATA", str(Path.home()))
            return Path(appdata) / "Aemeath" / "settings.json"
        return Path.home() / ".config" / "aemeath" / "settings.json"

    def _load_config(self) -> None:
        if not self._config_path.exists():
            return
        try:
            data = json.loads(self._config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self._api_key = str(data.get("deepseek_api_key", "")).strip()

    def _save_config(self) -> bool:
        payload = {"deepseek_api_key": self._api_key}
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True
        except OSError:
            return False

    def _show_settings_dialog(self) -> None:
        dialog = SettingsDialog(api_key=self._api_key, parent=None)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return
        self._api_key = dialog.api_key()
        if self._save_config():
            QMessageBox.information(self, "保存成功", "API Key 已保存，后续将自动读取。")
            return
        QMessageBox.warning(self, "保存失败", "无法写入配置文件，请检查目录权限。")

    def _load_movies(self) -> None:
        for idx in [*self.idle_ids, self.hover_id, self.seal_id]:
            movie_path = self.resources_dir / f"{idx}.gif"
            if not movie_path.exists():
                raise FileNotFoundError(f"Missing resource: {movie_path}")
            movie = QMovie(str(movie_path))
            if not movie.frameRect().isValid():
                movie.jumpToFrame(0)
            source_size = movie.frameRect().size()
            if source_size.isValid():
                scaled_size = QSize(
                    max(1, int(source_size.width() * 0.75)),
                    max(1, int(source_size.height() * 0.75)),
                )
                movie.setScaledSize(scaled_size)
            self._movies[idx] = movie

    def _set_movie(self, movie_id: int) -> None:
        if self._current_movie_id == movie_id:
            return
        if self._current_movie is not None:
            self._current_movie.stop()
            try:
                self._current_movie.frameChanged.disconnect(self._on_movie_frame_changed)
            except (TypeError, RuntimeError):
                pass

        movie = self._movies[movie_id]
        self._current_movie_id = movie_id
        if movie_id == 1:
            self._mirror_h = random.choice([False, True])
        self._current_movie = movie
        movie.frameChanged.connect(self._on_movie_frame_changed)
        movie.start()
        if not movie.frameRect().isValid():
            movie.jumpToFrame(0)
        self._on_movie_frame_changed()

    def _on_movie_frame_changed(self, *_args) -> None:
        if self._current_movie is None:
            return
        frame: QPixmap = self._current_movie.currentPixmap()
        if frame.isNull():
            return

        if self._mirror_h:
            frame = frame.transformed(QTransform().scale(-1, 1))
        self.setPixmap(frame)
        self.resize(frame.size())

    def _place_initial_position(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = area.left() + int(area.width() * 0.1)
        y = area.bottom() - self.height() - 80
        self.move(x, y)

    def _switch_idle_animation(self) -> None:
        if self._is_hovering:
            return
        self._set_movie(random.choice(self.idle_ids))
        self._randomize_idle_position()

    def _randomize_idle_position(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        width = max(1, self.width())
        height = max(1, self.height())

        edge_mode = random.random() < 0.45
        if edge_mode:
            side = random.choice(["left", "right", "top", "bottom"])
            if side == "left":
                x = area.left() - int(width * 0.35)
                y = random.randint(area.top(), max(area.top(), area.bottom() - height))
            elif side == "right":
                x = area.right() - int(width * 0.65)
                y = random.randint(area.top(), max(area.top(), area.bottom() - height))
            elif side == "top":
                x = random.randint(area.left(), max(area.left(), area.right() - width))
                y = area.top() - int(height * 0.35)
            else:
                x = random.randint(area.left(), max(area.left(), area.right() - width))
                y = area.bottom() - int(height * 0.65)
        else:
            x = random.randint(area.left(), max(area.left(), area.right() - width))
            y = random.randint(area.top(), max(area.top(), area.bottom() - height))

        self.move(x, y)
        self._apply_edge_orientation(area)

    def _apply_edge_orientation(self, area: QRect) -> None:
        if self._current_movie_id == 1:
            self._mirror_h = random.choice([False, True])
            self._on_movie_frame_changed()
            return

        margin = 32
        near_left = self.x() <= area.left() + margin
        near_right = self.x() + self.width() >= area.right() - margin

        if near_left:
            self._mirror_h = False
        elif near_right:
            self._mirror_h = True
        else:
            self._mirror_h = random.choice([False, True])
        self._on_movie_frame_changed()

    def _seal_closed(self, seal_widget: SealWidget) -> None:
        if seal_widget in self._seal_widgets:
            self._seal_widgets.remove(seal_widget)

    def _clear_seals(self) -> None:
        for seal in list(self._seal_widgets):
            seal.close()
        self._seal_widgets.clear()

    def _spawn_seals(self, count: int) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self._clear_seals()
        for _ in range(count):
            seal = SealWidget(
                movie_path=self.resources_dir / f"{self.seal_id}.gif",
                geometry=area,
                on_closed=self._seal_closed,
            )
            self._seal_widgets.append(seal)

    def _setup_audio(self) -> None:
        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(0.7)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)

    def _setup_menu(self) -> None:
        self._menu = QMenu(self)
        self._chat_action = self._menu.addAction("和小爱聊天")
        self._transform_action = self._menu.addAction("爱弥斯，变身！")
        self._hacker_action = self._menu.addAction("黑客爱弥斯！")
        self._seal_action = self._menu.addAction("")
        self._music_action = self._menu.addAction("你看，又唱")
        self._exit_action = self._menu.addAction("拜拜～爱弥斯")

        self._chat_action.triggered.connect(self._chat_with_xiaoai)
        self._transform_action.triggered.connect(self._transform_emis)
        self._hacker_action.triggered.connect(self._launch_hacker_terminal)
        self._seal_action.triggered.connect(self._toggle_seals)
        self._music_action.triggered.connect(self._play_random_music)
        self._exit_action.triggered.connect(self._quit_app)

    def _setup_terminal_monitor(self) -> None:
        # Initialize with current state to avoid hiding immediately
        # when the app itself is started from an already-open terminal.
        self._terminal_open = self._is_terminal_open()
        self._terminal_timer = QTimer(self)
        # Keep polling low-frequency to reduce osascript overhead.
        self._terminal_timer.setInterval(6000)
        self._terminal_timer.timeout.connect(self._sync_terminal_visibility)
        self._terminal_timer.start()

    def _pin_topmost_once(self) -> None:
        self.show()
        self.raise_()
        for seal in self._seal_widgets:
            seal.show()
            seal.raise_()

    def _sync_terminal_visibility(self) -> None:
        terminal_open = self._is_terminal_open()
        fullscreen_open = self._is_foreground_fullscreen_cached()
        terminal_just_opened = terminal_open and not self._terminal_open
        self._terminal_open = terminal_open

        should_hide = terminal_open or fullscreen_open
        if should_hide == self._visibility_suppressed:
            if terminal_just_opened:
                self._print_terminal_greeting()
            return

        self._visibility_suppressed = should_hide
        if should_hide:
            if self.isVisible():
                self.hide()
            for seal in self._seal_widgets:
                if seal.isVisible():
                    seal.hide()
            if terminal_just_opened:
                self._print_terminal_greeting()
            return

        self.show()
        self.raise_()
        for seal in self._seal_widgets:
            seal.show()
            seal.raise_()

    def _is_foreground_fullscreen_cached(self) -> bool:
        now = time.monotonic()
        # AX queries are expensive; cache for a short period.
        if now - self._last_fullscreen_checked_at < 3.5:
            return self._last_fullscreen_state
        self._last_fullscreen_checked_at = now
        self._last_fullscreen_state = self._is_foreground_fullscreen()
        return self._last_fullscreen_state

    def _is_foreground_fullscreen(self) -> bool:
        if sys.platform != "darwin":
            return False

        script = """
        tell application "System Events"
            try
                set frontProc to first application process whose frontmost is true
                if (count of windows of frontProc) is 0 then return "0"
                set isFS to value of attribute "AXFullScreen" of window 1 of frontProc
                if isFS is true then
                    return "1"
                end if
            end try
        end tell
        return "0"
        """
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=0.8,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0 and result.stdout.strip() == "1"

    def _is_terminal_open(self) -> bool:
        if sys.platform != "darwin":
            return False

        script = """
        set hasTerminalWindow to false
        set hasITermWindow to false

        tell application "System Events"
            if exists process "Terminal" then
                tell application "Terminal"
                    if (count of windows) > 0 then set hasTerminalWindow to true
                end tell
            end if
            if exists process "iTerm2" then
                tell application "iTerm2"
                    if (count of windows) > 0 then set hasITermWindow to true
                end tell
            end if
        end tell

        if hasTerminalWindow or hasITermWindow then
            return "1"
        else
            return "0"
        end if
        """
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=0.8,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0 and result.stdout.strip() == "1"

    def _print_terminal_greeting(self) -> None:
        if sys.platform != "darwin":
            return

        tty_path = self._get_active_terminal_tty()
        if not tty_path:
            return

        # 为了降低延迟，尝试用异步线程写入 tty，避免阻塞主线程
        import threading

        def write_greeting(current_tty_path: str) -> None:
            try:
                # 利用os.open和os.write高效写入，避免缓冲区和Python高级I/O带来的额外开销
                import os
                fd = os.open(current_tty_path, os.O_WRONLY | os.O_NOCTTY)
                try:
                    msg = "电子幽灵登场！Ciallo～(∠・ω< )⌒★"
                    os.write(fd, msg.encode("utf-8", errors="ignore"))
                finally:
                    os.close(fd)
            except OSError:
                pass

        threading.Thread(target=write_greeting, args=(tty_path,), daemon=True).start()

    def _get_active_terminal_tty(self) -> str:
        terminal_script = """
        try
            tell application "Terminal"
                if (count of windows) > 0 then
                    return tty of selected tab of front window
                end if
            end tell
        end try
        return ""
        """
        terminal_tty = self._run_osascript(terminal_script)
        if terminal_tty:
            return terminal_tty

        iterm_script = """
        try
            tell application "iTerm2"
                if (count of windows) > 0 then
                    return tty of current session of current window
                end if
            end tell
        end try
        return ""
        """
        return self._run_osascript(iterm_script)

    def _run_osascript(self, script: str) -> str:
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=0.8,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    def _refresh_menu_labels(self) -> None:
        self._seal_action.setText("拜拜海豹" if self._seal_widgets else "召唤雪绒海豹")

    def _show_menu(self, global_pos: QPoint) -> None:
        self._refresh_menu_labels()
        self._menu.exec(global_pos)

    def _chat_with_xiaoai(self) -> None:
        if self._chat_window is None:
            self._chat_window = ChatWindow(
                config_dir=self._config_path.parent,
                api_key_getter=lambda: self._api_key,
                parent=None,
            )
            self._chat_window.destroyed.connect(self._on_chat_window_destroyed)
        self._chat_window.show()
        self._chat_window.raise_()
        self._chat_window.activateWindow()

    def _on_chat_window_destroyed(self) -> None:
        self._chat_window = None

    def _transform_emis(self) -> None:
        QMessageBox.information(
            self,
            "待实现",
            "“爱弥斯，变身！”待你制作正常形态动画后接入。",
        )

    def _launch_hacker_terminal(self) -> None:
        start_dir = self.resources_dir.parent / "src"
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-a", "Terminal", str(start_dir)])
            QTimer.singleShot(450, self._print_terminal_greeting)
            return
        if sys.platform.startswith("win"):
            subprocess.Popen("start cmd", shell=True)
            return
        try:
            subprocess.Popen(["x-terminal-emulator"])
        except FileNotFoundError:
            QMessageBox.warning(self, "启动失败", "未找到可用终端，请手动启动 terminal。")

    def _toggle_seals(self) -> None:
        if self._seal_widgets:
            self._clear_seals()
            return
        self._spawn_seals(random.randint(1, 6))

    def _play_random_music(self) -> None:
        music_dir = self.resources_dir / "music"
        if not music_dir.exists():
            QMessageBox.information(
                self,
                "暂无音乐",
                "未找到 resources/music 目录，上传音乐后可播放。",
            )
            return

        supported_exts = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}
        tracks = [p for p in music_dir.iterdir() if p.suffix.lower() in supported_exts]
        if not tracks:
            QMessageBox.information(
                self,
                "暂无音乐",
                "resources/music 目录中没有可播放的音乐文件。",
            )
            return

        track = random.choice(tracks)
        self._player.setSource(QUrl.fromLocalFile(str(track)))
        self._player.play()

    def _quit_app(self) -> None:
        self._clear_seals()
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def enterEvent(self, event) -> None:
        self._is_hovering = True
        self._set_movie(self.hover_id)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._is_hovering = False
        self._set_movie(random.choice(self.idle_ids))
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            # Open settings on release to avoid interrupting Qt mouse state.
            self._right_click_pending = True
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._right_click_pending = False
            self._mouse_pressed_global = event.globalPosition().toPoint()
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._has_dragged = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            current_pos = event.globalPosition().toPoint()
            if self._mouse_pressed_global is not None:
                if (current_pos - self._mouse_pressed_global).manhattanLength() > 4:
                    self._has_dragged = True
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            if self._right_click_pending:
                self._show_settings_dialog()
            self._right_click_pending = False
            self._drag_offset = None
            self._mouse_pressed_global = None
            self._has_dragged = False
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._has_dragged:
                self._show_menu(QCursor.pos())
            self._drag_offset = None
            self._mouse_pressed_global = None
            self._has_dragged = False
            event.accept()
            return
        super().mouseReleaseEvent(event)
