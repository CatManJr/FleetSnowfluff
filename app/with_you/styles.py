"""Focus-mode and mini-call-bar QSS. Isolated from window logic."""
from __future__ import annotations

from app.design_tokens import focus_theme_base_tokens
from app.ui_scale import px


def focus_theme_tokens() -> dict[str, str]:
    """Theme tokens for WithYouWindow focus/config view."""
    tokens = {
        "bg_dialog": "#0f141b",
        "text_light": "#e6edf3",
        "panel_grad_a": "rgba(10, 18, 36, 1)",
        "panel_grad_b": "rgba(34, 56, 86, 1)",
        "panel_border": "#ffffff",
        "settings_bg": "#eef2f6",
        "focus_window_bg": "#fdf0f4",
        "config_window_bg": "#eef2f6",
        "settings_panel_bg": "#ffeadc",
        "status_text": "#EAF5FF",
        "round_text": "#CFE8FF",
        "tip_text": "#DDEBFF",
        "settings_text": "#EAF3FF",
        "unit_text": "#C8DBF7",
        "divider": "rgba(180, 203, 233, 0.45)",
        "card_bg_a": "rgba(237, 245, 255, 0.30)",
        "card_bg_b": "rgba(224, 236, 252, 0.20)",
        "card_border": "rgba(191, 219, 255, 0.38)",
        "countdown": "#DDF1FF",
        "input_bg": "rgba(246, 251, 255, 0.42)",
        "input_border": "rgba(197, 220, 246, 0.50)",
        "input_focus": "rgba(211, 230, 252, 0.72)",
        "input_focus_bg": "rgba(250, 253, 255, 0.62)",
        "btn_pink_top": "rgba(241, 233, 255, 0.55)",
        "btn_pink_bottom": "rgba(222, 238, 255, 0.50)",
        "btn_pink_border": "rgba(184, 206, 238, 0.55)",
        "btn_pink_border_pressed": "rgba(160, 184, 220, 0.60)",
        "btn_pink_hover_top": "#f8fbff",
        "btn_pink_hover_bottom": "#e9f2ff",
        "text_dark": "#1B2A40",
        "font_family": " 'Source Han Sans SC', 'PingFang SC'",
        "mini_panel_a": "rgba(18, 30, 52, 0.92)",
        "mini_panel_b": "rgba(34, 53, 82, 0.92)",
        "mini_panel_border": "rgba(176, 207, 246, 0.58)",
        "mini_text": "#D7E9FF",
        "mini_focus": "#89E4C0",
        "mini_break": "#F9D188",
        "mini_pause": "#C0D5EE",
        "mini_config": "#B8CCE5",
        "mini_hangup": "#FFB8CF",
        "mini_timer": "#F0C9FF",
        "mini_btn_a": "rgba(240, 232, 255, 0.62)",
        "mini_btn_b": "rgba(220, 236, 255, 0.56)",
        "mini_btn_border": "rgba(175, 205, 240, 0.60)",
        "mini_btn_text": "#1B2A42",
        "mini_btn_hover": "rgba(212, 228, 248, 0.88)",
        "mini_btn_pressed": "rgba(183, 205, 233, 0.92)",
        "mini_danger_a": "rgba(255, 223, 236, 0.74)",
        "mini_danger_b": "rgba(244, 206, 227, 0.68)",
        "mini_danger_border": "rgba(226, 167, 200, 0.86)",
        "mini_danger_text": "#3A2540",
        "mini_danger_hover_a": "rgba(255, 232, 242, 0.84)",
        "mini_danger_hover_b": "rgba(248, 214, 232, 0.80)",
        "mini_danger_pressed_a": "rgba(247, 211, 230, 0.86)",
        "mini_danger_pressed_b": "rgba(239, 197, 220, 0.82)",
        "focus_bg_cream": "#fdf0f4",
        "macaron_pink": "#E8D0E6",
        "popup_bg": "#EAF2FF",
    }
    tokens.update(focus_theme_base_tokens())
    tokens["status_text"] = "#EAF5FF"
    tokens["round_text"] = "#CFE8FF"
    tokens["countdown"] = "#DDF1FF"
    tokens["macaron_pink"] = "#E8D0E6"
    return tokens


def build_focus_stylesheet(scale: float) -> str:
    """Build QSS for WithYouWindow (focus/config)."""
    t = focus_theme_tokens()
    return f"""
            QDialog {{
                background: {t["bg_dialog"]};
                color: {t["text_light"]};
            }}
            QDialog#noisePopup, QDialog#bgmPopup {{
                background: transparent;
                border: none;
            }}
            QDialog#withYouWindow {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {t["panel_grad_a"]}, stop:1 {t["panel_grad_b"]});
                border: none;
            }}
            QFrame#noisePopupPanel, QFrame#bgmPopupPanel {{
                background: {t["popup_bg"]};
                border: 1px solid {t["card_border"]};
                border-radius: 14px;
                border-image: none;
            }}
            QFrame#noisePopupPanel QLabel, QFrame#bgmPopupPanel QLabel {{
                color: {t["macaron_pink"]};
            }}
            QFrame#noisePopupPanel QCheckBox, QFrame#bgmPopupPanel QCheckBox {{
                color: {t["macaron_pink"]};
            }}
            QDialog#withYouWindow[viewMode="config"] {{
                color: {t["settings_text"]};
            }}
            QLabel#statusLabel, QLabel#roundLabel, QLabel#countdownLabel, QPushButton {{
                font-family: {t["font_family"]};
            }}
            QDialog#withYouWindow QFrame#interactivePage,
            QDialog#withYouWindow QFrame#topBar,
            QDialog#withYouWindow QFrame#bottomBar,
            QDialog#withYouWindow QScrollArea#settingsScroll,
            QDialog#withYouWindow QScrollArea#settingsScroll > QWidget#qt_scrollarea_viewport,
            QDialog#withYouWindow QFrame#withyouPanel {{
                background: transparent;
                border: none;
            }}
            QDialog#withYouWindow QFrame#interactivePage {{
                background: rgba(9, 18, 34, 0.28);
            }}
            QDialog#withYouWindow QFrame#settingsContentPanel {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(28, 44, 68, 0.34),
                    stop:1 rgba(41, 62, 92, 0.28)
                );
                border: none;
                border-radius: 0px;
            }}
            QDialog#withYouWindow QFrame#topBar,
            QDialog#withYouWindow QFrame#bottomBar {{
                background: rgba(9, 17, 34, 0.34);
                border: none;
                border-radius: 0px;
            }}
            QDialog#withYouWindow[viewMode="config"] QFrame#topBar,
            QDialog#withYouWindow[viewMode="config"] QFrame#bottomBar {{
                background: rgba(9, 17, 34, 0.42);
                border: none;
            }}
            QLabel#statusLabel {{ font-size: {px(17, scale)}px; font-weight: 700; color: {t["status_text"]}; }}
            QLabel#roundLabel {{ font-size: {px(32, scale)}px; font-weight: 700; color: {t["round_text"]}; }}
            QDialog[viewMode="config"] QLabel#statusLabel {{ color: {t["settings_text"]}; }}
            QDialog[viewMode="config"] QLabel#roundLabel {{ color: {t["unit_text"]}; }}
            QLabel#tipLabel {{ font-size: {px(13, scale)}px; color: {t["tip_text"]}; padding: 2px 4px; }}
            QCheckBox {{ color: #b8c4d3; font-size: {px(26, scale)}px; font-weight: 700; }}
            QLabel#settingFieldLabel, QLabel#roundsFieldLabel, QLabel#timeFieldLabel {{
                font-size: {px(14, scale)}px; color: {t["settings_text"]};
            }}
            QLabel#unitLabel {{ font-size: {px(28, scale)}px; color: {t["unit_text"]}; }}
            QFrame#settingsDivider {{ background: {t["divider"]}; border-radius: 1px; margin-bottom: 2px; }}
            QFrame#settingCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["card_bg_a"]}, stop:1 {t["card_bg_b"]});
                border: 1px solid {t["card_border"]};
                border-radius: 14px;
            }}
            QLabel#companionInfoTopLabel {{
                font-size: {px(16, scale)}px;
                color: {t["status_text"]};
                font-weight: 700;
            }}
            QDialog[viewMode="config"] QLabel#companionInfoTopLabel {{
                color: {t["settings_text"]};
            }}
            QLabel#countdownLabel {{
                font-size: {px(56, scale)}px;
                font-weight: 800;
                color: {t["countdown"]};
                letter-spacing: 1px;
            }}
            QFrame {{ border: none; }}
            QSpinBox {{
                background: {t["input_bg"]};
                border: 1px solid {t["input_border"]};
                border-radius: 10px;
                padding: 4px 8px;
                min-height: {px(34, scale)}px;
                color: {t["text_dark"]};
                font-size: {px(12, scale)}px;
            }}
            QSpinBox:focus {{
                border: 2px solid {t["input_focus"]};
                background: {t["input_focus_bg"]};
            }}
            QSpinBox#roundsFieldSpin, QSpinBox#timeFieldSpin {{
                font-size: {px(24, scale)}px;
            }}
            QPushButton#primaryBtn, QPushButton#ghostBtn, QPushButton#chocoBtn, QPushButton#dangerBtn {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {t["btn_pink_top"]}, stop:1 {t["btn_pink_bottom"]});
                border: 1px solid {t["btn_pink_border"]};
                border-bottom: 2px solid {t["btn_pink_border_pressed"]};
                color: {t["text_dark"]};
                font-weight: 700;
            }}
            QPushButton#primaryBtn {{
                border-radius: 16px;
                min-height: {px(44, scale)}px;
                font-size: {px(15, scale)}px;
                padding: 6px 10px;
            }}
            QPushButton#ghostBtn {{
                border-radius: 16px;
                min-height: {px(36, scale)}px;
                min-width: {px(66, scale)}px;
                font-size: {px(13, scale)}px;
                padding: 6px 10px;
            }}
            QPushButton#chocoBtn {{
                border-radius: 14px;
                min-height: {px(30, scale)}px;
                min-width: 0px;
                margin: 2px;
                padding: 6px 8px;
                font-size: {px(13, scale)}px;
            }}
            QPushButton#dangerBtn {{
                border-radius: 16px;
                min-height: {px(36, scale)}px;
                min-width: {px(66, scale)}px;
                font-size: {px(13, scale)}px;
                padding: 6px 10px;
            }}
            QPushButton#primaryBtn:hover, QPushButton#ghostBtn:hover, QPushButton#chocoBtn:hover, QPushButton#dangerBtn:hover {{
                border-color: #e2a7c2;
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {t["btn_pink_hover_top"]},
                    stop:1 {t["btn_pink_hover_bottom"]}
                );
            }}
            QPushButton#primaryBtn:pressed, QPushButton#ghostBtn:pressed, QPushButton#chocoBtn:pressed, QPushButton#dangerBtn:pressed {{
                border-bottom: 1px solid {t["btn_pink_border_pressed"]};
                padding-top: 7px;
                padding-bottom: 5px;
            }}
            QPushButton[iconOnly="true"] {{
                padding: 0px;
                margin: 0px;
                min-width: 0px;
                min-height: 0px;
                text-align: center;
            }}
        """


def mini_call_bar_theme_tokens() -> dict[str, str]:
    """Default theme tokens for MiniCallBar."""
    return {
        "mini_panel_a": "rgba(18, 30, 52, 0.92)",
        "mini_panel_b": "rgba(34, 53, 82, 0.92)",
        "mini_panel_border": "rgba(176, 207, 246, 0.58)",
        "mini_text": "#D7E9FF",
        "mini_focus": "#89E4C0",
        "mini_break": "#F9D188",
        "mini_pause": "#C0D5EE",
        "mini_config": "#B8CCE5",
        "mini_hangup": "#FFB8CF",
        "mini_timer": "#F0C9FF",
        "mini_btn_a": "rgba(240, 232, 255, 0.62)",
        "mini_btn_b": "rgba(220, 236, 255, 0.56)",
        "mini_btn_border": "rgba(175, 205, 240, 0.60)",
        "mini_btn_text": "#1B2A42",
        "mini_btn_hover": "rgba(212, 228, 248, 0.88)",
        "mini_btn_pressed": "rgba(183, 205, 233, 0.92)",
        "mini_danger_a": "rgba(255, 223, 236, 0.74)",
        "mini_danger_b": "rgba(244, 206, 227, 0.68)",
        "mini_danger_border": "rgba(226, 167, 200, 0.86)",
        "mini_danger_text": "#3A2540",
        "mini_danger_hover_a": "rgba(255, 232, 242, 0.84)",
        "mini_danger_hover_b": "rgba(248, 214, 232, 0.80)",
        "mini_danger_pressed_a": "rgba(247, 211, 230, 0.86)",
        "mini_danger_pressed_b": "rgba(239, 197, 220, 0.82)",
        "font_family": '"SF Pro Rounded", "PingFang SC", "Helvetica Neue", sans-serif',
    }


def build_mini_call_bar_stylesheet(scale: float, theme_tokens: dict[str, str]) -> str:
    """Build QSS for MiniCallBar."""
    t = theme_tokens
    return f"""
            QFrame#miniPanel {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["mini_panel_a"]}, stop:1 {t["mini_panel_b"]});
                border: none;
                border-radius: 20px;
            }}
            QLabel#miniStatus, QLabel#miniTimer, QPushButton {{
                font-family: {t["font_family"]};
            }}
            QLabel#miniStatus {{
                color: {t["mini_text"]};
                font-size: {px(12, scale)}px;
                font-weight: 700;
            }}
            QLabel#miniStatus[miniState="focus"] {{ color: {t["mini_focus"]}; }}
            QLabel#miniStatus[miniState="break"] {{ color: {t["mini_break"]}; }}
            QLabel#miniStatus[miniState="pause"] {{ color: {t["mini_pause"]}; }}
            QLabel#miniStatus[miniState="config"] {{ color: {t["mini_config"]}; }}
            QLabel#miniStatus[miniState="hangup"] {{ color: {t["mini_hangup"]}; }}
            QLabel#miniTimer {{
                color: {t["mini_timer"]};
                font-size: {px(16, scale)}px;
                font-weight: 800;
            }}
            QPushButton#miniBtn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["mini_btn_a"]}, stop:1 {t["mini_btn_b"]});
                border: 1px solid {t["mini_btn_border"]};
                border-radius: 12px;
                color: {t["mini_btn_text"]};
                min-width: 44px;
                min-height: 28px;
                padding: 2px 8px;
            }}
            QPushButton#miniBtn:hover {{ border-color: {t["mini_btn_hover"]}; }}
            QPushButton#miniBtn:pressed {{ background: {t["mini_btn_pressed"]}; }}
            QPushButton#miniDanger {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["mini_danger_a"]}, stop:1 {t["mini_danger_b"]});
                border: 1px solid {t["mini_danger_border"]};
                border-radius: 12px;
                color: {t["mini_danger_text"]};
                min-width: 44px;
                min-height: 28px;
                padding: 2px 8px;
                font-weight: 700;
            }}
            QPushButton#miniDanger:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["mini_danger_hover_a"]}, stop:1 {t["mini_danger_hover_b"]});
            }}
            QPushButton#miniDanger:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["mini_danger_pressed_a"]}, stop:1 {t["mini_danger_pressed_b"]});
            }}
        """


def build_sticky_note_stylesheet(scale: float) -> str:
    """Build QSS for StickyNoteWindow."""
    return f"""
            QDialog {{
                background: #fff7fb;
                color: #2a1f2a;
            }}
            QTabWidget::pane {{
                border: 1px solid #ffd3e6;
                border-radius: 10px;
                background: #ffffff;
            }}
            QTabBar::tab {{
                background: #fff0f7;
                border: 1px solid #ffbfdc;
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 5px 10px;
                margin-right: 4px;
            }}
            QTabBar::tab:selected {{
                background: #ffdced;
            }}
            QTextEdit {{
                border: none;
                background: #fffdfd;
                color: #2a1f2a;
                font-size: {px(14, scale)}px;
            }}
            QPushButton {{
                background: #fff0f7;
                border: 1px solid #ffb7d6;
                border-radius: 9px;
                color: #8d365d;
                padding: 6px 10px;
            }}
            """
