from __future__ import annotations

import json
import os
import subprocess
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
import streamlit.components.v1 as components
from theme.colors import (
    ALERT_COLORS,
    INFRASTRUCTURE_CONTINUOUS_SCALE,
    PRESSURE_CONTINUOUS_SCALE,
    get_alert_color,
    get_alert_level_from_score,
    get_score_color,
    plotly_alert_color_map,
)
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dashboard still reads existing process env
    load_dotenv = None


ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "datasets" / "gold" / "current"
META = ROOT / "data" / "metadata"
EXPORTS = ROOT / "exports"
ENV_FILE = ROOT / ".env"
VN_TZ = "Asia/Ho_Chi_Minh"

SUPPORTED_ENV_KEYS = [
    "POSITIONSTACK_API_KEY",
    "OPENROUTESERVICE_API_KEY",
    "RAPIDAPI_KEY",
    "RAPIDAPI_SERP_HOST",
    "RAPIDAPI_GOOGLE_MAPS_HOST",
    "RAPIDAPI_GOOGLE_PLACES_HOST",
    "GOOGLE_SHEETS_ID",
    "GEMINI_API_KEY",
    "AI_PROVIDER",
    "GEMINI_MODEL",
]


SHEET_SUMMARY_TABLES = [
    ("Ranking toàn quốc", CURRENT / "xep_hang_canh_bao_toan_quoc.csv"),
    ("Dự báo", CURRENT / "forecast_demand_scores.csv"),
    ("Trạng thái dữ liệu", META / "data_freshness_status.csv"),
    ("Dữ liệu mới cập nhật", CURRENT / "source_monitor_status.csv"),
    ("Dữ liệu cũ gần đây", META / "pipeline_run_log.csv"),
    ("Kiểm định proxy", CURRENT / "proxy_vs_nearrealtime_comparison.csv"),
    ("Hiệu quả kinh tế", CURRENT / "de_xuat_hieu_qua_kinh_te.csv"),
]


st.set_page_config(page_title="SEA", page_icon=None, layout="wide")


@st.cache_data(show_spinner=False)
def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig")


def to_num(value: Any, default: float | None = None) -> float | None:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def numeric_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


def vn_time(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == "":
        return "thiếu dữ liệu"
    try:
        text = str(value).strip()
        if len(text) == 16 and text[2] == "/" and text[5] == "/":
            ts = pd.to_datetime(text, format="%d/%m/%Y %H:%M", errors="coerce")
            if pd.isna(ts):
                return text
            return ts.strftime("%d/%m/%Y %H:%M")
        ts = pd.to_datetime(text, errors="coerce", utc=True, dayfirst=True)
        if pd.isna(ts):
            return str(value)
        return ts.tz_convert(VN_TZ).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(value)


def file_time(path: Path) -> str:
    if not path.exists():
        return "thiếu dữ liệu"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")


def strip_accents(text: str) -> str:
    text = str(text).lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def read_env() -> dict[str, str]:
    if load_dotenv is not None and ENV_FILE.exists() and ENV_FILE.is_file():
        load_dotenv(ENV_FILE, override=True)
    env = {key: os.getenv(key, "").strip() for key in SUPPORTED_ENV_KEYS}
    env["CONFIG_SOURCE"] = ".env" if ENV_FILE.exists() and ENV_FILE.is_file() else "chưa tìm thấy .env"
    return env


def sheet_credentials_status() -> tuple[bool, str]:
    json_text = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    credential_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if json_text:
        try:
            json.loads(json_text)
            return True, "Đã có GOOGLE_SERVICE_ACCOUNT_JSON"
        except json.JSONDecodeError:
            return False, "GOOGLE_SERVICE_ACCOUNT_JSON không phải JSON hợp lệ"
    if credential_path:
        path = Path(credential_path)
        if path.exists() and path.is_file():
            return True, f"Đã có credentials file: {path.name}"
        return False, f"Không tìm thấy file credentials: {credential_path}"
    return False, "Thiếu GOOGLE_SERVICE_ACCOUNT_JSON hoặc GOOGLE_APPLICATION_CREDENTIALS"


def google_sheet_client() -> tuple[Any | None, str]:
    try:
        import gspread
    except ImportError:
        return None, "Thiếu package gspread/google-auth. Chạy: pip install -r requirements.txt"
    json_text = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    credential_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    try:
        if json_text:
            return gspread.service_account_from_dict(json.loads(json_text)), ""
        if credential_path:
            return gspread.service_account(filename=credential_path), ""
    except Exception as exc:
        return None, f"Không đọc được Google credentials: {exc}"
    return None, "Thiếu GOOGLE_SERVICE_ACCOUNT_JSON hoặc GOOGLE_APPLICATION_CREDENTIALS"


def sync_google_sheets_summary(sheet_id: str) -> pd.DataFrame:
    now = datetime.now().astimezone().strftime("%d/%m/%Y %H:%M")
    if not sheet_id:
        status = pd.DataFrame(
            [{"Bảng summary": name, "Trạng thái": "Lỗi", "Số dòng": 0, "Lỗi": "Thiếu GOOGLE_SHEETS_ID", "Đồng bộ lúc": now} for name, _ in SHEET_SUMMARY_TABLES]
        )
        status.to_csv(META / "google_sheets_sync_status.csv", index=False, encoding="utf-8-sig")
        return status
    client, client_error = google_sheet_client()
    if client is None:
        status = pd.DataFrame(
            [{"Bảng summary": name, "Trạng thái": "Lỗi", "Số dòng": 0, "Lỗi": client_error, "Đồng bộ lúc": now} for name, _ in SHEET_SUMMARY_TABLES]
        )
        status.to_csv(META / "google_sheets_sync_status.csv", index=False, encoding="utf-8-sig")
        return status
    try:
        spreadsheet = client.open_by_key(sheet_id)
    except Exception as exc:
        status = pd.DataFrame(
            [{"Bảng summary": name, "Trạng thái": "Lỗi", "Số dòng": 0, "Lỗi": f"Không mở được Sheet. Kiểm tra share quyền Editor cho service account: {exc}", "Đồng bộ lúc": now} for name, _ in SHEET_SUMMARY_TABLES]
        )
        status.to_csv(META / "google_sheets_sync_status.csv", index=False, encoding="utf-8-sig")
        return status

    rows: list[dict[str, Any]] = []
    for sheet_name, path in SHEET_SUMMARY_TABLES:
        if not path.exists():
            rows.append({"Bảng summary": sheet_name, "Trạng thái": "Lỗi", "Số dòng": 0, "Lỗi": f"Không thấy file {path.relative_to(ROOT)}", "Đồng bộ lúc": now})
            continue
        try:
            df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("").head(5000)
            values = [list(df.columns)] + df.astype(str).values.tolist()
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
            except Exception:
                worksheet = spreadsheet.add_worksheet(title=sheet_name[:100], rows=max(len(values), 100), cols=max(len(df.columns), 10))
            worksheet.clear()
            worksheet.update(values, value_input_option="USER_ENTERED")
            rows.append({"Bảng summary": sheet_name, "Trạng thái": "Đã sync", "Số dòng": len(df), "Lỗi": "", "Đồng bộ lúc": now})
        except Exception as exc:
            rows.append({"Bảng summary": sheet_name, "Trạng thái": "Lỗi", "Số dòng": 0, "Lỗi": str(exc)[:500], "Đồng bộ lúc": now})
    status = pd.DataFrame(rows)
    status.to_csv(META / "google_sheets_sync_status.csv", index=False, encoding="utf-8-sig")
    return status


def alert_color(level: Any) -> str:
    level = str(level).lower().strip()
    return {
        "đỏ": "#c92a2a",
        "do": "#c92a2a",
        "cam": "#e67700",
        "vàng": "#f2c94c",
        "vang": "#f2c94c",
        "xanh": "#2f9e44",
        "xám": "#8b7bbf",
        "xam": "#8b7bbf",
    }.get(level, "#8b7bbf")


def alert_label(level: Any) -> str:
    level = strip_accents(str(level))
    if level == "do":
        return "Đỏ - nguy cơ quá tải"
    if level == "cam":
        return "Cam - áp lực cao"
    if level == "vang":
        return "Vàng - cần theo dõi"
    if level == "xanh":
        return "Xanh - còn dư địa"
    return "Thiếu dữ liệu"


def alert_color(level: Any) -> str:
    return get_alert_color(level)


def alert_color_map() -> dict[str, str]:
    return plotly_alert_color_map()


def apply_chart_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(color="#18201c"),
        legend_title_text="Mức cảnh báo",
        margin=dict(l=32, r=24, t=58, b=36),
    )
    fig.update_xaxes(gridcolor="#e9ecef", zerolinecolor="#dee2e6")
    fig.update_yaxes(gridcolor="#e9ecef", zerolinecolor="#dee2e6")
    return fig


def pressure_level(score: Any) -> str:
    return get_alert_level_from_score(score)


def data_type_label(value: Any) -> str:
    text = strip_accents(str(value))
    if "missing" in text or "thieu" in text:
        return "thiếu dữ liệu"
    if "near" in text:
        return "near-realtime và proxy"
    if "proxy" in text:
        return "proxy"
    if "real" in text:
        return "dữ liệu thật"
    if "schema" in text:
        return "chỉ có schema"
    return str(value) if str(value).strip() else "thiếu dữ liệu"


REGION_LABELS = {
    "central_coast": "Duyên hải miền Trung",
    "central_coast_islands": "Đảo miền Trung",
    "central_highlands": "Tây Nguyên",
    "mekong_delta": "Đồng bằng sông Cửu Long",
    "mekong_islands": "Đảo Tây Nam Bộ",
    "northeast": "Đông Bắc",
    "north_central_coast": "Bắc Trung Bộ",
    "northern_mountains": "Miền núi phía Bắc",
    "red_river_delta": "Đồng bằng sông Hồng",
    "south_central_coast": "Nam Trung Bộ",
    "southeast": "Đông Nam Bộ",
    "southeast_islands": "Đảo Đông Nam Bộ",
    "southwest": "Tây Nam Bộ",
}

TOURISM_TYPE_LABELS = {
    "coastal": "biển",
    "beach": "bãi biển",
    "urban": "đô thị",
    "heritage": "di sản",
    "island": "đảo",
    "mountain": "núi",
    "nature": "tự nhiên",
    "gateway": "cửa ngõ",
    "mekong": "Mekong",
    "resort": "nghỉ dưỡng",
    "culture": "văn hóa",
    "food": "ẩm thực",
    "attraction": "khu vui chơi",
    "ticket": "vé/khu vui chơi",
}


def region_label(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return "thiếu dữ liệu"
    return REGION_LABELS.get(text.lower(), text)


def tourism_type_label(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return "thiếu dữ liệu"
    parts = [part.strip() for part in text.replace(",", ";").split(";") if part.strip()]
    return "; ".join(TOURISM_TYPE_LABELS.get(part.lower(), part) for part in parts)


def confidence_label(value: Any) -> str:
    score = to_num(value, 0) or 0
    if score >= 80:
        return "Cao"
    if score >= 65:
        return "Khá"
    if score >= 45:
        return "Trung bình"
    return "Thấp"


def explain(title: str, body: str) -> None:
    with st.expander(f"? {title}", expanded=False):
        st.markdown(body)


def card(title: str, value: str, note: str, help_text: str) -> None:
    st.metric(title, value, help=help_text)
    st.caption(note)


def status_caption(dataset_id: str, freshness: pd.DataFrame) -> None:
    updated = "thiếu dữ liệu"
    status = "cần kiểm tra"
    source = "SEA gold/current"
    confidence = "Trung bình"
    if not freshness.empty and "dataset_id" in freshness.columns:
        row = freshness[freshness["dataset_id"].astype(str).eq(dataset_id)]
        if row.empty:
            row = freshness.head(1)
        if not row.empty:
            item = row.iloc[0]
            updated = vn_time(item.get("cap_nhat_lan_cuoi", item.get("ngay_cap_nhat", "")))
            status = item.get("trang_thai_du_lieu", item.get("trang_thai_do_moi", status))
            source = item.get("nguon_du_lieu_chinh", item.get("loai_du_lieu", source))
            confidence = item.get("do_tin_cay", confidence)
    st.caption(
        f"Cập nhật lần cuối: {updated} | Múi giờ: Việt Nam | "
        f"Trạng thái dữ liệu: {status} | Nguồn dữ liệu chính: {source} | Độ tin cậy: {confidence}"
    )


def display_df(df: pd.DataFrame, cols: list[str] | None = None, height: int = 380) -> None:
    if df.empty:
        st.info("Thiếu dữ liệu để hiển thị bảng này.")
        return
    out = df.copy()
    if cols:
        out = out[[c for c in cols if c in out.columns]]
    for col in out.columns:
        if "cap_nhat" in strip_accents(col) or "kiem_tra" in strip_accents(col) or "last" in strip_accents(col):
            out[col] = out[col].map(vn_time)
    st.dataframe(out, width="stretch", hide_index=True, height=height)


def display_alert_ranking(df: pd.DataFrame, height: int = 520) -> None:
    if df.empty:
        st.info("Thiếu dữ liệu để hiển thị bảng ranking.")
        return
    out = vietnamese_alerts(df)

    def row_style(row: pd.Series) -> list[str]:
        raw = df.loc[row.name, "muc_canh_bao"] if "muc_canh_bao" in df.columns and row.name in df.index else ""
        color = get_alert_color(raw)
        return [f"border-left: 6px solid {color}; background-color: {color}18" for _ in row]

    st.dataframe(out.style.apply(row_style, axis=1), width="stretch", hide_index=True, height=height)


def vietnamese_alerts(alerts: pd.DataFrame) -> pd.DataFrame:
    df = alerts.copy()
    rename = {
        "rank": "Xếp hạng",
        "xep_hang": "Xếp hạng",
        "ten_diem_den": "Điểm đến",
        "tinh_thanh": "Tỉnh/thành",
        "vung": "Vùng",
        "loai_hinh_du_lich": "Loại hình",
        "muc_canh_bao": "Mức cảnh báo",
        "diem_ap_luc": "Điểm áp lực",
        "rui_ro_thoi_tiet": "Điểm thời tiết",
        "diem_thoi_tiet": "Điểm thời tiết",
        "diem_ha_tang": "Điểm hạ tầng",
        "diem_co_hoi_kinh_te": "Cơ hội kinh tế",
        "diem_dieu_phoi": "Điểm điều phối",
        "du_bao_24_gio": "Dự báo 24 giờ",
        "du_bao_7_ngay": "Dự báo 7 ngày",
        "du_bao_30_ngay": "Dự báo 30 ngày",
        "nhiet_do_hien_tai": "Nhiệt độ hiện tại",
        "mua_hien_tai": "Khả năng mưa",
        "kha_nang_mua": "Khả năng mưa",
        "gio_hien_tai": "Gió",
        "gio": "Gió",
        "trang_thai_thoi_tiet_ngan": "Trạng thái thời tiết",
        "cap_nhat_thoi_tiet_luc": "Cập nhật thời tiết lúc",
        "co_hoi_kinh_te": "Cơ hội kinh tế",
        "kha_nang_dieu_phoi": "Điểm điều phối",
        "diem_san_sang_ha_tang": "Điểm hạ tầng",
        "diem_suc_khoe_diem_den": "Sức khỏe điểm đến",
        "loai_du_lieu": "Loại dữ liệu",
        "do_tin_cay": "Độ tin cậy",
        "nguyen_nhan_chinh": "Lý do chính",
        "ly_do_xep_hang": "Lý do chính",
        "hanh_dong_de_xuat": "Hành động đề xuất",
        "hieu_qua_kinh_te_ky_vong": "Hiệu quả kinh tế kỳ vọng",
        "hieu_qua_kinh_te_du_kien": "Hiệu quả kinh tế kỳ vọng",
        "cap_nhat_lan_cuoi": "Cập nhật lần cuối",
    }
    df = df.rename(columns=rename)
    if "Mức cảnh báo" in df.columns:
        df["Mức cảnh báo"] = df["Mức cảnh báo"].map(alert_label)
    if "Vùng" in df.columns:
        df["Vùng"] = df["Vùng"].map(region_label)
    if "Loại hình" in df.columns:
        df["Loại hình"] = df["Loại hình"].map(tourism_type_label)
    if "Loại dữ liệu" in df.columns:
        df["Loại dữ liệu"] = df["Loại dữ liệu"].map(data_type_label)
    if "Cập nhật lần cuối" in df.columns:
        df["Cập nhật lần cuối"] = df["Cập nhật lần cuối"].map(vn_time)
    return df


def get_row(alerts: pd.DataFrame, name: str) -> pd.Series:
    if alerts.empty:
        return pd.Series(dtype=object)
    wanted = strip_accents(name)
    exact = alerts[alerts["ten_diem_den"].map(strip_accents).eq(wanted)]
    if not exact.empty:
        return exact.iloc[0]
    contains = alerts[alerts["ten_diem_den"].map(strip_accents).str.contains(wanted, na=False)]
    if not contains.empty:
        return contains.iloc[0]
    return alerts.iloc[0]


def open_destination_profile(name: str) -> None:
    st.session_state["selected_destination"] = str(name)
    st.session_state["active_page"] = "Hồ sơ điểm đến"
    st.rerun()


def missing_data_text(row: pd.Series) -> str:
    missing: list[str] = []
    if str(row.get("ten_diem_den", "")).strip() == "":
        missing.append("tên điểm đến")
    if pd.isna(to_num(row.get("nhiet_do_hien_tai"), None)):
        missing.append("thời tiết hiện tại")
    if pd.isna(to_num(row.get("lat"), None)) or pd.isna(to_num(row.get("lng"), None)):
        missing.append("tọa độ/geocode")
    if "missing" in str(row.get("loai_du_lieu", "")).lower() or strip_accents(row.get("muc_canh_bao", "")) == "xam":
        missing.extend(["POI", "khách sạn", "tuyến di chuyển", "vé/khu vui chơi", "tin tức hoặc cập nhật gần đây"])
    if not missing:
        return "Chưa ghi nhận thiếu dữ liệu bắt buộc trong bảng current, nhưng SEA vẫn cần API đối tác để có crowd, traffic, occupancy và ticket sales realtime."
    return (
        "Điểm thiếu dữ liệu vì chưa có một hoặc nhiều nguồn: tọa độ, thời tiết, POI, khách sạn, "
        "tuyến di chuyển, vé/khu vui chơi, tin tức hoặc cập nhật gần đây. Thiếu cụ thể: "
        + ", ".join(dict.fromkeys(missing))
        + "."
    )


def color_explanation(level: Any) -> str:
    key = strip_accents(str(level))
    if key == "do":
        return "Màu đỏ nghĩa là nguy cơ quá tải, thường từ 85-100/100. Cần hành động ngay: phân luồng, tăng shuttle, chia khung giờ, cảnh báo sớm và giảm quảng bá đại trà."
    if key == "cam":
        return "Màu cam nghĩa là điểm đến có áp lực cao, thường trong khoảng 70-84/100. SEA đánh dấu cam khi nhiều tín hiệu cùng tăng như thời tiết thuận lợi, mật độ khách sạn/POI cao, có sự kiện hoặc dự báo nhu cầu tăng. Mức này cần chuẩn bị điều phối khách, shuttle, chia khung giờ hoặc truyền thông sớm."
    if key == "vang":
        return "Màu vàng nghĩa là cần theo dõi. Điểm đến có dấu hiệu tăng nhu cầu nhưng chưa cần hành động mạnh."
    if key == "xanh":
        return "Màu xanh nghĩa là còn dư địa. Có thể kích cầu có kiểm soát hoặc nhận khách điều phối nếu hạ tầng phù hợp."
    return "Màu tím nhạt/xanh xám nghĩa là Thiếu dữ liệu. SEA chưa đủ dữ liệu để đánh giá chắc chắn vì có thể thiếu tọa độ, thời tiết, POI, khách sạn, tuyến di chuyển, vé/khu vui chơi, tin tức hoặc cập nhật gần đây. Thiếu dữ liệu không có nghĩa là an toàn; cần bổ sung nguồn trước khi ra quyết định mạnh."


def weather_text(row: pd.Series) -> dict[str, str]:
    temp = to_num(row.get("nhiet_do_hien_tai"), None)
    rain = to_num(row.get("mua_hien_tai"), None)
    wind = to_num(row.get("gio_hien_tai"), None)
    humidity = to_num(row.get("do_am_hien_tai"), None)
    beach = str(row.get("coastal_zone", "")).lower() == "yes"
    weather_risk = to_num(row.get("rui_ro_thoi_tiet"), None)
    outdoor = "thiếu dữ liệu"
    if weather_risk is not None:
        outdoor = "Tốt" if weather_risk < 40 else "Trung bình" if weather_risk < 70 else "Thấp do rủi ro thời tiết tăng"
    sea = "không áp dụng"
    if beach:
        sea = outdoor if outdoor != "Tốt" else "Tốt, vẫn cần theo dõi mưa/gió"
    return {
        "Nhiệt độ hiện tại": "thiếu dữ liệu" if temp is None else f"{temp:.1f}°C",
        "Mưa hiện tại": "thiếu dữ liệu" if rain is None else f"{rain:.1f} mm",
        "Gió": "thiếu dữ liệu" if wind is None else f"{wind:.1f} km/h",
        "Độ ẩm": "thiếu dữ liệu" if humidity is None else f"{humidity:.0f}%",
        "Phù hợp du lịch ngoài trời": outdoor,
        "Phù hợp đi biển": sea,
        "Cập nhật thời tiết lúc": vn_time(row.get("cap_nhat_lan_cuoi", "")),
    }


def build_map_html(alerts: pd.DataFrame, poi: pd.DataFrame, routes: pd.DataFrame) -> str:
    items: list[dict[str, Any]] = []
    for _, row in alerts.iterrows():
        lat = to_num(row.get("lat"), None)
        lng = to_num(row.get("lng"), None)
        if lat is None or lng is None:
            continue
        wt = weather_text(row)
        wt["Khả năng mưa"] = wt.get("Mưa hiện tại", "thiếu dữ liệu")
        items.append(
            {
                "id": row.get("destination_id", ""),
                "name": row.get("ten_diem_den", ""),
                "province": row.get("tinh_thanh", ""),
                "region": region_label(row.get("vung", "")),
                "type": tourism_type_label(row.get("loai_hinh_du_lich", "")),
                "level": row.get("muc_canh_bao", "xám"),
                "levelLabel": alert_label(row.get("muc_canh_bao", "xám")),
                "color": alert_color(row.get("muc_canh_bao", "xám")),
                "pressure": row.get("diem_ap_luc", "thiếu dữ liệu"),
                "infrastructure": row.get("diem_san_sang_ha_tang", "thiếu dữ liệu"),
                "economy": row.get("co_hoi_kinh_te", "thiếu dữ liệu"),
                "health": row.get("diem_suc_khoe_diem_den", "thiếu dữ liệu"),
                "forecast24": row.get("du_bao_24_gio", "thiếu dữ liệu"),
                "forecast7": row.get("du_bao_7_ngay", "thiếu dữ liệu"),
                "forecast30": row.get("du_bao_30_ngay", "thiếu dữ liệu"),
                "reason": row.get("nguyen_nhan_chinh", "thiếu dữ liệu"),
                "action": row.get("hanh_dong_de_xuat", "thiếu dữ liệu"),
                "impact": row.get("hieu_qua_kinh_te_ky_vong", "thiếu dữ liệu"),
                "dataType": data_type_label(row.get("loai_du_lieu", "")),
                "missing": missing_data_text(row),
                "updated": vn_time(row.get("cap_nhat_lan_cuoi", "")),
                "confidence": f"{row.get('do_tin_cay', 'thiếu dữ liệu')} ({confidence_label(row.get('do_tin_cay'))})",
                "lat": lat,
                "lng": lng,
                "weather": wt,
                "colorText": color_explanation(row.get("muc_canh_bao", "xám")),
            }
        )

    poi_items: list[dict[str, Any]] = []
    if not poi.empty:
        for _, row in poi.head(900).iterrows():
            lat = to_num(row.get("lat"), None)
            lng = to_num(row.get("lng"), None)
            if lat is None or lng is None:
                continue
            poi_items.append(
                {
                    "lat": lat,
                    "lng": lng,
                    "name": row.get("ten_poi", row.get("ten_dia_diem", "POI")),
                    "type": row.get("nhom_chi_tieu", row.get("loai_ve", "POI")),
                    "destination": row.get("ten_diem_den", ""),
                }
            )

    route_items: list[dict[str, Any]] = []
    by_id = {str(row.get("destination_id")): row for _, row in alerts.iterrows()}
    if not routes.empty:
        for _, row in routes.iterrows():
            origin = by_id.get(str(row.get("origin_id")))
            alt = by_id.get(str(row.get("alternative_id")))
            if origin is None or alt is None:
                continue
            lat1, lng1 = to_num(origin.get("lat"), None), to_num(origin.get("lng"), None)
            lat2, lng2 = to_num(alt.get("lat"), None), to_num(alt.get("lng"), None)
            if None in (lat1, lng1, lat2, lng2):
                continue
            route_items.append(
                {
                    "origin": origin.get("ten_diem_den", row.get("origin_id")),
                    "target": alt.get("ten_diem_den", row.get("alternative_id")),
                    "lat1": lat1,
                    "lng1": lng1,
                    "lat2": lat2,
                    "lng2": lng2,
                    "time": row.get("route_time_minutes", row.get("approx_travel_time_minutes", "thiếu dữ liệu")),
                    "score": row.get("redistribution_opportunity_score", "thiếu dữ liệu"),
                }
            )

    return f"""
    <div style="display:grid;grid-template-columns:1fr 360px;gap:12px;font-family:Arial,sans-serif;">
      <div>
        <div id="sea-map" style="height:760px;width:100%;border:1px solid #d8dee4;border-radius:10px;"></div>
      </div>
      <aside id="sea-panel" style="height:760px;overflow:auto;border:1px solid #d8dee4;border-radius:10px;padding:14px;background:#fff;">
        <h3 style="margin-top:0;">Hồ sơ điểm đến</h3>
        <p>Bấm vào marker trên bản đồ để xem thời tiết, dự báo, lý do cảnh báo, dữ liệu thiếu và hành động đề xuất.</p>
      </aside>
    </div>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
      const destinations = {json.dumps(items, ensure_ascii=False)};
      const poiItems = {json.dumps(poi_items, ensure_ascii=False)};
      const routeItems = {json.dumps(route_items, ensure_ascii=False)};
      const map = L.map('sea-map').setView([16.2, 106.3], 6);
      L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{ attribution: '&copy; OpenStreetMap &copy; CARTO', maxZoom: 19 }}).addTo(map);

      const layers = {{
        "Điểm đến": L.layerGroup().addTo(map),
        "Bãi biển": L.layerGroup().addTo(map),
        "Khách sạn": L.layerGroup().addTo(map),
        "Nhà hàng/ăn uống": L.layerGroup().addTo(map),
        "Khu vui chơi/vé": L.layerGroup().addTo(map),
        "POI khác": L.layerGroup().addTo(map),
        "Tuyến điều phối": L.layerGroup().addTo(map),
        "Thời tiết": L.layerGroup().addTo(map),
        "Heatmap áp lực": L.layerGroup().addTo(map),
        "Heatmap POI/khách sạn": L.layerGroup().addTo(map)
      }};

      function renderPanel(d) {{
        document.getElementById('sea-panel').innerHTML = `
          <h3 style="margin-top:0;">${{d.name}}</h3>
          <div style="display:inline-block;background:${{d.color}};color:white;border-radius:999px;padding:6px 10px;font-weight:700;">${{d.levelLabel}}</div>
          <p><b>Tỉnh/thành:</b> ${{d.province}}<br><b>Loại hình:</b> ${{d.type}}</p>
          <p><b>Giải thích màu:</b> ${{d.colorText}}</p>
          <hr>
          <p><b>Nhiệt độ hiện tại:</b> ${{d.weather["Nhiệt độ hiện tại"]}}<br>
          <b>Khả năng mưa:</b> ${{d.weather["Khả năng mưa"]}}<br>
          <b>Gió:</b> ${{d.weather["Gió"]}}<br>
          <b>Độ ẩm:</b> ${{d.weather["Độ ẩm"]}}<br>
          <b>Phù hợp du lịch ngoài trời:</b> ${{d.weather["Phù hợp du lịch ngoài trời"]}}<br>
          <b>Phù hợp đi biển:</b> ${{d.weather["Phù hợp đi biển"]}}<br>
          <b>Cập nhật thời tiết lúc:</b> ${{d.weather["Cập nhật thời tiết lúc"]}}</p>
          <hr>
          <p><b>Dự báo 24 giờ:</b> ${{d.forecast24}}/100<br>
          <b>Dự báo 7 ngày:</b> ${{d.forecast7}}/100<br>
          <b>Dự báo 30 ngày:</b> ${{d.forecast30}}/100</p>
          <p><b>Điểm áp lực:</b> ${{d.pressure}}/100<br>
          <b>Điểm hạ tầng:</b> ${{d.infrastructure}}/100<br>
          <b>Điểm cơ hội kinh tế:</b> ${{d.economy}}/100<br>
          <b>Điểm sức khỏe điểm đến:</b> ${{d.health}}/100</p>
          <p><b>Dữ liệu dùng:</b> ${{d.dataType}}<br>
          <b>Dữ liệu thiếu:</b> ${{d.missing}}<br>
          <b>Cập nhật lần cuối:</b> ${{d.updated}}<br>
          <b>Độ tin cậy:</b> ${{d.confidence}}</p>
          <p><b>Lý do chính:</b> ${{d.reason}}</p>
          <p><b>Hành động đề xuất:</b> ${{d.action}}</p>
          <p><b>Hiệu quả kinh tế kỳ vọng:</b> ${{d.impact}}</p>
          <a target="_parent" href="?page=profile&destination=${{encodeURIComponent(d.name)}}" style="display:block;text-align:center;text-decoration:none;border-radius:8px;background:#0b7285;color:white;padding:10px;font-weight:700;">Mở Hồ sơ điểm đến</a>
        `;
      }}

      destinations.forEach(d => {{
        const marker = L.circleMarker([d.lat, d.lng], {{
          radius: 11, color: "#17202a", weight: 2.5, fillColor: d.color, fillOpacity: .94
        }}).addTo(layers["Điểm đến"]);
        marker.bindTooltip(`<b>${{d.name}}</b><br>${{d.levelLabel}}<br>Áp lực: ${{d.pressure}}/100<br>Nhiệt độ: ${{d.weather["Nhiệt độ hiện tại"]}}<br>Dự báo 7 ngày: ${{d.forecast7}}/100<br>${{d.reason}}`);
        marker.bindPopup(`<b>${{d.name}}</b><br>${{d.levelLabel}}<br>Áp lực: ${{d.pressure}}/100<br>Dự báo 7 ngày: ${{d.forecast7}}/100<br>Cập nhật: ${{d.updated}}`);
        marker.on('click', () => {{
          renderPanel(d);
          window.top.location.href = `?page=profile&destination=${{encodeURIComponent(d.name)}}`;
        }});
        L.circle([d.lat, d.lng], {{radius: 4500 + Number(d.pressure || 0) * 140, color: d.color, fillColor: d.color, fillOpacity: .08, weight: 1}}).addTo(layers["Heatmap áp lực"]);
      }});

      poiItems.forEach(p => {{
        const typeText = String(p.type || "").toLowerCase();
        let layerName = "POI khác";
        if (typeText.includes("beach") || typeText.includes("bãi biển")) layerName = "Bãi biển";
        else if (typeText.includes("hotel") || typeText.includes("khách sạn")) layerName = "Khách sạn";
        else if (typeText.includes("restaurant") || typeText.includes("ăn") || typeText.includes("food")) layerName = "Nhà hàng/ăn uống";
        else if (typeText.includes("ticket") || typeText.includes("attraction") || typeText.includes("vui chơi") || typeText.includes("vé")) layerName = "Khu vui chơi/vé";
        L.circleMarker([p.lat, p.lng], {{radius:4, color:"#1864ab", fillColor:"#4dabf7", fillOpacity:.75, weight:1}})
          .bindTooltip(`<b>${{p.name}}</b><br>${{p.type}}<br>${{p.destination}}`)
          .addTo(layers[layerName]);
        L.circle([p.lat, p.lng], {{radius:1600, color:"#4dabf7", fillColor:"#4dabf7", fillOpacity:.05, weight:0}})
          .addTo(layers["Heatmap POI/khách sạn"]);
      }});

      destinations.forEach(d => {{
        L.circleMarker([d.lat + 0.015, d.lng + 0.015], {{radius:6, color:"#0b7285", fillColor:"#66d9e8", fillOpacity:.86, weight:1}})
          .bindTooltip(`<b>Thời tiết ${{d.name}}</b><br>Nhiệt độ: ${{d.weather["Nhiệt độ hiện tại"]}}<br>Khả năng mưa: ${{d.weather["Khả năng mưa"]}}<br>Gió: ${{d.weather["Gió"]}}`)
          .addTo(layers["Thời tiết"]);
      }});

      routeItems.forEach(r => {{
        L.polyline([[r.lat1, r.lng1], [r.lat2, r.lng2]], {{color:"#1971c2", weight:4, opacity:.72}})
          .bindTooltip(`<b>${{r.origin}} → ${{r.target}}</b><br>Thời gian: ${{r.time}} phút<br>Điểm điều phối: ${{r.score}}`)
          .addTo(layers["Tuyến điều phối"]);
      }});

      const legend = L.control({{position:'bottomleft'}});
      legend.onAdd = function() {{
        const div = L.DomUtil.create('div', 'legend');
        div.style.background = 'white';
        div.style.padding = '12px';
        div.style.border = '1px solid #d8dee4';
        div.style.borderRadius = '8px';
        div.style.lineHeight = '1.5';
        div.innerHTML = `<b>Chú giải cảnh báo</b><br>
          <span style="color:#c92a2a;font-weight:700;">●</span> Đỏ: nguy cơ quá tải<br>
          <span style="color:#e67700;font-weight:700;">●</span> Cam: áp lực cao<br>
          <span style="color:#f2c94c;font-weight:700;">●</span> Vàng: cần theo dõi<br>
          <span style="color:#2f9e44;font-weight:700;">●</span> Xanh: còn dư địa<br>
          <span style="color:#8b7bbf;font-weight:700;">●</span> Thiếu dữ liệu`;
        return div;
      }};
      legend.addTo(map);
      L.control.layers(null, layers, {{collapsed:false}}).addTo(map);
    </script>
    """


def forecast_for_destination(forecast: pd.DataFrame, name: str) -> pd.DataFrame:
    if forecast.empty:
        return pd.DataFrame()
    df = forecast[forecast["ten_diem_den"].astype(str).eq(name)].copy()
    if df.empty:
        return df
    df["Điểm dự báo SEA"] = pd.to_numeric(df.get("forecast_demand_score"), errors="coerce")
    df["Mốc thời gian"] = df.get("forecast_horizon", "")
    df["Trung bình mùa vụ"] = pd.to_numeric(df.get("seasonal_baseline_score"), errors="coerce")
    df["Lịch sử cùng kỳ"] = pd.to_numeric(df.get("historical_same_period_score"), errors="coerce")
    return df


def forecast_line_chart(df: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        fig.update_layout(title=title)
        return fig
    x = df["Mốc thời gian"]
    fig.add_trace(go.Scatter(x=x, y=df["Điểm dự báo SEA"], mode="lines+markers", name="Dự báo SEA"))
    if df["Trung bình mùa vụ"].notna().any():
        fig.add_trace(go.Scatter(x=x, y=df["Trung bình mùa vụ"], mode="lines+markers", name="Trung bình mùa vụ"))
    if df["Lịch sử cùng kỳ"].notna().any():
        fig.add_trace(go.Scatter(x=x, y=df["Lịch sử cùng kỳ"], mode="lines+markers", name="Lịch sử cùng kỳ"))
    if "forecast_lower" in df.columns and "forecast_upper" in df.columns:
        lower = pd.to_numeric(df["forecast_lower"], errors="coerce")
        upper = pd.to_numeric(df["forecast_upper"], errors="coerce")
        if lower.notna().any() and upper.notna().any():
            fig.add_trace(go.Scatter(x=x, y=upper, mode="lines", line=dict(width=0), showlegend=False, name="Cận trên"))
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=lower,
                    mode="lines",
                    line=dict(width=0),
                    fill="tonexty",
                    fillcolor="rgba(11,114,133,0.16)",
                    name="Vùng bất định",
                )
            )
    fig.update_layout(title=title, yaxis_title="Điểm áp lực dự báo 0-100", xaxis_title="Thời gian")
    return fig


def vietnamese_routes(routes: pd.DataFrame, alerts: pd.DataFrame) -> pd.DataFrame:
    if routes.empty:
        return pd.DataFrame()
    name_by_id = alerts.set_index("destination_id")["ten_diem_den"].to_dict() if "destination_id" in alerts.columns else {}
    out = pd.DataFrame(
        {
            "Điểm đang áp lực": routes.get("origin_id", pd.Series(dtype=str)).astype(str).map(name_by_id).fillna(routes.get("origin_id", "")),
            "Điểm đề xuất chuyển sang": routes.get("alternative_id", pd.Series(dtype=str)).astype(str).map(name_by_id).fillna(routes.get("alternative_id", "")),
            "Lý do": routes.get("reason", "Điểm nguồn áp lực cao hơn, điểm đích còn dư địa hoặc có khả năng tạo chi tiêu liên vùng."),
            "Thời gian di chuyển": routes.get("route_time_minutes", routes.get("approx_travel_time_minutes", "thiếu dữ liệu")).astype(str) + " phút",
            "Mức giảm áp lực dự kiến": routes.get("expected_pressure_reduction", routes.get("redistribution_opportunity_score", "thiếu dữ liệu")),
            "Lợi ích kinh tế dự kiến": routes.get("economic_benefit_note", "Tăng chi tiêu vùng phụ, giảm quá tải điểm nóng và giảm chi phí xã hội do kẹt xe/quá tải."),
            "Đối tượng thực hiện": routes.get("implementation_owner", "chính quyền, công an/giao thông, doanh nghiệp du lịch, vận tải/shuttle"),
            "Độ tin cậy": routes.get("confidence_score", routes.get("do_tin_cay", "trung bình")),
        }
    )
    return out


def calendar_heatmap(selected_row: pd.Series) -> pd.DataFrame:
    base = to_num(selected_row.get("du_bao_7_ngay"), None)
    if base is None:
        return pd.DataFrame()
    rows = []
    today = datetime.now()
    for day in range(30):
        date = today + timedelta(days=day)
        weekend = 8 if date.weekday() >= 5 else 0
        pressure = max(0, min(100, base + weekend + (day % 6 - 2) * 1.5))
        rows.append(
            {
                "Ngày": date.strftime("%d/%m"),
                "Tuần": f"Tuần {day // 7 + 1}",
                "Điểm dự báo": round(pressure, 1),
                "Giải thích": "Cuối tuần làm tăng áp lực" if weekend else "Ngày thường, áp lực thấp hơn cuối tuần",
            }
        )
    return pd.DataFrame(rows)


def destination_profile(
    selected: str,
    alerts: pd.DataFrame,
    forecast: pd.DataFrame,
    routes: pd.DataFrame,
    actions: pd.DataFrame,
    spending: pd.DataFrame,
    tickets: pd.DataFrame,
) -> None:
    row = get_row(alerts, selected)
    if row.empty:
        st.info("Thiếu dữ liệu hồ sơ điểm đến.")
        return
    name = row.get("ten_diem_den", selected)
    st.subheader(f"Hồ sơ điểm đến: {name}")
    status_caption("national_destination_alerts", freshness)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        card("Mức cảnh báo", alert_label(row.get("muc_canh_bao")), "Màu hiện tại của điểm đến.", color_explanation(row.get("muc_canh_bao")))
    with c2:
        card("Điểm áp lực", f"{row.get('diem_ap_luc', 'thiếu dữ liệu')}/100", "Áp lực du lịch hiện tại.", "Điểm cao nghĩa là cần kiểm soát dòng khách và dịch vụ.")
    with c3:
        card("Điểm hạ tầng", f"{row.get('diem_san_sang_ha_tang', 'thiếu dữ liệu')}/100", "Khả năng tiếp nhận thêm khách.", "Hạ tầng thấp không nên đẩy khách đại trà.")
    with c4:
        card("Cơ hội kinh tế", f"{row.get('co_hoi_kinh_te', 'thiếu dữ liệu')}/100", "Tiềm năng tạo chi tiêu.", "Điểm cao gợi ý có dư địa tạo doanh thu địa phương.")
    with c5:
        card("Sức khỏe điểm đến", f"{row.get('diem_suc_khoe_diem_den', 'thiếu dữ liệu')}/100", "Tổng hợp áp lực, thời tiết, hạ tầng và dữ liệu.", "Điểm thấp cần can thiệp hoặc bổ sung dữ liệu.")
    with c6:
        card("Độ tin cậy", confidence_label(row.get("do_tin_cay")), f"{row.get('do_tin_cay', 'thiếu dữ liệu')}/100", "Độ tin cậy tính từ nguồn, độ mới, độ phủ, độ đầy đủ và kiểm định proxy.")

    st.markdown("**Tình hình hiện tại**")
    wt = weather_text(row)
    w1, w2, w3 = st.columns(3)
    with w1:
        st.write(f"Nhiệt độ hiện tại: **{wt['Nhiệt độ hiện tại']}**")
        st.write(f"Mưa hiện tại: **{wt['Mưa hiện tại']}**")
    with w2:
        st.write(f"Gió: **{wt['Gió']}**")
        st.write(f"Độ ẩm: **{wt['Độ ẩm']}**")
    with w3:
        st.write(f"Phù hợp ngoài trời: **{wt['Phù hợp du lịch ngoài trời']}**")
        st.write(f"Phù hợp đi biển: **{wt['Phù hợp đi biển']}**")

    st.info(f"Vì sao điểm này có màu hiện tại: {color_explanation(row.get('muc_canh_bao'))} Lý do chính: {row.get('nguyen_nhan_chinh', 'thiếu dữ liệu')}")

    explain(
        "Dấu ? của hồ sơ điểm đến",
        "Hồ sơ điểm đến gom tình hình hiện tại, KPI, thời tiết, dự báo, hạ tầng, điều phối, hành động và độ tin cậy cho một điểm cụ thể. Nếu điểm có màu tím nhạt/xanh xám, SEA chưa đủ dữ liệu để ra quyết định mạnh và sẽ ghi rõ thiếu nguồn nào.",
    )

    fdf = forecast_for_destination(forecast, name)
    kpi_chart = pd.DataFrame(
        [
            {"Chỉ số": "Áp lực", "Điểm": to_num(row.get("diem_ap_luc"), 0)},
            {"Chỉ số": "Hạ tầng", "Điểm": to_num(row.get("diem_san_sang_ha_tang"), 0)},
            {"Chỉ số": "Thời tiết", "Điểm": to_num(row.get("rui_ro_thoi_tiet"), 0)},
            {"Chỉ số": "Cơ hội kinh tế", "Điểm": to_num(row.get("co_hoi_kinh_te"), 0)},
            {"Chỉ số": "Điều phối", "Điểm": to_num(row.get("kha_nang_dieu_phoi"), 0)},
            {"Chỉ số": "Sức khỏe điểm đến", "Điểm": to_num(row.get("diem_suc_khoe_diem_den"), 0)},
        ]
    )
    kpi_chart["Màu"] = kpi_chart.apply(lambda r: get_score_color(r["Điểm"], is_reverse=str(r["Chỉ số"]).lower().find("hạ tầng") >= 0), axis=1)
    st.plotly_chart(apply_chart_theme(px.bar(kpi_chart, x="Chỉ số", y="Điểm", color="Màu", color_discrete_map={c: c for c in ALERT_COLORS.values()}, title=f"Biểu đồ KPI của {name}", range_y=[0, 100])), width="stretch")
    st.plotly_chart(forecast_line_chart(fdf, f"Dự báo riêng cho {name}"), width="stretch")
    cal = calendar_heatmap(row)
    if cal.empty:
        st.warning("Chưa đủ dữ liệu để vẽ calendar heatmap cho điểm này.")
    else:
        st.caption("Heatmap dự báo: màu nhạt = thấp, màu đậm = cao. Hover để xem ngày, điểm rủi ro và lý do.")
        st.plotly_chart(apply_chart_theme(px.density_heatmap(cal, x="Ngày", y="Tuần", z="Điểm dự báo", color_continuous_scale=PRESSURE_CONTINUOUS_SCALE, hover_data=["Giải thích"])), width="stretch")

    st.markdown("**Hạ tầng và dịch vụ**")
    service = pd.concat([spending, tickets], ignore_index=True, sort=False)
    rel_routes = routes[
        routes.get("origin_id", pd.Series(dtype=str)).astype(str).eq(str(row.get("destination_id")))
        | routes.get("alternative_id", pd.Series(dtype=str)).astype(str).eq(str(row.get("destination_id")))
    ] if not routes.empty else pd.DataFrame()
    st.markdown("**Bản đồ nhỏ khu vực điểm đến**")
    destination_map = pd.DataFrame([row.to_dict()])
    components.html(build_map_html(destination_map, service[service.get("ten_diem_den", "").astype(str).eq(name)] if not service.empty else pd.DataFrame(), rel_routes), height=620)
    if not service.empty:
        display_df(service[service.get("ten_diem_den", "").astype(str).eq(name)].head(80), height=260)
    else:
        st.info("Thiếu dữ liệu khách sạn, nhà hàng, khu vui chơi hoặc POI cho điểm này.")
    st.write(f"Điểm yếu hạ tầng/thiếu dữ liệu: {missing_data_text(row)}")

    st.markdown("**Điều phối**")
    display_df(rel_routes.head(30), height=240)

    st.markdown("**Hành động kinh tế**")
    action_df = actions[actions.get("diem_den", pd.Series(dtype=str)).astype(str).eq(name)] if not actions.empty else pd.DataFrame()
    if action_df.empty:
        st.info("Thiếu bảng hành động riêng cho điểm này, dùng khuyến nghị tổng quát từ ranking.")
        st.write(row.get("hanh_dong_de_xuat", "thiếu dữ liệu"))
    else:
        render_action_cards(action_df.head(8))

    st.markdown("**Dữ liệu & độ tin cậy**")
    st.write(f"Loại dữ liệu: **{data_type_label(row.get('loai_du_lieu'))}**")
    st.write(f"Dữ liệu thiếu: **{missing_data_text(row)}**")
    st.write(f"Cập nhật lần cuối: **{vn_time(row.get('cap_nhat_lan_cuoi'))}**")
    if st.button(f"Hỏi trợ lý SEA về {name}"):
        st.markdown(ask_sea_assistant(f"phân tích {name}", env, alerts, routes, freshness, source_monitor, api_catalog))


def render_action_cards(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Thiếu dữ liệu hành động đề xuất.")
        return
    group_col = "doi_tuong_thuc_hien" if "doi_tuong_thuc_hien" in df.columns else None
    groups = df.groupby(group_col, dropna=False) if group_col else [("Hành động", df)]
    for group, part in groups:
        st.markdown(f"### {group}")
        for _, row in part.head(18).iterrows():
            priority = row.get("muc_uu_tien", row.get("Mức ưu tiên", "trung bình"))
            priority_color = get_score_color(row.get("diem_uu_tien", row.get("Điểm ưu tiên", "")), missing=False)
            updated = vn_time(row.get("cap_nhat_lan_cuoi", ""))
            st.markdown(
                f"""
                <div style="border:1px solid #d8dee4;border-left:7px solid {priority_color};border-radius:8px;padding:14px;margin:10px 0;background:#fff;">
                  <div style="font-weight:700;color:{priority_color};">Mức ưu tiên: {priority}</div>
                  <b>Điểm đến:</b> {row.get('diem_den', 'thiếu dữ liệu')}<br>
                  <b>Vấn đề:</b> {row.get('van_de', 'thiếu dữ liệu')}<br>
                  <b>Ai cần làm:</b> {row.get('doi_tuong_thuc_hien', 'thiếu dữ liệu')}<br>
                  <b>Hành động cụ thể:</b> {row.get('hanh_dong', 'thiếu dữ liệu')}<br>
                  <b>Vì sao nên làm:</b> {row.get('logic_kinh_te', row.get('ly_do', 'Gắn với chuỗi Vấn đề -> Hành động -> KPI -> Hiệu quả kinh tế.'))}<br>
                  <b>Chi phí triển khai:</b> {row.get('chi_phi_uoc_tinh', row.get('chi_phi_trien_khai', 'thiếu dữ liệu'))}<br>
                  <b>KPI bị ảnh hưởng:</b> {row.get('kpi_do_luong', 'thiếu dữ liệu')}<br>
                  <b>Hiệu quả kinh tế kỳ vọng:</b> {row.get('loi_ich_ky_vong', 'thiếu dữ liệu')}<br>
                  <b>Dữ liệu dùng:</b> {row.get('du_lieu_chung_minh', row.get('du_lieu_dung', 'thiếu dữ liệu'))}<br>
                  <b>Độ tin cậy:</b> {row.get('do_tin_cay', 'thiếu dữ liệu')}<br>
                  <b>Cập nhật lần cuối:</b> {updated}
                </div>
                """,
                unsafe_allow_html=True,
            )


def answer_question(question: str, alerts: pd.DataFrame, routes: pd.DataFrame, freshness: pd.DataFrame, source_monitor: pd.DataFrame, api_catalog: pd.DataFrame) -> str:
    q = strip_accents(question)
    update_intent = any(token in q for token in ["cap nhat", "du lieu moi", "dataset", "archive", "sheet", "google", "api", "nguon"])
    proxy_intent = "proxy" in q or "near" in q or "realtime" in q
    gray_intent = "xam" in q
    forecast_intent = "du bao" in q or "forecast" in q
    economy_intent = "hieu qua" in q or "kinh te" in q

    if update_intent and ("api" in q or "sheet" in q or "google" in q):
        status_col = "trang_thai_cau_hinh" if "trang_thai_cau_hinh" in api_catalog.columns else "Trạng thái cấu hình"
        name_col = "ten_api" if "ten_api" in api_catalog.columns else "Tên nguồn"
        missing_api = api_catalog[api_catalog.get(status_col, pd.Series(dtype=str)).astype(str).str.contains("thiếu", case=False, na=False)] if not api_catalog.empty else pd.DataFrame()
        sheet = api_catalog[api_catalog.get(name_col, pd.Series(dtype=str)).astype(str).str.contains("Sheets", case=False, na=False)] if not api_catalog.empty else pd.DataFrame()
        sheet_status = sheet.iloc[0].get(status_col, "thiếu dữ liệu") if not sheet.empty else "thiếu dữ liệu"
        return f"""**Tình hình:** Google Sheets đang ở trạng thái **{sheet_status}**. Số API còn thiếu cấu hình: **{len(missing_api)}**.

**Vì sao:** SEA chỉ đồng bộ các bảng summary, không đồng bộ raw data lớn. API thiếu key sẽ bị bỏ qua và dùng nguồn thay thế nếu có.

**Dữ liệu dùng:** `data/metadata/api_source_catalog.csv`, `.env`, trạng thái nguồn trong `data/metadata/source_monitor_status.csv`.

**Độ tin cậy:** Khá, vì đây là metadata cấu hình nội bộ. Chưa phải kết quả gọi API realtime nếu chưa bấm `Kiểm tra lại API`.

**Nên làm:** Cấu hình biến môi trường còn thiếu nếu cần nguồn đó; nếu chưa cấu hình Google Sheets, SEA vẫn chạy bình thường và tải CSV/Excel từ Kho dữ liệu.

**Hiệu quả kinh tế:** API/Sheet đầy đủ giúp dữ liệu mới hơn, ranking và đề xuất điều phối cập nhật nhanh hơn, tránh quyết định dựa trên dữ liệu cũ."""

    if update_intent:
        pending = source_monitor[source_monitor.get("trang_thai", "").astype(str).str.contains("chờ|cần|lỗi|thiếu", case=False, na=False)] if not source_monitor.empty else pd.DataFrame()
        last = "thiếu dữ liệu"
        if not freshness.empty:
            last = vn_time(freshness.iloc[0].get("cap_nhat_lan_cuoi", ""))
        return f"""**Tình hình:** SEA đang dùng bản `datasets/gold/current/`. Lần cập nhật ghi nhận gần nhất: **{last}**. Số nguồn cần kiểm tra/chờ xử lý: **{len(pending)}**.

**Vì sao:** Trạng thái nằm trong `source_monitor_status.csv`, hàng chờ nằm trong `update_queue.csv`, nhật ký nằm trong `pipeline_run_log.csv`.

**Dữ liệu dùng:** Metadata cập nhật, freshness, queue và log pipeline.

**Độ tin cậy:** Khá, vì dựa trên file vận hành đã sinh từ pipeline.

**Nên làm:** Bấm `Cập nhật dữ liệu` khi có nguồn mới. SEA sẽ lưu bản current cũ vào archive, ghi bản mới vào current, tính lại KPI, forecast, ranking, hành động và knowledge base.

**Hiệu quả kinh tế:** Dữ liệu mới giúp cảnh báo đúng thời điểm hơn, đặc biệt với vé, thời tiết, tin tức, hàng không và điều phối khách."""

    if proxy_intent:
        return """**Tình hình:** Proxy là chỉ số ước lượng có kiểm soát khi SEA chưa có dữ liệu đo trực tiếp như camera, cảm biến, occupancy hoặc doanh số vé realtime.

**Vì sao:** SEA dùng thời tiết, cuối tuần/ngày lễ, mật độ POI, khách sạn, tin tức, giá và tuyến đi để ước lượng áp lực.

**Dữ liệu dùng:** Bảng `kiem_dinh_proxy.csv` và `proxy_vs_nearrealtime_comparison.csv`.

**Độ tin cậy:** Phụ thuộc độ lệch proxy so với near-realtime. Lệch dưới 10% là rất tốt; trên 35% là không ổn định và bị giảm confidence.

**Nên làm:** Với điểm có proxy lệch cao, cần bổ sung API đối tác hoặc dữ liệu đo trực tiếp trước khi ra quyết định mạnh.

**Hiệu quả kinh tế:** Kiểm định proxy giúp tránh điều phối sai, giảm rủi ro đẩy khách đến nơi chưa đủ hạ tầng."""

    if gray_intent:
        return """**Tình hình:** Điểm có màu tím nhạt/xanh xám nghĩa là SEA chưa đủ dữ liệu để đánh giá chắc chắn.

**Vì sao:** Có thể thiếu thời tiết, tọa độ, POI, khách sạn, giá vé, nguồn cập nhật hoặc dữ liệu near-realtime.

**Dữ liệu dùng:** Ranking toàn quốc, freshness, missing dataset registry và source monitor.

**Độ tin cậy:** Thấp, vì thiếu nguồn quan trọng.

**Nên làm:** Không coi điểm thiếu dữ liệu là an toàn. Cần bổ sung dữ liệu trước khi kích cầu hoặc điều phối khách quy mô lớn.

**Hiệu quả kinh tế:** Bổ sung dữ liệu giúp tránh đầu tư hoặc truyền thông sai điểm đến."""

    matched = None
    for _, row in alerts.iterrows():
        if strip_accents(row.get("ten_diem_den", "")) in q or q in strip_accents(row.get("ten_diem_den", "")):
            matched = row
            break
    if matched is None:
        matched = alerts.iloc[0] if not alerts.empty else pd.Series(dtype=object)
    if matched.empty:
        return "Hiện SEA chưa đủ dữ liệu để kết luận chắc chắn. Cần bổ sung: ranking, forecast, dữ liệu nguồn và knowledge base."

    name = matched.get("ten_diem_den", "điểm đến")
    rel_routes = routes[routes.get("origin_id", pd.Series(dtype=str)).astype(str).eq(str(matched.get("destination_id")))] if not routes.empty else pd.DataFrame()
    route_text = "Chưa có tuyến điều phối đủ tin cậy."
    if not rel_routes.empty:
        best = rel_routes.sort_values("redistribution_opportunity_score", ascending=False).iloc[0]
        route_text = f"Ưu tiên tuyến {best.get('origin_id')} → {best.get('alternative_id')}, khoảng {best.get('route_time_minutes', 'thiếu dữ liệu')} phút, điểm điều phối {best.get('redistribution_opportunity_score', 'thiếu dữ liệu')}."
    focus = "dự báo" if forecast_intent else "hiệu quả kinh tế" if economy_intent else "cảnh báo"
    return f"""**Tình hình:** {name} đang ở mức **{alert_label(matched.get('muc_canh_bao'))}**, điểm áp lực **{matched.get('diem_ap_luc', 'thiếu dữ liệu')}/100**, dự báo 7 ngày **{matched.get('du_bao_7_ngay', 'thiếu dữ liệu')}/100**. Câu hỏi của bạn thuộc nhóm **{focus}**.

**Vì sao:** {matched.get('nguyen_nhan_chinh', 'thiếu dữ liệu')}. {color_explanation(matched.get('muc_canh_bao'))}

**Dữ liệu dùng:** {data_type_label(matched.get('loai_du_lieu'))}; cập nhật lần cuối {vn_time(matched.get('cap_nhat_lan_cuoi', ''))}; {missing_data_text(matched)}.

**Độ tin cậy:** {matched.get('do_tin_cay', 'thiếu dữ liệu')}/100, mức {confidence_label(matched.get('do_tin_cay'))}.

**Nên làm:** {matched.get('hanh_dong_de_xuat', 'thiếu dữ liệu')} {route_text}

**Hiệu quả kinh tế:** {matched.get('hieu_qua_kinh_te_ky_vong', 'thiếu dữ liệu')}"""


def check_api_status(env: dict[str, str], api_catalog: pd.DataFrame) -> pd.DataFrame:
    rows = []
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    for _, row in api_catalog.iterrows():
        name = row.get("ten_api", "")
        key_name = str(row.get("bien_moi_truong", ""))
        configured = row.get("trang_thai_cau_hinh", "")
        result = "chưa có endpoint kiểm tra nhẹ"
        error = ""
        if "không cần key" in key_name:
            configured = "có"
        elif key_name and key_name != "không cần key":
            configured = "có" if env.get(key_name) or os.getenv(key_name) else "thiếu cấu hình"
        try:
            if name == "Open-Meteo":
                resp = requests.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={"latitude": 21.0285, "longitude": 105.8542, "current": "temperature_2m"},
                    timeout=6,
                )
                result = "thành công" if resp.ok else f"lỗi HTTP {resp.status_code}"
            elif name == "Positionstack" and configured == "có":
                resp = requests.get(
                    "http://api.positionstack.com/v1/forward",
                    params={"access_key": env.get("POSITIONSTACK_API_KEY"), "query": "Ha Long", "limit": 1},
                    timeout=6,
                )
                result = "thành công" if resp.ok else f"lỗi HTTP {resp.status_code}"
            elif name == "OpenRouteService" and configured == "có":
                resp = requests.get(
                    "https://api.openrouteservice.org/geocode/search",
                    params={"api_key": env.get("OPENROUTESERVICE_API_KEY"), "text": "Da Nang", "size": 1},
                    timeout=6,
                )
                result = "thành công" if resp.ok else f"lỗi HTTP {resp.status_code}"
            elif name == "Gemini 2.5 Flash" and configured == "có":
                model = env.get("GEMINI_MODEL", "gemini-2.5-flash")
                resp = requests.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}",
                    params={"key": env.get("GEMINI_API_KEY")},
                    timeout=6,
                )
                result = "thành công" if resp.ok else f"lỗi HTTP {resp.status_code}"
            elif "RapidAPI" in name and configured == "có":
                host = row.get("host_hoac_model", "") or env.get("RAPIDAPI_SERP_HOST", "")
                resp = requests.get(
                    f"https://{host}",
                    headers={"X-RapidAPI-Key": env.get("RAPIDAPI_KEY", ""), "X-RapidAPI-Host": host},
                    timeout=6,
                )
                result = "đã gọi host; cần endpoint cụ thể" if resp.status_code in {200, 400, 401, 403, 404} else f"lỗi HTTP {resp.status_code}"
            elif name == "Google Sheets":
                result = "đã cấu hình ID" if configured == "có" else "chưa cấu hình; dùng CSV/Excel"
        except Exception as exc:
            result = "thất bại"
            error = str(exc)
        rows.append(
            {
                "Tên nguồn": name,
                "Vai trò": row.get("vai_tro", ""),
                "Biến môi trường": key_name,
                "Trạng thái cấu hình": configured,
                "Kết quả kiểm tra": result,
                "Lần kiểm tra cuối": now,
                "Lỗi nếu có": error,
                "Ảnh hưởng nếu thiếu": row.get("ghi_chu", ""),
                "Nguồn thay thế": row.get("nguon_thay_the", "OSM/Open-Meteo/file current nếu có"),
            }
        )
    return pd.DataFrame(rows)


def check_api_status(env: dict[str, str], api_catalog: pd.DataFrame | None = None, live: bool = False) -> pd.DataFrame:
    """Build API status from the freshly loaded root .env, not from stale metadata."""
    config_source = ".env" if ENV_FILE.exists() and ENV_FILE.is_file() else "chưa tìm thấy .env"
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    api_defs = [
        ("Positionstack", "Geocode địa chỉ, POI, khách sạn thành tọa độ", "POSITIONSTACK_API_KEY", "https://api.positionstack.com", "", "Thiếu nguồn này thì SEA dùng tọa độ seed/current, độ phủ geocode giảm.", "Danh sách điểm đến mở rộng, OSM/Overpass"),
        ("OpenRouteService", "Routing, travel time và tuyến điều phối", "OPENROUTESERVICE_API_KEY", "https://api.openrouteservice.org", "", "Thiếu nguồn này thì SEA dùng OSRM hoặc tuyến proxy đã có.", "OSRM, destination network edges"),
        ("RapidAPI Google SERP", "Tìm tin tức, báo cáo và tín hiệu thị trường", "RAPIDAPI_KEY", env.get("RAPIDAPI_SERP_HOST") or "google-serp-search-api.p.rapidapi.com", "RAPIDAPI_SERP_HOST", "Thiếu nguồn này thì tin tức dùng snapshot/local signal, độ mới giảm.", "news_events hiện có, nguồn chính thống raw đã lưu"),
        ("RapidAPI Google Maps Extractor", "Business info, rating, review nếu endpoint hỗ trợ", "RAPIDAPI_KEY", env.get("RAPIDAPI_GOOGLE_MAPS_HOST") or "google-maps-extractor2.p.rapidapi.com", "RAPIDAPI_GOOGLE_MAPS_HOST", "Thiếu nguồn này thì SEA dùng OSM/POI current và dữ liệu công khai đã có.", "OSM/Overpass, Booking/Traveloka snapshot"),
        ("RapidAPI Google Places", "Mở rộng POI/điểm đến nếu có host hợp lệ", "RAPIDAPI_KEY", env.get("RAPIDAPI_GOOGLE_PLACES_HOST") or "", "RAPIDAPI_GOOGLE_PLACES_HOST", "Thiếu host/key thì SEA vẫn dùng seed list và OSM để không chỉ có 24 điểm.", "danh_sach_diem_den_mo_rong, OSM/Overpass"),
        ("Open-Meteo", "Thời tiết hiện tại, dự báo và lịch sử thời tiết", "", "https://api.open-meteo.com", "", "Nguồn công khai không cần key; nếu lỗi mạng thì dùng bản current ổn định gần nhất.", "weather_features current"),
        ("OSM/Overpass", "POI, bãi biển, khách sạn, nhà hàng, bãi đỗ", "", "https://overpass-api.de", "", "Nguồn mở không cần key; nếu lỗi mạng thì dùng POI đã lưu trong current.", "local_spending_poi current"),
        ("Google Sheets", "Đồng bộ các bảng summary cho người xem nhanh", "GOOGLE_SHEETS_ID", "https://docs.google.com/spreadsheets", "", "Thiếu Sheet ID thì SEA vẫn chạy, tải CSV/Excel từ Kho dữ liệu.", "exports/csv và exports/excel"),
        ("Gemini 2.5 Flash", "Trợ lý SEA trả lời theo knowledge base", "GEMINI_API_KEY", env.get("GEMINI_MODEL") or "gemini-2.5-flash", "", "Thiếu Gemini key thì fallback sang Ollama, sau đó rule-based.", "Ollama hoặc rule-based fallback"),
    ]
    rows = []
    for name, role, key_name, host, host_key, impact, fallback in api_defs:
        has_key = True if not key_name else bool(os.getenv(key_name, "").strip())
        host_ok = True if not host_key else bool(os.getenv(host_key, "").strip() or str(host).strip())
        configured = "Đã cấu hình" if has_key and host_ok else "Thiếu cấu hình"
        result = "Chưa kiểm tra live trong phiên này" if configured == "Đã cấu hình" else "Bỏ qua kiểm tra live vì thiếu cấu hình"
        error = ""
        if live and configured == "Đã cấu hình":
            try:
                if name == "Open-Meteo":
                    resp = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": 21.0285, "longitude": 105.8542, "current": "temperature_2m"}, timeout=6)
                    result = "Thành công" if resp.ok else f"Lỗi HTTP {resp.status_code}"
                elif name == "Positionstack":
                    resp = requests.get("http://api.positionstack.com/v1/forward", params={"access_key": os.getenv("POSITIONSTACK_API_KEY", ""), "query": "Ha Long", "limit": 1}, timeout=6)
                    result = "Thành công" if resp.ok else f"Lỗi HTTP {resp.status_code}"
                elif name == "OpenRouteService":
                    resp = requests.get("https://api.openrouteservice.org/geocode/search", params={"api_key": os.getenv("OPENROUTESERVICE_API_KEY", ""), "text": "Da Nang", "size": 1}, timeout=6)
                    result = "Thành công" if resp.ok else f"Lỗi HTTP {resp.status_code}"
                elif name == "Gemini 2.5 Flash":
                    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
                    resp = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models/{model}", params={"key": os.getenv("GEMINI_API_KEY", "")}, timeout=6)
                    result = "Thành công" if resp.ok else f"Lỗi HTTP {resp.status_code}"
                elif "RapidAPI" in name and host:
                    resp = requests.get(f"https://{host}", headers={"X-RapidAPI-Key": os.getenv("RAPIDAPI_KEY", ""), "X-RapidAPI-Host": str(host)}, timeout=6)
                    result = "Đã gọi host; cần endpoint cụ thể" if resp.status_code in {200, 400, 401, 403, 404} else f"Lỗi HTTP {resp.status_code}"
                elif name == "Google Sheets":
                    result = "Đã cấu hình ID; đồng bộ summary sẽ chạy trong pipeline"
                else:
                    result = "Nguồn không cần key; dùng dữ liệu current nếu không kiểm tra live"
            except Exception as exc:
                result = "Thất bại"
                error = str(exc)
        rows.append({
            "Tên nguồn": name,
            "Vai trò": role,
            "Biến môi trường": key_name or "Không cần key",
            "Host hoặc model": host or "Chưa cấu hình host",
            "Trạng thái cấu hình": configured,
            "Kết quả kiểm tra": result,
            "Lần kiểm tra cuối": now,
            "Đã đọc cấu hình từ": config_source,
            "Lỗi nếu có": error,
            "Ảnh hưởng nếu thiếu": impact,
            "Nguồn thay thế": fallback,
        })
    return pd.DataFrame(rows)


def build_rule_context(question: str, alerts: pd.DataFrame, routes: pd.DataFrame, freshness: pd.DataFrame, source_monitor: pd.DataFrame, api_catalog: pd.DataFrame) -> str:
    return answer_question(question, alerts, routes, freshness, source_monitor, api_catalog)


def ask_sea_assistant(question: str, env: dict[str, str], alerts: pd.DataFrame, routes: pd.DataFrame, freshness: pd.DataFrame, source_monitor: pd.DataFrame, api_catalog: pd.DataFrame) -> str:
    fallback = build_rule_context(question, alerts, routes, freshness, source_monitor, api_catalog)
    kb_path = ROOT / "rag" / "sea_knowledge_base.md"
    kb = kb_path.read_text(encoding="utf-8", errors="ignore")[:18000] if kb_path.exists() else ""
    prompt = (
        "Bạn là Trợ lý SEA. Chỉ trả lời bằng tiếng Việt, dựa trên dữ liệu được cung cấp. "
        "Nếu thiếu dữ liệu, nói rõ: SEA chưa đủ dữ liệu để kết luận chắc chắn. "
        "Luôn trả lời theo format: Tình hình, Vì sao, Dữ liệu dùng, Độ tin cậy, Nên làm, Hiệu quả kinh tế.\n\n"
        f"Knowledge base:\n{kb}\n\n"
        f"Câu hỏi: {question}\n\n"
        f"Fallback dữ liệu đã tính:\n{fallback}"
    )
    if (env.get("AI_PROVIDER") or os.getenv("AI_PROVIDER", "gemini")).lower() == "gemini" and (env.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")):
        model = env.get("GEMINI_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
        try:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": env.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=20,
            )
            if resp.ok:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                if text.strip():
                    return text
            fallback = fallback + f"\n\n**Ghi chú AI:** Gemini lỗi HTTP {resp.status_code}; SEA dùng fallback theo luật dữ liệu."
        except Exception as exc:
            fallback = fallback + f"\n\n**Ghi chú AI:** Gemini lỗi: {exc}. SEA dùng fallback theo luật dữ liệu."
    try:
        resp = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={"model": "llama3.1", "prompt": prompt, "stream": False},
            timeout=12,
        )
        if resp.ok and resp.json().get("response"):
            return resp.json()["response"]
        fallback = fallback + "\n\n**Ghi chú AI:** Ollama không trả lời được; SEA dùng fallback theo luật dữ liệu."
    except Exception:
        fallback = fallback + "\n\n**Ghi chú AI:** Ollama không khả dụng; SEA dùng fallback theo luật dữ liệu."
    return fallback


alerts = load_csv(CURRENT / "national_destination_alerts.csv")
ranking_vn = load_csv(CURRENT / "xep_hang_canh_bao_toan_quoc.csv")
expanded_destinations = load_csv(CURRENT / "danh_sach_diem_den_mo_rong.csv")
forecast = load_csv(CURRENT / "forecast_demand_scores.csv")
weather_current = load_csv(CURRENT / "thoi_tiet_hien_tai.csv")
weather_7d = load_csv(CURRENT / "du_bao_thoi_tiet_7_ngay.csv")
confidence = load_csv(CURRENT / "kpi_confidence_scores.csv")
proxy_vi = load_csv(CURRENT / "kiem_dinh_proxy.csv")
actions = load_csv(CURRENT / "economic_action_recommendations.csv")
economic_proof = load_csv(CURRENT / "de_xuat_hieu_qua_kinh_te.csv")
tickets = load_csv(CURRENT / "attraction_ticket_catalog.csv")
spending = load_csv(CURRENT / "local_spending_poi.csv")
ticket_pressure = load_csv(CURRENT / "ticket_pressure_scores.csv")
hotel_price = load_csv(CURRENT / "hotel_price_pressure.csv")
flight_price = load_csv(CURRENT / "flight_price_signal.csv")
news = load_csv(CURRENT / "news_events.csv")
news_risk = load_csv(CURRENT / "news_risk_signals.csv")
routes = load_csv(CURRENT / "redistribution_features.csv")
dataset_audit = load_csv(META / "dataset_audit.csv")
freshness = load_csv(META / "data_freshness_status.csv")
missing = load_csv(META / "missing_dataset_registry.csv")
api_catalog = load_csv(META / "api_source_catalog.csv")
kpi_catalog = load_csv(META / "kpi_methodology.csv")
source_monitor = load_csv(META / "source_monitor_status.csv")
update_queue = load_csv(META / "update_queue.csv")
pipeline_log = load_csv(META / "pipeline_run_log.csv")
source_check_log = load_csv(META / "source_check_log.csv")
env = read_env()

query_page = st.query_params.get("page")
query_destination = st.query_params.get("destination")
if query_page == "profile" and query_destination:
    st.session_state["active_page"] = "Hồ sơ điểm đến"
    st.session_state["selected_destination"] = str(query_destination)

for df, cols in [
    (alerts, ["rank", "diem_ap_luc", "rui_ro_thoi_tiet", "du_bao_24_gio", "du_bao_7_ngay", "du_bao_30_ngay", "co_hoi_kinh_te", "kha_nang_dieu_phoi", "diem_san_sang_ha_tang", "do_tin_cay", "lat", "lng", "diem_uu_tien_dau_tu", "diem_suc_khoe_diem_den", "nhiet_do_hien_tai", "mua_hien_tai", "gio_hien_tai", "do_am_hien_tai"]),
    (forecast, ["forecast_demand_score", "seasonal_baseline_score", "historical_same_period_score", "forecast_lower", "forecast_upper"]),
    (routes, ["redistribution_opportunity_score", "route_time_minutes", "approx_travel_time_minutes"]),
]:
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

if not alerts.empty:
    if "trang_thai_thoi_tiet_ngan" not in alerts.columns:
        def _short_weather(row: pd.Series) -> str:
            rain = to_num(row.get("mua_hien_tai"), None)
            wind = to_num(row.get("gio_hien_tai"), None)
            temp = to_num(row.get("nhiet_do_hien_tai"), None)
            if temp is None and rain is None and wind is None:
                return "thiếu dữ liệu"
            if rain is not None and rain >= 8:
                return "Mưa đáng chú ý"
            if wind is not None and wind >= 35:
                return "Gió mạnh"
            if temp is not None and temp >= 35:
                return "Nắng nóng"
            return "Ổn định"

        alerts["trang_thai_thoi_tiet_ngan"] = alerts.apply(_short_weather, axis=1)
    if "cap_nhat_thoi_tiet_luc" not in alerts.columns:
        alerts["cap_nhat_thoi_tiet_luc"] = alerts.get("cap_nhat_lan_cuoi", "")

if alerts.empty:
    st.error("Chưa có dữ liệu current. Hãy chạy: python scrapers/sea_operating_pipeline.py")
    st.stop()

st.markdown(
    """
    <style>
      .block-container {padding-top: 1rem; padding-bottom: 4rem;}
      [data-testid="stMetric"] {background:#fff;border:1px solid #d8dee4;border-radius:8px;padding:12px;}
      div[data-testid="stSidebar"] {background:#f8fafc;}
      .sea-chat {position:fixed;right:22px;bottom:22px;z-index:9999;}
      .sea-chat summary {list-style:none;width:58px;height:58px;border-radius:50%;background:#0b7285;color:#fff;display:flex;align-items:center;justify-content:center;font-size:24px;box-shadow:0 8px 24px rgba(0,0,0,.22);cursor:pointer;}
      .sea-chat-panel {width:340px;max-width:88vw;background:#fff;border:1px solid #d8dee4;border-radius:10px;padding:14px;margin-top:10px;box-shadow:0 12px 30px rgba(0,0,0,.18);}
    </style>
    <div class="sea-chat">
      <details>
        <summary>Chat</summary>
        <div class="sea-chat-panel">
          <b>Trợ lý SEA</b><br>
          Xin chào, tôi là trợ lý SEA. Bạn có thể hỏi tôi về cảnh báo du lịch, thời tiết, dữ liệu cập nhật, dự báo, điều phối khách và hiệu quả kinh tế.<br><br>
          <small>Gợi ý: Vì sao Đà Nẵng màu cam? Điểm thiếu dữ liệu nghĩa là gì? Google Sheets đã đồng bộ chưa? API nào đang thiếu?</small>
        </div>
      </details>
    </div>
    """,
    unsafe_allow_html=True,
)

st.title("SEA")
st.caption("Hệ thống điều hành kinh tế du lịch ven biển Việt Nam. Múi giờ: Asia/Ho_Chi_Minh.")
status_caption("national_destination_alerts", freshness)

if len(expanded_destinations) < 50 or len(alerts) < 50:
    st.warning("Danh sách điểm đến chưa đủ toàn quốc, cần chạy build_destination_registry.")

if not pipeline_log.empty:
    last_auto = vn_time(pipeline_log.iloc[-1].get("run_time", pipeline_log.iloc[-1].get("thoi_gian_chay", "")))
    st.caption(f"Lần cập nhật tự động gần nhất: {last_auto}")

menu = [
    "Tổng quan",
    "Bản đồ",
    "Ranking",
    "Hồ sơ điểm đến",
    "Dự báo",
    "Điều phối",
    "Vé & chi tiêu",
    "Hiệu quả kinh tế",
    "Dữ liệu",
    "Cập nhật",
    "API & Sheet",
    "Giải thích",
    "Trợ lý SEA",
]

with st.sidebar:
    st.subheader("Điều hướng")
    active_page = st.session_state.get("active_page", "Tổng quan")
    if active_page not in menu:
        active_page = "Tổng quan"
    page = st.radio("Chọn trang", menu, index=menu.index(active_page), label_visibility="collapsed")
    st.session_state["active_page"] = page
    st.divider()
    st.subheader("Bộ lọc chung")
    alert_choices = ["Tất cả", "đỏ", "cam", "vàng", "xanh", "Thiếu dữ liệu"]
    selected_alert = st.multiselect("Mức cảnh báo", alert_choices[1:], default=[])
    type_choices = ["Tất cả", "biển", "đô thị", "di sản", "đảo", "núi", "Mekong"]
    selected_type = st.selectbox("Loại điểm", type_choices)
    data_choices = ["Tất cả", "dữ liệu thật", "near-realtime", "proxy", "thiếu dữ liệu"]
    selected_data = st.selectbox("Loại dữ liệu", data_choices)
    only_action = st.checkbox("Chỉ hiện điểm cần xử lý", value=False)

view = alerts.copy()
if selected_alert:
    selected_alert_values = ["xám" if item == "Thiếu dữ liệu" else item for item in selected_alert]
    view = view[view["muc_canh_bao"].astype(str).isin(selected_alert_values)]
if selected_type != "Tất cả":
    type_token = {
        "biển": "coastal|bien|bai bien",
        "đô thị": "urban|do thi",
        "di sản": "heritage|di san",
        "đảo": "island|dao",
        "núi": "mountain|nui",
        "Mekong": "mekong",
    }[selected_type]
    view = view[view.get("loai_hinh_du_lich", "").map(strip_accents).str.contains(type_token, case=False, na=False)]
if selected_data != "Tất cả":
    token = "missing" if selected_data == "thiếu dữ liệu" else selected_data.replace("dữ liệu thật", "real")
    view = view[view.get("loai_du_lieu", "").astype(str).str.contains(token, case=False, na=False)]
if only_action:
    view = view[view["muc_canh_bao"].astype(str).isin(["đỏ", "cam", "xám"])]


if page == "Tổng quan":
    explain(
        "Cách đọc màu cảnh báo",
        """
        - Xanh: điểm còn dư địa, áp lực thấp, có thể kích cầu.
        - Vàng: cần theo dõi, có dấu hiệu tăng nhu cầu.
        - Cam: áp lực cao, cần chuẩn bị điều phối.
        - Đỏ: nguy cơ quá tải, cần hành động ngay.
        - Tím nhạt/xanh xám: thiếu dữ liệu, chưa đủ căn cứ đánh giá.
        """,
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        card("Điểm đến", f"{len(alerts):,}", "Ranking toàn quốc đang dùng.", "SEA không chỉ dùng 24 điểm mẫu; bảng mở rộng nằm tại danh_sach_diem_den_mo_rong.csv.")
    with c2:
        need = alerts["muc_canh_bao"].astype(str).isin(["đỏ", "cam"]).sum()
        card("Điểm cần xử lý", f"{need:,}", "Đỏ/cam cần ưu tiên vận hành.", "Các điểm này nên xem hành động, điều phối và hạ tầng trước.")
    with c3:
        coastal = alerts.get("coastal_zone", pd.Series(dtype=str)).astype(str).str.lower().eq("yes").sum()
        card("Điểm ven biển", f"{coastal:,}", "Trọng tâm kinh tế du lịch biển.", "Ven biển là nhóm ưu tiên trong SEA.")
    with c4:
        avg = numeric_series(alerts, "do_tin_cay").mean()
        card("Độ tin cậy TB", f"{avg:.1f}/100", confidence_label(avg), "Tính từ nguồn dữ liệu, độ mới, độ phủ, độ đầy đủ và kiểm định proxy.")
    with c5:
        card("Forecast", f"{len(forecast):,}", "Đã tính trước cho dashboard.", "AI chỉ giải thích forecast, không tự tạo số ngoài dữ liệu.")

    left, right = st.columns(2)
    with left:
        count = alerts["muc_canh_bao"].value_counts().reset_index()
        count.columns = ["Mức cảnh báo", "Số điểm"]
        count["Mức cảnh báo"] = count["Mức cảnh báo"].map(alert_label)
        st.plotly_chart(apply_chart_theme(px.pie(count, names="Mức cảnh báo", values="Số điểm", hole=0.55, color="Mức cảnh báo", color_discrete_map=alert_color_map(), title="Tỷ lệ điểm đến theo màu cảnh báo")), width="stretch")
    with right:
        top = alerts.sort_values("diem_ap_luc", ascending=False).head(10)
        st.plotly_chart(apply_chart_theme(px.bar(top, x="ten_diem_den", y="diem_ap_luc", color="muc_canh_bao", color_discrete_map=alert_color_map(), title="Top 10 điểm áp lực cao nhất", labels={"ten_diem_den": "Điểm đến", "diem_ap_luc": "Điểm áp lực", "muc_canh_bao": "Mức cảnh báo"})), width="stretch")
    lower = alerts.sort_values("diem_ap_luc", ascending=True).head(10)
    st.plotly_chart(apply_chart_theme(px.bar(lower, x="ten_diem_den", y="diem_ap_luc", color="muc_canh_bao", color_discrete_map=alert_color_map(), title="Top 10 điểm còn dư địa", labels={"ten_diem_den": "Điểm đến", "diem_ap_luc": "Điểm áp lực"})), width="stretch")
    display_df(vietnamese_alerts(view).head(80), height=420)

elif page == "Bản đồ":
    st.subheader("Bản đồ điều hành SEA")
    explain(
        "Bản đồ dùng để ra quyết định gì?",
        "Marker tròn thể hiện điểm đến theo màu cảnh báo. Hover để xem tóm tắt; bấm marker để mở panel hồ sơ bên phải với thời tiết, forecast, dữ liệu thiếu, độ tin cậy, hành động và hiệu quả kinh tế. Layer có thể bật/tắt để xem điểm đến, POI, tuyến điều phối và heatmap áp lực.",
    )
    components.html(build_map_html(view if not view.empty else alerts, pd.concat([spending, tickets], ignore_index=True, sort=False), routes), height=800)

elif page == "Ranking":
    st.subheader("Ranking cảnh báo toàn quốc")
    status_caption("national_destination_alerts", freshness)
    explain("Ranking đọc như thế nào?", "Bảng xếp hạng theo điểm áp lực, thời tiết, hạ tầng, cơ hội kinh tế và khả năng điều phối. Màu tím nhạt/xanh xám là Thiếu dữ liệu, không phải an toàn.")
    st.info("Điểm thiếu dữ liệu vì chưa có một hoặc nhiều nguồn: tọa độ, thời tiết, POI, khách sạn, tuyến di chuyển, vé/khu vui chơi, tin tức hoặc cập nhật gần đây.")
    display_alert_ranking(view, height=520)
    st.markdown("**Mở hồ sơ điểm đến từ ranking**")
    st.caption("Bấm `Xem hồ sơ` để mở dashboard riêng của điểm đến và tự lọc KPI, thời tiết, forecast, dịch vụ, điều phối, hành động kinh tế và độ tin cậy.")
    ranking_rows = view.sort_values("diem_ap_luc", ascending=False).reset_index(drop=True)
    for idx, row in ranking_rows.iterrows():
        cols = st.columns([0.7, 2.0, 1.5, 1.4, 1.2, 1.8])
        cols[0].write(f"#{idx + 1}")
        cols[1].write(f"**{row.get('ten_diem_den', '')}**")
        cols[2].write(row.get("tinh_thanh", ""))
        cols[3].write(alert_label(row.get("muc_canh_bao", "xám")))
        cols[4].write(f"{row.get('diem_ap_luc', 'thiếu dữ liệu')}/100")
        if cols[5].button("Xem hồ sơ", key=f"profile_from_ranking_{row.get('destination_id', idx)}"):
            open_destination_profile(row.get("ten_diem_den", ""))
    st.download_button("Tải ranking CSV", vietnamese_alerts(alerts).to_csv(index=False).encode("utf-8-sig"), "xep_hang_canh_bao_toan_quoc.csv")

elif page == "Hồ sơ điểm đến":
    default_names = ["Da Nang", "Ha Long", "Nha Trang", "Phu Quoc", "Hoi An", "Quy Nhon", "Vung Tau", "Mui Ne", "Cat Ba", "Sam Son", "Cua Lo", "Con Dao", "Ly Son"]
    names = alerts["ten_diem_den"].dropna().astype(str).tolist()
    selected_from_state = st.session_state.get("selected_destination")
    if selected_from_state in names:
        default_index = names.index(selected_from_state)
    else:
        default_index = next((names.index(n) for n in default_names if n in names), 0)
    top_cols = st.columns([1, 5])
    if top_cols[0].button("Quay lại Ranking"):
        st.session_state["active_page"] = "Ranking"
        st.rerun()
    selected = top_cols[1].selectbox("Chọn điểm đến", names, index=default_index)
    st.session_state["selected_destination"] = selected
    destination_profile(selected, alerts, forecast, routes, economic_proof if not economic_proof.empty else actions, spending, tickets)

elif page == "Dự báo":
    st.subheader("Dự báo du lịch")
    explain(
        "Forecast đọc như thế nào?",
        "Trục X là thời gian, trục Y là điểm áp lực dự báo 0-100. Đường dự báo SEA là kết quả pipeline tính trước. Trung bình mùa vụ và lịch sử cùng kỳ chỉ hiển thị nếu có trong dữ liệu; nếu thiếu lịch sử 3-5 năm, SEA ghi rõ đây là proxy forecast và giảm độ tin cậy.",
    )
    st.warning("Nếu chưa đủ lịch sử 3-5 năm, forecast hiện là proxy forecast dựa trên thời tiết, cuối tuần, POI, khách sạn và tin tức; không phải dữ liệu đo trực tiếp.")
    selected = st.selectbox("Chọn điểm đến để xem forecast", alerts["ten_diem_den"].tolist())
    fdf = forecast_for_destination(forecast, selected)
    st.plotly_chart(forecast_line_chart(fdf, f"Dự báo SEA cho {selected}"), width="stretch")
    row = get_row(alerts, selected)
    cal = calendar_heatmap(row)
    if not cal.empty:
        st.caption("Heatmap dự báo: màu nhạt = thấp, màu đậm = cao; thấp → vừa → cao → rất cao. Hover để xem điểm đến/ngày/điểm rủi ro/lý do.")
        st.plotly_chart(apply_chart_theme(px.density_heatmap(cal, x="Ngày", y="Tuần", z="Điểm dự báo", hover_data=["Giải thích"], color_continuous_scale=PRESSURE_CONTINUOUS_SCALE, title="Calendar heatmap dự báo trong 30 ngày")), width="stretch")
    rising = alerts.sort_values("du_bao_7_ngay", ascending=False).head(10)
    opportunity = alerts.sort_values("co_hoi_kinh_te", ascending=False).head(10)
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(apply_chart_theme(px.bar(rising, x="ten_diem_den", y="du_bao_7_ngay", color="muc_canh_bao", color_discrete_map=alert_color_map(), title="Top 10 điểm có rủi ro tăng 7 ngày tới")), width="stretch")
    with c2:
        st.plotly_chart(apply_chart_theme(px.bar(opportunity, x="ten_diem_den", y="co_hoi_kinh_te", color="muc_canh_bao", color_discrete_map=alert_color_map(), title="Top 10 điểm có cơ hội kích cầu")), width="stretch")
    st.markdown("**Bản đồ forecast theo màu dự báo 7 ngày**")
    forecast_map = alerts.copy()
    forecast_map["diem_ap_luc"] = forecast_map["du_bao_7_ngay"]
    forecast_map["muc_canh_bao"] = pd.to_numeric(forecast_map["du_bao_7_ngay"], errors="coerce").map(pressure_level)
    components.html(build_map_html(forecast_map, pd.DataFrame(), pd.DataFrame()), height=800)
    display_df(vietnamese_alerts(alerts[["ten_diem_den", "tinh_thanh", "muc_canh_bao", "du_bao_24_gio", "du_bao_7_ngay", "du_bao_30_ngay", "loai_du_lieu", "do_tin_cay", "cap_nhat_lan_cuoi"]].copy()), height=360)

elif page == "Điều phối":
    st.subheader("Luồng khách & điều phối")
    explain("Điều phối đọc như thế nào?", "Bảng trả lời điểm nào đang áp lực, nên chuyển sang đâu, vì sao, đi mất bao lâu và hiệu quả kinh tế là gì. Scatter giúp phân biệt: áp lực cao + hạ tầng thấp là không nên đẩy thêm khách; áp lực thấp + hạ tầng tốt là có thể nhận khách.")
    sorted_routes = routes.sort_values("redistribution_opportunity_score", ascending=False) if not routes.empty and "redistribution_opportunity_score" in routes.columns else routes
    display_df(vietnamese_routes(sorted_routes, alerts), height=360)
    if not routes.empty:
        st.plotly_chart(px.bar(routes.sort_values("redistribution_opportunity_score", ascending=False).head(10), x="alternative_id", y="redistribution_opportunity_score", color="origin_id", title="Top tuyến điều phối có lợi ích cao nhất", labels={"alternative_id": "Điểm nên chuyển sang", "redistribution_opportunity_score": "Điểm điều phối", "origin_id": "Điểm nguồn"}), width="stretch")
        labels = pd.unique(pd.concat([routes["origin_id"], routes["alternative_id"]], ignore_index=True).astype(str)).tolist()
        idx = {name: i for i, name in enumerate(labels)}
        fig = go.Figure(data=[go.Sankey(
            node=dict(label=labels, pad=18, thickness=16),
            link=dict(
                source=[idx[str(v)] for v in routes["origin_id"]],
                target=[idx[str(v)] for v in routes["alternative_id"]],
                value=pd.to_numeric(routes["redistribution_opportunity_score"], errors="coerce").fillna(20),
                hovertemplate="SEA đề xuất chuyển một phần khách từ %{source.label} sang %{target.label} vì điểm nguồn áp lực cao hơn và điểm đích còn dư địa.<extra></extra>",
            ),
        )])
        fig.update_layout(title_text="Dòng điều phối đề xuất: từ điểm áp lực cao sang điểm còn dư địa")
        st.plotly_chart(fig, width="stretch")
    scatter = px.scatter(alerts, x="diem_ap_luc", y="diem_san_sang_ha_tang", size="co_hoi_kinh_te", color="muc_canh_bao", color_discrete_map=alert_color_map(), hover_name="ten_diem_den", title="Áp lực điểm đến vs sẵn sàng hạ tầng", labels={"diem_ap_luc": "Áp lực điểm đến", "diem_san_sang_ha_tang": "Sẵn sàng hạ tầng"})
    scatter.add_annotation(x=85, y=30, text="Áp lực cao + hạ tầng thấp: không nên đẩy thêm khách", showarrow=False)
    scatter.add_annotation(x=25, y=85, text="Áp lực thấp + hạ tầng tốt: có thể nhận khách", showarrow=False)
    st.plotly_chart(apply_chart_theme(scatter), width="stretch")
    components.html(build_map_html(alerts, pd.DataFrame(), routes), height=800)

elif page == "Vé & chi tiêu":
    st.subheader("Vé, giá và chi tiêu địa phương")
    st.info("Dữ liệu giá nếu có là snapshot công khai tại thời điểm cập nhật, không phải realtime. Cần API đối tác để cập nhật tự động theo thời gian thực.")
    display_df(tickets.head(200), height=300)
    display_df(spending.head(200), height=300)
    display_df(ticket_pressure.head(100), height=240)
    display_df(hotel_price.head(100), height=240)
    display_df(flight_price.head(100), height=220)

elif page == "Hiệu quả kinh tế":
    st.subheader("Hiệu quả kinh tế")
    explain("Chứng minh hiệu quả kinh tế", "Mỗi đề xuất theo chuỗi: Vấn đề -> Hành động -> KPI dự kiến thay đổi -> Hiệu quả kinh tế -> Dữ liệu chứng minh -> Độ tin cậy.")
    action_view = economic_proof if not economic_proof.empty else actions
    if not action_view.empty and "muc_uu_tien" in action_view.columns:
        c1, c2 = st.columns(2)
        with c1:
            priority_count = action_view["muc_uu_tien"].value_counts().reset_index()
            priority_count.columns = ["Mức ưu tiên", "Số hành động"]
            st.plotly_chart(px.pie(priority_count, names="Mức ưu tiên", values="Số hành động", hole=0.5, title="Tỷ lệ ưu tiên Cao/Trung bình/Thấp"), width="stretch")
        with c2:
            top_priority = action_view.copy()
            if "diem_uu_tien" in top_priority.columns:
                top_priority["diem_uu_tien"] = pd.to_numeric(top_priority["diem_uu_tien"], errors="coerce")
                st.plotly_chart(px.bar(top_priority.sort_values("diem_uu_tien", ascending=False).head(15), x="diem_den", y="diem_uu_tien", color="muc_uu_tien", title="Ranking hành động tạo hiệu quả kinh tế cao nhất"), width="stretch")
        if {"diem_tac_dong_kinh_te", "diem_kha_thi"}.issubset(action_view.columns):
            bubble_df = action_view.copy()
            bubble_df["diem_tac_dong_kinh_te"] = pd.to_numeric(bubble_df["diem_tac_dong_kinh_te"], errors="coerce")
            bubble_df["diem_kha_thi"] = pd.to_numeric(bubble_df["diem_kha_thi"], errors="coerce")
            bubble_df["diem_uu_tien"] = pd.to_numeric(bubble_df.get("diem_uu_tien"), errors="coerce")
            st.plotly_chart(px.scatter(bubble_df, x="diem_tac_dong_kinh_te", y="diem_kha_thi", size="diem_uu_tien", color="muc_uu_tien", hover_name="diem_den", title="Tác động kinh tế vs khả thi"), width="stretch")
    render_action_cards(action_view.head(60))
    if not alerts.empty:
        st.plotly_chart(apply_chart_theme(px.bar(alerts.sort_values("co_hoi_kinh_te", ascending=False).head(15), x="ten_diem_den", y="co_hoi_kinh_te", color="muc_canh_bao", color_discrete_map=alert_color_map(), title="Lợi ích/cơ hội kinh tế kỳ vọng theo điểm đến")), width="stretch")
        st.plotly_chart(apply_chart_theme(px.scatter(alerts, x="co_hoi_kinh_te", y="diem_ap_luc", size="diem_uu_tien_dau_tu", color="muc_canh_bao", color_discrete_map=alert_color_map(), hover_name="ten_diem_den", title="Cơ hội kinh tế vs rủi ro quá tải")), width="stretch")
        st.plotly_chart(apply_chart_theme(px.scatter(alerts, x="diem_san_sang_ha_tang", y="co_hoi_kinh_te", color="muc_canh_bao", color_discrete_map=alert_color_map(), hover_name="ten_diem_den", title="Hạ tầng vs tiềm năng kinh tế")), width="stretch")

elif page == "Dữ liệu":
    st.subheader("Kho dữ liệu")
    status_caption("dataset_audit", freshness)
    files = sorted(CURRENT.glob("*.csv"))
    chosen = st.selectbox("Bảng dữ liệu mới nhất", [p.name for p in files])
    path = CURRENT / chosen
    preview = load_csv(path).head(50)
    display_df(preview, height=380)
    st.caption("Chỉ xem trước 50 dòng để dashboard không tải nặng.")
    st.download_button("Tải CSV", path.read_bytes(), chosen)
    display_df(dataset_audit.head(200), height=320)

elif page == "Cập nhật":
    st.subheader("Cập nhật dữ liệu")
    latest_count = source_monitor.get("trang_thai", pd.Series(dtype=str)).astype(str).str.contains("mới nhất", case=False, na=False).sum() if not source_monitor.empty else 0
    need_count = source_monitor.get("trang_thai", pd.Series(dtype=str)).astype(str).str.contains("cần|đã cũ", case=False, na=False).sum() if not source_monitor.empty else 0
    waiting_count = source_monitor.get("trang_thai", pd.Series(dtype=str)).astype(str).str.contains("chờ", case=False, na=False).sum() if not source_monitor.empty else 0
    error_count = source_monitor.get("trang_thai", pd.Series(dtype=str)).astype(str).str.contains("lỗi", case=False, na=False).sum() if not source_monitor.empty else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dữ liệu mới nhất", latest_count)
    c2.metric("Cần cập nhật", need_count)
    c3.metric("Có dữ liệu mới chờ xử lý", waiting_count)
    c4.metric("Cập nhật lỗi", error_count)
    last_check = "thiếu dữ liệu"
    last_success = "thiếu dữ liệu"
    if not source_monitor.empty:
        check_col = "lan_kiem_tra_cuoi" if "lan_kiem_tra_cuoi" in source_monitor.columns else "kiem_tra_lan_cuoi"
        success_col = "lan_cap_nhat_thanh_cong_cuoi" if "lan_cap_nhat_thanh_cong_cuoi" in source_monitor.columns else "cap_nhat_thanh_cong_lan_cuoi"
        if check_col in source_monitor.columns:
            last_check = vn_time(source_monitor[check_col].dropna().astype(str).tail(1).iloc[0]) if not source_monitor[check_col].dropna().empty else last_check
        if success_col in source_monitor.columns:
            last_success = vn_time(source_monitor[success_col].dropna().astype(str).tail(1).iloc[0]) if not source_monitor[success_col].dropna().empty else last_success
    m1, m2 = st.columns(2)
    m1.metric("Lần kiểm tra cuối", last_check)
    m2.metric("Lần cập nhật thành công cuối", last_success)
    display_df(source_monitor, height=360)
    display_df(update_queue, height=240)
    st.markdown("**Bấm cập nhật sẽ làm gì?**")
    st.write("1. Kiểm tra nguồn mới  2. Tải dữ liệu mới  3. Lưu bản cũ vào archive  4. Ghi bản mới vào current  5. Tính lại KPI  6. Tính lại forecast  7. Cập nhật ranking  8. Cập nhật AI  9. Đồng bộ Google Sheets summary nếu đã cấu hình.")
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("Kiểm tra nguồn mới"):
            st.info("Đã đọc trạng thái nguồn trong metadata. Để kiểm tra online cần cấu hình API và chạy pipeline/source monitor.")
    with b2:
        if st.button("Cập nhật ngay"):
            st.warning("Quá trình cập nhật có thể mất vài phút. SEA sẽ không ghi đè dữ liệu tốt nếu nguồn mới lỗi.")
            steps = [
                "Kiểm tra nguồn dữ liệu",
                "Tải dữ liệu mới",
                "Lưu bản cũ vào archive",
                "Ghi bản mới vào current",
                "Tính lại KPI",
                "Tính lại dự báo",
                "Tính lại ranking",
                "Cập nhật hồ sơ điểm đến",
                "Cập nhật trợ lý SEA",
                "Đồng bộ Google Sheets summary nếu có",
            ]
            progress = st.progress(0)
            try:
                for i, step in enumerate(steps, start=1):
                    st.write(f"{i}. {step}")
                    progress.progress(i / len(steps))
                result = subprocess.run([sys.executable, str(ROOT / "scrapers" / "sea_operating_pipeline.py")], cwd=str(ROOT), capture_output=True, text=True, timeout=900)
                if result.returncode == 0:
                    st.success(f"Cập nhật thành công lúc {datetime.now().strftime('%d/%m/%Y %H:%M')} theo giờ Việt Nam.")
                    load_csv.clear()
                    st.rerun()
                else:
                    st.error("Cập nhật lỗi. SEA đang giữ bản dữ liệu ổn định gần nhất.")
                    st.code(result.stderr[-3000:] or result.stdout[-3000:])
                    try:
                        log_path = META / "nhat_ky_pipeline.csv"
                        fail = pd.DataFrame([{
                            "thoi_gian_chay": datetime.now().strftime("%d/%m/%Y %H:%M"),
                            "mui_gio": "Việt Nam",
                            "buoc_pipeline": "dashboard_cap_nhat_ngay",
                            "trang_thai": "error",
                            "ghi_chu": "Pipeline trả mã lỗi; giữ bản current ổn định gần nhất.",
                            "error": (result.stderr or result.stdout)[-1000:],
                        }])
                        old = load_csv(log_path)
                        pd.concat([old, fail], ignore_index=True).to_csv(log_path, index=False, encoding="utf-8-sig")
                    except Exception:
                        pass
            except Exception as exc:
                st.error("Cập nhật lỗi. SEA đang giữ bản dữ liệu ổn định gần nhất.")
                st.code(str(exc))
                try:
                    log_path = META / "nhat_ky_pipeline.csv"
                    fail = pd.DataFrame([{
                        "thoi_gian_chay": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "mui_gio": "Việt Nam",
                        "buoc_pipeline": "dashboard_cap_nhat_ngay",
                        "trang_thai": "error",
                        "ghi_chu": "Cập nhật ngay trên dashboard lỗi; giữ bản current ổn định gần nhất.",
                        "error": str(exc)[:1000],
                    }])
                    old = load_csv(log_path)
                    pd.concat([old, fail], ignore_index=True).to_csv(log_path, index=False, encoding="utf-8-sig")
                except Exception:
                    pass
    with b3:
        if st.button("Xem nhật ký cập nhật"):
            display_df(pipeline_log.tail(80), height=300)
    display_df(source_check_log.tail(80), height=260)

elif page == "API & Sheet":
    st.subheader("Trạng thái API")
    api_view = check_api_status(env, live=False)
    st.caption(f"Đã đọc cấu hình từ: {env.get('CONFIG_SOURCE', '.env')}")
    display_df(api_view, height=360)
    if st.button("Kiểm tra lại API"):
        st.info("SEA đang kiểm tra cấu hình và gọi endpoint nhẹ nếu nguồn có endpoint phù hợp. Nếu mạng bị hạn chế, dashboard sẽ ghi rõ lỗi và dùng nguồn thay thế.")
        env = read_env()
        checked = check_api_status(env, live=True)
        checked.to_csv(META / "api_source_catalog.csv", index=False, encoding="utf-8-sig")
        display_df(checked, height=420)

    st.subheader("Đồng bộ Google Sheets")
    sheet_id = env.get("GOOGLE_SHEETS_ID", os.getenv("GOOGLE_SHEETS_ID", ""))
    credentials_ok, credentials_note = sheet_credentials_status()
    sync_tables = [name for name, _ in SHEET_SUMMARY_TABLES]
    last_sheet_sync = "thiếu dữ liệu"
    if not freshness.empty and "google_sheets_summary_da_sync" in freshness.columns:
        last_sheet_sync = str(freshness["google_sheets_summary_da_sync"].dropna().astype(str).tail(1).iloc[0]) if not freshness["google_sheets_summary_da_sync"].dropna().empty else last_sheet_sync
    sync_status_path = META / "google_sheets_sync_status.csv"
    existing_sync_status = load_csv(sync_status_path)
    if not existing_sync_status.empty and "Đồng bộ lúc" in existing_sync_status.columns:
        last_sheet_sync = str(existing_sync_status["Đồng bộ lúc"].dropna().astype(str).tail(1).iloc[0])
    s1, s2, s3 = st.columns(3)
    s1.metric("GOOGLE_SHEETS_ID", "Đã có" if sheet_id else "Chưa có")
    s2.metric("Credentials", "Đã có" if credentials_ok else "Chưa có")
    s3.metric("Lần đồng bộ cuối", last_sheet_sync)
    if sheet_id:
        st.success("Đã cấu hình GOOGLE_SHEETS_ID.")
        st.markdown(f"[Mở Google Sheets](https://docs.google.com/spreadsheets/d/{sheet_id})")
    else:
        st.warning("Chưa cấu hình Google Sheets. SEA vẫn chạy bình thường; có thể tải CSV/Excel từ Kho dữ liệu.")
    if credentials_ok:
        st.success(credentials_note)
    else:
        st.error(credentials_note)
        st.caption("Cần tạo Google Service Account, chia sẻ Sheet cho email service account quyền Editor, rồi cấu hình một trong hai biến trên trong `.env` hoặc GitHub Actions Secrets.")
    st.write("Chỉ sync summary, không sync raw data.")
    if existing_sync_status.empty:
        sheet_status = pd.DataFrame(
            {
                "Bảng summary": sync_tables,
                "Trạng thái": ["Chờ sync nếu đủ Sheet ID + credentials + gspread" if sheet_id else "Chưa sync vì thiếu GOOGLE_SHEETS_ID"] * len(sync_tables),
                "Lỗi": ["" if credentials_ok else credentials_note] * len(sync_tables),
            }
        )
    else:
        sheet_status = existing_sync_status
    display_df(sheet_status, height=260)
    if st.button("Đồng bộ Sheet summary"):
        if sheet_id:
            with st.spinner("Đang đồng bộ Google Sheets summary..."):
                result = sync_google_sheets_summary(sheet_id)
            if not result.empty and result["Trạng thái"].astype(str).eq("Đã sync").all():
                st.success(f"Đồng bộ Google Sheets thành công lúc {datetime.now().astimezone().strftime('%d/%m/%Y %H:%M')}.")
            else:
                st.error("Đồng bộ Google Sheets chưa thành công. Xem cột Lỗi bên dưới.")
            display_df(result, height=260)
        else:
            st.error("Chưa cấu hình Google Sheets. Không thể đồng bộ.")

elif page == "Giải thích":
    st.subheader("Giải thích SEA")
    explain("POI là gì?", "POI là điểm quan tâm du lịch, ví dụ bãi biển, điểm tham quan, khách sạn, nhà hàng, chợ đêm, khu vui chơi, bãi đỗ xe. SEA dùng POI để hiểu khu vực đó có nhiều dịch vụ/điểm hút khách hay không.")
    explain("Proxy là gì?", "Proxy là chỉ số ước lượng có kiểm soát khi chưa có dữ liệu đo trực tiếp. Ví dụ chưa có số người realtime ở bãi biển, SEA dùng thời tiết, cuối tuần, mật độ khách sạn, POI, tin tức và giá để ước lượng nguy cơ đông.")
    explain("Near-realtime là gì?", "Near-realtime là dữ liệu gần hiện tại từ API hoặc nguồn online như thời tiết, route, review, tin tức. Đây không phải dữ liệu đo trực tiếp liên tục như camera hoặc cảm biến.")
    explain("Dự báo 7 ngày là gì?", "Dự báo 7 ngày là mức áp lực du lịch dự kiến trong 7 ngày tới, dựa trên thời tiết, cuối tuần/ngày lễ, tin tức/sự kiện, POI, khách sạn và dữ liệu lịch sử nếu có.")
    explain("Dự báo 30 ngày là gì?", "Dự báo 30 ngày dùng để nhìn xu hướng ngắn hạn trong tháng tới, phục vụ kế hoạch nhân sự, shuttle, truyền thông, combo và chuẩn bị mùa cao điểm.")
    explain("Áp lực giá và lưu trú", "Chỉ số này cho biết dấu hiệu khu vực có thể đang căng về lưu trú/giá. Nếu chưa có occupancy thật, SEA dùng giá phòng công khai, mật độ khách sạn, review và độ phổ biến làm proxy. Chỉ số này không phải occupancy realtime.")
    explain("Điểm ưu tiên đầu tư", "Chỉ số giúp chọn nơi nên đầu tư hạ tầng trước. Điểm cao khi nơi đó có tiềm năng du lịch và lợi ích kinh tế tốt, nhưng còn thiếu hạ tầng cần nâng cấp.")
    explain("Điểm sức khỏe điểm đến", "Chỉ số tổng hợp tình trạng điểm đến: áp lực, thời tiết, hạ tầng, dữ liệu, cơ hội kinh tế và rủi ro. Điểm sức khỏe thấp nghĩa là cần can thiệp hoặc bổ sung dữ liệu.")
    explain("Điểm còn dư địa", "Điểm còn dư địa là nơi áp lực chưa cao, hạ tầng tương đối ổn hoặc có thể nhận thêm khách. Đây là ứng viên để điều phối khách từ điểm quá tải sang.")
    explain("Điểm cần cập nhật dữ liệu", "Là điểm có dữ liệu đã cũ, thiếu nguồn quan trọng hoặc chưa được kiểm tra gần đây. SEA không nên ra quyết định mạnh với điểm này cho đến khi cập nhật.")
    display_df(kpi_catalog, height=360)

elif page == "Trợ lý SEA":
    st.subheader("Trợ lý SEA")
    st.info("Xin chào, tôi là trợ lý SEA. Bạn có thể hỏi tôi về cảnh báo du lịch, thời tiết, dữ liệu cập nhật, dự báo, điều phối khách và hiệu quả kinh tế.")
    suggestions = [
        "Vì sao Đà Nẵng màu cam?",
        "Điểm thiếu dữ liệu nghĩa là gì?",
        "Dự báo 7 ngày là gì?",
        "Dữ liệu này cập nhật lúc nào?",
        "Proxy là gì?",
        "SEA đề xuất điều phối khách đi đâu?",
        "Google Sheets đã đồng bộ chưa?",
        "API nào đang thiếu?",
        "Hành động nào tạo hiệu quả kinh tế cao nhất?",
    ]
    picked = st.selectbox("Câu hỏi gợi ý", [""] + suggestions)
    question = st.text_input("Nhập câu hỏi", value=picked, placeholder="Ví dụ: phân tích Hạ Long")
    if question:
        st.markdown(ask_sea_assistant(question, env, alerts, routes, freshness, source_monitor, api_catalog))
