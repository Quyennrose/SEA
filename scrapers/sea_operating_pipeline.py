from __future__ import annotations

import csv
import json
import math
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - pipeline still works without python-dotenv
    load_dotenv = None

from build_destination_registry import build_destination_registry


ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "datasets"
GOLD = DATASETS / "gold"
CURRENT = GOLD / "current"
ARCHIVE = GOLD / "archive"
CURRENT_CSV = GOLD / "current_csv"
CURRENT_PARQUET = GOLD / "current_parquet"
EXPORTS = ROOT / "exports"
EXPORTS_CSV = EXPORTS / "csv"
EXPORTS_EXCEL = EXPORTS / "excel"
EXPORTS_REPORTS = EXPORTS / "reports"
META = ROOT / "data" / "metadata"
LOGS = ROOT / "data" / "logs"
RAG = ROOT / "rag"
ENV_FILE = ROOT / ".env"
LAST_ARCHIVE_DIR: Path | None = None

SUPPORTED_ENV_KEYS = [
    "POSITIONSTACK_API_KEY",
    "OPENROUTESERVICE_API_KEY",
    "RAPIDAPI_KEY",
    "RAPIDAPI_SERP_HOST",
    "RAPIDAPI_GOOGLE_MAPS_HOST",
    "RAPIDAPI_GOOGLE_PLACES_HOST",
    "GOOGLE_SHEETS_ID",
    "SYNC_FULL_DATA_TO_SHEETS",
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


def now_vn() -> str:
    return datetime.now().astimezone().strftime("%d/%m/%Y %H:%M")


def today_key() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(path, dtype=str)


def to_num(series: pd.Series | object, default: float = 0) -> pd.Series:
    if isinstance(series, pd.Series):
        return pd.to_numeric(series, errors="coerce").fillna(default)
    return pd.Series(dtype=float)


def minmax(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if s.dropna().empty:
        return pd.Series([50.0] * len(s), index=s.index)
    lo = float(s.min())
    hi = float(s.max())
    if math.isclose(lo, hi):
        return pd.Series([50.0] * len(s), index=s.index)
    return ((s - lo) / (hi - lo) * 100).clip(0, 100).round(2)


def classify_alert(score: float | int | str | None, missing: bool = False) -> str:
    if missing:
        return "xám"
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "xám"
    if value >= 85:
        return "đỏ"
    if value >= 70:
        return "cam"
    if value >= 40:
        return "vàng"
    return "xanh"


def confidence_label(score: float | int | str | None) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "Thấp"
    if value >= 80:
        return "Cao"
    if value >= 65:
        return "Khá"
    if value >= 45:
        return "Trung bình"
    return "Thấp"


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


def region_label(value: object) -> str:
    text = str(value).strip()
    if not text:
        return "thiếu dữ liệu"
    return REGION_LABELS.get(text.lower(), text)


def tourism_type_label(value: object) -> str:
    text = str(value).strip()
    if not text:
        return "thiếu dữ liệu"
    parts = [part.strip() for part in text.replace(",", ";").split(";") if part.strip()]
    return "; ".join(TOURISM_TYPE_LABELS.get(part.lower(), part) for part in parts)


def classify_alert(score: float | int | str | None, missing: bool = False) -> str:
    if missing:
        return "xám"
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "xám"
    if value >= 85:
        return "đỏ"
    if value >= 70:
        return "cam"
    if value >= 40:
        return "vàng"
    return "xanh"


def confidence_label(score: float | int | str | None) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "Thấp"
    if value >= 80:
        return "Cao"
    if value >= 65:
        return "Khá"
    if value >= 45:
        return "Trung bình"
    return "Thấp"


def ensure_dirs() -> None:
    for path in [
        DATASETS / "raw" / "news",
        DATASETS / "raw" / "search_results",
        DATASETS / "raw" / "api",
        DATASETS / "raw" / "tickets",
        DATASETS / "raw" / "osm",
        DATASETS / "raw" / "weather",
        DATASETS / "bronze",
        DATASETS / "silver",
        CURRENT,
        ARCHIVE,
        CURRENT_CSV,
        CURRENT_PARQUET,
        EXPORTS_CSV,
        EXPORTS_EXCEL,
        EXPORTS_REPORTS,
        META,
        LOGS,
        RAG,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def archive_current() -> None:
    global LAST_ARCHIVE_DIR
    if not CURRENT.exists():
        return
    files = [p for p in CURRENT.iterdir() if p.is_file()]
    if not files:
        return
    target = ARCHIVE / today_key()
    target.mkdir(parents=True, exist_ok=True)
    LAST_ARCHIVE_DIR = target
    stamp = datetime.now(timezone.utc).strftime("%H%M%SZ")
    for file in files:
        shutil.copy2(file, target / f"{file.stem}_{stamp}{file.suffix}")


def write_table(df: pd.DataFrame, name: str) -> None:
    for path in [CURRENT / f"{name}.csv", CURRENT_CSV / f"{name}.csv", EXPORTS_CSV / f"{name}.csv"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False, encoding="utf-8-sig")
    try:
        df.to_parquet(CURRENT_PARQUET / f"{name}.parquet", index=False)
    except Exception:
        pass


def load_env() -> dict[str, str]:
    if load_dotenv is not None and ENV_FILE.exists() and ENV_FILE.is_file():
        load_dotenv(ENV_FILE, override=True)
    return {key: os.getenv(key, "").strip() for key in SUPPORTED_ENV_KEYS}


def build_api_catalog(env: dict[str, str]) -> pd.DataFrame:
    rows = [
        ("positionstack", "Positionstack", "geocode địa chỉ/POI/khách sạn thành tọa độ", "POSITIONSTACK_API_KEY", "partner_api_required"),
        ("rapidapi_serp", "RapidAPI Google SERP", "tìm tin tức, báo cáo và tín hiệu thị trường", "RAPIDAPI_KEY", "near_real_time"),
        ("rapidapi_maps", "RapidAPI Google Maps Extractor", "business info, rating, review nếu endpoint hỗ trợ", "RAPIDAPI_KEY", "partner_api_required"),
        ("openrouteservice", "OpenRouteService", "routing, travel time, tuyến điều phối", "OPENROUTESERVICE_API_KEY", "near_real_time"),
        ("osm_overpass", "OSM/Overpass", "POI, bãi biển, khách sạn, nhà hàng, bãi đỗ", "", "real_data"),
        ("open_meteo", "Open-Meteo", "thời tiết hiện tại, dự báo, lịch sử thời tiết", "", "near_real_time"),
        ("google_sheets", "Google Sheets", "sync bảng tổng hợp cho giám khảo xem nhanh", "GOOGLE_SHEETS_ID", "summary_only"),
    ]
    out = []
    for api_id, name, role, key, data_type in rows:
        configured = "có" if (not key or env.get(key) or os.getenv(key)) else "thiếu"
        out.append(
            {
                "api_id": api_id,
                "ten_api": name,
                "vai_tro": role,
                "bien_moi_truong": key or "không cần key",
                "trang_thai_cau_hinh": configured,
                "loai_du_lieu": data_type if configured == "có" else "missing",
                "ghi_chu": "Bỏ qua nguồn này nếu thiếu key; pipeline không crash.",
            }
        )
    return pd.DataFrame(out)


def format_vn_time(value: datetime | None = None) -> str:
    value = value or datetime.now().astimezone()
    return value.astimezone().strftime("%d/%m/%Y %H:%M")


def file_update_time(path: Path) -> str:
    if not path.exists():
        return ""
    return format_vn_time(datetime.fromtimestamp(path.stat().st_mtime).astimezone())


def build_api_catalog(env: dict[str, str]) -> pd.DataFrame:
    rows = [
        ("positionstack", "Positionstack", "Geocode địa chỉ, POI, khách sạn thành tọa độ", "POSITIONSTACK_API_KEY", "partner_api_required", "Dùng tọa độ seed/current nếu thiếu key."),
        ("openrouteservice", "OpenRouteService", "Routing, travel time, tuyến điều phối", "OPENROUTESERVICE_API_KEY", "near_real_time", "Dùng OSRM hoặc graph proxy nếu thiếu key."),
        ("rapidapi_serp", "RapidAPI Google SERP", "Tìm tin tức, báo cáo và tín hiệu thị trường", "RAPIDAPI_KEY", "near_real_time", "Tin tức dùng snapshot/local signal nếu thiếu key."),
        ("rapidapi_google_maps", "RapidAPI Google Maps Extractor", "Business info, rating, review nếu endpoint hỗ trợ", "RAPIDAPI_KEY", "partner_api_required", "Dùng OSM/POI current nếu thiếu key."),
        ("rapidapi_google_places", "RapidAPI Google Places", "Mở rộng POI/điểm đến nếu có host hợp lệ", "RAPIDAPI_KEY", "partner_api_required", "Dùng seed list và OSM nếu thiếu key."),
        ("osm_overpass", "OSM/Overpass", "POI, bãi biển, khách sạn, nhà hàng, bãi đỗ", "", "real_data", "Nguồn mở, dùng làm fallback bản đồ/POI."),
        ("open_meteo", "Open-Meteo", "Thời tiết hiện tại, dự báo, lịch sử thời tiết", "", "near_real_time", "Nguồn công khai, không cần key."),
        ("google_sheets", "Google Sheets", "Đồng bộ bảng summary cho giám khảo xem nhanh", "GOOGLE_SHEETS_ID", "summary_only", "Nếu thiếu ID vẫn tải CSV/Excel từ dashboard."),
        ("gemini", "Gemini 2.5 Flash", "Trợ lý SEA trả lời theo knowledge base", "GEMINI_API_KEY", "ai_provider", "Fallback sang Ollama rồi rule-based nếu lỗi."),
    ]
    out = []
    for api_id, name, role, key, data_type, fallback in rows:
        configured = "Đã cấu hình" if (not key or env.get(key) or os.getenv(key)) else "Thiếu cấu hình"
        host = ""
        if api_id == "rapidapi_serp":
            host = env.get("RAPIDAPI_SERP_HOST") or os.getenv("RAPIDAPI_SERP_HOST") or "google-serp-search-api.p.rapidapi.com"
        elif api_id == "rapidapi_google_maps":
            host = env.get("RAPIDAPI_GOOGLE_MAPS_HOST") or os.getenv("RAPIDAPI_GOOGLE_MAPS_HOST") or "google-maps-extractor2.p.rapidapi.com"
        elif api_id == "rapidapi_google_places":
            host = env.get("RAPIDAPI_GOOGLE_PLACES_HOST") or os.getenv("RAPIDAPI_GOOGLE_PLACES_HOST") or "chưa cấu hình host"
        elif api_id == "gemini":
            host = env.get("GEMINI_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
        out.append(
            {
                "api_id": api_id,
                "ten_api": name,
                "vai_tro": role,
                "bien_moi_truong": key or "không cần key",
                "trang_thai_cau_hinh": configured,
                "host_hoac_model": host,
                "loai_du_lieu": data_type if configured == "Đã cấu hình" else "missing",
                "ket_qua_kiem_tra": "chưa kiểm tra trong pipeline; bấm Kiểm tra lại API trên dashboard",
                "lan_kiem_tra_cuoi": format_vn_time(),
                "da_doc_cau_hinh_tu": ".env" if ENV_FILE.exists() else "chưa tìm thấy .env",
                "nguon_thay_the": fallback,
                "ghi_chu": "Nếu thiếu cấu hình, SEA bỏ qua nguồn này, dùng fallback nếu có và không làm pipeline crash.",
            }
        )
    return pd.DataFrame(out)


def build_source_monitor_status(env: dict[str, str]) -> pd.DataFrame:
    checked = format_vn_time()
    source_defs = [
        ("vnat_report", "Báo cáo du lịch VNAT", "báo cáo du lịch", "https://thongke.tourism.vn/", "datasets/raw/vietnam_tourism_statistics", "national_destination_alerts", "", "cao"),
        ("gso_report", "Báo cáo GSO", "báo cáo thống kê", "https://www.gso.gov.vn/", "", "tourism_demand_monthly", "", "trung bình"),
        ("caav_acv_report", "CAAV/ACV", "hàng không", "https://caa.gov.vn/;https://vietnamairport.vn/", "datasets/raw/transport", "flight_price_signal", "", "cao"),
        ("flight_price", "Dữ liệu vé máy bay", "giá vé máy bay", "", "", "flight_price_signal", "RAPIDAPI_KEY", "trung bình"),
        ("attraction_ticket", "Vé khu vui chơi", "giá vé", "datasets/raw/tickets", "datasets/raw/tickets", "attraction_ticket_catalog;ticket_pressure_scores", "", "cao"),
        ("hotel_price", "Giá khách sạn", "giá khách sạn", "datasets/booking;datasets/traveloka", "datasets/booking", "hotel_price_pressure", "", "cao"),
        ("tourism_news", "Tin tức du lịch", "tin tức", "Google SERP/RapidAPI nếu có key", "datasets/raw/news", "news_events;news_risk_signals", "RAPIDAPI_KEY", "cao"),
        ("weather_risk", "Tin thời tiết/rủi ro", "thời tiết", "https://open-meteo.com/", "datasets/raw/weather", "forecast_demand_scores;national_destination_alerts", "", "cao"),
        ("traffic_news", "Tin giao thông/kẹt xe/sạt lở", "giao thông", "Google SERP/RapidAPI nếu có key", "datasets/raw/search_results", "redistribution_features;national_destination_alerts", "RAPIDAPI_KEY", "cao"),
        ("event_festival", "Sự kiện/lễ hội", "sự kiện", "Google SERP/RapidAPI nếu có key", "datasets/raw/news", "news_events;forecast_demand_scores", "RAPIDAPI_KEY", "trung bình"),
        ("google_serp", "Google SERP Search", "tìm kiếm/tin tức", env.get("RAPIDAPI_SERP_HOST", "google-serp-search-api.p.rapidapi.com"), "datasets/raw/search_results", "news_events", "RAPIDAPI_KEY", "cao"),
        ("rapidapi_google_maps", "RapidAPI Google Maps Extractor", "POI/rating/review", env.get("RAPIDAPI_GOOGLE_MAPS_HOST", "google-maps-extractor2.p.rapidapi.com"), "datasets/raw/api", "local_spending_poi;attraction_ticket_catalog", "RAPIDAPI_KEY", "trung bình"),
        ("open_meteo", "Open-Meteo", "thời tiết near-real-time", "https://api.open-meteo.com/", "datasets/raw/weather/open_meteo_forecast", "forecast_demand_scores;national_destination_alerts", "", "cao"),
        ("osm_overpass", "OSM/Overpass", "POI/bản đồ", "https://overpass-api.de/api/interpreter", "datasets/raw/geospatial/overpass", "local_spending_poi;attraction_ticket_catalog", "", "trung bình"),
        ("positionstack", "Positionstack", "geocoding", "https://positionstack.com/", "datasets/raw/api", "destination_registry;local_spending_poi", "POSITIONSTACK_API_KEY", "trung bình"),
        ("ors_osrm", "OpenRouteService/OSRM", "routing/travel time", "https://openrouteservice.org/;https://router.project-osrm.org/", "datasets/raw/mobility/osrm", "redistribution_features", "", "cao"),
        ("google_sheets", "Google Sheets summary", "bảng tổng hợp", "GOOGLE_SHEETS_ID", "", "source_monitor_status;data_freshness_status;dataset_audit;national_destination_alerts", "GOOGLE_SHEETS_ID", "trung bình"),
    ]
    rows = []
    for source_id, name, data_type, url, raw_rel, dataset, key, priority in source_defs:
        raw_path = ROOT / raw_rel if raw_rel else None
        has_key = not key or bool(env.get(key) or os.getenv(key))
        has_raw = bool(raw_path and raw_path.exists() and any(raw_path.rglob("*.*")))
        current_datasets = [d.strip() for d in dataset.split(";") if d.strip()]
        current_paths = [CURRENT / f"{d}.csv" for d in current_datasets]
        current_times = [p.stat().st_mtime for p in current_paths if p.exists()]
        last_success = format_vn_time(datetime.fromtimestamp(max(current_times)).astimezone()) if current_times else ""

        if key and not has_key:
            status = "thiếu API key"
            new_data = "Không"
            new_items = 0
            action = f"cấu hình {key} trong .env hoặc GitHub Secrets"
        elif not url and not raw_rel:
            status = "chưa cấu hình nguồn"
            new_data = "Không"
            new_items = 0
            action = "bổ sung URL/API hợp lệ trước khi cập nhật"
        elif has_raw or current_times:
            status = "mới nhất"
            new_data = "Không"
            new_items = 0
            action = "không cần; theo dõi định kỳ"
        else:
            status = "cần kiểm tra"
            new_data = "Chưa rõ"
            new_items = 0
            action = "kiểm tra nguồn trước khi đưa vào update_queue"

        if source_id == "google_sheets":
            if has_key:
                status = "cần kiểm tra"
                action = "sync các bảng summary sau khi pipeline thành công"
            else:
                action = "chưa sync vì thiếu GOOGLE_SHEETS_ID"

        rows.append(
            {
                "source_id": source_id,
                "ten_nguon": name,
                "loai_du_lieu": data_type,
                "source_url": url or "chưa cấu hình nguồn",
                "lan_kiem_tra_cuoi": checked,
                "lan_cap_nhat_thanh_cong_cuoi": last_success,
                "co_du_lieu_moi": new_data,
                "so_item_moi": new_items,
                "ngay_bai_hoac_bao_cao_moi_nhat": last_success,
                "trang_thai": status,
                "hanh_dong_can_lam": action,
                "dataset_cap_nhat": dataset,
                "muc_uu_tien": priority,
                "ghi_chu": "Không gọi dữ liệu mới nếu chưa có API/key hợp lệ; không gọi proxy là realtime.",
            }
        )
    return pd.DataFrame(rows)


def build_source_monitor_status(env: dict[str, str]) -> pd.DataFrame:
    checked = format_vn_time()
    source_defs = [
        ("vnat_report", "Báo cáo du lịch VNAT", "báo cáo du lịch", "https://thongke.tourism.vn/", "datasets/raw/vietnam_tourism_statistics", "national_destination_alerts", "", "cao"),
        ("gso_report", "Báo cáo GSO", "báo cáo thống kê", "https://www.gso.gov.vn/", "", "tourism_demand_monthly", "", "trung bình"),
        ("caav_acv_report", "CAAV/ACV", "hàng không", "https://caa.gov.vn/;https://vietnamairport.vn/", "datasets/raw/transport", "flight_price_signal", "", "cao"),
        ("flight_price", "Dữ liệu vé máy bay", "giá vé máy bay", "", "", "flight_price_signal", "RAPIDAPI_KEY", "trung bình"),
        ("attraction_ticket", "Vé khu vui chơi", "giá vé", "datasets/raw/tickets", "datasets/raw/tickets", "attraction_ticket_catalog;ticket_pressure_scores", "", "cao"),
        ("hotel_price", "Giá khách sạn", "giá khách sạn", "datasets/booking;datasets/traveloka", "datasets/booking", "hotel_price_pressure", "", "cao"),
        ("tourism_news", "Tin tức du lịch", "tin tức", "Google SERP/RapidAPI nếu có key", "datasets/raw/news", "news_events;news_risk_signals", "RAPIDAPI_KEY", "cao"),
        ("weather_risk", "Tin thời tiết/rủi ro", "thời tiết", "https://open-meteo.com/", "datasets/raw/weather", "forecast_demand_scores;national_destination_alerts", "", "cao"),
        ("traffic_news", "Tin giao thông/kẹt xe/sạt lở", "giao thông", "Google SERP/RapidAPI nếu có key", "datasets/raw/search_results", "redistribution_features;national_destination_alerts", "RAPIDAPI_KEY", "cao"),
        ("event_festival", "Sự kiện/lễ hội", "sự kiện", "Google SERP/RapidAPI nếu có key", "datasets/raw/news", "news_events;forecast_demand_scores", "RAPIDAPI_KEY", "trung bình"),
        ("google_serp", "Google SERP Search", "tìm kiếm/tin tức", env.get("RAPIDAPI_SERP_HOST", "google-serp-search-api.p.rapidapi.com"), "datasets/raw/search_results", "news_events", "RAPIDAPI_KEY", "cao"),
        ("rapidapi_google_maps", "RapidAPI Google Maps Extractor", "POI/rating/review", env.get("RAPIDAPI_GOOGLE_MAPS_HOST", "google-maps-extractor2.p.rapidapi.com"), "datasets/raw/api", "local_spending_poi;attraction_ticket_catalog", "RAPIDAPI_KEY", "trung bình"),
        ("rapidapi_google_places", "RapidAPI Google Places", "POI/điểm đến", env.get("RAPIDAPI_GOOGLE_PLACES_HOST", "chưa cấu hình host"), "datasets/raw/api", "danh_sach_diem_den_mo_rong;local_spending_poi", "RAPIDAPI_KEY", "trung bình"),
        ("open_meteo", "Open-Meteo", "thời tiết near-realtime", "https://api.open-meteo.com/", "datasets/raw/weather/open_meteo_forecast", "forecast_demand_scores;national_destination_alerts", "", "cao"),
        ("osm_overpass", "OSM/Overpass", "POI/bản đồ", "https://overpass-api.de/api/interpreter", "datasets/raw/geospatial/overpass", "local_spending_poi;attraction_ticket_catalog", "", "trung bình"),
        ("positionstack", "Positionstack", "geocoding", "https://positionstack.com/", "datasets/raw/api", "destination_registry;local_spending_poi", "POSITIONSTACK_API_KEY", "trung bình"),
        ("ors_osrm", "OpenRouteService/OSRM", "routing/travel time", "https://openrouteservice.org/;https://router.project-osrm.org/", "datasets/raw/mobility/osrm", "redistribution_features", "", "cao"),
        ("google_sheets", "Google Sheets summary", "bảng tổng hợp", "GOOGLE_SHEETS_ID", "", "source_monitor_status;data_freshness_status;dataset_audit;national_destination_alerts", "GOOGLE_SHEETS_ID", "trung bình"),
        ("gemini", "Gemini 2.5 Flash", "AI/RAG", "GEMINI_MODEL=gemini-2.5-flash", "", "rag/sea_knowledge_base.md", "GEMINI_API_KEY", "trung bình"),
    ]
    rows = []
    for source_id, name, data_type, url, raw_rel, dataset, key, priority in source_defs:
        raw_path = ROOT / raw_rel if raw_rel else None
        has_key = not key or bool(env.get(key) or os.getenv(key))
        has_raw = bool(raw_path and raw_path.exists() and any(raw_path.rglob("*.*")))
        current_datasets = [d.strip() for d in dataset.split(";") if d.strip()]
        current_paths = [CURRENT / f"{d}.csv" for d in current_datasets]
        current_times = [p.stat().st_mtime for p in current_paths if p.exists()]
        last_success = format_vn_time(datetime.fromtimestamp(max(current_times)).astimezone()) if current_times else ""

        if key and not has_key:
            status = "thiếu API key"
            new_data = "Không"
            new_items = 0
            action = f"cấu hình {key} trong .env hoặc GitHub Secrets"
        elif not url and not raw_rel:
            status = "chưa cấu hình nguồn"
            new_data = "Không"
            new_items = 0
            action = "bổ sung URL/API hợp lệ trước khi cập nhật"
        elif has_raw or current_times:
            status = "mới nhất"
            new_data = "Không"
            new_items = 0
            action = "không cần; theo dõi định kỳ"
        else:
            status = "cần kiểm tra"
            new_data = "Chưa rõ"
            new_items = 0
            action = "kiểm tra nguồn trước khi đưa vào hàng chờ cập nhật"

        if source_id == "google_sheets":
            action = "đồng bộ các bảng summary sau khi pipeline thành công" if has_key else "chưa sync vì thiếu GOOGLE_SHEETS_ID"
        if source_id == "gemini":
            action = "dùng Gemini nếu có key; fallback sang Ollama rồi rule-based nếu lỗi"

        rows.append(
            {
                "source_id": source_id,
                "ten_nguon": name,
                "loai_du_lieu": data_type,
                "source_url": url or "chưa cấu hình nguồn",
                "lan_kiem_tra_cuoi": checked,
                "lan_cap_nhat_thanh_cong_cuoi": last_success,
                "co_du_lieu_moi": new_data,
                "so_item_moi": new_items,
                "ngay_bai_hoac_bao_cao_moi_nhat": last_success,
                "trang_thai": status,
                "hanh_dong_can_lam": action,
                "dataset_cap_nhat": dataset,
                "muc_uu_tien": priority,
                "ghi_chu": "Không gọi dữ liệu mới nếu chưa có API/key hợp lệ; không gọi proxy là realtime.",
            }
        )
    return pd.DataFrame(rows)


def build_update_queue(source_status: pd.DataFrame) -> pd.DataFrame:
    queued = source_status[
        source_status["trang_thai"].isin(["có dữ liệu mới chờ cập nhật", "cần kiểm tra", "đang lỗi"])
        | source_status["co_du_lieu_moi"].isin(["Có", "Chưa rõ"])
    ].copy()
    if queued.empty:
        return pd.DataFrame(
            columns=[
                "queue_id",
                "source_id",
                "ten_nguon",
                "hanh_dong",
                "dataset_cap_nhat",
                "muc_uu_tien",
                "trang_thai_queue",
                "tao_luc",
                "ghi_chu",
            ]
        )
    queued = queued.reset_index(drop=True)
    return pd.DataFrame(
        {
            "queue_id": [f"queue_{i + 1:03d}" for i in range(len(queued))],
            "source_id": queued["source_id"],
            "ten_nguon": queued["ten_nguon"],
            "hanh_dong": queued["hanh_dong_can_lam"],
            "dataset_cap_nhat": queued["dataset_cap_nhat"],
            "muc_uu_tien": queued["muc_uu_tien"],
            "trang_thai_queue": queued["trang_thai"].map(lambda x: "chờ xử lý" if x != "thiếu API key" else "bị chặn do thiếu API key"),
            "tao_luc": format_vn_time(),
            "ghi_chu": "Khi bấm Cập nhật dữ liệu, SEA đọc queue này, archive current cũ, rebuild bảng tổng hợp và giữ bản ổn định nếu lỗi.",
        }
    )


def build_update_queue(source_status: pd.DataFrame) -> pd.DataFrame:
    queued = source_status[
        source_status["trang_thai"].isin(["có dữ liệu mới chờ cập nhật", "cần kiểm tra", "đang lỗi"])
        | source_status["co_du_lieu_moi"].isin(["Có", "Chưa rõ"])
    ].copy()
    columns = [
        "queue_id",
        "source_id",
        "ten_nguon",
        "hanh_dong",
        "dataset_cap_nhat",
        "muc_uu_tien",
        "trang_thai_queue",
        "tao_luc",
        "ghi_chu",
    ]
    if queued.empty:
        return pd.DataFrame(columns=columns)
    queued = queued.reset_index(drop=True)
    out = pd.DataFrame(
        {
            "queue_id": [f"queue_{i + 1:03d}" for i in range(len(queued))],
            "source_id": queued["source_id"],
            "ten_nguon": queued["ten_nguon"],
            "hanh_dong": queued["hanh_dong_can_lam"],
            "dataset_cap_nhat": queued["dataset_cap_nhat"],
            "muc_uu_tien": queued["muc_uu_tien"],
            "trang_thai_queue": queued["trang_thai"].map(lambda x: "chờ xử lý" if x != "thiếu API key" else "bị chặn do thiếu API key"),
            "tao_luc": format_vn_time(),
            "ghi_chu": "Khi bấm Cập nhật dữ liệu, SEA đọc queue này, archive current cũ, rebuild bảng tổng hợp và giữ bản ổn định nếu lỗi.",
        }
    )
    return out[columns]


def write_source_monitor_files(env: dict[str, str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    source_status = build_source_monitor_status(env)
    update_queue = build_update_queue(source_status)
    source_status.to_csv(META / "source_monitor_status.csv", index=False, encoding="utf-8-sig")
    update_queue.to_csv(META / "update_queue.csv", index=False, encoding="utf-8-sig")

    check_log = source_status.copy()
    check_log.insert(0, "log_time", format_vn_time())
    check_log.to_csv(META / "source_check_log.csv", index=False, encoding="utf-8-sig")
    return source_status, update_queue


def build_catalogs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    audit_old = read_csv(META / "dataset_audit.csv")
    quality_old = read_csv(META / "data_quality_scores.csv")
    rows = []
    for path in sorted(DATASETS.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".csv", ".parquet", ".json", ".html"}:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if "raw/" in rel:
            kind = "real_data"
        elif "current/" in rel or "gold/" in rel:
            kind = "mixed"
        elif "bronze/" in rel or "silver/" in rel:
            kind = "mixed"
        else:
            kind = "proxy"
        rows.append(
            {
                "dataset_id": path.stem,
                "ten_tieng_viet": path.stem.replace("_", " "),
                "duong_dan": rel,
                "nguon": "repo SEA",
                "source_url": rel,
                "ngay_cap_nhat": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
                "loai_du_lieu": kind,
                "do_tin_cay": 70 if kind == "real_data" else 55,
                "dung_cho_kpi_nao": "KPI vận hành SEA nếu đã qua silver/gold; raw dùng làm bằng chứng nguồn.",
                "gioi_han_du_lieu": "Cần đọc catalog chi tiết; không xem schema-only là dữ liệu thật.",
                "can_cap_nhat_khong": "có" if kind in {"near_real_time", "missing"} else "theo lịch",
                "tooltip_giai_thich": "Bảng audit tự động từ file trong repo, phân loại thận trọng theo thư mục.",
            }
        )
    audit = pd.DataFrame(rows)
    if not audit_old.empty:
        old = audit_old.rename(
            columns={
                "path": "duong_dan",
                "primary_sources": "nguon",
                "current_status": "loai_du_lieu",
                "reliability_notes": "tooltip_giai_thich",
            }
        )
        for col in audit.columns:
            if col not in old.columns:
                old[col] = ""
        audit = pd.concat([old[audit.columns], audit], ignore_index=True).drop_duplicates("duong_dan", keep="last")

    quality = audit[["dataset_id", "duong_dan", "loai_du_lieu", "do_tin_cay"]].copy()
    quality["quality_score"] = quality["do_tin_cay"]
    quality["freshness_score"] = quality["loai_du_lieu"].map(lambda x: 90 if x == "near_real_time" else 70 if x == "real_data" else 55)
    quality["coverage_score"] = quality["loai_du_lieu"].map(lambda x: 75 if x in {"real_data", "mixed"} else 40)
    quality["completeness_score"] = quality["loai_du_lieu"].map(lambda x: 80 if x == "real_data" else 55 if x == "mixed" else 25)
    quality["operational_readiness"] = quality["loai_du_lieu"].map(lambda x: "sẵn sàng một phần" if x in {"real_data", "mixed"} else "cần bổ sung")
    if not quality_old.empty:
        for col in quality.columns:
            if col not in quality_old.columns:
                quality_old[col] = ""
        quality = pd.concat([quality_old[quality.columns], quality], ignore_index=True).drop_duplicates("dataset_id", keep="last")

    freshness = audit[["dataset_id", "ten_tieng_viet", "duong_dan", "ngay_cap_nhat", "loai_du_lieu"]].copy()
    freshness["trang_thai_do_moi"] = freshness["loai_du_lieu"].map(lambda x: "mới" if x in {"real_data", "near_real_time"} else "cần kiểm tra")
    freshness["ghi_chu"] = "Thời gian là mốc file trong repo; realtime/near-real-time được ghi rõ theo nguồn."

    missing = pd.DataFrame(
        [
            ["traffic_realtime", "Mật độ giao thông theo tuyến vào điểm đến", "partner_api_required", "Cần API giao thông/đối tác địa phương", "Điểm áp lực, điều phối"],
            ["crowd_density", "Mật độ khách theo giờ tại bãi biển/POI", "partner_api_required", "Cần camera/IoT/telco/đối tác", "Cảnh báo quá tải"],
            ["hotel_occupancy", "Công suất phòng khách sạn", "partner_api_required", "Cần PMS/OTA partner API", "Áp lực lưu trú, dự báo"],
            ["ticket_sales_velocity", "Tốc độ bán vé khu vui chơi", "partner_api_required", "Cần API khu vui chơi", "Áp lực vé và chia khung giờ"],
            ["marine_warning", "Sóng, dòng chảy, cảnh báo bão biển", "missing", "Cần nguồn khí tượng biển chính thức", "Rủi ro thời tiết biển"],
            ["tourism_revenue_local", "Doanh thu theo điểm đến/ngành", "missing", "Cần thống kê địa phương hoặc đối tác thanh toán", "Hiệu quả kinh tế"],
        ],
        columns=["dataset_id", "ten_tieng_viet", "loai_du_lieu", "ly_do_thieu", "dung_cho_kpi_nao"],
    )
    missing["do_tin_cay_hien_tai"] = 0
    missing["tooltip_giai_thich"] = "SEA vẫn hiển thị nhưng đánh màu xám/độ tin cậy thấp cho phần thiếu nguồn này."

    source_catalog = audit[["dataset_id", "ten_tieng_viet", "nguon", "source_url", "loai_du_lieu", "tooltip_giai_thich"]].copy()
    return audit, quality, freshness, missing, source_catalog


def build_kpi_methodology_files() -> pd.DataFrame:
    kpis = [
        ("destination_pressure", "Điểm áp lực điểm đến", "0.35*rủi ro thời tiết + 0.25*áp lực giá khách sạn + 0.20*độ hấp dẫn POI + 0.20*rủi ro cao điểm", "Dùng proxy khi thiếu crowd/occupancy; cần kiểm định bằng dữ liệu đối tác.", "Điểm cao cần cảnh báo và điều phối."),
        ("coastal_pressure", "Điểm áp lực ven biển", "Điểm áp lực điểm đến + 10 nếu là ven biển, giới hạn 100", "Ưu tiên trọng tâm SEA là du lịch ven biển.", "Điểm cao cần phân luồng bãi biển, bãi đỗ, shuttle."),
        ("peak_risk", "Điểm rủi ro cao điểm", "0.60*hotel_price_pressure_proxy + 0.40*POI attractiveness", "Giá/phủ dịch vụ là proxy cho sức hút và áp lực mùa cao điểm.", "Dùng để chia khung giờ và kích hoạt điểm thay thế."),
        ("weather_risk", "Điểm rủi ro thời tiết", "Open-Meteo: mưa, gió, UV và mã thời tiết quy đổi 0-100", "Không thay thế cảnh báo khí tượng biển chính thức.", "Điểm cao cần cảnh báo an toàn và tránh đẩy khách."),
        ("ticket_pressure", "Điểm áp lực vé/khu vui chơi", "Proxy từ mật độ POI attraction và trạng thái nguồn vé", "Thiếu API bán vé nên không gọi là realtime.", "Điểm cao cần vé theo khung giờ/QR/nhân sự soát vé."),
        ("infrastructure_readiness", "Điểm sẵn sàng hạ tầng", "0.45*service POI + 0.25*khách sạn + 0.20*accessibility + 0.10*data quality", "Proxy cho năng lực tiếp nhận khi thiếu hạ tầng thực địa.", "Điểm thấp không nên đẩy khách đại trà."),
        ("economic_opportunity", "Điểm cơ hội kinh tế", "0.40*dư địa hạ tầng + 0.25*độ hấp dẫn + 0.20*chi tiêu địa phương + 0.15*khả năng điều phối", "Ưu tiên điểm có thể tăng chi tiêu mà không quá tải.", "Điểm cao phù hợp combo, OCOP, lưu trú liên vùng."),
        ("redistribution", "Điểm điều phối khách", "Từ graph tuyến: accessibility, weather suitability, capacity proxy, satisfaction", "Không phải điều phối realtime nếu thiếu traffic/crowd.", "Điểm cao là tuyến đề xuất điều phối."),
        ("investment_priority", "Điểm ưu tiên đầu tư", "0.40*cơ hội kinh tế + 0.35*(100-hạ tầng) + 0.25*áp lực", "Đầu tư nơi vừa có nhu cầu vừa nghẽn hạ tầng.", "Dùng cho bãi đỗ, shuttle, vệ sinh, biển chỉ dẫn."),
        ("destination_health", "Điểm sức khỏe điểm đến", "100 - 0.45*áp lực - 0.25*thời tiết + 0.30*hạ tầng", "Sức khỏe giảm khi áp lực/rủi ro cao.", "Điểm thấp cần giảm quảng bá và tăng bảo vệ môi trường."),
    ]
    df = pd.DataFrame(
        kpis,
        columns=["kpi_id", "ten_kpi", "cong_thuc", "vi_sao_hop_ly", "y_nghia_van_hanh"],
    )
    df["thang_do"] = "0-100"
    df["nguong_mau"] = "0-39 xanh, 40-69 vàng, 70-84 cam, 85-100 đỏ; riêng hạ tầng đảo chiều theo catalog."
    df["y_nghia_kinh_te"] = "Gắn dữ liệu với quyết định phân bổ khách, doanh thu địa phương và giảm chi phí xã hội do quá tải."
    df["loai_du_lieu"] = "mixed/proxy có ghi rõ giới hạn"
    df["do_tin_cay_mac_dinh"] = 65
    df["tooltip_tieng_viet"] = df.apply(lambda r: f"{r['ten_kpi']}: {r['cong_thuc']}. {r['vi_sao_hop_ly']}", axis=1)
    META.mkdir(parents=True, exist_ok=True)
    df.to_csv(META / "kpi_scale_catalog.csv", index=False, encoding="utf-8-sig")
    df.to_csv(META / "kpi_methodology.csv", index=False, encoding="utf-8-sig")
    (META / "confidence_methodology.csv").write_text(
        "cong_thuc,ghi_chu\n"
        "\"0.30*source_reliability + 0.25*freshness_score + 0.20*coverage_score + 0.15*completeness_score + 0.10*proxy_validation_score\","
        "\"Nếu không có proxy_validation_score thì chia lại trọng số cho 4 thành phần còn lại.\"\n",
        encoding="utf-8-sig",
    )
    return df


def build_operating_tables() -> dict[str, pd.DataFrame]:
    dest = read_csv(META / "destination_registry.csv")
    expanded_dest = read_csv(CURRENT / "danh_sach_diem_den_mo_rong.csv")
    if not expanded_dest.empty:
        dest = pd.DataFrame(
            {
                "destination_id": expanded_dest["ma_diem_den"],
                "canonical_name": expanded_dest["ten_diem_den"],
                "province_or_city": expanded_dest["tinh_thanh"],
                "tourism_types": expanded_dest["loai_hinh"].map(tourism_type_label),
                "region": expanded_dest["vung"].map(region_label),
                "lat": expanded_dest["vi_do"],
                "lng": expanded_dest["kinh_do"],
                "coastal_zone": expanded_dest["la_ven_bien"].map(lambda x: "yes" if str(x).lower() in {"có", "yes", "true"} else "no"),
                "island_zone": expanded_dest["loai_hinh"].map(tourism_type_label).astype(str).str.contains("đảo", case=False, na=False).map(lambda x: "yes" if x else "no"),
                "heritage_zone": expanded_dest["loai_hinh"].map(tourism_type_label).astype(str).str.contains("di sản", case=False, na=False).map(lambda x: "yes" if x else "no"),
                "mountain_zone": expanded_dest["loai_hinh"].map(tourism_type_label).astype(str).str.contains("núi", case=False, na=False).map(lambda x: "yes" if x else "no"),
                "urban_zone": expanded_dest["loai_hinh"].map(tourism_type_label).astype(str).str.contains("đô thị", case=False, na=False).map(lambda x: "yes" if x else "no"),
                "mekong_zone": expanded_dest["loai_hinh"].astype(str).str.contains("mekong", case=False, na=False).map(lambda x: "yes" if x else "no"),
                "operational_role": "expanded_national_registry",
            }
        )
    readiness = read_csv(GOLD / "destination_readiness_scores.csv")
    weather = read_csv(GOLD / "weather_risk_features.csv")
    redistribution = read_csv(GOLD / "redistribution_features.csv")
    poi = read_csv(GOLD / "poi_master.csv")
    if dest.empty:
        raise SystemExit("Thiếu data/metadata/destination_registry.csv")

    df = dest.merge(readiness, on="destination_id", how="left", suffixes=("", "_ready"))
    weather_cols = [c for c in ["destination_id", "weather_risk_score", "temperature_2m", "precipitation", "rain", "wind_speed_10m", "relative_humidity_2m", "collection_time"] if c in weather.columns]
    df = df.merge(weather[weather_cols], on="destination_id", how="left", suffixes=("", "_weather"))

    df["poi_total_num"] = to_num(df.get("poi_total"), 0)
    df["weather_risk_num"] = to_num(df.get("weather_risk_score"), 50)
    df["price_pressure_num"] = to_num(df.get("hotel_price_pressure_proxy"), 50)
    df["readiness_num"] = to_num(df.get("destination_readiness_score"), 35)
    df["attractiveness_num"] = to_num(df.get("poi_attractiveness_score"), 0)
    df["hotel_records_num"] = to_num(df.get("hotel_records"), 0)
    df["missing_flag"] = (df["poi_total_num"] <= 0) | df.get("data_status", "").astype(str).str.contains("partial|missing", case=False, na=True)
    df["diem_rui_ro_cao_diem"] = (0.6 * df["price_pressure_num"] + 0.4 * df["attractiveness_num"]).round(2)
    df["diem_ap_luc"] = (0.35 * df["weather_risk_num"] + 0.25 * df["price_pressure_num"] + 0.20 * df["attractiveness_num"] + 0.20 * df["diem_rui_ro_cao_diem"]).clip(0, 100).round(2)
    df["diem_ap_luc_ven_bien"] = (df["diem_ap_luc"] + df["coastal_zone"].map(lambda x: 10 if str(x).lower() == "yes" else 0)).clip(0, 100).round(2)
    df["diem_san_sang_ha_tang"] = df["readiness_num"].clip(0, 100).round(2)
    df["diem_co_hoi_kinh_te"] = ((100 - df["diem_ap_luc"]) * 0.20 + df["diem_san_sang_ha_tang"] * 0.35 + df["attractiveness_num"] * 0.25 + minmax(df["hotel_records_num"]) * 0.20).clip(0, 100).round(2)
    df["diem_uu_tien_dau_tu"] = (df["diem_co_hoi_kinh_te"] * 0.40 + (100 - df["diem_san_sang_ha_tang"]) * 0.35 + df["diem_ap_luc"] * 0.25).clip(0, 100).round(2)
    df["diem_suc_khoe_diem_den"] = (100 - df["diem_ap_luc"] * 0.45 - df["weather_risk_num"] * 0.25 + df["diem_san_sang_ha_tang"] * 0.30).clip(0, 100).round(2)
    df["muc_canh_bao"] = df.apply(lambda r: classify_alert(r["diem_ap_luc"], bool(r["missing_flag"])), axis=1)
    df["loai_du_lieu"] = df["missing_flag"].map(lambda x: "mixed_proxy_thieu_du_lieu" if x else "mixed_proxy_near_real_time")
    df["do_tin_cay"] = (0.30 * 70 + 0.25 * to_num(df.get("freshness_score"), 55) + 0.20 * to_num(df.get("coverage_score"), 45) + 0.15 * 60 + 0.10 * 60).round(2)
    df.loc[df["missing_flag"], "do_tin_cay"] = (df.loc[df["missing_flag"], "do_tin_cay"] - 15).clip(20, 100)

    red_by_origin = redistribution.groupby("origin_id")["redistribution_opportunity_score"].apply(lambda s: pd.to_numeric(s, errors="coerce").max()).to_dict() if not redistribution.empty else {}
    df["kha_nang_dieu_phoi"] = df["destination_id"].map(red_by_origin).fillna(35).astype(float).round(2)
    df["du_bao_24_gio"] = (df["diem_ap_luc"] * 0.70 + df["weather_risk_num"] * 0.30).round(2)
    df["du_bao_7_ngay"] = (df["diem_ap_luc"] * 0.75 + df["diem_rui_ro_cao_diem"] * 0.25).round(2)
    df["du_bao_30_ngay"] = (df["diem_rui_ro_cao_diem"] * 0.45 + df["diem_ap_luc"] * 0.35 + df["diem_co_hoi_kinh_te"] * 0.20).round(2)
    df["du_bao_3_thang"] = (df["du_bao_30_ngay"] * 0.80 + df["diem_co_hoi_kinh_te"] * 0.20).round(2)

    def reason(row: pd.Series) -> str:
        bits = []
        if row["weather_risk_num"] >= 70:
            bits.append("rủi ro thời tiết cao")
        if row["price_pressure_num"] >= 70:
            bits.append("proxy giá/lưu trú căng")
        if row["diem_san_sang_ha_tang"] < 40:
            bits.append("hạ tầng proxy yếu")
        if row["missing_flag"]:
            bits.append("thiếu POI/nguồn kiểm định")
        return "; ".join(bits) or "áp lực ở mức theo dõi từ dữ liệu hiện có"

    def action(row: pd.Series) -> str:
        if row["muc_canh_bao"] in {"đỏ", "cam"}:
            return "Phân luồng giao thông, tăng shuttle, chia khung giờ vào điểm nóng, tạm giảm quảng bá đại trà và đẩy khách sang điểm thay thế có hạ tầng tốt hơn."
        if row["diem_san_sang_ha_tang"] < 40:
            return "Không đẩy khách đại trà; ưu tiên bãi đỗ, vệ sinh công cộng, biển chỉ dẫn, QR vé và điểm thông tin du lịch."
        if row["muc_canh_bao"] == "xanh":
            return "Kích cầu có kiểm soát bằng combo lưu trú - ăn uống - trải nghiệm địa phương và tuyến liên vùng."
        return "Theo dõi thời tiết, giá/lưu trú và sự kiện; chuẩn bị shuttle, voucher giờ thấp điểm."

    df["nguyen_nhan_chinh"] = df.apply(reason, axis=1)
    df["hanh_dong_de_xuat"] = df.apply(action, axis=1)
    df["hieu_qua_kinh_te_ky_vong"] = df.apply(
        lambda r: "Giảm áp lực điểm nóng, tăng chi tiêu ăn uống/vận tải/lưu trú ở điểm phụ, giảm chi phí xã hội do kẹt xe và trải nghiệm xấu."
        if r["muc_canh_bao"] in {"đỏ", "cam"}
        else "Tăng doanh thu mùa thấp điểm và kéo dài thời gian lưu trú nếu kích cầu đúng phân khúc.",
        axis=1,
    )

    alerts = pd.DataFrame(
        {
            "destination_id": df["destination_id"],
            "ten_diem_den": df["canonical_name"],
            "tinh_thanh": df["province_or_city"],
            "vung": df["region"],
            "loai_hinh_du_lich": df["tourism_types"],
            "muc_canh_bao": df["muc_canh_bao"],
            "diem_ap_luc": df["diem_ap_luc"],
            "rui_ro_thoi_tiet": df["weather_risk_num"].round(2),
            "du_bao_24_gio": df["du_bao_24_gio"],
            "du_bao_7_ngay": df["du_bao_7_ngay"],
            "du_bao_30_ngay": df["du_bao_30_ngay"],
            "du_bao_3_thang": df["du_bao_3_thang"],
            "co_hoi_kinh_te": df["diem_co_hoi_kinh_te"],
            "kha_nang_dieu_phoi": df["kha_nang_dieu_phoi"],
            "diem_san_sang_ha_tang": df["diem_san_sang_ha_tang"],
            "loai_du_lieu": df["loai_du_lieu"],
            "do_tin_cay": df["do_tin_cay"],
            "nguyen_nhan_chinh": df["nguyen_nhan_chinh"],
            "hanh_dong_de_xuat": df["hanh_dong_de_xuat"],
            "hieu_qua_kinh_te_ky_vong": df["hieu_qua_kinh_te_ky_vong"],
            "cap_nhat_lan_cuoi": now_vn(),
            "nhiet_do_hien_tai": df.get("temperature_2m", ""),
            "mua_hien_tai": df.get("precipitation", ""),
            "gio_hien_tai": df.get("wind_speed_10m", ""),
            "do_am_hien_tai": df.get("relative_humidity_2m", ""),
            "trang_thai_thoi_tiet_ngan": df.get("weather_status_short", ""),
            "cap_nhat_thoi_tiet_luc": now_vn(),
            "lat": df["lat"],
            "lng": df["lng"],
            "coastal_zone": df["coastal_zone"],
            "diem_uu_tien_dau_tu": df["diem_uu_tien_dau_tu"],
            "diem_suc_khoe_diem_den": df["diem_suc_khoe_diem_den"],
        }
    ).sort_values(["muc_canh_bao", "diem_ap_luc"], ascending=[True, False])
    if "trang_thai_thoi_tiet_ngan" in alerts.columns:
        temp = pd.to_numeric(alerts.get("nhiet_do_hien_tai"), errors="coerce")
        rain = pd.to_numeric(alerts.get("mua_hien_tai"), errors="coerce")
        wind = pd.to_numeric(alerts.get("gio_hien_tai"), errors="coerce")
        alerts["trang_thai_thoi_tiet_ngan"] = "Ổn định"
        alerts.loc[temp.isna() & rain.isna() & wind.isna(), "trang_thai_thoi_tiet_ngan"] = "thiếu dữ liệu"
        alerts.loc[temp >= 35, "trang_thai_thoi_tiet_ngan"] = "Nắng nóng"
        alerts.loc[wind >= 35, "trang_thai_thoi_tiet_ngan"] = "Gió mạnh"
        alerts.loc[rain >= 8, "trang_thai_thoi_tiet_ngan"] = "Mưa đáng chú ý"
    order = {"đỏ": 0, "cam": 1, "vàng": 2, "xanh": 3, "xám": 4}
    alerts["_order"] = alerts["muc_canh_bao"].map(order)
    alerts = alerts.sort_values(["_order", "diem_ap_luc"], ascending=[True, False]).drop(columns="_order").reset_index(drop=True)
    alerts.insert(0, "rank", range(1, len(alerts) + 1))

    forecast_rows = []
    horizons = [("giờ", "24 giờ", "du_bao_24_gio"), ("ngày", "7 ngày", "du_bao_7_ngay"), ("tuần", "30 ngày", "du_bao_30_ngay"), ("tháng", "3 tháng", "du_bao_3_thang")]
    for _, row in alerts.iterrows():
        for granularity, horizon, col in horizons:
            forecast_rows.append(
                {
                    "destination_id": row["destination_id"],
                    "ten_diem_den": row["ten_diem_den"],
                    "tinh_thanh": row["tinh_thanh"],
                    "vung": row["vung"],
                    "forecast_granularity": granularity,
                    "forecast_horizon": horizon,
                    "forecast_demand_score": row[col],
                    "muc_canh_bao_du_bao": classify_alert(row[col], row["muc_canh_bao"] == "xám"),
                    "drivers": row["nguyen_nhan_chinh"],
                    "recommended_action": row["hanh_dong_de_xuat"],
                    "data_type": row["loai_du_lieu"],
                    "confidence_score": row["do_tin_cay"],
                    "last_updated": now_vn(),
                    "method_note": "Forecast tính trước bằng rule/proxy từ weather, POI, hotel price pressure và graph; AI chỉ giải thích, không tự bịa.",
                }
            )
    forecast = pd.DataFrame(forecast_rows)

    weather_current = alerts[
        [
            "destination_id",
            "ten_diem_den",
            "tinh_thanh",
            "vung",
            "lat",
            "lng",
            "coastal_zone",
            "nhiet_do_hien_tai",
            "mua_hien_tai",
            "gio_hien_tai",
            "do_am_hien_tai",
            "trang_thai_thoi_tiet_ngan",
            "cap_nhat_thoi_tiet_luc",
            "rui_ro_thoi_tiet",
        ]
    ].copy()
    weather_current["phu_hop_di_bien"] = weather_current.apply(
        lambda r: "không áp dụng"
        if str(r.get("coastal_zone", "")).lower() != "yes"
        else "phù hợp, theo dõi mưa/gió"
        if pd.to_numeric(pd.Series([r.get("rui_ro_thoi_tiet")]), errors="coerce").iloc[0] < 40
        else "cần theo dõi"
        if pd.to_numeric(pd.Series([r.get("rui_ro_thoi_tiet")]), errors="coerce").iloc[0] < 70
        else "không thuận lợi",
        axis=1,
    )
    weather_current["chan_doan_thieu_thoi_tiet"] = weather_current.apply(
        lambda r: ""
        if pd.notna(pd.to_numeric(pd.Series([r.get("nhiet_do_hien_tai")]), errors="coerce").iloc[0])
        else "Thiếu thời tiết: kiểm tra vi_do/kinh_do, geocode, Open-Meteo call và bước ghi gold/current.",
        axis=1,
    )

    weather_7d = forecast[forecast["forecast_horizon"].astype(str).str.contains("7", na=False)].copy()
    weather_7d = weather_7d.rename(
        columns={
            "forecast_demand_score": "diem_rui_ro_7_ngay",
            "muc_canh_bao_du_bao": "muc_rui_ro_7_ngay",
            "drivers": "ly_do",
            "last_updated": "cap_nhat_luc",
        }
    )

    conf_rows = []
    for _, row in alerts.iterrows():
        for metric, value in [
            ("Điểm áp lực điểm đến", row["diem_ap_luc"]),
            ("Điểm rủi ro thời tiết", row["rui_ro_thoi_tiet"]),
            ("Điểm sẵn sàng hạ tầng", row["diem_san_sang_ha_tang"]),
            ("Điểm cơ hội kinh tế", row["co_hoi_kinh_te"]),
            ("Điểm điều phối khách", row["kha_nang_dieu_phoi"]),
        ]:
            conf_rows.append(
                {
                    "destination_id": row["destination_id"],
                    "ten_diem_den": row["ten_diem_den"],
                    "metric_name": metric,
                    "metric_score": value,
                    "confidence_score": row["do_tin_cay"],
                    "confidence_label": confidence_label(row["do_tin_cay"]),
                    "confidence_reason": f"Nguồn: {row['loai_du_lieu']}; {row['nguyen_nhan_chinh']}",
                    "source_list": "OpenStreetMap; Open-Meteo; OTA snapshot; destination graph",
                    "last_updated": now_vn(),
                    "proxy_validation_error": "",
                }
            )
    confidence = pd.DataFrame(conf_rows)

    proxy_rows = []
    for _, row in alerts.iterrows():
        proxy = float(row["diem_ap_luc"])
        near = float(row["rui_ro_thoi_tiet"])
        err = abs(proxy - near)
        pct = err / max(near, 1) * 100
        if pct <= 10:
            label = "proxy rất tốt"
            after = float(row["do_tin_cay"])
        elif pct <= 20:
            label = "proxy tốt, dùng được"
            after = float(row["do_tin_cay"]) - 3
        elif pct <= 35:
            label = "cần theo dõi"
            after = float(row["do_tin_cay"]) - 8
        else:
            label = "proxy không ổn định, giảm confidence"
            after = float(row["do_tin_cay"]) - 15
        proxy_rows.append(
            {
                "destination_id": row["destination_id"],
                "ten_diem_den": row["ten_diem_den"],
                "metric_name": "Áp lực điểm đến proxy so với thời tiết near-real-time",
                "proxy_score": round(proxy, 2),
                "near_realtime_score": round(near, 2),
                "absolute_error": round(err, 2),
                "percentage_error": round(pct, 2),
                "reliability_label": label,
                "confidence_before": row["do_tin_cay"],
                "confidence_after": max(20, round(after, 2)),
                "data_used_proxy": "POI, hotel price pressure, readiness, peak risk",
                "data_used_nearrealtime": "Open-Meteo forecast/current snapshot",
                "last_updated": now_vn(),
                "method_note": "So sánh proxy vận hành với thành phần near-real-time hiện có; không gọi proxy là realtime.",
            }
        )
    proxy = pd.DataFrame(proxy_rows)

    poi_summary = poi.groupby(["destination_id", "category"]).size().reset_index(name="so_luong") if not poi.empty else pd.DataFrame(columns=["destination_id", "category", "so_luong"])
    ticket = poi[poi.get("category", pd.Series(dtype=str)).astype(str).str.contains("attraction|beach|tourism", na=False)].copy() if not poi.empty else pd.DataFrame()
    if ticket.empty:
        ticket_catalog = pd.DataFrame(columns=["destination_id", "ten_diem_den", "ten_dia_diem", "loai_ve", "gia_ve_cong_khai", "gio_mo_cua", "loai_du_lieu", "tooltip"])
    else:
        ticket_catalog = ticket[["destination_id", "destination_name", "poi_name", "category", "source_name", "collection_time"]].head(300).rename(
            columns={"destination_name": "ten_diem_den", "poi_name": "ten_dia_diem", "category": "loai_ve"}
        )
        ticket_catalog["gia_ve_cong_khai"] = "thiếu dữ liệu giá"
        ticket_catalog["gio_mo_cua"] = "cần Google Maps/đối tác hoặc OSM tag opening_hours"
        ticket_catalog["loai_du_lieu"] = "public_snapshot_osm"
        ticket_catalog["tooltip"] = "Dữ liệu giá lấy từ nguồn công khai tại thời điểm cập nhật nếu có; hiện chưa phải realtime. Cần API đối tác để cập nhật tự động."

    spending = poi[poi.get("category", pd.Series(dtype=str)).astype(str).isin(["restaurant", "hotel_osm", "parking", "transport_hub"])] if not poi.empty else pd.DataFrame()
    if not spending.empty:
        spending = spending[["destination_id", "destination_name", "poi_name", "category", "lat", "lng", "source_name"]].head(500).rename(
            columns={"destination_name": "ten_diem_den", "poi_name": "ten_poi", "category": "nhom_chi_tieu"}
        )
        spending["goi_y_kinh_te"] = spending["nhom_chi_tieu"].map(
            {
                "restaurant": "Đưa vào combo ăn uống địa phương/OCOP và voucher giờ thấp điểm.",
                "hotel_osm": "Gắn với combo lưu trú liên vùng, không dùng như occupancy thật.",
                "parking": "Ưu tiên bãi đỗ vệ tinh và shuttle.",
                "transport_hub": "Tăng chuyến shuttle/xe điện vào giờ cao điểm.",
            }
        ).fillna("Khai thác như điểm chi tiêu phụ trợ.")
    else:
        spending = pd.DataFrame(columns=["destination_id", "ten_diem_den", "ten_poi", "nhom_chi_tieu", "lat", "lng", "source_name", "goi_y_kinh_te"])

    ticket_pressure = alerts[["destination_id", "ten_diem_den", "diem_ap_luc", "do_tin_cay"]].copy()
    attraction_counts = poi_summary[poi_summary["category"].astype(str).str.contains("attraction|beach|tourism", na=False)].groupby("destination_id")["so_luong"].sum().to_dict()
    ticket_pressure["attraction_poi_count"] = ticket_pressure["destination_id"].map(attraction_counts).fillna(0).astype(int)
    ticket_pressure["ticket_pressure_score"] = (ticket_pressure["diem_ap_luc"] * 0.65 + minmax(ticket_pressure["attraction_poi_count"]) * 0.35).round(2)
    ticket_pressure["tooltip"] = "Proxy từ áp lực điểm đến và mật độ POI bán vé/điểm tham quan; cần API bán vé để realtime."

    hotel_price = alerts[["destination_id", "ten_diem_den", "diem_ap_luc", "do_tin_cay"]].copy()
    price_lookup = df.set_index("destination_id")["price_pressure_num"].to_dict()
    hotel_price["hotel_price_pressure_score"] = hotel_price["destination_id"].map(price_lookup).fillna(50).astype(float).round(2)
    hotel_price["tooltip"] = "Proxy từ snapshot giá OTA công khai, không phải công suất phòng hay giá realtime."

    flight_price = pd.DataFrame(
        [
            {
                "destination_id": row["destination_id"],
                "ten_diem_den": row["ten_diem_den"],
                "flight_price_signal": "thiếu nguồn hợp lệ",
                "loai_du_lieu": "partner_api_required",
                "tooltip": "Cần API hàng không/OTA được phép dùng; SEA không bịa tín hiệu giá vé máy bay.",
                "last_updated": now_vn(),
            }
            for _, row in alerts.iterrows()
        ]
    )

    actions = []
    for _, row in alerts.iterrows():
        base_problem = "quá tải/áp lực cao" if row["muc_canh_bao"] in {"đỏ", "cam"} else "dư địa hoặc cần theo dõi"
        actors = [
            ("Cơ quan quản lý du lịch", "điều chỉnh truyền thông, kích cầu điểm phụ, công bố cảnh báo trên dashboard/app"),
            ("Công an/giao thông địa phương", "phân luồng, đặt biển báo, tăng lực lượng tại nút vào bãi biển/POI"),
            ("Doanh nghiệp du lịch", "bán gói liên vùng, chuyển tour sang khung giờ thấp điểm"),
            ("Khu vui chơi", "chia vé theo khung giờ, tăng nhân sự soát vé, đẩy QR/e-ticket"),
            ("Khách sạn", "combo lưu trú dài hơn, voucher ăn uống địa phương, không đẩy giá khi trải nghiệm giảm"),
            ("Nhà hàng/OCOP", "voucher giờ thấp điểm, menu combo địa phương, điểm bán vệ tinh"),
            ("Vận tải/shuttle", "tăng shuttle từ bãi đỗ vệ tinh và tuyến thay thế"),
        ]
        for actor, act in actors:
            actions.append(
                {
                    "diem_den": row["ten_diem_den"],
                    "van_de": base_problem,
                    "hanh_dong": act,
                    "doi_tuong_thuc_hien": actor,
                    "chi_phi_trien_khai": "thấp-trung bình" if actor not in {"Vận tải/shuttle", "Công an/giao thông địa phương"} else "trung bình",
                    "loi_ich_ky_vong": row["hieu_qua_kinh_te_ky_vong"],
                    "logic_kinh_te": "Chuyển một phần cầu khỏi điểm nóng, tăng chi tiêu ở điểm phụ và giảm tổn thất do kẹt xe/quá tải.",
                    "kpi_do_luong": "điểm áp lực; điểm điều phối; doanh thu ăn uống/vé/lưu trú; phản hồi du khách",
                    "muc_uu_tien": row["muc_canh_bao"],
                    "du_lieu_dung": row["loai_du_lieu"],
                    "do_tin_cay": row["do_tin_cay"],
                }
            )
    economic_actions = pd.DataFrame(actions)
    clean_actions = []
    actors = [
        ("Chính quyền", "Điều chỉnh truyền thông, kích cầu điểm phụ, công bố cảnh báo trên dashboard/app", 74, 78),
        ("Công an/giao thông", "Phân luồng tại tuyến ven biển, đặt biển báo, tăng lực lượng ở nút vào bãi biển/POI", 82, 62),
        ("Doanh nghiệp du lịch", "Bán gói liên vùng, chuyển tour sang khung giờ thấp điểm hoặc điểm còn dư địa", 76, 80),
        ("Khách sạn", "Tạo combo lưu trú dài hơn, voucher ăn uống địa phương và điều tiết giá theo trải nghiệm", 70, 84),
        ("Khu vui chơi", "Chia vé theo khung giờ, tăng nhân sự soát vé, đẩy QR/e-ticket", 73, 82),
        ("Nhà hàng/OCOP", "Tạo voucher giờ thấp điểm, menu combo địa phương và điểm bán vệ tinh", 66, 86),
        ("Vận tải/shuttle", "Tăng shuttle từ bãi đỗ vệ tinh và tuyến thay thế khi điểm áp lực tăng", 80, 68),
    ]
    for _, row in alerts.iterrows():
        pressure = float(row.get("diem_ap_luc", 0))
        economy = float(row.get("co_hoi_kinh_te", 0))
        infrastructure = float(row.get("diem_san_sang_ha_tang", 0))
        conf_score = float(row.get("do_tin_cay", 0))
        alert_bonus = 16 if row["muc_canh_bao"] == "đỏ" else 10 if row["muc_canh_bao"] == "cam" else 4 if row["muc_canh_bao"] == "vàng" else 0
        urgent = min(100, max(0, pressure + alert_bonus))
        problem = "áp lực cao/nguy cơ quá tải" if row["muc_canh_bao"] in {"đỏ", "cam"} else "còn dư địa hoặc cần theo dõi"
        for actor, action_text, impact_base, feasibility_base in actors:
            impact_score = min(100, max(0, 0.50 * economy + 0.35 * pressure + 0.15 * impact_base + alert_bonus))
            feasibility_score = min(100, max(0, 0.45 * infrastructure + 0.35 * feasibility_base + 0.20 * conf_score))
            priority_score = round(0.4 * impact_score + 0.3 * urgent + 0.2 * feasibility_score + 0.1 * conf_score, 2)
            if priority_score >= 80:
                priority = "Cao"
            elif priority_score >= 60:
                priority = "Trung bình"
            else:
                priority = "Thấp"
            cost = "trung bình" if actor in {"Công an/giao thông", "Vận tải/shuttle"} else "thấp-trung bình"
            if actor == "Chính quyền" and infrastructure < 45:
                cost = "cao"
            clean_actions.append(
                {
                    "diem_den": row["ten_diem_den"],
                    "van_de": problem,
                    "hanh_dong": action_text,
                    "doi_tuong_thuc_hien": actor,
                    "chi_phi_trien_khai": cost,
                    "loi_ich_ky_vong": row["hieu_qua_kinh_te_ky_vong"],
                    "logic_kinh_te": "Vấn đề -> Hành động -> KPI thay đổi -> Hiệu quả kinh tế: giảm áp lực tại điểm nóng, tăng chi tiêu ăn uống/vận tải/lưu trú/vé ở vùng phụ và giảm chi phí xã hội do kẹt xe/quá tải.",
                    "kpi_do_luong": "Điểm áp lực; điểm điều phối; điểm hạ tầng; cơ hội kinh tế; doanh thu ăn uống/vé/lưu trú; phản hồi du khách",
                    "diem_tac_dong_kinh_te": round(impact_score, 2),
                    "diem_kha_thi": round(feasibility_score, 2),
                    "diem_khan_cap": round(urgent, 2),
                    "diem_uu_tien": priority_score,
                    "muc_uu_tien": priority,
                    "du_lieu_dung": row["loai_du_lieu"],
                    "do_tin_cay": row["do_tin_cay"],
                }
            )
    economic_actions = pd.DataFrame(clean_actions)

    news_events, news_risk, news_actions, seen_registry, taxonomy = build_news_tables(alerts)
    kb = build_knowledge_base_text(alerts, forecast, economic_actions, proxy)
    (RAG / "sea_knowledge_base.md").write_text(kb, encoding="utf-8")
    (RAG / "tourism_kb.md").write_text(kb, encoding="utf-8")

    return {
        "national_destination_alerts": alerts,
        "redistribution_features": redistribution,
        "forecast_demand_scores": forecast,
        "thoi_tiet_hien_tai": weather_current,
        "du_bao_thoi_tiet_7_ngay": weather_7d,
        "kpi_confidence_scores": confidence,
        "proxy_vs_nearrealtime_comparison": proxy,
        "attraction_ticket_catalog": ticket_catalog,
        "local_spending_poi": spending,
        "ticket_pressure_scores": ticket_pressure,
        "hotel_price_pressure": hotel_price,
        "flight_price_signal": flight_price,
        "economic_action_recommendations": economic_actions,
        "news_events": news_events,
        "news_risk_signals": news_risk,
        "news_action_recommendations": news_actions,
        "news_seen_registry": seen_registry,
        "news_event_taxonomy": taxonomy,
    }


def build_news_tables(alerts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    keywords = [
        "du lịch Việt Nam",
        "du lịch biển Việt Nam",
        "quá tải du lịch",
        "cháy rừng khu du lịch",
        "bão du lịch",
        "sạt lở điểm du lịch",
        "lễ hội du lịch",
        "doanh thu du lịch",
        "lượng khách du lịch",
        "vé khu vui chơi",
        "giá vé du lịch",
        "du lịch Đà Nẵng",
        "du lịch Phú Quốc",
        "du lịch Nha Trang",
        "du lịch Hạ Long",
        "du lịch Hội An",
    ]
    taxonomy = pd.DataFrame(
        [
            ("environmental_risk", "cháy rừng, ô nhiễm, rác thải, sự cố môi trường", "giảm Destination Health, không recommend điểm đó"),
            ("weather_disruption", "bão, mưa lớn, ngập, biển động", "tăng Weather Risk, cảnh báo tuyến/bãi biển"),
            ("traffic_disruption", "kẹt xe, sạt lở, ùn tắc, cấm đường", "tăng Travel Friction, đề xuất phân luồng"),
            ("event_pressure", "lễ hội, concert, sự kiện thể thao", "tăng Demand Score, chia khung giờ, tăng shuttle"),
            ("capacity_change", "đóng/mở điểm tham quan, thay đổi sức chứa", "cập nhật áp lực vé/hạ tầng"),
            ("economic_opportunity", "doanh thu, sản phẩm mới, kích cầu", "tăng cơ hội kinh tế, combo địa phương"),
            ("policy_change", "quy định, phí, chính sách visa/du lịch", "điều chỉnh khuyến nghị vận hành"),
            ("ticket_price_change", "giá vé, combo, khuyến mãi", "cập nhật ticket pressure và gợi ý giá"),
        ],
        columns=["event_type", "tu_khoa_nhan_dien", "tac_dong_van_hanh"],
    )
    events = []
    for _, row in alerts.head(12).iterrows():
        event_type = "event_pressure" if row["muc_canh_bao"] in {"đỏ", "cam"} else "economic_opportunity"
        events.append(
            {
                "event_id": f"local_signal_{row['destination_id']}",
                "keyword": f"du lịch {row['ten_diem_den']}",
                "title": f"Tín hiệu vận hành tổng hợp cho {row['ten_diem_den']}",
                "source_url": "local_gold_current",
                "published_time": row["cap_nhat_lan_cuoi"],
                "affected_destination_id": row["destination_id"],
                "affected_destination": row["ten_diem_den"],
                "event_type": event_type,
                "risk_score_delta": 8 if event_type == "event_pressure" else -5,
                "opportunity_score_delta": 6 if event_type == "economic_opportunity" else 2,
                "data_type": "local_signal_from_gold_data",
                "confidence_score": row["do_tin_cay"],
                "summary_vi": row["nguyen_nhan_chinh"],
            }
        )
    news_events = pd.DataFrame(events)
    risk = news_events[["event_id", "affected_destination_id", "affected_destination", "event_type", "risk_score_delta", "confidence_score"]].copy()
    risk["operation_signal"] = risk["event_type"].map(
        {
            "event_pressure": "tăng Demand Score, tăng shuttle, chia khung giờ, đẩy điểm phụ",
            "economic_opportunity": "ưu tiên combo ăn uống/vé/lưu trú nếu hạ tầng đủ",
        }
    )
    actions = risk.copy()
    actions["recommended_action"] = actions["operation_signal"]
    actions["owner"] = "địa phương/doanh nghiệp/khu vui chơi/vận tải"
    seen = pd.DataFrame({"keyword": keywords, "last_checked": now_vn(), "status": "chưa gọi API nếu thiếu RAPIDAPI_KEY"})
    return news_events, risk, actions, seen, taxonomy


def build_knowledge_base_text(alerts: pd.DataFrame, forecast: pd.DataFrame, actions: pd.DataFrame, proxy: pd.DataFrame) -> str:
    lines = [
        "# Knowledge Base SEA",
        "",
        "Xin chào, tôi là Trợ lý điều hành SEA. Tôi có thể giúp bạn xem cảnh báo du lịch, giải thích chỉ số, đề xuất điều phối khách và phân tích hiệu quả kinh tế.",
        "",
        "Quy tắc: chỉ trả lời dựa trên bảng gold/current; nếu thiếu dữ liệu phải nói rõ thiếu dữ liệu, confidence thấp hoặc cần API đối tác.",
        "",
        "## Cảnh báo điểm đến",
    ]
    for _, row in alerts.iterrows():
        lines.append(
            f"- {row['ten_diem_den']} ({row['tinh_thanh']}): cảnh báo {row['muc_canh_bao']}, áp lực {row['diem_ap_luc']}, "
            f"thời tiết {row['rui_ro_thoi_tiet']}, hạ tầng {row['diem_san_sang_ha_tang']}, điều phối {row['kha_nang_dieu_phoi']}. "
            f"Vì sao: {row['nguyen_nhan_chinh']}. Nên làm: {row['hanh_dong_de_xuat']}. "
            f"Hiệu quả kinh tế: {row['hieu_qua_kinh_te_ky_vong']}. Dữ liệu dùng: {row['loai_du_lieu']}. Độ tin cậy: {row['do_tin_cay']}."
        )
    lines += ["", "## Forecast", ""]
    for _, row in forecast.head(80).iterrows():
        lines.append(f"- {row['ten_diem_den']} {row['forecast_horizon']}: {row['forecast_demand_score']} ({row['muc_canh_bao_du_bao']}). {row['recommended_action']}")
    lines += ["", "## Kiểm định proxy", ""]
    for _, row in proxy.iterrows():
        lines.append(f"- {row['ten_diem_den']}: lệch {row['percentage_error']}%, {row['reliability_label']}, confidence sau kiểm định {row['confidence_after']}.")
    lines += ["", "## Format trả lời AI", "Tình hình:\nVì sao:\nNên làm:\nHiệu quả kinh tế:\nDữ liệu dùng:\nĐộ tin cậy:"]
    return "\n".join(lines)


def write_metadata_tables(env: dict[str, str]) -> None:
    audit, quality, freshness, missing, source_catalog = build_catalogs()
    api_catalog = build_api_catalog(env)
    audit.to_csv(META / "dataset_audit.csv", index=False, encoding="utf-8-sig")
    quality.to_csv(META / "data_quality_scores.csv", index=False, encoding="utf-8-sig")
    freshness.to_csv(META / "data_freshness_status.csv", index=False, encoding="utf-8-sig")
    missing.to_csv(META / "missing_dataset_registry.csv", index=False, encoding="utf-8-sig")
    source_catalog.to_csv(META / "data_source_catalog.csv", index=False, encoding="utf-8-sig")
    api_catalog.to_csv(META / "api_source_catalog.csv", index=False, encoding="utf-8-sig")


def write_excel_summary(tables: dict[str, pd.DataFrame]) -> None:
    path = EXPORTS_EXCEL / "sea_summary.xlsx"
    try:
        with pd.ExcelWriter(path) as writer:
            for name in [
                "national_destination_alerts",
                "forecast_demand_scores",
                "economic_action_recommendations",
                "proxy_vs_nearrealtime_comparison",
                "kpi_confidence_scores",
                "ticket_pressure_scores",
                "source_monitor_status",
            ]:
                if name in tables:
                    tables[name].head(5000).to_excel(writer, sheet_name=name[:31], index=False)
    except Exception:
        (EXPORTS_REPORTS / "excel_export_status.txt").write_text("Chưa export Excel được; cần cài openpyxl/xlsxwriter.\n", encoding="utf-8")


def google_sheet_client() -> tuple[object | None, str]:
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


def sync_google_sheets_summary(env: dict[str, str]) -> pd.DataFrame:
    now = now_vn()
    sheet_id = env.get("GOOGLE_SHEETS_ID") or os.getenv("GOOGLE_SHEETS_ID", "").strip()
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

    rows = []
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


def write_current_freshness_status(tables: dict[str, pd.DataFrame], source_status: pd.DataFrame, env: dict[str, str]) -> None:
    source_lookup = {}
    for _, row in source_status.iterrows():
        for dataset in str(row.get("dataset_cap_nhat", "")).split(";"):
            dataset = dataset.strip()
            if dataset:
                source_lookup.setdefault(dataset, row)

    rows = []
    archive_path = LAST_ARCHIVE_DIR.relative_to(ROOT).as_posix() if LAST_ARCHIVE_DIR and LAST_ARCHIVE_DIR.exists() else ""
    sheets_status = "Có GOOGLE_SHEETS_ID, chờ bước sync summary" if env.get("GOOGLE_SHEETS_ID") or os.getenv("GOOGLE_SHEETS_ID") else "Chưa sync vì thiếu GOOGLE_SHEETS_ID"
    for name, df in tables.items():
        path = CURRENT / f"{name}.csv"
        source_row = source_lookup.get(name)
        source_name = source_row["ten_nguon"] if source_row is not None else "SEA gold/current"
        source_state = source_row["trang_thai"] if source_row is not None else "mới nhất"
        rows.append(
            {
                "dataset_id": name,
                "ten_dataset": name.replace("_", " "),
                "duong_dan_current": path.relative_to(ROOT).as_posix(),
                "duong_dan_current_csv": (CURRENT_CSV / f"{name}.csv").relative_to(ROOT).as_posix(),
                "duong_dan_current_parquet": (CURRENT_PARQUET / f"{name}.parquet").relative_to(ROOT).as_posix(),
                "duong_dan_archive_gan_nhat": archive_path,
                "cap_nhat_lan_cuoi": file_update_time(path) or format_vn_time(),
                "mui_gio": "Việt Nam",
                "trang_thai_du_lieu": source_state,
                "nguon_du_lieu_chinh": source_name,
                "so_dong": len(df),
                "do_tin_cay": round(pd.to_numeric(df.get("do_tin_cay", pd.Series([70])), errors="coerce").mean(), 2) if not df.empty else 0,
                "google_sheets_summary_da_sync": sheets_status,
                "ghi_chu": "Dashboard đang dùng bản current này. Nếu cập nhật lỗi, SEA giữ bản current ổn định gần nhất và ghi lỗi vào pipeline_run_log.",
            }
        )
    freshness_df = pd.DataFrame(rows)
    freshness_df.to_csv(META / "data_freshness_status.csv", index=False, encoding="utf-8-sig")
    freshness_df.rename(
        columns={
            "dataset_id": "ma_dataset",
            "ten_dataset": "ten_dataset",
            "duong_dan_current": "duong_dan_du_lieu_moi_nhat",
            "duong_dan_archive_gan_nhat": "duong_dan_du_lieu_cu_gan_nhat",
            "cap_nhat_lan_cuoi": "cap_nhat_lan_cuoi",
            "trang_thai_du_lieu": "trang_thai",
            "nguon_du_lieu_chinh": "nguon_du_lieu_chinh",
            "google_sheets_summary_da_sync": "trang_thai_google_sheets",
        }
    ).to_csv(META / "trang_thai_do_moi_du_lieu.csv", index=False, encoding="utf-8-sig")


def build_vietnamese_summary_tables(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    alerts = tables.get("national_destination_alerts", pd.DataFrame())
    if not alerts.empty:
        out["xep_hang_canh_bao_toan_quoc"] = alerts.rename(
            columns={
                "rank": "xep_hang",
                "ten_diem_den": "ten_diem_den",
                "tinh_thanh": "tinh_thanh",
                "vung": "vung",
                "muc_canh_bao": "muc_canh_bao",
                "diem_ap_luc": "diem_ap_luc",
                "rui_ro_thoi_tiet": "diem_thoi_tiet",
                "diem_san_sang_ha_tang": "diem_ha_tang",
                "co_hoi_kinh_te": "diem_co_hoi_kinh_te",
                "kha_nang_dieu_phoi": "diem_dieu_phoi",
                "du_bao_24_gio": "du_bao_24_gio",
                "du_bao_7_ngay": "du_bao_7_ngay",
                "du_bao_30_ngay": "du_bao_30_ngay",
                "nhiet_do_hien_tai": "nhiet_do_hien_tai",
                "mua_hien_tai": "kha_nang_mua",
                "gio_hien_tai": "gio",
                "trang_thai_thoi_tiet_ngan": "trang_thai_thoi_tiet_ngan",
                "cap_nhat_thoi_tiet_luc": "cap_nhat_thoi_tiet_luc",
                "loai_du_lieu": "loai_du_lieu",
                "do_tin_cay": "do_tin_cay",
                "nguyen_nhan_chinh": "ly_do_xep_hang",
                "hanh_dong_de_xuat": "hanh_dong_de_xuat",
                "hieu_qua_kinh_te_ky_vong": "hieu_qua_kinh_te_du_kien",
                "cap_nhat_lan_cuoi": "cap_nhat_lan_cuoi",
            }
        )[
            [
                "xep_hang",
                "ten_diem_den",
                "tinh_thanh",
                "vung",
                "muc_canh_bao",
                "diem_ap_luc",
                "diem_thoi_tiet",
                "diem_ha_tang",
                "diem_co_hoi_kinh_te",
                "diem_dieu_phoi",
                "du_bao_24_gio",
                "du_bao_7_ngay",
                "du_bao_30_ngay",
                "nhiet_do_hien_tai",
                "kha_nang_mua",
                "gio",
                "trang_thai_thoi_tiet_ngan",
                "cap_nhat_thoi_tiet_luc",
                "loai_du_lieu",
                "do_tin_cay",
                "ly_do_xep_hang",
                "hanh_dong_de_xuat",
                "hieu_qua_kinh_te_du_kien",
                "cap_nhat_lan_cuoi",
            ]
        ]

    proxy = tables.get("proxy_vs_nearrealtime_comparison", pd.DataFrame())
    if not proxy.empty:
        out["kiem_dinh_proxy"] = proxy.rename(
            columns={
                "ten_diem_den": "ten_diem_den",
                "metric_name": "ten_chi_so",
                "proxy_score": "diem_proxy",
                "near_realtime_score": "diem_near_realtime",
                "absolute_error": "do_lech_tuyet_doi",
                "percentage_error": "do_lech_phan_tram",
                "reliability_label": "muc_danh_gia",
                "confidence_before": "do_tin_cay_truoc",
                "confidence_after": "do_tin_cay_sau",
                "data_used_proxy": "nguon_proxy",
                "data_used_nearrealtime": "nguon_near_realtime",
                "last_updated": "cap_nhat_lan_cuoi",
                "method_note": "giai_thich",
            }
        )[
            [
                "ten_diem_den",
                "ten_chi_so",
                "diem_proxy",
                "diem_near_realtime",
                "do_lech_tuyet_doi",
                "do_lech_phan_tram",
                "muc_danh_gia",
                "do_tin_cay_truoc",
                "do_tin_cay_sau",
                "nguon_proxy",
                "nguon_near_realtime",
                "cap_nhat_lan_cuoi",
                "giai_thich",
            ]
        ]

    actions = tables.get("economic_action_recommendations", pd.DataFrame())
    if not actions.empty:
        out["de_xuat_hieu_qua_kinh_te"] = actions.rename(
            columns={
                "chi_phi_trien_khai": "chi_phi_uoc_tinh",
                "loi_ich_ky_vong": "loi_ich_ky_vong",
                "du_lieu_dung": "du_lieu_chung_minh",
            }
        )
        out["de_xuat_hieu_qua_kinh_te"]["cap_nhat_lan_cuoi"] = format_vn_time()
        out["de_xuat_hieu_qua_kinh_te"] = out["de_xuat_hieu_qua_kinh_te"][
            [
                "diem_den",
                "van_de",
                "hanh_dong",
                "doi_tuong_thuc_hien",
                "chi_phi_uoc_tinh",
                "loi_ich_ky_vong",
                "logic_kinh_te",
                "kpi_do_luong",
                "diem_tac_dong_kinh_te",
                "diem_kha_thi",
                "diem_khan_cap",
                "diem_uu_tien",
                "muc_uu_tien",
                "du_lieu_chung_minh",
                "do_tin_cay",
                "cap_nhat_lan_cuoi",
            ]
        ]

    source_status = tables.get("source_monitor_status", pd.DataFrame())
    if not source_status.empty:
        out["trang_thai_nguon_du_lieu"] = source_status.rename(
            columns={
                "source_id": "ma_nguon",
                "source_url": "duong_dan_nguon",
                "lan_kiem_tra_cuoi": "kiem_tra_lan_cuoi",
                "lan_cap_nhat_thanh_cong_cuoi": "cap_nhat_thanh_cong_lan_cuoi",
                "dataset_cap_nhat": "dataset_bi_anh_huong",
            }
        )
    update_queue = tables.get("update_queue", pd.DataFrame())
    if not update_queue.empty:
        out["hang_cho_cap_nhat"] = update_queue.rename(columns={"source_id": "ma_nguon", "ten_nguon": "ten_nguon"})
    return out


def write_logs(tables: dict[str, pd.DataFrame], status: str = "ok", error: str = "") -> None:
    fieldnames = [
        "run_time",
        "timezone",
        "step",
        "status",
        "rows",
        "current_path",
        "archive_path",
        "google_sheets_summary_da_sync",
        "note",
        "error",
    ]
    for log_path in [LOGS / "pipeline_run_log.csv", META / "pipeline_run_log.csv"]:
        exists = log_path.exists()
        with log_path.open("a", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            if not exists:
                writer.writeheader()
            for name, df in tables.items():
                writer.writerow(
                    {
                        "run_time": format_vn_time(),
                        "timezone": "Việt Nam",
                        "step": name,
                        "status": status,
                        "rows": len(df),
                        "current_path": (CURRENT / f"{name}.csv").relative_to(ROOT).as_posix(),
                        "archive_path": LAST_ARCHIVE_DIR.relative_to(ROOT).as_posix() if LAST_ARCHIVE_DIR else "",
                        "google_sheets_summary_da_sync": "chưa sync trong bản local; chỉ sync khi cấu hình GOOGLE_SHEETS_ID và connector/job tương ứng",
                        "note": "SEA operating pipeline: archive current cũ, rebuild KPI/forecast/ranking/recommendation/AI knowledge base.",
                        "error": error,
                    }
                )
    if (META / "pipeline_run_log.csv").exists():
        log_df = read_csv(META / "pipeline_run_log.csv")
        log_df.rename(
            columns={
                "run_time": "thoi_gian_chay",
                "timezone": "mui_gio",
                "step": "buoc_pipeline",
                "status": "trang_thai",
                "rows": "so_dong",
                "current_path": "duong_dan_current",
                "archive_path": "duong_dan_archive",
                "note": "ghi_chu",
            }
        ).to_csv(META / "nhat_ky_pipeline.csv", index=False, encoding="utf-8-sig")


def main() -> None:
    ensure_dirs()
    env = load_env()
    source_status, update_queue = write_source_monitor_files(env)
    tables: dict[str, pd.DataFrame] = {}
    try:
        expanded_destinations = build_destination_registry()
        archive_current()
        write_metadata_tables(env)
        source_status, update_queue = write_source_monitor_files(env)
        kpi = build_kpi_methodology_files()
        tables = build_operating_tables()
        tables["kpi_scale_catalog"] = kpi
        tables["source_monitor_status"] = source_status
        tables["update_queue"] = update_queue
        tables["danh_sach_diem_den_mo_rong"] = expanded_destinations
        tables.update(build_vietnamese_summary_tables(tables))
        for name, df in tables.items():
            if name in {"news_seen_registry", "news_event_taxonomy", "source_monitor_status", "update_queue", "trang_thai_nguon_du_lieu", "hang_cho_cap_nhat"}:
                df.to_csv(META / f"{name}.csv", index=False, encoding="utf-8-sig")
            else:
                write_table(df, name)
        write_current_freshness_status(tables, source_status, env)
        write_excel_summary(tables)
        sheet_status = sync_google_sheets_summary(env)
        tables["google_sheets_sync_status"] = sheet_status
        write_logs(tables)
        print(json.dumps({"status": "ok", "updated": now_vn(), "tables": {k: len(v) for k, v in tables.items()}}, ensure_ascii=False, indent=2))
    except Exception as exc:
        if tables:
            write_logs(tables, status="error", error=str(exc))
        else:
            error_row = pd.DataFrame([{"error": str(exc)}])
            write_logs({"pipeline_error": error_row}, status="error", error=str(exc))
        raise


if __name__ == "__main__":
    main()
