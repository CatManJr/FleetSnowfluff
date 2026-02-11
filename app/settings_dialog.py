from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QVBoxLayout


class SettingsDialog(QDialog):
    def __init__(self, api_key: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fleet Snowfluff 设置")
        self.setModal(True)
        self.resize(420, 120)

        self.api_key_input = QLineEdit(self)
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("请输入 DeepSeek API Key")
        self.api_key_input.setText(api_key)

        form = QFormLayout()
        form.addRow("DeepSeek API Key", self.api_key_input)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

    def api_key(self) -> str:
        return self.api_key_input.text().strip()
