from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QSpinBox, QVBoxLayout


class SettingsDialog(QDialog):
    def __init__(
        self,
        api_key: str,
        min_jump_distance: int,
        flight_speed: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fleet Snowfluff 设置")
        self.setModal(True)
        self.resize(440, 190)

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

        form = QFormLayout()
        form.addRow("DeepSeek API Key", self.api_key_input)
        form.addRow("最短跳跃距离", self.min_jump_distance_input)
        form.addRow("飞行速度", self.flight_speed_input)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

    def api_key(self) -> str:
        return self.api_key_input.text().strip()

    def min_jump_distance(self) -> int:
        return int(self.min_jump_distance_input.value())

    def flight_speed(self) -> int:
        return int(self.flight_speed_input.value())
