"""QSS for chat window, history viewer, and history editor."""
from __future__ import annotations

from app.utils.design_tokens import chat_theme_tokens
from app.utils.ui_scale import px


def build_chat_stylesheet(scale: float) -> str:
    """Build main chat window QSS."""
    t = chat_theme_tokens()
    btn = px(52, scale)
    return f"""
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


def build_history_viewer_stylesheet() -> str:
    """Build QSS for the history viewer dialog."""
    return """
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


def build_history_editor_stylesheet() -> str:
    """Build QSS for the history editor (edit reply) dialog."""
    return """
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


def bubble_time_style(timestamp_color: str, font_size_px: int) -> str:
    """Style string for bubble timestamp label."""
    return f"color:{timestamp_color}; font-size:{font_size_px}px; letter-spacing:0.3px; padding:0 2px;"


def bubble_body_style(font_size_px: int) -> str:
    """Style string for bubble text body (transparent bg)."""
    return f"font-size: {font_size_px}px; color: #26374a; background: transparent; border: none; margin: 0; padding: 1px 2px 3px 2px;"


def user_bubble_style() -> str:
    """Style for user chat bubble frame."""
    return """
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(249, 229, 242, 0.96),
                    stop:1 rgba(229, 240, 255, 0.93)
                );
                border: 1px solid rgba(186, 206, 228, 0.92);
                border-radius: 14px;
                color: #243548;
                """


def assistant_bubble_style() -> str:
    """Style for assistant chat bubble frame."""
    return """
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.98),
                    stop:1 rgba(242, 249, 255, 0.94)
                );
                border: 1px solid rgba(195, 214, 236, 0.86);
                border-radius: 14px;
                color: #223446;
                """
