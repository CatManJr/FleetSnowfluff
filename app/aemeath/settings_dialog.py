from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from app.utils.fluent_compat import FPushButton as QPushButton
from app.utils.fluent_compat import init_fluent_theme
from app.utils.ui_scale import current_app_scale, px


class SettingsDialog(QDialog):
    def __init__(
        self,
        api_key: str,
        min_jump_distance: int,
        flight_speed: int,
        snowfluff_scale_percent: int,
        aemeath_scale_percent: int,
        sound_effects_enabled: bool,
        reasoning_enabled: bool,
        chat_context_turns: int,
        open_chat_history_callback: Callable[[], None] | None = None,
        open_persona_callback: Callable[[], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        init_fluent_theme()
        self.setWindowTitle("Fleet Snowfluff 设置")
        self.setModal(True)
        self.resize(520, 420)

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

        self.snowfluff_scale_percent_input = QSpinBox(self)
        self.snowfluff_scale_percent_input.setRange(0, 200)
        self.snowfluff_scale_percent_input.setSingleStep(5)
        self.snowfluff_scale_percent_input.setSuffix(" %")
        self.snowfluff_scale_percent_input.setValue(max(0, min(200, int(snowfluff_scale_percent))))

        self.aemeath_scale_percent_input = QSpinBox(self)
        self.aemeath_scale_percent_input.setRange(0, 200)
        self.aemeath_scale_percent_input.setSingleStep(5)
        self.aemeath_scale_percent_input.setSuffix(" %")
        self.aemeath_scale_percent_input.setValue(max(0, min(200, int(aemeath_scale_percent))))

        self.sound_effects_enabled_input = QCheckBox("启用音效（开机/关机/变身语音）", self)
        self.sound_effects_enabled_input.setChecked(bool(sound_effects_enabled))

        self.reasoning_enabled_input = QCheckBox("启用 Reasoning 模式（deepseek-reasoner）", self)
        self.reasoning_enabled_input.setChecked(bool(reasoning_enabled))

        self.chat_context_turns_input = QSpinBox(self)
        self.chat_context_turns_input.setRange(0, 120)
        self.chat_context_turns_input.setSingleStep(1)
        self.chat_context_turns_input.setSuffix(" 组")
        self.chat_context_turns_input.setValue(max(0, int(chat_context_turns)))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        quick_actions = QHBoxLayout()
        quick_actions.setSpacing(8)
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
        for btn in (open_history_btn, open_persona_btn):
            btn.setMinimumHeight(32)

        api_form = QFormLayout()
        api_form.setHorizontalSpacing(10)
        api_form.setVerticalSpacing(8)
        api_form.addRow("DeepSeek API Key", self.api_key_input)

        motion_form = QFormLayout()
        motion_form.setHorizontalSpacing(10)
        motion_form.setVerticalSpacing(8)
        motion_form.addRow("最短跳跃距离", self.min_jump_distance_input)
        motion_form.addRow("飞行速度", self.flight_speed_input)
        motion_form.addRow("飞行雪绒形态尺寸（原图比例）", self.snowfluff_scale_percent_input)
        motion_form.addRow("爱弥斯形态尺寸（原图比例）", self.aemeath_scale_percent_input)
        motion_form.addRow("音效开关", self.sound_effects_enabled_input)

        chat_form = QFormLayout()
        chat_form.setHorizontalSpacing(10)
        chat_form.setVerticalSpacing(8)
        chat_form.addRow("聊天模型", self.reasoning_enabled_input)
        chat_form.addRow("聊天上下文长度", self.chat_context_turns_input)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)
        root.addWidget(self._make_settings_card("API 与连接", api_form))
        root.addWidget(self._make_settings_card("动作参数", motion_form))
        root.addWidget(self._make_settings_card("聊天行为", chat_form))
        root.addWidget(self._make_settings_card("快捷动作", quick_actions))
        root.addStretch(1)
        root.addWidget(buttons)
        self._apply_scaled_styles()

    def _make_settings_card(self, title: str, body_layout: QLayout) -> QFrame:
        card = QFrame(self)
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        title_label = QLabel(title, card)
        title_label.setObjectName("settingsCardTitle")
        layout.addWidget(title_label)
        layout.addLayout(body_layout)
        return card

    def _apply_scaled_styles(self) -> None:
        app = QApplication.instance()
        scale = current_app_scale(app) if app is not None else 1.0
        fs = px(15, scale)
        button_h = px(34, scale)
        self.setStyleSheet(
            f"""
            QDialog {{
                background: rgba(248, 252, 255, 0.95);
                color: #233246;
            }}
            QFrame#settingsCard {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(247, 252, 255, 0.88),
                    stop:1 rgba(236, 246, 255, 0.78)
                );
                border: 1px solid rgba(188, 208, 230, 0.84);
                border-radius: 14px;
            }}
            QLabel#settingsCardTitle {{
                color: #2d4160;
                font-size: {fs}px;
                font-weight: 700;
                padding-bottom: 2px;
            }}
            QLabel {{
                color: #2b3b50;
                font-size: {fs}px;
            }}
            QLineEdit, QSpinBox {{
                background: rgba(255, 255, 255, 0.94);
                border: 1px solid rgba(190, 207, 226, 0.92);
                border-radius: 12px;
                padding: 5px 10px;
                min-height: 32px;
                font-size: {fs}px;
                color: #203144;
                selection-background-color: rgba(182, 208, 236, 0.75);
            }}
            QLineEdit:focus, QSpinBox:focus {{
                border: 2px solid rgba(160, 193, 228, 0.92);
                background: rgba(251, 254, 255, 0.98);
            }}
            QLineEdit::placeholder {{
                color: #8c9aae;
            }}
            QCheckBox {{
                color: #314258;
                font-size: {fs}px;
                spacing: 6px;
            }}
            QDialogButtonBox QPushButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(244, 233, 255, 0.90),
                    stop:1 rgba(216, 235, 255, 0.86)
                );
                border: 1px solid rgba(176, 201, 229, 0.95);
                border-radius: 12px;
                color: #24384d;
                min-height: {button_h}px;
                padding: 4px 14px;
                font-size: {fs}px;
                font-weight: 700;
            }}
            QDialogButtonBox QPushButton:hover {{
                border-color: rgba(157, 187, 221, 0.98);
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(250, 244, 255, 0.94),
                    stop:1 rgba(226, 240, 255, 0.90)
                );
            }}
            QDialogButtonBox QPushButton:pressed {{
                background: rgba(215, 231, 248, 0.90);
            }}
            QPushButton#quickActionBtn {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(250, 244, 255, 0.90),
                    stop:1 rgba(230, 241, 255, 0.86)
                );
                border: 1px solid rgba(182, 205, 232, 0.92);
                border-radius: 12px;
                color: #2b3f55;
                min-height: {button_h}px;
                padding: 4px 10px;
                font-size: {fs}px;
                font-weight: 600;
            }}
            QPushButton#quickActionBtn:hover {{
                border-color: rgba(163, 191, 222, 0.96);
                background: rgba(237, 246, 255, 0.92);
            }}
            QPushButton#quickActionBtn:disabled {{
                color: #8f9db0;
                border-color: rgba(200, 210, 222, 0.72);
                background: rgba(244, 247, 250, 0.88);
            }}
            """
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

    def snowfluff_scale_percent(self) -> int:
        return int(self.snowfluff_scale_percent_input.value())

    def aemeath_scale_percent(self) -> int:
        return int(self.aemeath_scale_percent_input.value())

    def sound_effects_enabled(self) -> bool:
        return bool(self.sound_effects_enabled_input.isChecked())

    def reasoning_enabled(self) -> bool:
        return bool(self.reasoning_enabled_input.isChecked())

    def chat_context_turns(self) -> int:
        return int(self.chat_context_turns_input.value())
