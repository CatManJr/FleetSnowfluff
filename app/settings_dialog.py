from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QSpinBox, QVBoxLayout


class SettingsDialog(QDialog):
    def __init__(
        self,
        api_key: str,
        min_jump_distance: int,
        flight_speed: int,
        reasoning_enabled: bool,
        chat_context_turns: int,
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

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)
        self.setStyleSheet(
            """
            QDialog {
                background: #fff7fb;
                color: #2a1f2a;
            }
            QLabel {
                color: #2a1f2a;
                font-size: 13px;
            }
            QLineEdit, QSpinBox {
                background: #fff2f8;
                border: 2px solid #ffb3d4;
                border-radius: 10px;
                padding: 4px 8px;
                min-height: 30px;
                font-size: 13px;
                color: #2a1f2a;
            }
            QLineEdit::placeholder {
                color: #a14a73;
            }
            QCheckBox {
                color: #7a2f51;
                font-size: 13px;
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
                font-size: 13px;
            }
            QDialogButtonBox QPushButton:hover {
                border-color: #ff8fc1;
                background: #ffe7f3;
            }
            """
        )

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
