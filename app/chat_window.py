from __future__ import annotations

import json
import re
import subprocess
import sys
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, QRect, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices, QFontMetrics, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .design_tokens import chat_theme_tokens
from .fluent_compat import FPushButton as QPushButton
from .fluent_compat import fluent_icon
from .fluent_compat import init_fluent_theme
from .with_you import WithYouWindow
from .ui_scale import current_app_scale, px


class ChatWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        api_key: str,
        messages: list[dict[str, str]],
        temperature: float,
        reasoning_enabled: bool,
    ) -> None:
        super().__init__()
        self.api_key = api_key
        self.messages = messages
        self.temperature = temperature
        self.reasoning_enabled = reasoning_enabled

    def run(self) -> None:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
            model = "deepseek-reasoner" if self.reasoning_enabled else "deepseek-chat"
            response = client.chat.completions.create(
                model=model,
                messages=cast(Any, self.messages),
                temperature=self.temperature,
            )
            answer = response.choices[0].message.content if response.choices else ""
            answer = (answer or "").strip()
            if not answer:
                answer = "飞行雪绒 暂时没有想好怎么回复。"
            self.finished.emit(answer)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ChatInputBox(QPlainTextEdit):
    submitRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._ime_composing = False

    def inputMethodEvent(self, event) -> None:
        self._ime_composing = bool(event.preeditString())
        super().inputMethodEvent(event)
        # Some IMEs clear preedit after committing selected text.
        if not event.preeditString():
            self._ime_composing = False

    def keyPressEvent(self, event) -> None:
        is_enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        modifiers = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
        is_shift = modifiers == Qt.KeyboardModifier.ShiftModifier
        is_plain_enter = modifiers == Qt.KeyboardModifier.NoModifier
        if is_enter and self._ime_composing:
            # During IME composition/selection, Enter confirms candidate text.
            # Never treat it as submit in this state.
            super().keyPressEvent(event)
            return
        if is_enter and is_plain_enter:
            self.submitRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ChatTimelineList(QListWidget):
    def keyPressEvent(self, event) -> None:
        bar = self.verticalScrollBar()
        step = max(24, bar.singleStep())
        page = max(step * 4, bar.pageStep())
        key = event.key()
        if key == Qt.Key.Key_Up:
            bar.setValue(bar.value() - step)
            event.accept()
            return
        if key == Qt.Key.Key_Down:
            bar.setValue(bar.value() + step)
            event.accept()
            return
        if key == Qt.Key.Key_PageUp:
            bar.setValue(bar.value() - page)
            event.accept()
            return
        if key == Qt.Key.Key_PageDown:
            bar.setValue(bar.value() + page)
            event.accept()
            return
        if key == Qt.Key.Key_Home:
            bar.setValue(bar.minimum())
            event.accept()
            return
        if key == Qt.Key.Key_End:
            bar.setValue(bar.maximum())
            event.accept()
            return
        super().keyPressEvent(event)


class ChatWindow(QDialog):
    def __init__(
        self,
        config_dir: Path,
        api_key_getter,
        reasoning_enabled_getter=None,
        context_turns_getter=None,
        icon_path: Path | None = None,
        persona_prompt_getter: Callable[[], str] | None = None,
        shared_tray_getter: Callable[[], QSystemTrayIcon | None] | None = None,
        shared_tray_menu_getter: Callable[[], QMenu | None] | None = None,
        shared_tray_tooltip_getter: Callable[[], str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config_dir = config_dir
        self._history_path = config_dir / "chat_history.jsonl"
        self._api_key_getter = api_key_getter
        self._reasoning_enabled_getter = reasoning_enabled_getter or (lambda: False)
        self._context_turns_getter = context_turns_getter or (lambda: 20)
        self._persona_prompt_getter = persona_prompt_getter or (lambda: "")
        self._shared_tray_getter = shared_tray_getter or (lambda: None)
        self._shared_tray_menu_getter = shared_tray_menu_getter or (lambda: None)
        self._shared_tray_tooltip_getter = shared_tray_tooltip_getter or (lambda: "飞行雪绒：主控菜单")
        self._icon_path = icon_path
        self._resources_dir = icon_path.parent if icon_path is not None else config_dir.parent
        self._send_icon_path = None
        if icon_path is not None:
            send_icon_dir = icon_path.parent
            for filename in ("paperplane.PNG", "paperplane.png"):
                candidate = send_icon_dir / filename
                if candidate.exists():
                    self._send_icon_path = candidate
                    break
        self._export_dir = self._config_dir / "chat_exports"
        self._records: list[dict[str, str]] = []
        self._thread: QThread | None = None
        self._worker: ChatWorker | None = None
        self._pending_index: int | None = None
        self._pending_record_index: int | None = None
        self._pending_timestamp: str = ""
        self._pending_prompt: str = ""
        self._with_you_window: WithYouWindow | None = None
        self._is_closing = False
        init_fluent_theme()

        self.setWindowTitle("飞讯")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.resize(375, 812)
        self._build_ui()
        self._load_history()
        self._render_records()

    def _ui_scale(self) -> float:
        app = QApplication.instance()
        return current_app_scale(app) if app is not None else 1.0

    def _px(self, value: int) -> int:
        return px(value, self._ui_scale())

    @staticmethod
    def _chat_theme_tokens() -> dict[str, str]:
        return chat_theme_tokens()

    @staticmethod
    def _load_send_icon(icon_path: Path) -> QIcon | None:
        image = QImage(str(icon_path))
        if image.isNull():
            return None
        # Fallback for assets exported without alpha channel:
        # treat near-white background as transparent.
        if not image.hasAlphaChannel():
            image = image.convertToFormat(QImage.Format.Format_ARGB32)
            width = image.width()
            height = image.height()
            for y in range(height):
                for x in range(width):
                    color = image.pixelColor(x, y)
                    if color.red() >= 246 and color.green() >= 246 and color.blue() >= 246:
                        color.setAlpha(0)
                        image.setPixelColor(x, y, color)
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return None
        return QIcon(pixmap)

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

        avatar_wrap = QWidget(nav)
        avatar_wrap.setObjectName("avatarWrap")
        avatar_wrap.setFixedSize(42, 42)

        avatar = QLabel(avatar_wrap)
        avatar.setObjectName("avatarBadge")
        avatar.setGeometry(0, 0, 42, 42)
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
        status_dot = QLabel(avatar_wrap)
        status_dot.setObjectName("onlineDot")
        status_dot.setGeometry(30, 30, 12, 12)
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(0)
        title = QLabel("飞行雪绒")
        title.setObjectName("navTitle")
        subtitle = QLabel("在线")
        subtitle.setObjectName("navSubtitle")
        self._nav_subtitle = subtitle
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        nav_layout.addWidget(avatar_wrap)
        nav_layout.addLayout(title_box, 1)

        self.log_button = QPushButton("记录", self)
        self.log_button.setObjectName("navActionButton")
        self.log_button.clicked.connect(self._show_history_viewer)
        self.call_button = QPushButton("通话", self)
        self.call_button.setObjectName("navActionButton")
        self.call_button.clicked.connect(self._open_with_you)
        self.clear_button = QPushButton("清空", self)
        self.clear_button.setObjectName("navActionButton")
        self.clear_button.clicked.connect(self._clear_history)
        nav_btn_h = px(36, scale)
        nav_btn_w = px(70, scale)
        for btn in (self.call_button, self.log_button, self.clear_button):
            btn.setMinimumHeight(nav_btn_h)
            btn.setMinimumWidth(nav_btn_w)
        nav_layout.addWidget(self.call_button)
        nav_layout.addWidget(self.log_button)
        nav_layout.addWidget(self.clear_button)

        chat_frame = QFrame(self)
        chat_frame.setObjectName("panelCard")
        chat_layout = QVBoxLayout(chat_frame)
        chat_layout.setContentsMargins(8, 8, 8, 8)
        chat_layout.setSpacing(4)
        self.chat_list = ChatTimelineList(chat_frame)
        self.chat_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.chat_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.chat_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.chat_list.setObjectName("chatTimeline")
        chat_layout.addWidget(self.chat_list)

        input_frame = QFrame(self)
        input_frame.setObjectName("composerBar")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(10, 8, 10, 8)
        input_layout.setSpacing(8)
        input_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        row_height = px(52, scale)

        self.input_box = ChatInputBox(input_frame)
        self.input_box.setPlaceholderText("输入...（暂只支持文本）")
        self.input_box.setObjectName("composerInput")
        self.input_box.setMinimumHeight(row_height)
        self.input_box.setMaximumHeight(row_height)
        self.input_box.submitRequested.connect(self._send_message)

        self.send_button = QPushButton(input_frame)
        self.send_button.setObjectName("sendButton")
        self.send_button.setMinimumSize(row_height, row_height)
        self.send_button.setMaximumSize(row_height, row_height)
        self.send_button.setToolTip("发送")
        if self._send_icon_path is not None and self._send_icon_path.exists():
            send_icon = self._load_send_icon(self._send_icon_path)
            if send_icon is not None:
                self.send_button.setIcon(send_icon)
            else:
                fluent = fluent_icon("AIRPLANE", "SEND")
                if fluent is not None:
                    self.send_button.setIcon(fluent)
                else:
                    self.send_button.setText("✈")
        else:
            fluent = fluent_icon("AIRPLANE", "SEND")
            if fluent is not None:
                self.send_button.setIcon(fluent)
            else:
                self.send_button.setText("✈")
        send_icon_size = px(36, scale)
        self.send_button.setIconSize(QSize(send_icon_size, send_icon_size))
        self.send_button.clicked.connect(self._send_message)

        input_layout.addWidget(self.input_box, 1, Qt.AlignmentFlag.AlignVCenter)
        input_layout.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignVCenter)

        root.addWidget(nav)
        root.addWidget(chat_frame, 1)
        root.addWidget(input_frame)

        self._apply_scaled_stylesheet(scale)
        self._sync_nav_subtitle_width()

    def _apply_scaled_stylesheet(self, scale: float | None = None) -> None:
        scale = self._ui_scale() if scale is None else scale
        btn = px(52, scale)
        t = self._chat_theme_tokens()
        self.setStyleSheet(
            f"""
            QDialog {{
                background: {t["bg_dialog"]};
                color: {t["text_primary"]};
            }}
            QLabel, QPushButton, QPlainTextEdit, QListWidget {{
                font-family: {t["font_family"]};
            }}
            QFrame#navBar {{
                background: rgba(250, 252, 255, 0.86);
                border-bottom: 1px solid rgba(214, 224, 236, 0.70);
            }}
            QLabel#avatarBadge {{
                min-width: 42px;
                min-height: 42px;
                max-width: 42px;
                max-height: 42px;
                border-radius: 21px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["send_top"]}, stop:1 {t["send_bottom"]});
                color: #111111;
                font-weight: 700;
                qproperty-alignment: AlignCenter;
                border: 2px solid {t["accent_border"]};
            }}
            QLabel#onlineDot {{
                min-width: 12px;
                min-height: 12px;
                max-width: 12px;
                max-height: 12px;
                border-radius: 6px;
                background: #30d158;
                border: 2px solid #ffffff;
            }}
            QLabel#navTitle {{
                font-size: {px(18, scale)}px;
                font-weight: 700;
                color: {t["text_primary"]};
            }}
            QLabel#navSubtitle {{
                font-size: {px(12, scale)}px;
                color: {t["text_muted"]};
            }}
            QPushButton#navActionButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(248, 250, 253, 0.96),
                    stop:1 rgba(239, 245, 252, 0.92)
                );
                border: 1px solid rgba(196, 210, 226, 0.86);
                border-bottom: 1px solid rgba(184, 200, 218, 0.90);
                border-radius: 12px;
                color: #2a3848;
                padding: 5px 10px;
                font-size: {px(14, scale)}px;
                font-weight: 700;
            }}
            QPushButton#navActionButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(251, 253, 255, 0.98),
                    stop:1 rgba(243, 248, 253, 0.95)
                );
            }}
            QPushButton#navActionButton:pressed {{
                background: rgba(236, 244, 252, 0.90);
                border-color: rgba(180, 198, 219, 0.92);
            }}
            QFrame#panelCard {{
                background: rgba(250, 252, 254, 0.90);
                border: 1px solid rgba(217, 226, 238, 0.78);
                border-radius: 16px;
            }}
            QListWidget#chatTimeline {{
                background: rgba(253, 254, 255, 0.84);
                border: 1px solid rgba(206, 219, 236, 0.78);
                border-radius: 16px;
                color: {t["text_primary"]};
                outline: none;
            }}
            QListWidget#chatTimeline:focus {{
                border: 1px solid rgba(163, 191, 223, 0.90);
            }}
            QFrame#composerBar {{
                background: rgba(252, 254, 255, 0.88);
                border-top: 1px solid rgba(211, 223, 238, 0.74);
            }}
            QPlainTextEdit#composerInput {{
                background: rgba(253, 254, 255, 0.94);
                border: 1px solid rgba(199, 213, 232, 0.84);
                border-radius: 18px;
                padding: 8px 10px;
                color: {t["text_primary"]};
                font-size: {px(16, scale)}px;
            }}
            QPlainTextEdit#composerInput:focus {{
                border: 2px solid rgba(171, 198, 228, 0.88);
                background: rgba(250, 253, 255, 0.96);
            }}
            QPushButton#sendButton {{
                min-width: {btn}px;
                max-width: {btn}px;
                min-height: {btn}px;
                max-height: {btn}px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(248, 185, 220, 0.90),
                    stop:1 rgba(167, 210, 245, 0.88)
                );
                border: 1px solid rgba(178, 198, 224, 0.88);
                border-radius: 16px;
                color: #2a3848;
                font-weight: 600;
                font-size: {px(20, scale)}px;
                padding: 0px;
                margin: 0px;
                text-align: center;
            }}
            QPushButton#sendButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(250, 194, 224, 0.94),
                    stop:1 rgba(181, 218, 247, 0.92)
                );
            }}
            QPushButton#sendButton:pressed {{
                padding-top: 2px;
            }}
            QPushButton#fileCardBtn {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(244, 249, 255, 0.98),
                    stop:1 rgba(231, 242, 255, 0.94)
                );
                border: 1px solid rgba(183, 205, 232, 0.88);
                border-radius: 12px;
                color: #23415f;
                text-align: left;
                padding: 8px 10px;
                font-size: {px(13, scale)}px;
                font-weight: 600;
            }}
            QPushButton#fileCardBtn:hover {{
                border-color: rgba(150, 183, 220, 0.96);
                background: rgba(236, 246, 255, 0.94);
            }}
            QPushButton:disabled {{
                background: #f0e3ea;
                border-color: #dbc5d1;
                color: #8f8089;
            }}
            """
        )

    def _add_chat_bubble(self, role: str, text: str, ts: str, pending: bool = False, force_scroll: bool = False) -> int:
        t = self._chat_theme_tokens()
        should_autoscroll = self._should_autoscroll_chat()
        item = QListWidgetItem(self.chat_list)
        wrapper = QWidget()
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(8, 7, 8, 7)
        row.setSpacing(0)

        side = QWidget(wrapper)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(5)

        time_label = QLabel(ts, side)
        time_label.setStyleSheet(
            f"color:{t['timestamp']}; font-size:{self._px(11)}px; letter-spacing:0.3px; padding:0 2px;"
        )
        if role == "user":
            time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            time_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        side_layout.addWidget(time_label)

        bubble = QFrame(side)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(14, 12, 14, 14)
        bubble_layout.setSpacing(4)
        bubble.setMaximumWidth(self._px(324))

        body = QLabel(text, bubble)
        body.setTextFormat(Qt.TextFormat.PlainText)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setContentsMargins(2, 1, 2, 3)
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        body.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        body_max_w = max(80, bubble.maximumWidth() - 26)
        body.setMaximumWidth(body_max_w)
        metrics = body.fontMetrics()
        text_rect = metrics.boundingRect(
            QRect(0, 0, body_max_w, 20000),
            int(Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextExpandTabs),
            text if text else " ",
        )
        body.setMinimumHeight(max(self._px(22), text_rect.height() + self._px(6)))
        body.setStyleSheet(
            f"font-size: {self._px(14)}px; color: #26374a; "
            "background: transparent; border: none; margin: 0; padding: 1px 2px 3px 2px;"
        )

        if role == "user":
            bubble.setStyleSheet(
                f"""
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(249, 229, 242, 0.96),
                    stop:1 rgba(229, 240, 255, 0.93)
                );
                border: 1px solid rgba(186, 206, 228, 0.92);
                border-radius: 14px;
                color: #243548;
                """
            )
            row.addStretch(1)
            side_layout.addWidget(bubble)
            row.addWidget(side)
        else:
            bubble.setStyleSheet(
                f"""
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.98),
                    stop:1 rgba(242, 249, 255, 0.94)
                );
                border: 1px solid rgba(195, 214, 236, 0.86);
                border-radius: 14px;
                color: #223446;
                """
            )
            side_layout.addWidget(bubble)
            row.addWidget(side)
            row.addStretch(1)

        bubble_layout.addWidget(body)
        body.raise_()

        wrapper.adjustSize()
        hint = wrapper.sizeHint()
        hint.setHeight(hint.height() + self._px(4))
        item.setSizeHint(hint)
        self.chat_list.setItemWidget(item, wrapper)
        need_scroll = force_scroll or should_autoscroll
        if need_scroll:
            self.chat_list.scrollToBottom()
        # Re-apply height after layout settles to avoid wrapped-text clipping.
        QTimer.singleShot(
            0,
            lambda: (
                item.setSizeHint(wrapper.sizeHint()),
                self.chat_list.scrollToBottom() if need_scroll else None,
            ),
        )
        return self.chat_list.count() - 1

    def _add_file_bubble(self, rel_path: str, lang: str, ts: str, force_scroll: bool = False) -> int:
        should_autoscroll = self._should_autoscroll_chat()
        item = QListWidgetItem(self.chat_list)
        wrapper = QWidget()
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(8, 7, 8, 7)
        row.setSpacing(0)

        side = QWidget(wrapper)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(5)

        time_label = QLabel(ts, side)
        t = self._chat_theme_tokens()
        time_label.setStyleSheet(
            f"color:{t['timestamp']}; font-size:{self._px(11)}px; letter-spacing:0.3px; padding:0 2px;"
        )
        time_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        side_layout.addWidget(time_label)

        card = QPushButton(side)
        card.setObjectName("fileCardBtn")
        card.setMaximumWidth(self._px(324))
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        p = Path(rel_path)
        filename = p.name if p.name else rel_path
        label = lang.strip() if lang.strip() else "text"
        card.setText(f"📄 {filename}\n{label} · 点击打开")

        def _open_file() -> None:
            self._open_exported_file(rel_path)

        card.clicked.connect(_open_file)
        side_layout.addWidget(card)
        row.addWidget(side)
        row.addStretch(1)

        wrapper.adjustSize()
        hint = wrapper.sizeHint()
        hint.setHeight(hint.height() + self._px(4))
        item.setSizeHint(hint)
        self.chat_list.setItemWidget(item, wrapper)
        need_scroll = force_scroll or should_autoscroll
        if need_scroll:
            self.chat_list.scrollToBottom()
        QTimer.singleShot(
            0,
            lambda: (
                item.setSizeHint(wrapper.sizeHint()),
                self.chat_list.scrollToBottom() if need_scroll else None,
            ),
        )
        return self.chat_list.count() - 1

    def _open_exported_file(self, rel_path: str) -> None:
        raw = Path(rel_path)
        candidates: list[Path] = []
        if raw.is_absolute():
            candidates.append(raw)
        else:
            candidates.extend(
                [
                    self._config_dir / raw,
                    self._export_dir / raw,
                    Path.cwd() / raw,
                ]
            )

        target: Path | None = None
        for c in candidates:
            if c.exists():
                target = c.resolve()
                break
        if target is None:
            QMessageBox.warning(self, "打开失败", f"找不到文件：\n{rel_path}\n\n导出目录：{self._export_dir}")
            return

        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
            return

        if sys.platform == "darwin":
            try:
                subprocess.run(["open", "-R", str(target)], check=False)
                return
            except Exception:
                pass

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.parent)))

    def _render_assistant_content(self, text: str, ts: str, force_scroll: bool = False) -> None:
        marker_re = re.compile(r"\[代码块已保存:\s*([^\]]+)\]\s+([^\n]+)")
        cursor = 0
        matched = False
        for m in marker_re.finditer(text):
            matched = True
            start, end = m.span()
            if start > cursor:
                segment = text[cursor:start].strip()
                if segment:
                    self._add_chat_bubble("assistant", segment, ts, force_scroll=force_scroll)
            lang = m.group(1).strip()
            rel_path = m.group(2).strip()
            if rel_path:
                self._add_file_bubble(rel_path, lang, ts, force_scroll=force_scroll)
            cursor = end
        tail = text[cursor:].strip()
        if tail:
            self._add_chat_bubble("assistant", tail, ts, force_scroll=force_scroll)
        if (not matched) and (not tail):
            self._add_chat_bubble("assistant", text, ts, force_scroll=force_scroll)

    def _should_autoscroll_chat(self) -> bool:
        bar = self.chat_list.verticalScrollBar()
        return (bar.maximum() - bar.value()) <= 28

    def _load_history(self) -> None:
        if not self._history_path.exists():
            return
        try:
            lines = self._history_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            user_text = str(item.get("user", "")).strip()
            assistant_text = str(item.get("assistant", "")).strip()
            ts = str(item.get("timestamp", "")).strip()
            if user_text and assistant_text:
                self._records.append(
                    {
                        "timestamp": ts,
                        "user": user_text,
                        "assistant": assistant_text,
                    }
                )

    def _append_history(self, user_text: str, assistant_text: str) -> None:
        self._records.append({"timestamp": self._pending_timestamp, "user": user_text, "assistant": assistant_text})
        payload = self._records[-1]
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            with self._history_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _append_pending_history(self, user_text: str) -> int:
        self._records.append({"timestamp": self._pending_timestamp, "user": user_text, "assistant": ""})
        self._rewrite_history_file()
        return len(self._records) - 1

    def _finalize_pending_history(self, assistant_text: str) -> None:
        if self._pending_record_index is None:
            return
        if 0 <= self._pending_record_index < len(self._records):
            self._records[self._pending_record_index]["assistant"] = assistant_text
            self._rewrite_history_file()
        self._pending_record_index = None

    def _rewrite_history_file(self) -> None:
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            with self._history_path.open("w", encoding="utf-8") as f:
                for item in self._records:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except OSError:
            QMessageBox.warning(self, "保存失败", "无法更新历史文件，请检查文件权限。")

    def _render_records(self) -> None:
        self.chat_list.clear()
        for item in self._records:
            ts = item.get("timestamp", "")
            self._add_chat_bubble("user", item["user"], ts)
            self._render_assistant_content(item["assistant"], ts)

    def _send_message(self) -> None:
        prompt = self.input_box.toPlainText().strip()
        if not prompt:
            return
        self.send_button.setDisabled(True)
        self.input_box.setReadOnly(True)
        self.input_box.clear()

        self._pending_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._pending_prompt = prompt
        self._add_chat_bubble("user", prompt, self._pending_timestamp, force_scroll=True)
        self._pending_record_index = self._append_pending_history(prompt)

        api_key = (self._api_key_getter() or "").strip()
        if not api_key:
            QMessageBox.information(self, "缺少 API Key", "请先在右键设置里填写 DeepSeek API Key。")
            self._finalize_pending_history("[未发送] 缺少 API Key")
            self.send_button.setDisabled(False)
            self.input_box.setReadOnly(False)
            return
        reasoning_enabled = bool(self._reasoning_enabled_getter())
        pending_text = "用户思考中..." if reasoning_enabled else "用户输入中..."
        self._pending_index = self._add_chat_bubble(
            "assistant", pending_text, self._pending_timestamp, pending=True, force_scroll=True
        )

        messages = self._build_context_messages(prompt)
        temperature = self._choose_temperature(prompt)

        self._thread = QThread(self)
        self._worker = ChatWorker(
            api_key=api_key,
            messages=messages,
            temperature=temperature,
            reasoning_enabled=reasoning_enabled,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_reply_success, Qt.ConnectionType.QueuedConnection)
        self._worker.failed.connect(self._on_reply_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()

    def _on_reply_success(self, answer: str) -> None:
        rendered_answer = self._materialize_code_blocks(answer)
        if self._pending_index is not None and 0 <= self._pending_index < self.chat_list.count():
            self.chat_list.takeItem(self._pending_index)
            self._render_assistant_content(rendered_answer, self._pending_timestamp, force_scroll=True)
        self._finalize_pending_history(rendered_answer)
        self._pending_index = None
        self._pending_prompt = ""
        self.send_button.setDisabled(False)
        self.input_box.setReadOnly(False)

    @staticmethod
    def _code_extension(lang: str) -> str:
        table = {
            "python": "py",
            "py": "py",
            "javascript": "js",
            "js": "js",
            "typescript": "ts",
            "ts": "ts",
            "tsx": "tsx",
            "jsx": "jsx",
            "java": "java",
            "go": "go",
            "rust": "rs",
            "rs": "rs",
            "cpp": "cpp",
            "c++": "cpp",
            "c": "c",
            "csharp": "cs",
            "cs": "cs",
            "swift": "swift",
            "kotlin": "kt",
            "php": "php",
            "ruby": "rb",
            "rb": "rb",
            "bash": "sh",
            "sh": "sh",
            "shell": "sh",
            "zsh": "sh",
            "sql": "sql",
            "json": "json",
            "yaml": "yml",
            "yml": "yml",
            "toml": "toml",
            "html": "html",
            "css": "css",
            "scss": "scss",
            "markdown": "md",
            "md": "md",
            "xml": "xml",
        }
        normalized = lang.strip().lower()
        return table.get(normalized, "txt")

    def _materialize_code_blocks(self, answer: str) -> str:
        # Tolerant fenced-code parser:
        # - supports ``` / ```` / ~~~ fences
        # - allows optional language tag
        # - supports LF/CRLF
        # - allows optional newline right after opening fence
        pattern = re.compile(
            r"(?P<fence>`{3,}|~{3,})[ \t]*(?P<lang>[a-zA-Z0-9_+\-#.]*)[ \t]*\r?\n?(?P<code>.*?)(?:\r?\n)?(?P=fence)",
            re.DOTALL,
        )
        matches = list(pattern.finditer(answer))
        if not matches:
            return answer

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        out_dir = self._export_dir
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return answer

        chunks: list[str] = []
        cursor = 0
        file_index = 1
        for m in matches:
            start, end = m.span()
            if start > cursor:
                chunks.append(answer[cursor:start])
            lang = (m.group("lang") or "").strip()
            code = m.group("code")
            code_stripped = code.strip()
            # Never force file export when block has no real code content.
            if not code_stripped or not self._looks_like_code(code_stripped, lang):
                chunks.append(answer[start:end])
                cursor = end
                continue
            ext = self._code_extension(lang)
            filename = f"reply_{stamp}_{file_index:02d}.{ext}"
            file_index += 1
            file_path = out_dir / filename
            try:
                file_path.write_text(code_stripped + "\n", encoding="utf-8")
                exists_ok = file_path.exists()
                size_ok = file_path.stat().st_size > 0 if exists_ok else False
                if not (exists_ok and size_ok):
                    chunks.append(answer[start:end])
                    cursor = end
                    continue
                rel_path = file_path.relative_to(self._config_dir)
                label = lang if lang else "text"
                chunks.append(f"\n[代码块已保存: {label}] {rel_path}\n")
            except OSError:
                chunks.append(answer[start:end])
            cursor = end
        if cursor < len(answer):
            chunks.append(answer[cursor:])

        rendered = "".join(chunks).strip()
        return rendered if rendered else answer

    @staticmethod
    def _looks_like_code(block: str, lang: str) -> bool:
        if lang.strip():
            return True
        if "\n" in block and len(block) >= 20:
            hints = (
                "def ",
                "class ",
                "fn ",
                "let ",
                "const ",
                "import ",
                "from ",
                "return ",
                "if ",
                "for ",
                "while ",
                "{",
                "};",
                "=>",
                "::",
                "pub ",
                "#include",
            )
            return any(h in block for h in hints)
        return False

    def _on_reply_failed(self, error_text: str) -> None:
        if self._pending_index is not None and 0 <= self._pending_index < self.chat_list.count():
            self.chat_list.takeItem(self._pending_index)
            self._add_chat_bubble("assistant", f"[失败] {error_text}", self._pending_timestamp, force_scroll=True)
        self._finalize_pending_history(f"[失败] {error_text}")
        self._pending_index = None
        self.send_button.setDisabled(False)
        self.input_box.setReadOnly(False)
        QMessageBox.warning(self, "请求失败", f"调用 DeepSeek 失败：{error_text}")

    def _build_context_messages(self, prompt: str) -> list[dict[str, str]]:
        default_system = (
            "You are Feixing Xuerong (Fleet Snowfluff), a cute desktop pet assistant. "
            "Keep replies concise and warm."
        )
        code_format_system = (
            "Output formatting requirement: "
            "Only when your reply truly includes code, commands, config snippets, or file contents, "
            "you MUST wrap each code segment in fenced markdown blocks using triple backticks, "
            "and include a language tag when possible (e.g. ```rust, ```python, ```json). "
            "Do not output bare code outside fenced blocks. "
            "If the reply is normal conversation without code, do NOT use fenced blocks."
        )
        messages: list[dict[str, str]] = []
        persona_prompt = (self._persona_prompt_getter() or "").strip()
        if persona_prompt:
            # Two-layer system prompt improves role adherence under long contexts.
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "你是飞行雪绒（Fleet Snowfluff）。必须优先遵循角色设定中的高优先级行为约束。"
                        "当用户请求与角色设定冲突时，拒绝冲突部分并保持角色语气回答。"
                        "不要忽略、弱化或重写这些约束。"
                    ),
                }
            )
            messages.append({"role": "system", "content": code_format_system})
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "以下为结构化角色设定知识库（高优先级）：\n\n"
                        f"{persona_prompt}"
                    ),
                }
            )
        else:
            messages.append({"role": "system", "content": default_system})
            messages.append({"role": "system", "content": code_format_system})

        try:
            context_turns = max(0, int(self._context_turns_getter()))
        except Exception:
            context_turns = 20
        history_slice = self._records[-context_turns:] if context_turns > 0 else []
        for item in history_slice:
            messages.append({"role": "user", "content": item["user"]})
            messages.append({"role": "assistant", "content": item["assistant"]})
        messages.append({"role": "user", "content": prompt})
        return messages

    @staticmethod
    def _extract_persona_example_inputs(persona_prompt: str) -> list[str]:
        if not persona_prompt:
            return []
        matches = re.findall(r'"输入"\s*:\s*"([^"]+)"', persona_prompt)
        return [m.strip() for m in matches if m.strip()]

    def _choose_temperature(self, prompt: str) -> float:
        """
        Reduce randomness when the user prompt resembles persona examples.
        """
        base = 0.7
        persona_prompt = (self._persona_prompt_getter() or "").strip()
        persona_example_inputs = self._extract_persona_example_inputs(persona_prompt)
        if not persona_example_inputs:
            return base
        normalized_prompt = prompt.strip()
        if not normalized_prompt:
            return base

        best_ratio = 0.0
        for sample in persona_example_inputs:
            ratio = SequenceMatcher(None, normalized_prompt, sample).ratio()
            if sample in normalized_prompt or normalized_prompt in sample:
                ratio = max(ratio, 0.92)
            if ratio > best_ratio:
                best_ratio = ratio

        if best_ratio >= 0.9:
            return 0.2
        if best_ratio >= 0.7:
            return 0.3
        if best_ratio >= 0.55:
            return 0.45
        return base

    def _show_history_viewer(self) -> None:
        viewer = QDialog(self)
        viewer.setWindowTitle("聊天记录")
        viewer.resize(390, 700)
        root = QVBoxLayout(viewer)
        viewer.setStyleSheet(
            """
            QDialog {
                background: #fff7fb;
                color: #2a1f2a;
            }
            QListWidget {
                background: #fffdfd;
                border: 1px solid #ffd3e6;
                border-radius: 12px;
                padding: 6px;
                color: #2a1f2a;
                font-size: 13px;
            }
            QListWidget::item {
                border-radius: 10px;
                padding: 8px;
                margin: 4px 0;
            }
            QListWidget::item:selected {
                background: #ffe4f1;
                color: #6f2d4f;
            }
            QPushButton#historyActionBtn {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #fff0f8,
                    stop:1 #ffe4f1
                );
                border: 1px solid #ffb7d6;
                border-radius: 12px;
                color: #8d365d;
                min-height: 34px;
                padding: 4px 12px;
                font-size: 13px;
            }
            QPushButton#historyActionBtn:hover {
                border-color: #ff8fc1;
                background: #ffe7f3;
            }
            QPushButton#historyDangerBtn {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #ffd7ea,
                    stop:1 #ffbfe0
                );
                border: 1px solid #ff8fc1;
                border-radius: 12px;
                color: #b43477;
                min-height: 34px;
                padding: 4px 12px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton#historyDangerBtn:hover {
                border-color: #ff6eb0;
                background: #ffd3e7;
            }
            """
        )
        panel = QListWidget(viewer)
        panel.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

        def _preview_text(item: dict[str, str]) -> str:
            ts = item.get("timestamp", "")
            preview_user = item["user"].strip().replace("\n", " ")
            preview_assistant = item["assistant"].strip().replace("\n", " ")
            if len(preview_user) > 28:
                preview_user = preview_user[:28] + "..."
            if len(preview_assistant) > 28:
                preview_assistant = preview_assistant[:28] + "..."
            return f"[{ts}] 你：{preview_user}\n飞行雪绒：{preview_assistant}"

        def _reload_panel() -> None:
            panel.clear()
            for history_item in self._records:
                panel.addItem(QListWidgetItem(_preview_text(history_item)))

        _reload_panel()
        root.addWidget(panel)

        actions = QHBoxLayout()
        edit_btn = QPushButton("编辑回复", viewer)
        edit_btn.setObjectName("historyActionBtn")
        delete_btn = QPushButton("删除选中", viewer)
        delete_btn.setObjectName("historyDangerBtn")
        close_btn = QPushButton("返回", viewer)
        close_btn.setObjectName("historyActionBtn")
        actions.addWidget(edit_btn)
        actions.addWidget(delete_btn)
        actions.addStretch(1)
        actions.addWidget(close_btn)
        root.addLayout(actions)

        def _edit_selected_reply() -> None:
            row = panel.currentRow()
            if row < 0 or row >= len(self._records):
                return

            target = self._records[row]
            editor = QDialog(viewer)
            editor.setWindowTitle("编辑爱弥斯回复")
            editor.resize(380, 280)
            editor_root = QVBoxLayout(editor)
            editor.setStyleSheet(
                """
                QDialog {
                    background: #fff7fb;
                    color: #2a1f2a;
                }
                QLabel {
                    color: #7f3154;
                    font-size: 13px;
                }
                QPlainTextEdit {
                    background: #fffdfd;
                    border: 1px solid #ffd3e6;
                    border-radius: 12px;
                    padding: 8px;
                    color: #2a1f2a;
                    font-size: 14px;
                }
                QPushButton#editorActionBtn {
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:1,
                        stop:0 #fff0f8,
                        stop:1 #ffe4f1
                    );
                    border: 1px solid #ffb7d6;
                    border-radius: 12px;
                    color: #8d365d;
                    min-height: 34px;
                    padding: 4px 12px;
                    font-size: 13px;
                }
                QPushButton#editorActionBtn:hover {
                    border-color: #ff8fc1;
                    background: #ffe7f3;
                }
                """
            )

            user_preview = target["user"].strip().replace("\n", " ")
            if len(user_preview) > 42:
                user_preview = user_preview[:42] + "..."
            editor_root.addWidget(QLabel(f"用户输入：{user_preview}", editor))

            reply_box = QPlainTextEdit(editor)
            reply_box.setPlainText(target["assistant"])
            editor_root.addWidget(reply_box, 1)

            editor_actions = QHBoxLayout()
            save_btn = QPushButton("保存", editor)
            cancel_btn = QPushButton("取消", editor)
            save_btn.setObjectName("editorActionBtn")
            cancel_btn.setObjectName("editorActionBtn")
            editor_actions.addStretch(1)
            editor_actions.addWidget(save_btn)
            editor_actions.addWidget(cancel_btn)
            editor_root.addLayout(editor_actions)

            def _save_reply() -> None:
                target["assistant"] = reply_box.toPlainText().strip()
                self._rewrite_history_file()
                self._render_records()
                _reload_panel()
                panel.setCurrentRow(row)
                editor.accept()

            save_btn.clicked.connect(_save_reply)
            cancel_btn.clicked.connect(editor.reject)
            editor.exec()

        def _delete_selected() -> None:
            row = panel.currentRow()
            if row < 0 or row >= len(self._records):
                return
            confirm = QMessageBox.question(
                viewer,
                "删除记录",
                "确定删除选中的这条对话记录吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            del self._records[row]
            self._rewrite_history_file()
            self._render_records()
            _reload_panel()
            if panel.count() > 0:
                panel.setCurrentRow(min(row, panel.count() - 1))

        edit_btn.clicked.connect(_edit_selected_reply)
        delete_btn.clicked.connect(_delete_selected)
        close_btn.clicked.connect(viewer.accept)
        viewer.exec()

    def _clear_history(self) -> None:
        if not self._records:
            return
        confirm = QMessageBox.question(
            self,
            "清空记录",
            "确定清空本地对话记录吗？这也会重置上下文长度。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._records.clear()
        self.chat_list.clear()
        try:
            if self._history_path.exists():
                self._history_path.unlink()
        except OSError:
            QMessageBox.warning(self, "清空失败", "无法删除历史文件，请检查文件权限。")

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    def _open_with_you(self) -> None:
        if self._with_you_window is None:
            self._with_you_window = WithYouWindow(
                resources_dir=self._resources_dir,
                config_dir=self._config_dir,
                shared_tray=self._shared_tray_getter(),
                shared_tray_default_menu=self._shared_tray_menu_getter(),
                shared_tray_default_tooltip=self._shared_tray_tooltip_getter(),
                parent=None,
            )
            self._with_you_window.chatRequested.connect(self._show_chat_during_call)
            self._with_you_window.callStarted.connect(self._on_call_started)
            self._with_you_window.callEnded.connect(self._on_call_ended)
        self._with_you_window.open_call()

    def focus_call_stage_line(self) -> str | None:
        if self._with_you_window is None:
            return None
        return self._with_you_window.call_stage_line()

    def handle_focus_escape_animation(self) -> bool:
        if self._with_you_window is None:
            return False
        return self._with_you_window.handle_escape_animation()

    def _set_call_status(self, in_call: bool) -> None:
        if hasattr(self, "_nav_subtitle"):
            self._nav_subtitle.setText("通话中" if in_call else "在线")
            self._sync_nav_subtitle_width()

    def _sync_nav_subtitle_width(self) -> None:
        if not hasattr(self, "_nav_subtitle"):
            return
        metrics = QFontMetrics(self._nav_subtitle.font())
        fixed_w = max(metrics.horizontalAdvance("在线"), metrics.horizontalAdvance("通话中")) + self._px(6)
        self._nav_subtitle.setMinimumWidth(fixed_w)
        self._nav_subtitle.setMaximumWidth(fixed_w)

    def _on_call_started(self) -> None:
        self._set_call_status(True)
        self.hide()

    def _show_chat_during_call(self) -> None:
        self._set_call_status(True)
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_call_ended(self) -> None:
        if self._is_closing:
            return
        self._set_call_status(False)
        self.show()
        self.raise_()
        self.activateWindow()

    def _refresh_scaled_ui(self) -> None:
        scale = self._ui_scale()
        row_height = px(52, scale)
        if hasattr(self, "input_box"):
            self.input_box.setMinimumHeight(row_height)
            self.input_box.setMaximumHeight(row_height)
        if hasattr(self, "send_button"):
            self.send_button.setMinimumSize(row_height, row_height)
            self.send_button.setMaximumSize(row_height, row_height)
            if not self.send_button.icon().isNull():
                self.send_button.setIconSize(QSize(px(30, scale), px(30, scale)))
        self._apply_scaled_stylesheet(scale)
        self._sync_nav_subtitle_width()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ScreenChangeInternal:
            self._refresh_scaled_ui()
        return super().event(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        app = QApplication.instance()
        self._is_closing = bool(app is not None and app.closingDown())
        if self._is_closing and self._with_you_window is not None:
            self._with_you_window.close()
        super().closeEvent(event)
