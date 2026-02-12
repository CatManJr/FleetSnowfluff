from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QCursor, QGuiApplication, QMouseEvent, QMovie, QPixmap, QTransform
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMenu, QMessageBox

from .chat_window import ChatWindow
from .music_window import MusicWindow
from .seal_widget import SealWidget
from .settings_dialog import SettingsDialog
from .transform_window import TransformWindow


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
        self._music_window: MusicWindow | None = None
        self._transform_window: TransformWindow | None = None
        self._is_shutting_down = False
        self._persona_prompt = self._load_persona_prompt()
        self._playlist_order: list[Path] = []
        self._playlist_index: int = -1
        self._supported_music_exts = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}

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

        self._flight_timer = QTimer(self)
        self._flight_timer.setInterval(58)
        self._flight_timer.timeout.connect(self._on_flight_tick)
        self._flight_target: QPoint | None = None
        self._flight_base_speed_px = 10
        self._flight_fast_multiplier = 2.0
        self._idle_cycles_without_movie1 = 0

        self._set_movie(random.choice(self.idle_ids))
        self._place_initial_position()
        self.show()

        self.idle_switch_timer = QTimer(self)
        self.idle_switch_timer.setInterval(4500)
        self.idle_switch_timer.timeout.connect(self._switch_idle_animation)
        self.idle_switch_timer.start()

        self._load_config()
        self._ensure_resource_container()
        self._setup_audio()
        self._setup_menu()
        # Keep it simple: pin topmost once at startup, no runtime stack polling.
        QTimer.singleShot(0, self._pin_topmost_once)
        QTimer.singleShot(300, self._pin_topmost_once)

    def _load_persona_prompt(self) -> str:
        candidates = [
            # Packaged app path (preferred)
            self.resources_dir / "config" / "FleetSnowfluff.json",
            # Source-run path
            self.resources_dir.parent / "src" / "config" / "FleetSnowfluff.json",
            # Fallback for alternative layouts
            self.resources_dir.parent / "config" / "FleetSnowfluff.json",
        ]
        raw = ""
        for prompt_path in candidates:
            if not prompt_path.exists():
                continue
            try:
                raw = prompt_path.read_text(encoding="utf-8").strip()
                if raw:
                    break
            except OSError:
                continue
        if not raw:
            return ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback for malformed config; keep token budget bounded.
            return raw[:6000]
        return self._build_structured_persona_prompt(data)

    def _build_structured_persona_prompt(self, data: Any) -> str:
        if not isinstance(data, dict):
            return str(data)[:12000]

        sections: list[tuple[str, Any, int]] = []
        if "行为约束与准则" in data:
            sections.append(("高优先级行为约束与准则", data.get("行为约束与准则"), 5200))
        elif "行为准则" in data:
            sections.append(("高优先级行为准则", data.get("行为准则"), 5200))
        if "角色档案" in data:
            sections.append(("角色档案", data.get("角色档案"), 3600))
        if "核心关系" in data:
            sections.append(("核心关系", data.get("核心关系"), 2400))
        if "风格与语气" in data:
            sections.append(("风格与语气", data.get("风格与语气"), 2400))
        if "人格范例" in data:
            sections.append(("人格范例", data.get("人格范例"), 2800))
        if "世界观元素" in data:
            sections.append(("世界观元素", data.get("世界观元素"), 1600))

        if not sections:
            return json.dumps(data, ensure_ascii=False)[:12000]

        parts: list[str] = []
        for title, content, limit in sections:
            serialized = json.dumps(content, ensure_ascii=False, indent=2)[:limit]
            parts.append(f"【{title}】\n{serialized}")

        structured = "\n\n".join(parts)
        return structured[:14000]

    def _resolve_config_path(self) -> Path:
        app_dir = self._app_data_dir("FleetSnowfluff")
        legacy_dir = self._app_data_dir("Aemeath")
        self._migrate_legacy_app_data(legacy_dir=legacy_dir, app_dir=app_dir)
        return app_dir / "settings.json"

    def _app_data_dir(self, app_name: str) -> Path:
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / app_name
        if sys.platform.startswith("win"):
            appdata = os.environ.get("APPDATA", str(Path.home()))
            return Path(appdata) / app_name
        return Path.home() / ".config" / app_name.lower()

    def _migrate_legacy_app_data(self, legacy_dir: Path, app_dir: Path) -> None:
        """
        Migrate user data from old app naming to FleetSnowfluff.
        Copy-only strategy prevents accidental data loss.
        """
        if legacy_dir == app_dir or not legacy_dir.exists():
            return
        try:
            app_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        # Never migrate sensitive per-user secrets/history across app names.
        blocked_filenames = {"settings.json", "chat_history.jsonl"}
        for src in legacy_dir.rglob("*"):
            rel = src.relative_to(legacy_dir)
            if src.is_file() and src.name in blocked_filenames:
                continue
            dst = app_dir / rel
            try:
                if src.is_dir():
                    dst.mkdir(parents=True, exist_ok=True)
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                if dst.exists():
                    continue
                shutil.copy2(src, dst)
            except OSError:
                continue

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

    def _resource_container_dir(self) -> Path:
        return self._config_path.parent / "resources"

    def _resource_container_music_dir(self) -> Path:
        return self._resource_container_dir() / "music"

    def _ensure_resource_container(self) -> None:
        """
        Keep a writable runtime resource container under app data.
        Bundled resources remain read-only; user imports also go here.
        """
        source_music_dir = self.resources_dir / "music"
        target_music_dir = self._resource_container_music_dir()
        try:
            target_music_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        if not source_music_dir.exists():
            return
        for src in source_music_dir.iterdir():
            if not src.is_file():
                continue
            dst = target_music_dir / src.name
            if dst.exists():
                continue
            try:
                shutil.copy2(src, dst)
            except OSError:
                continue

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
        if movie_id == 1 and not self._is_hovering and self._drag_offset is None:
            # Hard rule: 1.gif must be in flight whenever it becomes active.
            self._start_slow_flight()

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
        # step0: switch action (must differ from previous one)
        candidates = [mid for mid in self.idle_ids if mid != self._current_movie_id]
        if not candidates:
            next_movie_id = random.choice(self.idle_ids)
        elif 1 in candidates and self._idle_cycles_without_movie1 >= 3:
            # Ensure 1.gif appears regularly even under unlucky randomness.
            next_movie_id = 1
        else:
            next_movie_id = random.choice(candidates)
        if next_movie_id == 1:
            self._idle_cycles_without_movie1 = 0
        else:
            self._idle_cycles_without_movie1 += 1
        self._stop_flight()
        self._set_movie(next_movie_id)

        # step1: whether to jump (20% no jump, 80% large flash jump)
        should_jump = random.random() >= 0.2
        if should_jump:
            self._flash_move_large_range()

        # step2: whether to move after switch (1.gif must move)
        # Non-1 actions: 80% move / 20% stay.
        should_move = True if next_movie_id == 1 else (random.random() < 0.8)
        if should_move:
            self._start_slow_flight()

    def _start_slow_flight(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        if self._current_movie_id == 1:
            start_point, target = self._plan_movie1_flight(area)
            self.move(start_point)
            self._flight_target = target
            self._flight_timer.start()
            return
        target = self._pick_random_position(
            area=area,
            min_distance=max(90, int(min(area.width(), area.height()) * 0.18)),
        )
        if target is None:
            return
        self._flight_target = target
        self._flight_timer.start()

    def _plan_movie1_flight(self, area: QRect) -> tuple[QPoint, QPoint]:
        width = max(1, self.width())
        height = max(1, self.height())
        min_y = area.top()
        max_y = max(area.top(), area.bottom() - height)
        span = max(1, area.width())
        side_band = max(28, int(span * 0.14))

        if not self._mirror_h:
            # Facing right: spawn from left side, fly to right side.
            start_x = random.randint(area.left(), min(area.left() + side_band, area.right() - width))
            target_x_min = max(area.left(), area.right() - width - side_band)
            target_x = random.randint(target_x_min, max(target_x_min, area.right() - width))
        else:
            # Facing left (mirrored): spawn from right side, fly to left side.
            start_x_min = max(area.left(), area.right() - width - side_band)
            start_x = random.randint(start_x_min, max(start_x_min, area.right() - width))
            target_x = random.randint(area.left(), min(area.left() + side_band, area.right() - width))

        start_y = random.randint(min_y, max_y)
        target_y = random.randint(min_y, max_y)
        return QPoint(start_x, start_y), QPoint(target_x, target_y)

    def _flash_move_large_range(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        target = self._pick_random_position(
            area=area,
            min_distance=max(140, int(min(area.width(), area.height()) * 0.3)),
        )
        if target is None:
            return
        self.move(target)
        self._apply_edge_orientation(area)

    def _pick_random_position(self, area: QRect, min_distance: int) -> QPoint | None:
        width = max(1, self.width())
        height = max(1, self.height())
        min_x = area.left()
        max_x = max(area.left(), area.right() - width)
        min_y = area.top()
        max_y = max(area.top(), area.bottom() - height)
        current = self.pos()
        for _ in range(16):
            target = QPoint(
                random.randint(min_x, max_x),
                random.randint(min_y, max_y),
            )
            if (target - current).manhattanLength() >= min_distance:
                return target
        return QPoint(random.randint(min_x, max_x), random.randint(min_y, max_y))

    def _stop_flight(self) -> None:
        self._flight_target = None
        if self._flight_timer.isActive():
            self._flight_timer.stop()

    def _on_flight_tick(self) -> None:
        if self._flight_target is None:
            self._stop_flight()
            return
        if self._is_hovering or self._drag_offset is not None:
            self._stop_flight()
            return

        current = self.pos()
        target = self._flight_target
        dx = target.x() - current.x()
        dy = target.y() - current.y()
        distance = (dx * dx + dy * dy) ** 1
        speed_px = self._current_flight_speed()
        if distance <= speed_px:
            self.move(target)
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                self._apply_edge_orientation(screen.availableGeometry())
            self._stop_flight()
            return

        step_x = int(round(dx / distance * speed_px))
        step_y = int(round(dy / distance * speed_px))
        if step_x == 0 and dx != 0:
            step_x = 1 if dx > 0 else -1
        if step_y == 0 and dy != 0:
            step_y = 1 if dy > 0 else -1
        self.move(current.x() + step_x, current.y() + step_y)

    def _current_flight_speed(self) -> float:
        if self._current_movie_id == 1:
            return self._flight_base_speed_px * self._flight_fast_multiplier
        return self._flight_base_speed_px

    def _apply_edge_orientation(self, area: QRect) -> None:
        if self._current_movie_id == 1:
            self._mirror_h = random.choice([False, True])
            self._on_movie_frame_changed()
            return

        margin = 16
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
        self._sync_seal_state()
        self._refresh_menu_labels()

    def _sync_seal_state(self) -> None:
        alive: list[SealWidget] = []
        for seal in self._seal_widgets:
            try:
                _ = seal.isVisible()
            except RuntimeError:
                continue
            alive.append(seal)
        self._seal_widgets = alive

    def _clear_seals(self) -> None:
        for seal in list(self._seal_widgets):
            seal.close()
        self._seal_widgets.clear()
        self._refresh_menu_labels()

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
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)

    def _setup_menu(self) -> None:
        self._menu = QMenu(self)
        self._menu.setStyleSheet(
            """
            QMenu {
                background: #ffffff;
                border: 2px solid #ffb7d6;
                border-radius: 14px;
                padding: 6px;
            }
            QMenu::item {
                border-radius: 10px;
                padding: 8px 12px;
                margin: 2px 0;
                color: #6c2e4e;
                background: transparent;
                font-size: 12px;
            }
            QMenu::item:selected {
                background: #fff0f7;
                color: #8d365d;
            }
            QMenu::item:pressed {
                background: #ffd9ea;
                color: #7a2b4d;
            }
            """
        )
        self._chat_action = self._menu.addAction("打开飞讯")
        self._transform_action = self._menu.addAction("爱弥斯，变身！")
        self._hacker_action = self._menu.addAction("电子幽灵登场！")
        self._seal_action = self._menu.addAction("")
        self._music_action = self._menu.addAction("你看，又唱")
        self._exit_action = self._menu.addAction("拜拜～")

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
        self._sync_seal_state()
        self._seal_action.setText("拜拜海豹" if self._seal_widgets else "召唤雪绒海豹")

    def _show_menu(self, global_pos: QPoint) -> None:
        self._refresh_menu_labels()
        self._menu.exec(global_pos)

    def _chat_with_xiaoai(self) -> None:
        if self._chat_window is None:
            self._chat_window = ChatWindow(
                config_dir=self._config_path.parent,
                api_key_getter=lambda: self._api_key,
                icon_path=self.resources_dir / "icon.webp",
                persona_prompt=self._persona_prompt,
                parent=None,
            )
            self._chat_window.destroyed.connect(self._on_chat_window_destroyed)
        self._chat_window.show()
        self._chat_window.raise_()
        self._chat_window.activateWindow()

    def _on_chat_window_destroyed(self) -> None:
        self._chat_window = None

    def _transform_emis(self) -> None:
        # Prefer alpha-capable transform source first.
        candidates = [
            self.resources_dir / "aemeath.mov",
            self.resources_dir / "human.mov",
            self.resources_dir / "human.mp4",
        ]
        video_path = next((p for p in candidates if p.exists()), candidates[-1])
        if not video_path.exists():
            QMessageBox.warning(self, "资源缺失", f"未找到变身播片：{video_path.name}")
            return
        if self._transform_window is None:
            self._transform_window = TransformWindow(parent=None)
            self._transform_window.destroyed.connect(self._on_transform_window_destroyed)
            self._transform_window.playbackFinished.connect(self._on_transform_playback_finished)
            self._transform_window.playbackFailed.connect(self._on_transform_playback_failed)
        self._stop_flight()
        target_geometry = self.frameGeometry()
        scaled_w = max(1, int(target_geometry.width() * 1.5))
        scaled_h = max(1, int(target_geometry.height() * 1.5))
        center = target_geometry.center()
        target_geometry = QRect(
            center.x() - scaled_w // 2,
            center.y() - scaled_h // 2,
            scaled_w,
            scaled_h,
        )
        self.hide()
        self._transform_window.play_media(video_path, target_geometry)

    def _on_transform_window_destroyed(self) -> None:
        self._transform_window = None

    def _on_transform_playback_finished(self) -> None:
        if self._is_shutting_down:
            return
        self.show()
        self.raise_()
        self.activateWindow()
        if not self._is_hovering:
            self._set_movie(random.choice(self.idle_ids))

    def _on_transform_playback_failed(self, error_text: str) -> None:
        if self._is_shutting_down:
            return
        QMessageBox.warning(
            self,
            "变身播片失败",
            "当前视频编码可能与系统解码器不兼容。\n"
            "建议优先使用带 alpha 的 human.mov，或将 human.mp4 转码为 H.264/AAC 后重试。\n"
            f"详情：{error_text}",
        )

    def _launch_hacker_terminal(self) -> None:
        if sys.platform == "darwin":
            script = '''
            tell application "Terminal"
                if not running then
                    launch
                end if
                reopen
                activate
                delay 0.1
                if (count of windows) is 0 then
                    do script ""
                    delay 0.1
                end if
                activate
            end tell
            '''
            try:
                subprocess.run(["osascript", "-e", script], check=False)
            except OSError:
                subprocess.Popen(["open", "-a", "Terminal"])
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
        self._sync_seal_state()
        if self._seal_widgets:
            self._clear_seals()
            return
        self._spawn_seals(random.randint(1, 12))
        self._refresh_menu_labels()

    def _play_random_music(self) -> None:
        self._open_music_window()
        self._start_random_loop()

    def _music_dir(self) -> Path:
        self._ensure_resource_container()
        return self._resource_container_music_dir()

    def _music_background_path(self) -> Path:
        container_music_dir = self._music_dir()
        for filename in ("player.jpg", "background.PNG", "background.png"):
            candidate = container_music_dir / filename
            if candidate.exists():
                return candidate
        # Fallback for dev-time safety if container copy fails.
        for filename in ("player.jpg", "background.PNG", "background.png"):
            candidate = self.resources_dir / "music" / filename
            if candidate.exists():
                return candidate
        return self.resources_dir / "music" / "player.jpg"

    def _list_music_tracks(self) -> list[Path]:
        music_dir = self._music_dir()
        if not music_dir.exists():
            return []
        return sorted(
            [p for p in music_dir.iterdir() if p.is_file() and p.suffix.lower() in self._supported_music_exts],
            key=lambda p: p.name.lower(),
        )

    def _start_random_loop(self) -> bool:
        tracks = self._list_music_tracks()
        if not tracks:
            QMessageBox.information(
                self,
                "暂无音乐",
                "未找到可播放音乐。请导入到 resources/music 后再试。",
            )
            return False
        self._playlist_order = tracks[:]
        random.shuffle(self._playlist_order)
        self._playlist_index = 0
        self._play_current_playlist_track()
        return True

    def _play_current_playlist_track(self) -> None:
        if not self._playlist_order or self._playlist_index < 0:
            return
        track = self._playlist_order[self._playlist_index]
        self._player.setSource(QUrl.fromLocalFile(str(track)))
        self._player.play()

    def _play_next_track(self) -> None:
        if not self._playlist_order:
            if not self._start_random_loop():
                return
            return
        self._playlist_index = (self._playlist_index + 1) % len(self._playlist_order)
        self._play_current_playlist_track()

    def _play_prev_track(self) -> None:
        if not self._playlist_order:
            if not self._start_random_loop():
                return
            return
        self._playlist_index = (self._playlist_index - 1) % len(self._playlist_order)
        self._play_current_playlist_track()

    def _play_selected_track(self, track_path: Path) -> None:
        tracks = self._list_music_tracks()
        if not tracks:
            return
        if track_path not in tracks:
            return
        remainder = [t for t in tracks if t != track_path]
        random.shuffle(remainder)
        self._playlist_order = [track_path, *remainder]
        self._playlist_index = 0
        self._play_current_playlist_track()

    def _toggle_music_play_pause(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            return
        if self._player.source().isEmpty():
            self._start_random_loop()
            return
        self._player.play()

    def _is_music_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def _on_media_status_changed(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._play_next_track()
            if self._music_window is not None:
                self._music_window.refresh_tracks()

    def _current_track(self) -> Path | None:
        if not self._playlist_order or self._playlist_index < 0:
            return None
        if self._playlist_index >= len(self._playlist_order):
            return None
        return self._playlist_order[self._playlist_index]

    def _stop_music_playback(self) -> None:
        self._player.stop()
        self._playlist_order = []
        self._playlist_index = -1

    def _import_music_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            None,
            "导入音乐到曲库",
            str(Path.home()),
            "Audio Files (*.mp3 *.wav *.m4a *.flac *.ogg)",
        )
        if not files:
            return
        music_dir = self._music_dir()
        music_dir.mkdir(parents=True, exist_ok=True)
        imported = 0
        for file_path in files:
            src = Path(file_path)
            dst = music_dir / src.name
            try:
                shutil.copy2(src, dst)
                imported += 1
            except OSError:
                continue
        QMessageBox.information(self, "导入完成", f"已导入 {imported} 首音乐。")
        if self._music_window is not None:
            self._music_window.refresh_tracks()

    def _open_music_window(self) -> None:
        if self._music_window is None:
            self._music_window = MusicWindow(
                icon_path=self.resources_dir / "icon.webp",
                playlist_bg_path=self._music_background_path(),
                list_tracks_fn=self._list_music_tracks,
                import_tracks_fn=self._import_music_files,
                start_random_loop_fn=self._start_random_loop,
                play_track_fn=self._play_selected_track,
                play_next_fn=self._play_next_track,
                play_prev_fn=self._play_prev_track,
                current_track_fn=self._current_track,
                toggle_play_pause_fn=self._toggle_music_play_pause,
                is_playing_fn=self._is_music_playing,
                stop_playback_fn=self._stop_music_playback,
                parent=None,
            )
            self._music_window.destroyed.connect(self._on_music_window_destroyed)
        self._music_window.refresh_tracks()
        self._music_window.show()
        self._music_window.raise_()
        self._music_window.activateWindow()

    def _on_music_window_destroyed(self) -> None:
        self._music_window = None

    def _quit_app(self) -> None:
        self._is_shutting_down = True
        self._stop_flight()
        if self.idle_switch_timer.isActive():
            self.idle_switch_timer.stop()
        if self._transform_window is not None:
            self._transform_window.close()
        if self._chat_window is not None:
            self._chat_window.close()
        if self._music_window is not None:
            self._music_window.close()
        self._clear_seals()
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def closeEvent(self, event) -> None:
        self._is_shutting_down = True
        if self.idle_switch_timer.isActive():
            self.idle_switch_timer.stop()
        self._stop_flight()
        super().closeEvent(event)

    def enterEvent(self, event) -> None:
        self._is_hovering = True
        self._stop_flight()
        self._set_movie(self.hover_id)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._is_hovering = False
        self._set_movie(random.choice(self.idle_ids))
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            # Open settings on release to avoid interrupting Qt mouse state.
            self._stop_flight()
            self._right_click_pending = True
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._stop_flight()
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
