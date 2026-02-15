from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .with_you import WithYouWindow


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
        icon_path: Path | None = None,
        persona_prompt: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config_dir = config_dir
        self._history_path = config_dir / "chat_history.jsonl"
        self._api_key_getter = api_key_getter
        self._reasoning_enabled_getter = reasoning_enabled_getter or (lambda: False)
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
        self._persona_prompt = persona_prompt.strip()
        self._persona_example_inputs = self._extract_persona_example_inputs(self._persona_prompt)
        self._records: list[dict[str, str]] = []
        self._thread: QThread | None = None
        self._worker: ChatWorker | None = None
        self._pending_index: int | None = None
        self._pending_timestamp: str = ""
        self._pending_prompt: str = ""
        self._with_you_window: WithYouWindow | None = None
        self._is_closing = False

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
        row_height = 52

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
                self.send_button.setIconSize(QSize(52, 52))
            else:
                self.send_button.setText("✈")
        else:
            self.send_button.setText("✈")
        self.send_button.clicked.connect(self._send_message)

        input_layout.addWidget(self.input_box, 1, Qt.AlignmentFlag.AlignVCenter)
        input_layout.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignVCenter)

        root.addWidget(nav)
        root.addWidget(chat_frame, 1)
        root.addWidget(input_frame)

        self.setStyleSheet(
            """
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
            QLabel#onlineDot {
                min-width: 12px;
                min-height: 12px;
                max-width: 12px;
                max-height: 12px;
                border-radius: 6px;
                background: #30d158;
                border: 2px solid #ffffff;
            }
            QLabel#navTitle {
                font-size: 18px;
                font-weight: 700;
                color: #221626;
            }
            QLabel#navSubtitle {
                font-size: 12px;
                color: #9a6b85;
            }
            QPushButton#navActionButton {
                background: #fff0f7;
                border: 2px solid #ff9dc6;
                border-radius: 10px;
                color: #8d365d;
                padding: 4px 8px;
                font-size: 15px;
            }
            QFrame#panelCard {
                background: #fff7fb;
                border: none;
            }
            QListWidget#chatTimeline {
                background: #fff7fb;
                border: none;
                color: #2a1f2a;
            }
            QFrame#composerBar {
                background: #ffffff;
                border-top: 1px solid #ffd3e6;
            }
            QPlainTextEdit#composerInput {
                background: #fff2f8;
                border: 2px solid #ffb3d4;
                border-radius: 16px;
                padding: 8px;
                color: #2a1f2a;
                font-size: 16px;
            }
            QPushButton#sendButton {
                min-width: 52px;
                max-width: 52px;
                min-height: 52px;
                max-height: 52px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #ff5fa2,
                    stop:1 #ff8cc3
                );
                border: 2px solid #ff4f98;
                border-radius: 16px;
                color: #ffffff;
                font-weight: 600;
                font-size: 20px;
                padding: 0px;
            }
            QPushButton:disabled {
                background: #f3dbe8;
                border-color: #e8bfd3;
                color: #a68596;
            }
            """
        )

    def _add_chat_bubble(self, role: str, text: str, ts: str, pending: bool = False) -> int:
        should_autoscroll = self._should_autoscroll_chat()
        item = QListWidgetItem(self.chat_list)
        wrapper = QWidget()
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(6, 6, 6, 6)
        row.setSpacing(0)

        side = QWidget(wrapper)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(4)

        time_label = QLabel(ts, side)
        time_label.setStyleSheet("color:#9ba3c7; font-size:11px;")
        if role == "user":
            time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            time_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        side_layout.addWidget(time_label)

        bubble = QFrame(side)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 10, 12, 10)
        bubble_layout.setSpacing(4)
        bubble.setMaximumWidth(300)

        body = QLabel(text, bubble)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet(
            "font-size: 14px; "
            "background: transparent; border: none; margin: 0; padding: 0;"
        )

        if role == "user":
            bubble.setStyleSheet(
                """
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #ff5fa2,
                    stop:1 #ff8cc3
                );
                border: 2px solid #ff4f98;
                border-radius: 12px;
                color: #ffffff;
                """
            )
            row.addStretch(1)
            side_layout.addWidget(bubble)
            row.addWidget(side)
        else:
            bubble.setStyleSheet(
                """
                background:#fff0f7;
                border: 2px solid #ffb7d6;
                border-radius:12px;
                color:#2b1c2a;
                """
            )
            side_layout.addWidget(bubble)
            row.addWidget(side)
            row.addStretch(1)

        bubble_layout.addWidget(body)

        item.setSizeHint(wrapper.sizeHint())
        self.chat_list.setItemWidget(item, wrapper)
        if should_autoscroll:
            self.chat_list.scrollToBottom()
        return self.chat_list.count() - 1

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

    def _render_records(self) -> None:
        self.chat_list.clear()
        for item in self._records:
            ts = item.get("timestamp", "")
            self._add_chat_bubble("user", item["user"], ts)
            self._add_chat_bubble("assistant", item["assistant"], ts)

    def _send_message(self) -> None:
        prompt = self.input_box.toPlainText().strip()
        if not prompt:
            return
        self.send_button.setDisabled(True)
        self.input_box.setReadOnly(True)
        self.input_box.clear()

        self._pending_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._pending_prompt = prompt
        self._add_chat_bubble("user", prompt, self._pending_timestamp)

        api_key = (self._api_key_getter() or "").strip()
        if not api_key:
            QMessageBox.information(self, "缺少 API Key", "请先在右键设置里填写 DeepSeek API Key。")
            self.send_button.setDisabled(False)
            self.input_box.setReadOnly(False)
            return
        reasoning_enabled = bool(self._reasoning_enabled_getter())
        pending_text = "用户思考中..." if reasoning_enabled else "用户输入中..."
        self._pending_index = self._add_chat_bubble("assistant", pending_text, self._pending_timestamp, pending=True)

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
        if self._pending_index is not None and 0 <= self._pending_index < self.chat_list.count():
            self.chat_list.takeItem(self._pending_index)
            self._add_chat_bubble("assistant", answer, self._pending_timestamp)
        self._append_history(self._pending_prompt, answer)
        self._pending_index = None
        self._pending_prompt = ""
        self.send_button.setDisabled(False)
        self.input_box.setReadOnly(False)

    def _on_reply_failed(self, error_text: str) -> None:
        if self._pending_index is not None and 0 <= self._pending_index < self.chat_list.count():
            self.chat_list.takeItem(self._pending_index)
            self._add_chat_bubble("assistant", f"[失败] {error_text}", self._pending_timestamp)
        self._pending_index = None
        self.send_button.setDisabled(False)
        self.input_box.setReadOnly(False)
        QMessageBox.warning(self, "请求失败", f"调用 DeepSeek 失败：{error_text}")

    def _build_context_messages(self, prompt: str) -> list[dict[str, str]]:
        default_system = (
            "You are Feixing Xuerong (Fleet Snowfluff), a cute desktop pet assistant. "
            "Keep replies concise and warm."
        )
        messages: list[dict[str, str]] = []
        if self._persona_prompt:
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
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "以下为结构化角色设定知识库（高优先级）：\n\n"
                        f"{self._persona_prompt}"
                    ),
                }
            )
        else:
            messages.append({"role": "system", "content": default_system})

        for item in self._records[-20:]:
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
        if not self._persona_example_inputs:
            return base
        normalized_prompt = prompt.strip()
        if not normalized_prompt:
            return base

        best_ratio = 0.0
        for sample in self._persona_example_inputs:
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
        panel = QListWidget(viewer)
        panel.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        for item in self._records:
            ts = item.get("timestamp", "")
            panel.addItem(QListWidgetItem(f"[{ts}] 你：{item['user']}"))
            panel.addItem(QListWidgetItem(f"[{ts}] 飞行雪绒：{item['assistant']}"))
            panel.addItem(QListWidgetItem("-" * 34))
        root.addWidget(panel)
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
            self._with_you_window = WithYouWindow(resources_dir=self._resources_dir, parent=None)
            self._with_you_window.chatRequested.connect(self._show_chat_during_call)
            self._with_you_window.callStarted.connect(self._on_call_started)
            self._with_you_window.callEnded.connect(self._on_call_ended)
        self._with_you_window.open_call()

    def _set_call_status(self, in_call: bool) -> None:
        if hasattr(self, "_nav_subtitle"):
            self._nav_subtitle.setText("通话中" if in_call else "在线")

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

    def closeEvent(self, event: QCloseEvent) -> None:
        app = QApplication.instance()
        self._is_closing = bool(app is not None and app.closingDown())
        if self._is_closing and self._with_you_window is not None:
            self._with_you_window.close()
        super().closeEvent(event)
