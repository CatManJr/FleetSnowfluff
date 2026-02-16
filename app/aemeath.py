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

from PySide6.QtCore import QEvent, QPoint, QRect, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCursor, QDesktopServices, QGuiApplication, QIcon, QMouseEvent, QMovie, QPixmap, QTransform
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMenu, QMessageBox, QSystemTrayIcon

try:
    from shiboken6 import isValid as shiboken_is_valid
except ImportError:
    shiboken_is_valid = None

from .chat_window import ChatWindow
from .music_window import MusicWindow
from .seal_widget import SealWidget
from .settings_dialog import SettingsDialog
from .transform_window import TransformWindow
from .ui_scale import current_app_scale, px


class Aemeath(QLabel):
    def __init__(self, resources_dir: Path) -> None:
        super().__init__()
        self.resources_dir = resources_dir
        self._config_path = self._resolve_config_path()
        self._reasoning_enabled = False
        self._chat_context_turns = 20
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
        self._focus_hide_mascot_enabled = False
        self._last_fullscreen_state = False
        self._last_fullscreen_checked_at = 0.0
        self._chat_window: ChatWindow | None = None
        self._music_window: MusicWindow | None = None
        self._transform_window: TransformWindow | None = None
        self._transform_restore_fullscreen_mode = False
        self._hidden_windows_before_transform: dict[str, object] = {}
        self._is_shutting_down = False
        self._playlist_order: list[Path] = []
        self._playlist_index: int = -1
        self._pending_autoplay_music = False
        self._resume_music_after_transform = False
        self._supported_music_exts = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}
        self._runtime_settings = QSettings("FleetSnowfluff", "Aemeath")
        # Product requirement: always start with global hide OFF each launch.
        self._reset_focus_hide_mascot_on_startup()
        self._tray_icon: QSystemTrayIcon | None = None
        self._tray_focus_action: QAction | None = None
        self._focus_menu: QMenu | None = None

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
        self._min_jump_distance_px = 120
        self._flight_base_speed_px = 10
        self._flight_fast_multiplier = 2.0
        self._idle_cycles_without_movie1 = 0
        self._movie1_forced_remaining = 0

        self._set_movie(random.choice(self.idle_ids))
        self._place_initial_position()
        self.show()

        self.idle_switch_timer = QTimer(self)
        self.idle_switch_timer.setInterval(4500)
        self.idle_switch_timer.timeout.connect(self._switch_idle_animation)
        self.idle_switch_timer.start()

        self._load_config()
        self._focus_hide_mascot_enabled = self._load_focus_hide_mascot_enabled()
        self._ensure_resource_container()
        self._setup_audio()
        self._setup_menu()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        # Keep it simple: pin topmost once at startup, no runtime stack polling.
        QTimer.singleShot(0, self._pin_topmost_once)
        QTimer.singleShot(300, self._pin_topmost_once)

    @staticmethod
    def _is_widget_alive(widget: object | None) -> bool:
        if widget is None:
            return False
        if shiboken_is_valid is None:
            return True
        try:
            return bool(shiboken_is_valid(widget))
        except Exception:
            return False

    def _load_persona_prompt(self) -> str:
        candidates = self._persona_prompt_candidates()
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

    def _persona_prompt_candidates(self) -> list[Path]:
        return [
            # User-editable runtime file (preferred)
            self._config_path.parent / "FleetSnowfluff.json",
            # Packaged app path
            self.resources_dir / "config" / "FleetSnowfluff.json",
            # Source-run path
            self.resources_dir.parent / "src" / "config" / "FleetSnowfluff.json",
            # Fallback for alternative layouts
            self.resources_dir.parent / "config" / "FleetSnowfluff.json",
        ]

    def _ensure_editable_persona_json(self) -> Path | None:
        editable = self._config_path.parent / "FleetSnowfluff.json"
        try:
            editable.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
        if editable.exists():
            return editable
        for src in self._persona_prompt_candidates()[1:]:
            if not src.exists():
                continue
            try:
                shutil.copy2(src, editable)
                return editable
            except OSError:
                continue
        try:
            editable.write_text("{}", encoding="utf-8")
            return editable
        except OSError:
            return None

    def _open_chat_history_json_quick(self) -> None:
        history_path = self._config_path.parent / "chat_history.jsonl"
        try:
            history_path.parent.mkdir(parents=True, exist_ok=True)
            if not history_path.exists():
                history_path.write_text("", encoding="utf-8")
        except OSError:
            QMessageBox.warning(self, "打开失败", "无法创建聊天记录文件，请检查目录权限。")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(history_path.parent))):
            QMessageBox.warning(self, "打开失败", f"无法打开目录：{history_path.parent}")

    def _open_persona_json_quick(self) -> None:
        persona_path = self._ensure_editable_persona_json()
        if persona_path is None:
            QMessageBox.warning(self, "打开失败", "无法创建人设文件，请检查目录权限。")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(persona_path.parent))):
            QMessageBox.warning(self, "打开失败", f"无法打开目录：{persona_path.parent}")

    def _resolve_config_path(self) -> Path:
        app_dir = self._app_data_dir("FleetSnowfluff")
        for legacy_dir in self._legacy_app_data_dirs():
            self._migrate_legacy_app_data(legacy_dir=legacy_dir, app_dir=app_dir)
        return app_dir / "settings.json"

    def _read_config_json(self) -> dict[str, Any]:
        if not self._config_path.exists():
            return {}
        try:
            parsed = json.loads(self._config_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                return dict(parsed)
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _read_api_key_from_config(self) -> str:
        data = self._read_config_json()
        return str(data.get("deepseek_api_key", "")).strip()

    def _legacy_app_data_dirs(self) -> list[Path]:
        """
        Candidate legacy runtime data locations from older releases/names.
        """
        names = ("Aemeath", "Fleet Snowfluff", "fleet_snowfluff")
        dirs: list[Path] = []
        seen: set[Path] = set()
        current_dir = self._app_data_dir("FleetSnowfluff")
        for name in names:
            candidate = self._app_data_dir(name)
            if candidate == current_dir or candidate in seen:
                continue
            seen.add(candidate)
            dirs.append(candidate)
        return dirs

    def _app_data_dir(self, app_name: str) -> Path:
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / app_name
        if sys.platform.startswith("win"):
            appdata = os.environ.get("APPDATA", str(Path.home()))
            return Path(appdata) / app_name
        return Path.home() / ".config" / app_name.lower()

    def _migrate_legacy_app_data(self, legacy_dir: Path, app_dir: Path) -> None:
        """
        Migrate user data from old app naming/locations to FleetSnowfluff.
        Copy-only strategy prevents accidental data loss and never overwrites.
        """
        if legacy_dir == app_dir or not legacy_dir.exists():
            return
        try:
            app_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        for src in legacy_dir.rglob("*"):
            rel = src.relative_to(legacy_dir)
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
        data = self._read_config_json()
        if not data:
            return
        reasoning_raw = data.get("reasoning_enabled", self._reasoning_enabled)
        if isinstance(reasoning_raw, bool):
            self._reasoning_enabled = reasoning_raw
        elif isinstance(reasoning_raw, str):
            self._reasoning_enabled = reasoning_raw.strip().lower() in {"1", "true", "yes", "on"}
        else:
            self._reasoning_enabled = bool(reasoning_raw)
        try:
            self._min_jump_distance_px = max(20, int(data.get("min_jump_distance_px", self._min_jump_distance_px)))
        except (TypeError, ValueError):
            pass
        try:
            self._flight_base_speed_px = max(1, int(data.get("flight_speed_px", self._flight_base_speed_px)))
        except (TypeError, ValueError):
            pass
        try:
            self._chat_context_turns = max(0, int(data.get("chat_context_turns", self._chat_context_turns)))
        except (TypeError, ValueError):
            pass

    def _save_config(self, *, api_key: str | None = None) -> bool:
        payload = self._read_config_json()
        final_api_key = self._read_api_key_from_config() if api_key is None else str(api_key).strip()
        payload.update(
            {
                "deepseek_api_key": final_api_key,
                "reasoning_enabled": self._reasoning_enabled,
                "min_jump_distance_px": self._min_jump_distance_px,
                "flight_speed_px": self._flight_base_speed_px,
                "chat_context_turns": self._chat_context_turns,
            }
        )
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
        sync_background_files = {"player.jpg", "background.PNG", "background.png"}
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
            try:
                if not dst.exists():
                    shutil.copy2(src, dst)
                    continue
                # Keep runtime cache fresh for bundled background assets:
                # if source changed, refresh container copy on startup.
                if src.name in sync_background_files:
                    src_stat = src.stat()
                    dst_stat = dst.stat()
                    changed = (
                        src_stat.st_size != dst_stat.st_size
                        or src_stat.st_mtime_ns > dst_stat.st_mtime_ns
                    )
                    if changed:
                        shutil.copy2(src, dst)
            except OSError:
                continue

    def _show_settings_dialog(self) -> None:
        dialog = SettingsDialog(
            api_key=self._read_api_key_from_config(),
            min_jump_distance=self._min_jump_distance_px,
            flight_speed=self._flight_base_speed_px,
            reasoning_enabled=self._reasoning_enabled,
            chat_context_turns=self._chat_context_turns,
            open_chat_history_callback=self._open_chat_history_json_quick,
            open_persona_callback=self._open_persona_json_quick,
            parent=None,
        )
        result = dialog.exec()
        if result != SettingsDialog.DialogCode.Accepted:
            return
        api_key = dialog.api_key()
        self._reasoning_enabled = dialog.reasoning_enabled()
        self._min_jump_distance_px = dialog.min_jump_distance()
        self._flight_base_speed_px = dialog.flight_speed()
        self._chat_context_turns = dialog.chat_context_turns()
        if self._save_config(api_key=api_key):
            QMessageBox.information(self, "保存成功", "设置已保存，后续将自动读取。")
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
        elif self._movie1_forced_remaining > 0 and 1 in candidates:
            # Continue the forced sequence until 1.gif has appeared enough times.
            next_movie_id = 1
        elif 1 in candidates and self._idle_cycles_without_movie1 >= 3:
            # Starvation prevention: each trigger guarantees at least two 1.gif appearances.
            self._movie1_forced_remaining = max(self._movie1_forced_remaining, 2)
            next_movie_id = 1
        else:
            next_movie_id = random.choice(candidates)
        if next_movie_id == 1:
            self._idle_cycles_without_movie1 = 0
            if self._movie1_forced_remaining > 0:
                self._movie1_forced_remaining -= 1
        else:
            self._idle_cycles_without_movie1 += 1
        self._stop_flight()
        self._set_movie(next_movie_id)

        # step1: whether to jump (20% no jump, 80% large flash jump)
        should_jump = random.random() >= 0.2
        if should_jump:
            self._flash_move_large_range()

        # step2: whether to move after switch (1.gif must move)
        # Non-1 actions: 90% move / 10% stay.
        should_move = True if next_movie_id == 1 else (random.random() < 0.9)
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
            min_distance=max(self._min_jump_distance_px, int(min(area.width(), area.height()) * 0.18)),
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
            min_distance=max(self._min_jump_distance_px, int(min(area.width(), area.height()) * 0.3)),
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
        self._audio_output.setVolume(self._load_music_volume_percent() / 100.0)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)

    def _load_music_volume_percent(self) -> int:
        raw = self._runtime_settings.value("audio/music_volume_percent", 70)
        if isinstance(raw, bool):
            volume = int(raw)
        elif isinstance(raw, (int, float, str)):
            try:
                volume = int(raw)
            except (TypeError, ValueError):
                volume = 70
        else:
            volume = 70
        return max(0, min(100, volume))

    def _persist_music_volume_percent(self, volume_percent: int) -> None:
        self._runtime_settings.setValue("audio/music_volume_percent", max(0, min(100, int(volume_percent))))

    def _load_focus_hide_mascot_enabled(self) -> bool:
        raw = self._runtime_settings.value("focus/hide_mascot_enabled", False)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return False

    def _reset_focus_hide_mascot_on_startup(self) -> None:
        self._runtime_settings.setValue("focus/hide_mascot_enabled", False)
        self._focus_hide_mascot_enabled = False

    def _set_focus_hide_mascot_enabled(self, enabled: bool) -> None:
        self._focus_hide_mascot_enabled = bool(enabled)
        self._runtime_settings.setValue("focus/hide_mascot_enabled", self._focus_hide_mascot_enabled)
        self._refresh_menu_labels()
        # Fast path for manual toggle: apply visibility from cached state immediately,
        # then reconcile with external probes on the next event-loop tick.
        self._sync_terminal_visibility(refresh_external_state=False)
        QTimer.singleShot(0, self._sync_terminal_visibility)

    def _setup_menu(self) -> None:
        self._menu = QMenu(self)
        app = QApplication.instance()
        scale = current_app_scale(app) if app is not None else 1.0
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
                font-size: %dpx;
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
            % px(14, scale)
        )
        self._chat_action = self._menu.addAction("打开飞讯")
        self._transform_action = self._menu.addAction("爱弥斯，变身！")
        self._hacker_action = self._menu.addAction("电子幽灵登场！")
        self._music_action = self._menu.addAction("你看，又唱")
        self._settings_action = self._menu.addAction("设置")
        self._focus_status_action = self._menu.addAction("")
        self._focus_status_action.setEnabled(False)
        self._focus_status_action.setVisible(False)
        self._focus_menu = self._menu.addMenu("浮游星海")
        self._seal_action = self._focus_menu.addAction("")
        self._tray_focus_action = self._focus_menu.addAction("")
        self._exit_action = self._menu.addAction("拜拜～")

        self._chat_action.triggered.connect(self._chat_with_xiaoai)
        self._transform_action.triggered.connect(self._transform_emis)
        self._hacker_action.triggered.connect(self._launch_hacker_terminal)
        self._seal_action.triggered.connect(self._toggle_seals)
        self._tray_focus_action.triggered.connect(self._toggle_focus_hide_mascot)
        self._music_action.triggered.connect(self._play_random_music)
        self._settings_action.triggered.connect(self._show_settings_dialog)
        self._exit_action.triggered.connect(self._quit_app)
        self._menu.aboutToShow.connect(self._refresh_menu_labels)
        self._setup_tray_icon()
        self._refresh_menu_labels()

    def _setup_tray_icon(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray_icon = QSystemTrayIcon(self)
        icon_path = self.resources_dir / "icon.webp"
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            if not icon.isNull():
                self._tray_icon.setIcon(icon)
        self._tray_icon.setToolTip("飞行雪绒：主控菜单")
        self._tray_icon.setContextMenu(self._menu)
        self._tray_icon.show()

    def _toggle_focus_hide_mascot(self) -> None:
        self._set_focus_hide_mascot_enabled(not self._focus_hide_mascot_enabled)

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

    def _sync_terminal_visibility(self, refresh_external_state: bool = True) -> None:
        if refresh_external_state:
            terminal_open = self._is_terminal_open()
            fullscreen_open = self._is_foreground_fullscreen_cached()
            terminal_just_opened = terminal_open and not self._terminal_open
            self._terminal_open = terminal_open
        else:
            terminal_open = self._terminal_open
            fullscreen_open = self._last_fullscreen_state
            terminal_just_opened = False

        should_hide = terminal_open or fullscreen_open or self._focus_hide_mascot_enabled
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
        if sys.platform.startswith("win"):
            # Windows terminal interaction is handled during launch via /k argument
            # or requires complex Win32 API injection which is out of scope.
            # We already handled the greeting in _launch_hacker_terminal for Windows.
            return

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
        focus_line: str | None = None
        chat_window = self._chat_window
        if self._is_widget_alive(chat_window) and chat_window is not None:
            focus_line = chat_window.focus_call_stage_line()
        if self._focus_status_action is not None:
            if focus_line:
                self._focus_status_action.setText(f"当前环节：{focus_line}")
                self._focus_status_action.setVisible(True)
            else:
                self._focus_status_action.setVisible(False)
        if self._tray_focus_action is not None:
            self._tray_focus_action.setText(
                "回来吧飞行雪绒"
                if self._focus_hide_mascot_enabled
                else "隐藏飞行雪绒"
            )

    def _show_menu(self, global_pos: QPoint) -> None:
        self._refresh_menu_labels()
        self._menu.exec(global_pos)

    def _chat_with_xiaoai(self) -> None:
        if not self._is_widget_alive(self._chat_window):
            self._chat_window = ChatWindow(
                config_dir=self._config_path.parent,
                api_key_getter=self._read_api_key_from_config,
                reasoning_enabled_getter=lambda: self._reasoning_enabled,
                context_turns_getter=lambda: self._chat_context_turns,
                icon_path=self.resources_dir / "icon.webp",
                persona_prompt_getter=self._load_persona_prompt,
                parent=None,
            )
        chat_window = self._chat_window
        if chat_window is None:
            return
        chat_window.show()
        chat_window.raise_()
        chat_window.activateWindow()

    def _on_chat_window_destroyed(self) -> None:
        self._chat_window = None

    def _transform_emis(self) -> None:
        # Prefer awaiting desktop-scene transform clip when available.
        awaiting_path = self.resources_dir / "awaiting.mov"
        if not awaiting_path.exists():
             awaiting_path = self.resources_dir / "awaiting.mp4"
        use_desktop_scene_mode = awaiting_path.exists()

        if use_desktop_scene_mode:
            video_path = awaiting_path
        else:
            # Fallback to previous alpha-capable transform source chain.
            candidates = [
                self.resources_dir / "aemeath.mov",
                self.resources_dir / "human.mov",
                self.resources_dir / "human.mp4",
            ]
            video_path = next((p for p in candidates if p.exists()), candidates[-1])
        if not video_path.exists():
            QMessageBox.warning(self, "变身播片失败", "⚠️Waring：虚质磁暴影响，通讯受阻")
            return
        if not self._is_widget_alive(self._transform_window):
            self._transform_window = TransformWindow(parent=None)
            self._transform_window.playbackFinished.connect(self._on_transform_playback_finished)
            self._transform_window.playbackFailed.connect(self._on_transform_playback_failed)
        self._stop_flight()
        if use_desktop_scene_mode:
            screen = QGuiApplication.primaryScreen()
            if screen is None:
                target_geometry = self.frameGeometry()
            else:
                # Use full screen geometry so top letterbox can hide behind macOS menu bar.
                target_geometry = screen.geometry()
            self._transform_restore_fullscreen_mode = True
        else:
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
            self._transform_restore_fullscreen_mode = False
        self._hide_windows_for_transform()
        self._pause_music_for_transform()
        self.hide()
        transform_window = self._transform_window
        if transform_window is None:
            return
        transform_window.play_media(
            video_path,
            target_geometry,
            desktop_scene_mode=use_desktop_scene_mode,
        )

    def _on_transform_window_destroyed(self) -> None:
        self._transform_window = None

    def _on_transform_playback_finished(self) -> None:
        if self._is_shutting_down:
            return
        self._transform_restore_fullscreen_mode = False
        self.show()
        self.raise_()
        self.activateWindow()
        self._restore_windows_after_transform()
        self._resume_music_after_transform_if_needed()
        if not self._is_hovering:
            self._set_movie(random.choice(self.idle_ids))

    def _on_transform_playback_failed(self, error_text: str) -> None:
        if self._is_shutting_down:
            return
        self._transform_restore_fullscreen_mode = False
        QMessageBox.warning(
            self,
            "变身播片失败",
            "⚠️Waring：虚质磁暴影响，通讯受阻",
        )

    def _hide_windows_for_transform(self) -> None:
        state: dict[str, object] = {
            "chat_visible": False,
            "music_state": None,
        }
        chat_window = self._chat_window
        if self._is_widget_alive(chat_window) and chat_window is not None and chat_window.isVisible():
            state["chat_visible"] = True
            chat_window.hide()
        music_window = self._music_window
        if self._is_widget_alive(music_window) and music_window is not None:
            state["music_state"] = music_window.capture_visibility_state()
            music_window.hide_for_transform()
        self._hidden_windows_before_transform = state

    def _restore_windows_after_transform(self) -> None:
        if not self._hidden_windows_before_transform:
            return
        state = self._hidden_windows_before_transform
        self._hidden_windows_before_transform = {}
        chat_window = self._chat_window
        if bool(state.get("chat_visible", False)) and self._is_widget_alive(chat_window) and chat_window is not None:
            chat_window.show()
            chat_window.raise_()
            chat_window.activateWindow()
        music_state = state.get("music_state")
        music_window = self._music_window
        if isinstance(music_state, dict) and self._is_widget_alive(music_window) and music_window is not None:
            music_window.restore_after_transform(music_state)

    def _pause_music_for_transform(self) -> None:
        self._resume_music_after_transform = self._is_music_playing()
        if self._resume_music_after_transform:
            self._player.pause()
            music_window = self._music_window
            if self._is_widget_alive(music_window) and music_window is not None:
                music_window.refresh_now_playing()

    def _resume_music_after_transform_if_needed(self) -> None:
        if not self._resume_music_after_transform:
            return
        self._resume_music_after_transform = False
        if not self._player.source().isEmpty():
            self._player.play()
            music_window = self._music_window
            if self._is_widget_alive(music_window) and music_window is not None:
                music_window.refresh_now_playing()

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
            # Use 'start "Title" cmd /k ...' to launch a new CMD window.
            # /k keeps the window open after the first command.
            # We echo the greeting and then leave the prompt open.
            greeting = "电子幽灵登场！Ciallo～(∠・ω< )⌒★"
            # Since 'start' is a shell builtin, we need shell=True.
            # Explicitly removing /D so it defaults to system behavior (often user profile if not forced).
            cmd = f'start "Electronic Ghost" cmd /k "echo {greeting}"'
            subprocess.Popen(cmd, shell=True)
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
        if self._is_music_playing():
            # If music is already running, only reveal the (possibly hidden) player UI.
            self._pending_autoplay_music = False
            self._open_music_window()
            return
        self._pending_autoplay_music = True
        self._open_music_window()

    def _on_music_window_ready_for_playback(self) -> None:
        if not self._pending_autoplay_music:
            return
        self._pending_autoplay_music = False
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
        music_window = self._music_window
        if self._is_widget_alive(music_window) and music_window is not None:
            music_window.refresh_now_playing()
            QTimer.singleShot(120, music_window.refresh_now_playing)

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

    def _music_position_ms(self) -> int:
        return max(0, int(self._player.position()))

    def _music_duration_ms(self) -> int:
        return max(0, int(self._player.duration()))

    def _seek_music_ms(self, position_ms: int) -> None:
        duration = self._music_duration_ms()
        if duration <= 0:
            return
        clamped = max(0, min(int(position_ms), duration))
        self._player.setPosition(clamped)

    def _music_volume_percent(self) -> int:
        return max(0, min(100, int(round(self._audio_output.volume() * 100))))

    def _set_music_volume_percent(self, volume_percent: int) -> None:
        clamped = max(0, min(int(volume_percent), 100))
        self._audio_output.setVolume(clamped / 100.0)
        self._persist_music_volume_percent(clamped)

    def _on_media_status_changed(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._play_next_track()
            music_window = self._music_window
            if self._is_widget_alive(music_window) and music_window is not None:
                music_window.refresh_now_playing()

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
        music_window = self._music_window
        if self._is_widget_alive(music_window) and music_window is not None:
            music_window.refresh_tracks()

    def _remove_music_track(self, track_path: Path) -> bool:
        track = Path(track_path)
        if not track.exists():
            return False
        try:
            track.resolve().relative_to(self._music_dir().resolve())
        except (OSError, ValueError):
            return False

        old_order = self._playlist_order[:]
        old_index = self._playlist_index
        old_current = self._current_track()
        try:
            track.unlink()
        except OSError:
            return False

        new_order = [p for p in old_order if p != track]
        if not new_order:
            self._stop_music_playback()
            return True

        self._playlist_order = new_order
        if old_current == track:
            self._playlist_index = min(max(0, old_index), len(new_order) - 1)
            self._play_current_playlist_track()
            return True

        if old_current in new_order:
            self._playlist_index = new_order.index(old_current)
        else:
            self._playlist_index = min(max(0, old_index), len(new_order) - 1)
        return True

    def _open_music_window(self) -> None:
        if not self._is_widget_alive(self._music_window):
            music_icon = self.resources_dir / "singer_icon.PNG"
            if not music_icon.exists():
                music_icon = self.resources_dir / "icon.webp"
            self._music_window = MusicWindow(
                icon_path=music_icon,
                playlist_bg_path=self._music_background_path(),
                list_tracks_fn=self._list_music_tracks,
                import_tracks_fn=self._import_music_files,
                remove_track_fn=self._remove_music_track,
                start_random_loop_fn=self._start_random_loop,
                play_track_fn=self._play_selected_track,
                play_next_fn=self._play_next_track,
                play_prev_fn=self._play_prev_track,
                current_track_fn=self._current_track,
                toggle_play_pause_fn=self._toggle_music_play_pause,
                is_playing_fn=self._is_music_playing,
                get_position_ms_fn=self._music_position_ms,
                get_duration_ms_fn=self._music_duration_ms,
                seek_position_ms_fn=self._seek_music_ms,
                get_volume_percent_fn=self._music_volume_percent,
                set_volume_percent_fn=self._set_music_volume_percent,
                stop_playback_fn=self._stop_music_playback,
                parent=None,
            )
            self._music_window.readyForPlayback.connect(self._on_music_window_ready_for_playback)
        music_window = self._music_window
        if music_window is None:
            return
        music_window.refresh_tracks()
        music_window.show()
        music_window.raise_()
        music_window.activateWindow()
        if self._pending_autoplay_music and music_window.is_ready_for_playback():
            # Window is already ready (e.g., reopened). Defer to next tick
            # to keep "load first, then play" behavior consistent.
            QTimer.singleShot(0, self._on_music_window_ready_for_playback)

    def _on_music_window_destroyed(self) -> None:
        self._music_window = None
        self._pending_autoplay_music = False

    def _quit_app(self) -> None:
        self._is_shutting_down = True
        # Reset global hide preference for next launch (default OFF).
        self._runtime_settings.setValue("focus/hide_mascot_enabled", False)
        self._stop_flight()
        if self.idle_switch_timer.isActive():
            self.idle_switch_timer.stop()
        transform_window = self._transform_window
        if self._is_widget_alive(transform_window) and transform_window is not None:
            transform_window.close()
        self._transform_window = None
        chat_window = self._chat_window
        if self._is_widget_alive(chat_window) and chat_window is not None:
            chat_window.close()
        self._chat_window = None
        music_window = self._music_window
        if self._is_widget_alive(music_window) and music_window is not None:
            music_window.close()
        self._music_window = None
        self._clear_seals()
        if self._tray_icon is not None:
            self._tray_icon.hide()
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def closeEvent(self, event) -> None:
        self._is_shutting_down = True
        # Reset global hide preference for next launch (default OFF).
        self._runtime_settings.setValue("focus/hide_mascot_enabled", False)
        if self.idle_switch_timer.isActive():
            self.idle_switch_timer.stop()
        self._stop_flight()
        if self._tray_icon is not None:
            self._tray_icon.hide()
        super().closeEvent(event)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.ShortcutOverride and event.key() == Qt.Key.Key_Escape:
            # Also consume shortcut-override ESC to prevent QDialog default reject.
            event.accept()
            return True
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            transform_window = self._transform_window
            if self._is_widget_alive(transform_window) and transform_window is not None and transform_window.isVisible():
                # ESC exits transform animation, but should not close the app.
                transform_window.close()
                event.accept()
                return True
            chat_window = self._chat_window
            if self._is_widget_alive(chat_window) and chat_window is not None:
                if chat_window.handle_focus_escape_animation():
                    event.accept()
                    return True
            # Global policy: block ESC-driven window close/exit elsewhere.
            event.accept()
            return True
        return super().eventFilter(watched, event)

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
