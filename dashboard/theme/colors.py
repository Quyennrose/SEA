from __future__ import annotations

import math
import unicodedata
from typing import Any


ALERT_COLORS = {
    "green": "#2f9e44",
    "light_green": "#8ce99a",
    "yellow": "#f2c94c",
    "orange": "#e67700",
    "red": "#c92a2a",
    "missing": "#8b7bbf",
    "gray": "#8b7bbf",
}

ALERT_COLOR_MAP = {
    "xanh": ALERT_COLORS["green"],
    "xanh nhat": ALERT_COLORS["light_green"],
    "vang": ALERT_COLORS["yellow"],
    "cam": ALERT_COLORS["orange"],
    "do": ALERT_COLORS["red"],
    "xam": ALERT_COLORS["missing"],
    "thieu du lieu": ALERT_COLORS["missing"],
    "green": ALERT_COLORS["green"],
    "yellow": ALERT_COLORS["yellow"],
    "orange": ALERT_COLORS["orange"],
    "red": ALERT_COLORS["red"],
    "gray": ALERT_COLORS["missing"],
    "missing": ALERT_COLORS["missing"],
}

PRESSURE_CONTINUOUS_SCALE = [
    [0.00, ALERT_COLORS["green"]],
    [0.39, ALERT_COLORS["green"]],
    [0.40, ALERT_COLORS["yellow"]],
    [0.69, ALERT_COLORS["yellow"]],
    [0.70, ALERT_COLORS["orange"]],
    [0.84, ALERT_COLORS["orange"]],
    [0.85, ALERT_COLORS["red"]],
    [1.00, ALERT_COLORS["red"]],
]

INFRASTRUCTURE_CONTINUOUS_SCALE = [
    [0.00, ALERT_COLORS["red"]],
    [0.39, ALERT_COLORS["red"]],
    [0.40, ALERT_COLORS["yellow"]],
    [0.69, ALERT_COLORS["yellow"]],
    [0.70, ALERT_COLORS["light_green"]],
    [0.84, ALERT_COLORS["light_green"]],
    [0.85, ALERT_COLORS["green"]],
    [1.00, ALERT_COLORS["green"]],
]


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value).strip().lower())
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    text = _normalize(value)
    return text in {"", "nan", "none", "null", "missing", "thieu du lieu", "xam"}


def get_alert_color(muc_canh_bao: Any) -> str:
    return ALERT_COLOR_MAP.get(_normalize(muc_canh_bao), ALERT_COLORS["missing"])


def get_score_color(score: Any, is_reverse: bool = False, missing: bool = False) -> str:
    if missing or _is_missing(score):
        return ALERT_COLORS["missing"]
    try:
        value = float(score)
    except (TypeError, ValueError):
        return ALERT_COLORS["missing"]
    value = max(0.0, min(100.0, value))
    if is_reverse:
        if value <= 39:
            return ALERT_COLORS["red"]
        if value <= 69:
            return ALERT_COLORS["yellow"]
        if value <= 84:
            return ALERT_COLORS["light_green"]
        return ALERT_COLORS["green"]
    if value <= 39:
        return ALERT_COLORS["green"]
    if value <= 69:
        return ALERT_COLORS["yellow"]
    if value <= 84:
        return ALERT_COLORS["orange"]
    return ALERT_COLORS["red"]


def get_alert_level_from_score(score: Any, missing: bool = False) -> str:
    color = get_score_color(score, missing=missing)
    if color == ALERT_COLORS["red"]:
        return "đỏ"
    if color == ALERT_COLORS["orange"]:
        return "cam"
    if color == ALERT_COLORS["yellow"]:
        return "vàng"
    if color == ALERT_COLORS["green"]:
        return "xanh"
    return "xám"


def plotly_alert_color_map() -> dict[str, str]:
    return {
        "đỏ": ALERT_COLORS["red"],
        "do": ALERT_COLORS["red"],
        "cam": ALERT_COLORS["orange"],
        "vàng": ALERT_COLORS["yellow"],
        "vang": ALERT_COLORS["yellow"],
        "xanh": ALERT_COLORS["green"],
        "xám": ALERT_COLORS["missing"],
        "xam": ALERT_COLORS["missing"],
        "Thiếu dữ liệu": ALERT_COLORS["missing"],
        "Đỏ - nguy cơ quá tải": ALERT_COLORS["red"],
        "Cam - áp lực cao": ALERT_COLORS["orange"],
        "Vàng - cần theo dõi": ALERT_COLORS["yellow"],
        "Xanh - còn dư địa": ALERT_COLORS["green"],
        "Thiếu dữ liệu": ALERT_COLORS["missing"],
        "Thiếu dữ liệu": ALERT_COLORS["missing"],
    }
