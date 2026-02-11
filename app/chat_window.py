from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ChatWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, api_key: str, messages: list[dict[str, str]]) -> None:
        super().__init__()
        self.api_key = api_key
        self.messages = messages

    def run(self) -> None:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=self.messages,
                temperature=0.7,
            )
            answer = response.choices[0].message.content if response.choices else ""
            answer = (answer or "").strip()
            if not answer:
                answer = "Aemeath 暂时没有想好怎么回复。"
            self.finished.emit(answer)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ChatWindow(QDialog):
    def __init__(self, config_dir: Path, api_key_getter, parent=None) -> None:
        super().__init__(parent)
        self._config_dir = config_dir
        self._history_path = config_dir / "chat_history.jsonl"
        self._api_key_getter = api_key_getter
        self._records: list[dict[str, str]] = []
        self._thread: QThread | None = None
        self._worker: ChatWorker | None = None
        self._pending_index: int | None = None
        self._pending_timestamp: str = ""
        self._pending_prompt: str = ""

        self.setWindowTitle("Aemeath Chat")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.resize(390, 760)
        self._build_ui()
        self._load_history()
        self._render_records()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        nav = QFrame(self)
        nav.setObjectName("navBar")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(12, 8, 12, 8)
        nav_layout.setSpacing(8)

        avatar = QLabel("A")
        avatar.setObjectName("avatarBadge")
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(0)
        title = QLabel("Aemeath")
        title.setObjectName("navTitle")
        subtitle = QLabel("在线")
        subtitle.setObjectName("navSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        nav_layout.addWidget(avatar)
        nav_layout.addLayout(title_box, 1)

        self.log_button = QPushButton("记录", self)
        self.log_button.setObjectName("navActionButton")
        self.log_button.clicked.connect(self._show_history_viewer)
        self.clear_button = QPushButton("清空", self)
        self.clear_button.setObjectName("navActionButton")
        self.clear_button.clicked.connect(self._clear_history)
        nav_layout.addWidget(self.log_button)
        nav_layout.addWidget(self.clear_button)

        chat_frame = QFrame(self)
        chat_frame.setObjectName("panelCard")
        chat_layout = QVBoxLayout(chat_frame)
        chat_layout.setContentsMargins(8, 8, 8, 8)
        chat_layout.setSpacing(4)
        self.chat_list = QListWidget(chat_frame)
        self.chat_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.chat_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.chat_list.setObjectName("chatTimeline")
        chat_layout.addWidget(self.chat_list)

        input_frame = QFrame(self)
        input_frame.setObjectName("composerBar")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(10, 8, 10, 8)
        input_layout.setSpacing(8)

        self.input_box = QTextEdit(input_frame)
        self.input_box.setPlaceholderText("输入你想对 Aemeath 说的话...")
        self.input_box.setObjectName("composerInput")
        self.input_box.setFixedHeight(52)
        self.input_box.setAcceptRichText(False)

        self.send_button = QPushButton("发送", input_frame)
        self.send_button.setObjectName("sendButton")
        self.send_button.clicked.connect(self._send_message)

        input_layout.addWidget(self.input_box, 1)
        input_layout.addWidget(self.send_button)

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
                min-width: 28px;
                min-height: 28px;
                max-width: 28px;
                max-height: 28px;
                border-radius: 14px;
                background: #ff5fa2;
                color: #ffffff;
                font-weight: 700;
                qproperty-alignment: AlignCenter;
            }
            QLabel#navTitle {
                font-size: 14px;
                font-weight: 700;
                color: #221626;
            }
            QLabel#navSubtitle {
                font-size: 11px;
                color: #9a6b85;
            }
            QPushButton#navActionButton {
                background: #fff0f7;
                border: 2px solid #ff9dc6;
                border-radius: 10px;
                color: #8d365d;
                padding: 4px 8px;
                font-size: 12px;
                font-family: Menlo, Monaco, monospace;
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
            QTextEdit#composerInput {
                background: #fff2f8;
                border: 2px solid #ffb3d4;
                border-radius: 16px;
                padding: 8px;
                color: #2a1f2a;
                font-family: Menlo, Monaco, monospace;
                font-size: 12px;
            }
            QPushButton#sendButton {
                min-width: 64px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #ff5fa2,
                    stop:1 #ff8cc3
                );
                border: 2px solid #ff4f98;
                border-radius: 16px;
                color: #ffffff;
                font-weight: 600;
                font-family: Menlo, Monaco, monospace;
            }
            QPushButton:disabled {
                background: #f3dbe8;
                border-color: #e8bfd3;
                color: #a68596;
            }
            """
        )

    def _add_chat_bubble(self, role: str, text: str, ts: str, pending: bool = False) -> int:
        item = QListWidgetItem(self.chat_list)
        wrapper = QWidget()
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(6, 6, 6, 6)

        bubble = QFrame(wrapper)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(10, 8, 10, 8)
        bubble_layout.setSpacing(4)
        bubble.setMaximumWidth(300)

        sender = "我" if role == "user" else "Aemeath"
        head = QLabel(f"{sender} · {ts}", bubble)
        head.setStyleSheet("color:#9ba3c7; font-size:11px;")
        body = QLabel(text, bubble)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet("font-family: Menlo, Monaco, monospace; font-size: 12px;")
        if pending:
            body.setStyleSheet("color:#cfd7ff; font-family: Menlo, Monaco, monospace; font-size: 12px;")

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
            row.addWidget(bubble)
        else:
            bubble.setStyleSheet(
                """
                background:#fff0f7;
                border: 2px solid #ffb7d6;
                border-radius:12px;
                color:#2b1c2a;
                """
            )
            row.addWidget(bubble)
            row.addStretch(1)

        bubble_layout.addWidget(head)
        bubble_layout.addWidget(body)

        item.setSizeHint(wrapper.sizeHint())
        self.chat_list.setItemWidget(item, wrapper)
        self.chat_list.scrollToBottom()
        return self.chat_list.count() - 1

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
        api_key = (self._api_key_getter() or "").strip()
        if not api_key:
            QMessageBox.information(self, "缺少 API Key", "请先在右键设置里填写 DeepSeek API Key。")
            return

        self.send_button.setDisabled(True)
        self.input_box.setDisabled(True)
        self.input_box.clear()

        self._pending_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._pending_prompt = prompt
        self._add_chat_bubble("user", prompt, self._pending_timestamp)
        self._pending_index = self._add_chat_bubble("assistant", "Aemeath 正在思考...", self._pending_timestamp, pending=True)

        messages = self._build_context_messages(prompt)

        self._thread = QThread(self)
        self._worker = ChatWorker(api_key=api_key, messages=messages)
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
        self.input_box.setDisabled(False)

    def _on_reply_failed(self, error_text: str) -> None:
        if self._pending_index is not None and 0 <= self._pending_index < self.chat_list.count():
            self.chat_list.takeItem(self._pending_index)
            self._add_chat_bubble("assistant", f"[失败] {error_text}", self._pending_timestamp)
        self._pending_index = None
        self.send_button.setDisabled(False)
        self.input_box.setDisabled(False)
        QMessageBox.warning(self, "请求失败", f"调用 DeepSeek 失败：{error_text}")

    def _build_context_messages(self, prompt: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": "You are Aemeath, a cute desktop pet assistant. Keep replies concise and warm.",
            }
        ]
        for item in self._records[-20:]:
            messages.append({"role": "user", "content": item["user"]})
            messages.append({"role": "assistant", "content": item["assistant"]})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _show_history_viewer(self) -> None:
        viewer = QDialog(self)
        viewer.setWindowTitle("Aemeath 对话回顾")
        viewer.resize(390, 700)
        root = QVBoxLayout(viewer)
        panel = QListWidget(viewer)
        panel.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        for item in self._records:
            ts = item.get("timestamp", "")
            panel.addItem(QListWidgetItem(f"[{ts}] 你：{item['user']}"))
            panel.addItem(QListWidgetItem(f"[{ts}] Aemeath：{item['assistant']}"))
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
