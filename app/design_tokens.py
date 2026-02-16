from __future__ import annotations


def brand_palette() -> dict[str, str]:
    """
    Pantone-inspired girl-core palette (pink / blue / white).
    Hex values are tuned for Qt readability and contrast.
    """
    return {
        "white": "#FCFDFF",
        "white_soft": "#FFF7FB",
        "pink_50": "#FFF0F8",
        "pink_100": "#FFE4F1",
        "pink_200": "#FFD2E7",
        "pink_300": "#FFB7D6",
        "pink_400": "#FF8FC1",
        "pink_500": "#E86BA6",
        "blue_50": "#EEF6FF",
        "blue_100": "#DDEEFF",
        "blue_200": "#BFDFFF",
        "blue_300": "#8EC6F9",
        "blue_400": "#5CA9E6",
        "blue_500": "#3B8ED8",
        "ink_900": "#1F2A36",
        "ink_700": "#445568",
        "ink_500": "#667788",
        "danger_400": "#F07AA8",
        "danger_500": "#D75D91",
        "success_400": "#42C98D",
    }


def chat_theme_tokens() -> dict[str, str]:
    p = brand_palette()
    return {
        "bg_dialog": p["white"],
        "text_primary": p["ink_900"],
        "text_muted": p["ink_500"],
        "panel": "#FFFFFF",
        "panel_soft": p["white_soft"],
        "panel_border": p["blue_100"],
        "accent_top": p["pink_50"],
        "accent_bottom": p["pink_100"],
        "accent_border": p["pink_300"],
        "accent_border_pressed": p["pink_400"],
        "accent_hover_top": p["white"],
        "accent_hover_bottom": p["pink_50"],
        "send_top": p["pink_300"],
        "send_bottom": p["pink_500"],
        "send_border": p["pink_400"],
        "send_hover_top": p["pink_200"],
        "send_hover_bottom": p["pink_400"],
        "timeline_bg": "#FFFDFE",
        "timeline_item_user_top": p["pink_100"],
        "timeline_item_user_bottom": p["pink_200"],
        "timeline_item_user_border": p["pink_300"],
        "timeline_item_assistant_top": "#FFFFFF",
        "timeline_item_assistant_bottom": p["blue_50"],
        "timeline_item_assistant_border": p["blue_100"],
        "timestamp": "#8B96A6",
        "font_family": '"SF Pro Rounded", "PingFang SC", "Helvetica Neue", sans-serif',
    }


def focus_theme_base_tokens() -> dict[str, str]:
    p = brand_palette()
    return {
        "status_text": p["ink_900"],
        "round_text": p["blue_300"],
        "settings_text": p["ink_900"],
        "divider": p["blue_100"],
        "btn_primary": p["pink_400"],
        "btn_primary_hover": p["pink_500"],
        "btn_soft": p["pink_100"],
        "btn_soft_hover": p["pink_200"],
        "btn_danger": p["danger_400"],
        "btn_danger_hover": p["danger_500"],
        "countdown": p["blue_300"],
    }
