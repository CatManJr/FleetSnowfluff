from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .ui_scale import current_app_scale, px


class SettingsDialog(QDialog):
    def __init__(
        self,
        api_key: str,
        min_jump_distance: int,
        flight_speed: int,
        reasoning_enabled: bool,
        chat_context_turns: int,
        open_chat_history_callback: Callable[[], None] | None = None,
        open_persona_callback: Callable[[], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fleet Snowfluff 设置")
        self.setModal(True)
        self.resize(460, 250)

        self.api_key_input = QLineEdit(self)
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("请输入 DeepSeek API Key")
        self.api_key_input.setText(api_key)

        self.min_jump_distance_input = QSpinBox(self)
        self.min_jump_distance_input.setRange(20, 2000)
        self.min_jump_distance_input.setSingleStep(10)
        self.min_jump_distance_input.setSuffix(" px")
        self.min_jump_distance_input.setValue(max(20, int(min_jump_distance)))

        self.flight_speed_input = QSpinBox(self)
        self.flight_speed_input.setRange(1, 80)
        self.flight_speed_input.setSingleStep(1)
        self.flight_speed_input.setSuffix(" px/tick")
        self.flight_speed_input.setValue(max(1, int(flight_speed)))

        self.reasoning_enabled_input = QCheckBox("启用 Reasoning 模式（deepseek-reasoner）", self)
        self.reasoning_enabled_input.setChecked(bool(reasoning_enabled))

        self.chat_context_turns_input = QSpinBox(self)
        self.chat_context_turns_input.setRange(0, 120)
        self.chat_context_turns_input.setSingleStep(1)
        self.chat_context_turns_input.setSuffix(" 组")
        self.chat_context_turns_input.setValue(max(0, int(chat_context_turns)))

        form = QFormLayout()
        form.addRow("DeepSeek API Key", self.api_key_input)
        form.addRow("最短跳跃距离", self.min_jump_distance_input)
        form.addRow("飞行速度", self.flight_speed_input)
        form.addRow("聊天模型", self.reasoning_enabled_input)
        form.addRow("聊天上下文长度", self.chat_context_turns_input)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        quick_actions = QHBoxLayout()
        open_history_btn = QPushButton("打开本地聊天记录 JSON")
        open_history_btn.setObjectName("quickActionBtn")
        open_history_btn.setEnabled(open_chat_history_callback is not None)
        if open_chat_history_callback is not None:
            open_history_btn.clicked.connect(open_chat_history_callback)
        open_persona_btn = QPushButton("打开人设 JSON")
        open_persona_btn.setObjectName("quickActionBtn")
        open_persona_btn.setEnabled(open_persona_callback is not None)
        if open_persona_callback is not None:
            open_persona_btn.clicked.connect(open_persona_callback)
        quick_actions.addWidget(open_history_btn, 1)
        quick_actions.addWidget(open_persona_btn, 1)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addLayout(quick_actions)
        root.addWidget(buttons)
        self._apply_scaled_styles()

    def _apply_scaled_styles(self) -> None:
        app = QApplication.instance()
        scale = current_app_scale(app) if app is not None else 1.0
        fs = px(15, scale)
        self.setStyleSheet(
            """
            QDialog {
                background: #fff7fb;
                color: #2a1f2a;
            }
            QLabel {
                color: #2a1f2a;
                font-size: %dpx;
            }
            QLineEdit, QSpinBox {
                background: #fff2f8;
                border: 2px solid #ffb3d4;
                border-radius: 10px;
                padding: 4px 8px;
                min-height: 30px;
                font-size: %dpx;
                color: #2a1f2a;
            }
            QLineEdit::placeholder {
                color: #a14a73;
            }
            QCheckBox {
                color: #7a2f51;
                font-size: %dpx;
            }
            QDialogButtonBox QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #fff0f8,
                    stop:1 #ffe4f1
                );
                border: 1px solid #ffb7d6;
                border-radius: 10px;
                color: #8d365d;
                min-height: 32px;
                padding: 4px 12px;
                font-size: %dpx;
            }
            QDialogButtonBox QPushButton:hover {
                border-color: #ff8fc1;
                background: #ffe7f3;
            }
            QPushButton#quickActionBtn {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #fff0f8,
                    stop:1 #ffe4f1
                );
                border: 1px solid #ffb7d6;
                border-radius: 10px;
                color: #8d365d;
                min-height: 30px;
                padding: 4px 10px;
                font-size: %dpx;
                font-weight: 600;
            }
            QPushButton#quickActionBtn:hover {
                border-color: #ff8fc1;
                background: #ffe7f3;
            }
            QPushButton#quickActionBtn:disabled {
                color: #b88aa0;
                border-color: #f0cade;
                background: #fff8fb;
            }
            """
            % (fs, fs, fs, fs, fs)
        )

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ScreenChangeInternal:
            self._apply_scaled_styles()
        return super().event(event)

    def api_key(self) -> str:
        return self.api_key_input.text().strip()

    def min_jump_distance(self) -> int:
        return int(self.min_jump_distance_input.value())

    def flight_speed(self) -> int:
        return int(self.flight_speed_input.value())

    def reasoning_enabled(self) -> bool:
        return bool(self.reasoning_enabled_input.isChecked())

    def chat_context_turns(self) -> int:
        return int(self.chat_context_turns_input.value())
