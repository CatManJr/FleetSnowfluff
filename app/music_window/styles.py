"""QSS for music window, mini playlist panel, and mini player bar."""
from __future__ import annotations

from app.ui_scale import px


def build_mini_playlist_stylesheet(scale: float) -> str:
    """Build QSS for MiniPlaylistPanel."""
    fs12 = px(12, scale)
    return f"""
            QFrame#playlistCard {{
                background: rgba(255, 247, 251, 0.97);
                border: 2px solid #ffc2de;
                border-radius: 14px;
            }}
            QLineEdit#playlistSearch {{
                border: 1px solid #ffb7d6;
                border-radius: 8px;
                padding: 6px 8px;
                background: #fff8fc;
                color: #6c2e4e;
                font-size: {fs12}px;
            }}
            QListWidget#playlistList {{
                border: 1px solid #ffd3e6;
                border-radius: 10px;
                background: #ffffff;
                color: #2a1f2a;
                font-size: {fs12}px;
                padding: 3px;
            }}
            QListWidget#playlistList::item {{
                padding: 5px 8px;
                border-radius: 6px;
            }}
            QListWidget#playlistList::item:selected {{
                background: rgba(255, 224, 240, 0.8);
                color: #8d365d;
            }}
            """


def build_mini_player_bar_stylesheet(scale: float) -> str:
    """Build QSS for MiniPlayerBar."""
    return f"""
            QDialog {{
                background: transparent;
                border: none;
            }}
            QFrame#miniCard {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.62),
                    stop:0.18 rgba(255, 252, 255, 0.50),
                    stop:0.52 rgba(255, 245, 252, 0.40),
                    stop:1 rgba(255, 228, 244, 0.34)
                );
                border: none;
                border-radius: 18px;
            }}
            QLabel#miniTitle {{
                color: #6a2f4f;
                font-size: {px(14, scale)}px;
                font-weight: 700;
                padding: 2px 7px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.40),
                    stop:1 rgba(255, 238, 248, 0.26)
                );
                border: none;
                border-radius: 9px;
            }}
            QPushButton#miniBtn {{
                min-width: {px(56, scale)}px;
                max-width: {px(56, scale)}px;
                min-height: {px(48, scale)}px;
                max-height: {px(48, scale)}px;
                border-radius: 14px;
                color: #5d1f3f;
                font-size: {px(24, scale)}px;
                border: none;
                background: transparent;
                padding: 0px;
                margin: 0px;
                text-align: center;
            }}
            QPushButton#miniBtn:hover {{
                background: rgba(255, 231, 246, 0.32);
            }}
            QPushButton#miniBtn:pressed {{
                background: rgba(255, 208, 231, 0.52);
                color: #4f1935;
            }}
            QPushButton#miniBtn:disabled {{
                color: rgba(93, 31, 63, 0.35);
                background: transparent;
            }}
            QPushButton#miniBtnExpand {{
                min-width: {px(50, scale)}px;
                max-width: {px(50, scale)}px;
                min-height: {px(50, scale)}px;
                max-height: {px(50, scale)}px;
                border-radius: 14px;
                color: #4f1935;
                font-size: {px(25, scale)}px;
                border: none;
                background: transparent;
                padding: 0px;
                margin: 0px;
                text-align: center;
            }}
            QPushButton#miniBtnExpand:hover {{
                background: rgba(255, 231, 246, 0.35);
            }}
            QPushButton#miniBtnExpand:pressed {{
                background: rgba(255, 208, 231, 0.56);
            }}
            QWidget#miniVolumePopup {{
                background: rgba(255, 247, 251, 0.96);
                border: 1px solid rgba(255, 197, 224, 0.85);
                border-radius: 12px;
            }}
            QLabel#miniVolumeValue {{
                color: #8d365d;
                font-size: {px(11, scale)}px;
                font-weight: 700;
            }}
            QSlider#miniVolumeSlider::groove:vertical {{
                width: 8px;
                border-radius: 4px;
                background: rgba(255, 221, 238, 0.52);
            }}
            QSlider#miniVolumeSlider::sub-page:vertical {{
                border-radius: 4px;
                background: qlineargradient(
                    x1:0, y1:1, x2:0, y2:0,
                    stop:0 rgba(255, 231, 243, 0.86),
                    stop:1 rgba(255, 208, 230, 0.78)
                );
            }}
            QSlider#miniVolumeSlider::add-page:vertical {{
                border-radius: 4px;
                background: qlineargradient(
                    x1:0, y1:1, x2:0, y2:0,
                    stop:0 rgba(255, 119, 176, 0.96),
                    stop:1 rgba(255, 153, 197, 0.96)
                );
            }}
            QSlider#miniVolumeSlider::handle:vertical {{
                height: 14px;
                margin: 0 -4px;
                border-radius: 7px;
                border: none;
                background: rgba(255, 248, 252, 0.98);
            }}
            QSlider#miniProgressSlider::groove:horizontal {{
                height: 4px;
                border-radius: 2px;
                background: rgba(255, 207, 229, 0.44);
            }}
            QSlider#miniProgressSlider::sub-page:horizontal {{
                border-radius: 2px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 143, 190, 0.92),
                    stop:1 rgba(255, 112, 171, 0.92)
                );
            }}
            QSlider#miniProgressSlider::handle:horizontal {{
                width: 10px;
                margin: -4px 0;
                border-radius: 5px;
                border: none;
                background: rgba(255, 247, 252, 0.96);
            }}
            """


def build_main_stylesheet(scale: float, track_list_background: str) -> str:
    """Build QSS for MusicWindow. track_list_background is the CSS for trackList background (e.g. gradient)."""
    t = """
            QDialog {
                background: rgba(245, 250, 255, 0.84);
                color: #1f2e40;
            }
            QFrame#navBar {
                background: rgba(255, 255, 255, 0.62);
                border-bottom: 1px solid rgba(197, 214, 235, 0.46);
            }
            QLabel#avatarBadge {
                min-width: 64px;
                min-height: 64px;
                max-width: 64px;
                max-height: 64px;
                border-radius: 32px;
                background: transparent;
                color: #ffffff;
                font-weight: 700;
                qproperty-alignment: AlignCenter;
                border: 1px solid rgba(196, 214, 236, 0.70);
            }
            QLabel#navTitle {
                font-size: __FS20__px;
                font-weight: 700;
                color: #221626;
            }
            QLabel#followCount {
                color: #8d365d;
                font-size: __FS14__px;
                font-weight: 700;
                padding: 0 2px;
            }
            QPushButton#followBtn {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 112, 178, 0.95),
                    stop:1 rgba(255, 139, 193, 0.92)
                );
                border: none;
                border-radius: 12px;
                color: #ffffff;
                min-width: __FOLLOW_W__px;
                min-height: __FOLLOW_H__px;
                padding: 0 10px;
                font-size: __FS15__px;
                font-weight: 700;
            }
            QPushButton#followBtn:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 124, 185, 0.98),
                    stop:1 rgba(255, 154, 202, 0.95)
                );
            }
            QPushButton#followBtn:pressed {
                background: rgba(255, 105, 170, 0.88);
            }
            QPushButton#navActionBtn {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.42),
                    stop:1 rgba(255, 235, 247, 0.30)
                );
                border: none;
                border-radius: 14px;
                color: #7a3658;
                min-width: __NAVBTN_W__px;
                max-width: __NAVBTN_W__px;
                min-height: __NAVBTN_H__px;
                max-height: __NAVBTN_H__px;
                padding: 0px;
                font-size: __FS34__px;
                font-weight: 600;
                margin: 0px;
                text-align: center;
            }
            QPushButton#navActionBtn:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.98),
                    stop:1 rgba(255, 227, 243, 0.95)
                );
            }
            QPushButton#navActionBtn:pressed {
                background: rgba(255, 211, 233, 0.38);
            }
            QFrame#panelCard {
                background: rgba(251, 254, 255, 0.58);
                border: 1px solid rgba(198, 217, 239, 0.52);
                border-radius: 16px;
            }
            QLabel#nowPlaying {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(252, 247, 255, 0.84),
                    stop:1 rgba(234, 244, 255, 0.76)
                );
                border: 1px solid rgba(203, 221, 243, 0.56);
                border-radius: 12px;
                padding: 8px;
                color: #2b3d53;
                font-size: __FS13__px;
            }
            QLabel#timeLabel {
                color: #8a4a69;
                min-width: __TIME_W__px;
                font-size: __FS11__px;
                font-weight: 600;
            }
            QSlider#progressSlider::groove:horizontal {
                height: 6px;
                border-radius: 3px;
                background: rgba(255, 205, 228, 0.52);
            }
            QSlider#progressSlider::sub-page:horizontal {
                border-radius: 3px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 143, 190, 0.95),
                    stop:1 rgba(255, 110, 170, 0.95)
                );
            }
            QSlider#progressSlider::handle:horizontal {
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
                border: none;
                background: rgba(255, 248, 252, 0.96);
            }
            QSlider#progressSlider::handle:horizontal:hover {
                background: rgba(255, 255, 255, 0.98);
            }
            QPushButton#volumeToggleBtn {
                min-width: __VOLBTN_W__px;
                max-width: __VOLBTN_W__px;
                min-height: __VOLBTN_H__px;
                max-height: __VOLBTN_H__px;
                border-radius: 10px;
                border: none;
                background: rgba(255, 255, 255, 0.36);
                color: #7a3658;
                font-size: __FS16__px;
                font-weight: 700;
                padding: 0px;
                margin: 0px;
                text-align: center;
            }
            QPushButton#volumeToggleBtn:hover {
                background: rgba(255, 255, 255, 0.56);
            }
            QPushButton#volumeToggleBtn:pressed {
                background: rgba(255, 220, 239, 0.64);
            }
            QWidget#volumePopup {
                background: rgba(255, 247, 251, 0.96);
                border: 1px solid rgba(255, 197, 224, 0.85);
                border-radius: 12px;
            }
            QLabel#volumePopupValue {
                color: #8d365d;
                font-size: __FS11__px;
                font-weight: 700;
            }
            QSlider#volumePopupSlider::groove:vertical {
                width: 8px;
                border-radius: 4px;
                background: rgba(255, 221, 238, 0.52);
            }
            QSlider#volumePopupSlider::sub-page:vertical {
                border-radius: 4px;
                background: qlineargradient(
                    x1:0, y1:1, x2:0, y2:0,
                    stop:0 rgba(255, 231, 243, 0.86),
                    stop:1 rgba(255, 208, 230, 0.78)
                );
            }
            QSlider#volumePopupSlider::add-page:vertical {
                border-radius: 4px;
                background: qlineargradient(
                    x1:0, y1:1, x2:0, y2:0,
                    stop:0 rgba(255, 119, 176, 0.96),
                    stop:1 rgba(255, 153, 197, 0.96)
                );
            }
            QSlider#volumePopupSlider::handle:vertical {
                height: 14px;
                margin: 0 -4px;
                border-radius: 7px;
                border: none;
                background: rgba(255, 248, 252, 0.98);
            }
            QSlider#volumePopupSlider::handle:vertical:hover {
                background: rgba(255, 255, 255, 1.0);
            }
            QTreeWidget#trackList {
                __TRACK_LIST_BACKGROUND__
                border: 1px solid rgba(196, 215, 238, 0.64);
                border-radius: 14px;
                padding: 4px;
                font-size: __FS14__px;
                color: #1f2e40;
            }
            QTreeWidget#trackList::item {
                height: 28px;
                padding: 2px 6px;
                background: transparent;
                margin: 1px 2px;
            }
            QTreeWidget#trackList::item:selected {
                background: rgba(222, 236, 252, 0.68);
                color: #224263;
            }
            QHeaderView::section {
                background: rgba(238, 246, 255, 0.86);
                border: none;
                border-bottom: 1px solid rgba(196, 214, 235, 0.54);
                padding: 6px 8px;
                color: #3b5878;
                font-size: __FS12__px;
                font-weight: 700;
            }
            QPushButton#actionBtn {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.34),
                    stop:0.58 rgba(255, 239, 249, 0.28),
                    stop:1 rgba(255, 217, 238, 0.24)
                );
                border: none;
                border-radius: 15px;
                color: #7b3356;
                min-width: __ACTION_W__px;
                min-height: __ACTION_H__px;
                padding: 0px;
                font-size: __FS20__px;
                font-weight: 600;
                margin: 0px;
                text-align: center;
            }
            QPushButton#actionBtn:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.56),
                    stop:0.55 rgba(255, 245, 251, 0.46),
                    stop:1 rgba(255, 226, 243, 0.40)
                );
            }
            QPushButton#actionBtn:pressed {
                background: rgba(255, 207, 231, 0.36);
                color: #6f2d4d;
            }
            QPushButton#actionBtn:disabled {
                background: rgba(245, 237, 242, 0.18);
                border: none;
                color: #b995ab;
            }
            QPushButton#actionMainBtn {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.42),
                    stop:0.5 rgba(255, 230, 245, 0.35),
                    stop:1 rgba(255, 198, 227, 0.30)
                );
                border: none;
                border-radius: 24px;
                color: #6f2a4a;
                min-width: __MAINBTN__px;
                max-width: __MAINBTN__px;
                min-height: __MAINBTN__px;
                max-height: __MAINBTN__px;
                padding: 0px;
                font-size: __FS21__px;
                font-weight: 700;
                margin: 0px;
                text-align: center;
            }
            QPushButton#actionMainBtn:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.64),
                    stop:1 rgba(255, 214, 238, 0.52)
                );
            }
            QPushButton#actionMainBtn:pressed {
                background: rgba(255, 185, 220, 0.42);
                color: #662640;
            }
            QPushButton#actionMainBtn:disabled {
                background: rgba(245, 237, 242, 0.18);
                border: none;
                color: #b995ab;
            }
            """
    stylesheet = t.replace("__TRACK_LIST_BACKGROUND__", track_list_background)
    stylesheet = (
        stylesheet.replace("__FS11__", str(px(11, scale)))
        .replace("__FS12__", str(px(12, scale)))
        .replace("__FS13__", str(px(13, scale)))
        .replace("__FS14__", str(px(14, scale)))
        .replace("__FS15__", str(px(15, scale)))
        .replace("__FS16__", str(px(16, scale)))
        .replace("__FS18__", str(px(18, scale)))
        .replace("__FS20__", str(px(20, scale)))
        .replace("__FS21__", str(px(21, scale)))
        .replace("__FS34__", str(px(34, scale)))
        .replace("__FOLLOW_W__", str(px(64, scale)))
        .replace("__FOLLOW_H__", str(px(36, scale)))
        .replace("__NAVBTN_W__", str(px(56, scale)))
        .replace("__NAVBTN_H__", str(px(96, scale)))
        .replace("__TIME_W__", str(px(44, scale)))
        .replace("__VOLBTN_W__", str(px(34, scale)))
        .replace("__VOLBTN_H__", str(px(28, scale)))
        .replace("__ACTION_W__", str(px(48, scale)))
        .replace("__ACTION_H__", str(px(40, scale)))
        .replace("__MAINBTN__", str(px(48, scale)))
    )
    return stylesheet
