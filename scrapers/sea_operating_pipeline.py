from __future__ import annotations

import csv
import json
import math
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - pipeline still works without python-dotenv
    load_dotenv = None

from build_destination_registry import build_destination_registry


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
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
VN_ZONE = ZoneInfo("Asia/Ho_Chi_Minh")

SUPPORTED_ENV_KEYS = [
    "POSITIONSTACK_API_KEY",
    "OPENROUTESERVICE_API_KEY",
    "RAPIDAPI_KEY",
    "RAPIDAPI_SERP_HOST",
    "RAPIDAPI_GOOGLE_MAPS_HOST",
    "RAPIDAPI_GOOGLE_PLACES_HOST",
    "OPEN_METEO",
    "GOOGLE_SHEETS_ID",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "SYNC_FULL_DATA_TO_SHEETS",
    "GEMINI_API_KEY",
    "AI_PROVIDER",
    "GEMINI_MODEL",
]


SHEET_SUMMARY_TABLES = [
    ("Ranking toÃ n quá»‘c", CURRENT / "xep_hang_canh_bao_toan_quoc.csv"),
    ("Dá»± bÃ¡o", CURRENT / "forecast_demand_scores.csv"),
    ("Tráº¡ng thÃ¡i dá»¯ liá»‡u", META / "data_freshness_status.csv"),
    ("Dá»¯ liá»‡u má»›i cáº­p nháº­t", META / "source_monitor_status.csv"),
    ("Dá»¯ liá»‡u cÅ© gáº§n Ä‘Ã¢y", META / "pipeline_run_log.csv"),
    ("Kiá»ƒm Ä‘á»‹nh proxy", CURRENT / "proxy_vs_nearrealtime_comparison.csv"),
    ("Hiá»‡u quáº£ kinh táº¿", CURRENT / "de_xuat_hieu_qua_kinh_te.csv"),
]


def now_vn() -> str:
    return datetime.now(VN_ZONE).strftime("%d/%m/%Y %H:%M")


def today_key() -> str:
    return datetime.now(VN_ZONE).strftime("%Y-%m-%d")


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
        return "xÃ¡m"
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "xÃ¡m"
    if value >= 85:
        return "Ä‘á»"
    if value >= 70:
        return "cam"
    if value >= 40:
        return "vÃ ng"
    return "xanh"


def confidence_label(score: float | int | str | None) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "Tháº¥p"
    if value >= 80:
        return "Cao"
    if value >= 65:
        return "KhÃ¡"
    if value >= 45:
        return "Trung bÃ¬nh"
    return "Tháº¥p"


REGION_LABELS = {
    "central_coast": "DuyÃªn háº£i miá»n Trung",
    "central_coast_islands": "Äáº£o miá»n Trung",
    "central_highlands": "TÃ¢y NguyÃªn",
    "mekong_delta": "Äá»“ng báº±ng sÃ´ng Cá»­u Long",
    "mekong_islands": "Äáº£o TÃ¢y Nam Bá»™",
    "northeast": "ÄÃ´ng Báº¯c",
    "north_central_coast": "Báº¯c Trung Bá»™",
    "northern_mountains": "Miá»n nÃºi phÃ­a Báº¯c",
    "red_river_delta": "Äá»“ng báº±ng sÃ´ng Há»“ng",
    "south_central_coast": "Nam Trung Bá»™",
    "southeast": "ÄÃ´ng Nam Bá»™",
    "southeast_islands": "Äáº£o ÄÃ´ng Nam Bá»™",
    "southwest": "TÃ¢y Nam Bá»™",
}

TOURISM_TYPE_LABELS = {
    "coastal": "biá»ƒn",
    "beach": "bÃ£i biá»ƒn",
    "urban": "Ä‘Ã´ thá»‹",
    "heritage": "di sáº£n",
    "island": "Ä‘áº£o",
    "mountain": "nÃºi",
    "nature": "tá»± nhiÃªn",
    "gateway": "cá»­a ngÃµ",
    "mekong": "Mekong",
    "resort": "nghá»‰ dÆ°á»¡ng",
    "culture": "vÄƒn hÃ³a",
    "food": "áº©m thá»±c",
    "attraction": "khu vui chÆ¡i",
    "ticket": "vÃ©/khu vui chÆ¡i",
}


def region_label(value: object) -> str:
    text = str(value).strip()
    if not text:
        return "thiáº¿u dá»¯ liá»‡u"
    return REGION_LABELS.get(text.lower(), text)


def tourism_type_label(value: object) -> str:
    text = str(value).strip()
    if not text:
        return "thiáº¿u dá»¯ liá»‡u"
    parts = [part.strip() for part in text.replace(",", ";").split(";") if part.strip()]
    return "; ".join(TOURISM_TYPE_LABELS.get(part.lower(), part) for part in parts)


def classify_alert(score: float | int | str | None, missing: bool = False) -> str:
    if missing:
        return "xÃ¡m"
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "xÃ¡m"
    if value >= 85:
        return "Ä‘á»"
    if value >= 70:
        return "cam"
    if value >= 40:
        return "vÃ ng"
    return "xanh"


def confidence_label(score: float | int | str | None) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "Tháº¥p"
    if value >= 80:
        return "Cao"
    if value >= 65:
        return "KhÃ¡"
    if value >= 45:
        return "Trung bÃ¬nh"
    return "Tháº¥p"


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
        ("positionstack", "Positionstack", "geocode Ä‘á»‹a chá»‰/POI/khÃ¡ch sáº¡n thÃ nh tá»a Ä‘á»™", "POSITIONSTACK_API_KEY", "partner_api_required"),
        ("rapidapi_serp", "RapidAPI Google SERP", "tÃ¬m tin tá»©c, bÃ¡o cÃ¡o vÃ  tÃ­n hiá»‡u thá»‹ trÆ°á»ng", "RAPIDAPI_KEY", "near_real_time"),
        ("rapidapi_maps", "RapidAPI Google Maps Extractor", "business info, rating, review náº¿u endpoint há»— trá»£", "RAPIDAPI_KEY", "partner_api_required"),
        ("openrouteservice", "OpenRouteService", "routing, travel time, tuyáº¿n Ä‘iá»u phá»‘i", "OPENROUTESERVICE_API_KEY", "near_real_time"),
        ("osm_overpass", "OSM/Overpass", "POI, bÃ£i biá»ƒn, khÃ¡ch sáº¡n, nhÃ  hÃ ng, bÃ£i Ä‘á»—", "", "real_data"),
        ("open_meteo", "Open-Meteo", "thá»i tiáº¿t hiá»‡n táº¡i, dá»± bÃ¡o, lá»‹ch sá»­ thá»i tiáº¿t", "", "near_real_time"),
        ("google_sheets", "Google Sheets", "sync báº£ng summary cho ngÆ°á»i xem nhanh", "GOOGLE_SHEETS_ID", "summary_only"),
    ]
    out = []
    for api_id, name, role, key, data_type in rows:
        configured = "cÃ³" if (not key or env.get(key) or os.getenv(key)) else "thiáº¿u"
        out.append(
            {
                "api_id": api_id,
                "ten_api": name,
                "vai_tro": role,
                "bien_moi_truong": key or "khÃ´ng cáº§n key",
                "trang_thai_cau_hinh": configured,
                "loai_du_lieu": data_type if configured == "cÃ³" else "missing",
                "ghi_chu": "Bá» qua nguá»“n nÃ y náº¿u thiáº¿u key; pipeline khÃ´ng crash.",
            }
        )
    return pd.DataFrame(out)


def format_vn_time(value: datetime | None = None) -> str:
    value = value or datetime.now(VN_ZONE)
    if value.tzinfo is None:
        value = value.replace(tzinfo=VN_ZONE)
    return value.astimezone(VN_ZONE).strftime("%d/%m/%Y %H:%M")


def file_update_time(path: Path) -> str:
    if not path.exists():
        return ""
    return format_vn_time(datetime.fromtimestamp(path.stat().st_mtime, VN_ZONE))


def build_api_catalog(env: dict[str, str]) -> pd.DataFrame:
    rows = [
        ("positionstack", "Positionstack", "Geocode Ä‘á»‹a chá»‰, POI, khÃ¡ch sáº¡n thÃ nh tá»a Ä‘á»™", "POSITIONSTACK_API_KEY", "partner_api_required", "DÃ¹ng tá»a Ä‘á»™ seed/current náº¿u thiáº¿u key."),
        ("openrouteservice", "OpenRouteService", "Routing, travel time, tuyáº¿n Ä‘iá»u phá»‘i", "OPENROUTESERVICE_API_KEY", "near_real_time", "DÃ¹ng OSRM hoáº·c graph proxy náº¿u thiáº¿u key."),
        ("rapidapi_serp", "RapidAPI Google SERP", "TÃ¬m tin tá»©c, bÃ¡o cÃ¡o vÃ  tÃ­n hiá»‡u thá»‹ trÆ°á»ng", "RAPIDAPI_KEY", "near_real_time", "Tin tá»©c dÃ¹ng snapshot/local signal náº¿u thiáº¿u key."),
        ("rapidapi_google_maps", "RapidAPI Google Maps Extractor", "Business info, rating, review náº¿u endpoint há»— trá»£", "RAPIDAPI_KEY", "partner_api_required", "DÃ¹ng OSM/POI current náº¿u thiáº¿u key."),
        ("rapidapi_google_places", "RapidAPI Google Places", "Má»Ÿ rá»™ng POI/Ä‘iá»ƒm Ä‘áº¿n náº¿u cÃ³ host há»£p lá»‡", "RAPIDAPI_KEY", "partner_api_required", "DÃ¹ng seed list vÃ  OSM náº¿u thiáº¿u key."),
        ("osm_overpass", "OSM/Overpass", "POI, bÃ£i biá»ƒn, khÃ¡ch sáº¡n, nhÃ  hÃ ng, bÃ£i Ä‘á»—", "", "real_data", "Nguá»“n má»Ÿ, dÃ¹ng lÃ m fallback báº£n Ä‘á»“/POI."),
        ("open_meteo", "Open-Meteo", "Thá»i tiáº¿t hiá»‡n táº¡i, dá»± bÃ¡o, lá»‹ch sá»­ thá»i tiáº¿t", "", "near_real_time", "Nguá»“n cÃ´ng khai, khÃ´ng cáº§n key."),
        ("google_sheets", "Google Sheets", "Äá»“ng bá»™ báº£ng summary cho ngÆ°á»i xem nhanh", "GOOGLE_SHEETS_ID", "summary_only", "Náº¿u thiáº¿u Google Sheets váº«n táº£i CSV/Excel tá»« dashboard."),
        ("gemini", "Gemini 2.5 Flash", "Trá»£ lÃ½ SEA tráº£ lá»i theo knowledge base", "GEMINI_API_KEY", "ai_provider", "Fallback sang Ollama rá»“i rule-based náº¿u lá»—i."),
    ]
    out = []
    for api_id, name, role, key, data_type, fallback in rows:
        configured = "ÄÃ£ cáº¥u hÃ¬nh" if (not key or env.get(key) or os.getenv(key)) else "Thiáº¿u cáº¥u hÃ¬nh"
        host = ""
        if api_id == "rapidapi_serp":
            host = env.get("RAPIDAPI_SERP_HOST") or os.getenv("RAPIDAPI_SERP_HOST") or "google-serp-search-api.p.rapidapi.com"
        elif api_id == "rapidapi_google_maps":
            host = env.get("RAPIDAPI_GOOGLE_MAPS_HOST") or os.getenv("RAPIDAPI_GOOGLE_MAPS_HOST") or "google-maps-extractor2.p.rapidapi.com"
        elif api_id == "rapidapi_google_places":
            host = env.get("RAPIDAPI_GOOGLE_PLACES_HOST") or os.getenv("RAPIDAPI_GOOGLE_PLACES_HOST") or "chÆ°a cáº¥u hÃ¬nh host"
        elif api_id == "gemini":
            host = env.get("GEMINI_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
        out.append(
            {
                "api_id": api_id,
                "ten_api": name,
                "vai_tro": role,
                "bien_moi_truong": key or "khÃ´ng cáº§n key",
                "trang_thai_cau_hinh": configured,
                "host_hoac_model": host,
                "loai_du_lieu": data_type if configured == "ÄÃ£ cáº¥u hÃ¬nh" else "missing",
                "ket_qua_kiem_tra": "chÆ°a kiá»ƒm tra trong pipeline; báº¥m Kiá»ƒm tra láº¡i API trÃªn dashboard",
                "lan_kiem_tra_cuoi": format_vn_time(),
                "da_doc_cau_hinh_tu": ".env" if ENV_FILE.exists() else "chÆ°a tÃ¬m tháº¥y .env",
                "nguon_thay_the": fallback,
                "ghi_chu": "Náº¿u thiáº¿u cáº¥u hÃ¬nh, SEA bá» qua nguá»“n nÃ y, dÃ¹ng fallback náº¿u cÃ³ vÃ  khÃ´ng lÃ m pipeline crash.",
            }
        )
    return pd.DataFrame(out)


def build_source_monitor_status(env: dict[str, str]) -> pd.DataFrame:
    checked = format_vn_time()
    source_defs = [
        ("vnat_report", "BÃ¡o cÃ¡o du lá»‹ch VNAT", "bÃ¡o cÃ¡o du lá»‹ch", "https://thongke.tourism.vn/", "datasets/raw/vietnam_tourism_statistics", "national_destination_alerts", "", "cao"),
        ("gso_report", "BÃ¡o cÃ¡o GSO", "bÃ¡o cÃ¡o thá»‘ng kÃª", "https://www.gso.gov.vn/", "", "tourism_demand_monthly", "", "trung bÃ¬nh"),
        ("caav_acv_report", "CAAV/ACV", "hÃ ng khÃ´ng", "https://caa.gov.vn/;https://vietnamairport.vn/", "datasets/raw/transport", "flight_price_signal", "", "cao"),
        ("flight_price", "Dá»¯ liá»‡u vÃ© mÃ¡y bay", "giÃ¡ vÃ© mÃ¡y bay", "", "", "flight_price_signal", "RAPIDAPI_KEY", "trung bÃ¬nh"),
        ("attraction_ticket", "VÃ© khu vui chÆ¡i", "giÃ¡ vÃ©", "datasets/raw/tickets", "datasets/raw/tickets", "attraction_ticket_catalog;ticket_pressure_scores", "", "cao"),
        ("hotel_price", "GiÃ¡ khÃ¡ch sáº¡n", "giÃ¡ khÃ¡ch sáº¡n", "datasets/booking;datasets/traveloka", "datasets/booking", "hotel_price_pressure", "", "cao"),
        ("tourism_news", "Tin tá»©c du lá»‹ch", "tin tá»©c", "Google SERP/RapidAPI náº¿u cÃ³ key", "datasets/raw/news", "news_events;news_risk_signals", "RAPIDAPI_KEY", "cao"),
        ("weather_risk", "Tin thá»i tiáº¿t/rá»§i ro", "thá»i tiáº¿t", "https://open-meteo.com/", "datasets/raw/weather", "forecast_demand_scores;national_destination_alerts", "", "cao"),
        ("traffic_news", "Tin giao thÃ´ng/káº¹t xe/sáº¡t lá»Ÿ", "giao thÃ´ng", "Google SERP/RapidAPI náº¿u cÃ³ key", "datasets/raw/search_results", "redistribution_features;national_destination_alerts", "RAPIDAPI_KEY", "cao"),
        ("event_festival", "Sá»± kiá»‡n/lá»… há»™i", "sá»± kiá»‡n", "Google SERP/RapidAPI náº¿u cÃ³ key", "datasets/raw/news", "news_events;forecast_demand_scores", "RAPIDAPI_KEY", "trung bÃ¬nh"),
        ("google_serp", "Google SERP Search", "tÃ¬m kiáº¿m/tin tá»©c", env.get("RAPIDAPI_SERP_HOST", "google-serp-search-api.p.rapidapi.com"), "datasets/raw/search_results", "news_events", "RAPIDAPI_KEY", "cao"),
        ("rapidapi_google_maps", "RapidAPI Google Maps Extractor", "POI/rating/review", env.get("RAPIDAPI_GOOGLE_MAPS_HOST", "google-maps-extractor2.p.rapidapi.com"), "datasets/raw/api", "local_spending_poi;attraction_ticket_catalog", "RAPIDAPI_KEY", "trung bÃ¬nh"),
        ("open_meteo", "Open-Meteo", "thá»i tiáº¿t near-real-time", "https://api.open-meteo.com/", "datasets/raw/weather/open_meteo_forecast", "forecast_demand_scores;national_destination_alerts", "", "cao"),
        ("osm_overpass", "OSM/Overpass", "POI/báº£n Ä‘á»“", "https://overpass-api.de/api/interpreter", "datasets/raw/geospatial/overpass", "local_spending_poi;attraction_ticket_catalog", "", "trung bÃ¬nh"),
        ("positionstack", "Positionstack", "geocoding", "https://positionstack.com/", "datasets/raw/api", "destination_registry;local_spending_poi", "POSITIONSTACK_API_KEY", "trung bÃ¬nh"),
        ("ors_osrm", "OpenRouteService/OSRM", "routing/travel time", "https://openrouteservice.org/;https://router.project-osrm.org/", "datasets/raw/mobility/osrm", "redistribution_features", "", "cao"),
        ("google_sheets", "Google Sheets summary", "báº£ng tá»•ng há»£p", "GOOGLE_SHEETS_ID", "", "source_monitor_status;data_freshness_status;dataset_audit;national_destination_alerts", "GOOGLE_SERVICE_ACCOUNT_JSON", "cao"),
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
            status = "thiáº¿u API key"
            new_data = "KhÃ´ng"
            new_items = 0
            action = f"cáº¥u hÃ¬nh {key} trong .env hoáº·c GitHub Secrets"
        elif not url and not raw_rel:
            status = "chÆ°a cáº¥u hÃ¬nh nguá»“n"
            new_data = "KhÃ´ng"
            new_items = 0
            action = "bá»• sung URL/API há»£p lá»‡ trÆ°á»›c khi cáº­p nháº­t"
        elif has_raw or current_times:
            status = "má»›i nháº¥t"
            new_data = "KhÃ´ng"
            new_items = 0
            action = "khÃ´ng cáº§n; theo dÃµi Ä‘á»‹nh ká»³"
        else:
            status = "cáº§n kiá»ƒm tra"
            new_data = "ChÆ°a rÃµ"
            new_items = 0
            action = "kiá»ƒm tra nguá»“n trÆ°á»›c khi Ä‘Æ°a vÃ o update_queue"

        if source_id == "google_sheets":
            if has_key:
                status = "cáº§n kiá»ƒm tra"
                action = "sync cÃ¡c báº£ng summary lÃªn Google Sheets sau khi pipeline thÃ nh cÃ´ng"
            else:
                action = "chÆ°a sync vÃ¬ thiáº¿u GOOGLE_SHEETS_ID hoáº·c Google credentials"

        rows.append(
            {
                "source_id": source_id,
                "ten_nguon": name,
                "loai_du_lieu": data_type,
                "source_url": url or "chÆ°a cáº¥u hÃ¬nh nguá»“n",
                "lan_kiem_tra_cuoi": checked,
                "lan_cap_nhat_thanh_cong_cuoi": last_success,
                "co_du_lieu_moi": new_data,
                "so_item_moi": new_items,
                "ngay_bai_hoac_bao_cao_moi_nhat": last_success,
                "trang_thai": status,
                "hanh_dong_can_lam": action,
                "dataset_cap_nhat": dataset,
                "muc_uu_tien": priority,
                "ghi_chu": "KhÃ´ng gá»i dá»¯ liá»‡u má»›i náº¿u chÆ°a cÃ³ API/key há»£p lá»‡; khÃ´ng gá»i proxy lÃ  realtime.",
            }
        )
    return pd.DataFrame(rows)


def build_source_monitor_status(env: dict[str, str]) -> pd.DataFrame:
    checked = format_vn_time()
    source_defs = [
        ("vnat_report", "BÃ¡o cÃ¡o du lá»‹ch VNAT", "bÃ¡o cÃ¡o du lá»‹ch", "https://thongke.tourism.vn/", "datasets/raw/vietnam_tourism_statistics", "national_destination_alerts", "", "cao"),
        ("gso_report", "BÃ¡o cÃ¡o GSO", "bÃ¡o cÃ¡o thá»‘ng kÃª", "https://www.gso.gov.vn/", "", "tourism_demand_monthly", "", "trung bÃ¬nh"),
        ("caav_acv_report", "CAAV/ACV", "hÃ ng khÃ´ng", "https://caa.gov.vn/;https://vietnamairport.vn/", "datasets/raw/transport", "flight_price_signal", "", "cao"),
        ("flight_price", "Dá»¯ liá»‡u vÃ© mÃ¡y bay", "giÃ¡ vÃ© mÃ¡y bay", "", "", "flight_price_signal", "RAPIDAPI_KEY", "trung bÃ¬nh"),
        ("attraction_ticket", "VÃ© khu vui chÆ¡i", "giÃ¡ vÃ©", "datasets/raw/tickets", "datasets/raw/tickets", "attraction_ticket_catalog;ticket_pressure_scores", "", "cao"),
        ("hotel_price", "GiÃ¡ khÃ¡ch sáº¡n", "giÃ¡ khÃ¡ch sáº¡n", "datasets/booking;datasets/traveloka", "datasets/booking", "hotel_price_pressure", "", "cao"),
        ("tourism_news", "Tin tá»©c du lá»‹ch", "tin tá»©c", "Google SERP/RapidAPI náº¿u cÃ³ key", "datasets/raw/news", "news_events;news_risk_signals", "RAPIDAPI_KEY", "cao"),
        ("weather_risk", "Tin thá»i tiáº¿t/rá»§i ro", "thá»i tiáº¿t", "https://open-meteo.com/", "datasets/raw/weather", "forecast_demand_scores;national_destination_alerts", "", "cao"),
        ("traffic_news", "Tin giao thÃ´ng/káº¹t xe/sáº¡t lá»Ÿ", "giao thÃ´ng", "Google SERP/RapidAPI náº¿u cÃ³ key", "datasets/raw/search_results", "redistribution_features;national_destination_alerts", "RAPIDAPI_KEY", "cao"),
        ("event_festival", "Sá»± kiá»‡n/lá»… há»™i", "sá»± kiá»‡n", "Google SERP/RapidAPI náº¿u cÃ³ key", "datasets/raw/news", "news_events;forecast_demand_scores", "RAPIDAPI_KEY", "trung bÃ¬nh"),
        ("google_serp", "Google SERP Search", "tÃ¬m kiáº¿m/tin tá»©c", env.get("RAPIDAPI_SERP_HOST", "google-serp-search-api.p.rapidapi.com"), "datasets/raw/search_results", "news_events", "RAPIDAPI_KEY", "cao"),
        ("rapidapi_google_maps", "RapidAPI Google Maps Extractor", "POI/rating/review", env.get("RAPIDAPI_GOOGLE_MAPS_HOST", "google-maps-extractor2.p.rapidapi.com"), "datasets/raw/api", "local_spending_poi;attraction_ticket_catalog", "RAPIDAPI_KEY", "trung bÃ¬nh"),
        ("rapidapi_google_places", "RapidAPI Google Places", "POI/Ä‘iá»ƒm Ä‘áº¿n", env.get("RAPIDAPI_GOOGLE_PLACES_HOST", "chÆ°a cáº¥u hÃ¬nh host"), "datasets/raw/api", "danh_sach_diem_den_mo_rong;local_spending_poi", "RAPIDAPI_KEY", "trung bÃ¬nh"),
        ("open_meteo", "Open-Meteo", "thá»i tiáº¿t near-realtime", "https://api.open-meteo.com/", "datasets/raw/weather/open_meteo_forecast", "forecast_demand_scores;national_destination_alerts", "", "cao"),
        ("osm_overpass", "OSM/Overpass", "POI/báº£n Ä‘á»“", "https://overpass-api.de/api/interpreter", "datasets/raw/geospatial/overpass", "local_spending_poi;attraction_ticket_catalog", "", "trung bÃ¬nh"),
        ("positionstack", "Positionstack", "geocoding", "https://positionstack.com/", "datasets/raw/api", "destination_registry;local_spending_poi", "POSITIONSTACK_API_KEY", "trung bÃ¬nh"),
        ("ors_osrm", "OpenRouteService/OSRM", "routing/travel time", "https://openrouteservice.org/;https://router.project-osrm.org/", "datasets/raw/mobility/osrm", "redistribution_features", "", "cao"),
        ("google_sheets", "Google Sheets summary", "báº£ng tá»•ng há»£p", "GOOGLE_SHEETS_ID", "", "source_monitor_status;data_freshness_status;dataset_audit;national_destination_alerts", "GOOGLE_SERVICE_ACCOUNT_JSON", "cao"),
        ("gemini", "Gemini 2.5 Flash", "AI/RAG", "GEMINI_MODEL=gemini-2.5-flash", "", "rag/sea_knowledge_base.md", "GEMINI_API_KEY", "trung bÃ¬nh"),
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
            status = "thiáº¿u API key"
            new_data = "KhÃ´ng"
            new_items = 0
            action = f"cáº¥u hÃ¬nh {key} trong .env hoáº·c GitHub Secrets"
        elif not url and not raw_rel:
            status = "chÆ°a cáº¥u hÃ¬nh nguá»“n"
            new_data = "KhÃ´ng"
            new_items = 0
            action = "bá»• sung URL/API há»£p lá»‡ trÆ°á»›c khi cáº­p nháº­t"
        elif has_raw or current_times:
            status = "má»›i nháº¥t"
            new_data = "KhÃ´ng"
            new_items = 0
            action = "khÃ´ng cáº§n; theo dÃµi Ä‘á»‹nh ká»³"
        else:
            status = "cáº§n kiá»ƒm tra"
            new_data = "ChÆ°a rÃµ"
            new_items = 0
            action = "kiá»ƒm tra nguá»“n trÆ°á»›c khi Ä‘Æ°a vÃ o hÃ ng chá» cáº­p nháº­t"

        if source_id == "google_sheets":
            action = "Ä‘á»“ng bá»™ cÃ¡c báº£ng summary lÃªn Google Sheets sau khi pipeline thÃ nh cÃ´ng" if has_key else "chÆ°a sync vÃ¬ thiáº¿u GOOGLE_SHEETS_ID hoáº·c Google credentials"
        if source_id == "gemini":
            action = "dÃ¹ng Gemini náº¿u cÃ³ key; fallback sang Ollama rá»“i rule-based náº¿u lá»—i"

        rows.append(
            {
                "source_id": source_id,
                "ten_nguon": name,
                "loai_du_lieu": data_type,
                "source_url": url or "chÆ°a cáº¥u hÃ¬nh nguá»“n",
                "lan_kiem_tra_cuoi": checked,
                "lan_cap_nhat_thanh_cong_cuoi": last_success,
                "co_du_lieu_moi": new_data,
                "so_item_moi": new_items,
                "ngay_bai_hoac_bao_cao_moi_nhat": last_success,
                "trang_thai": status,
                "hanh_dong_can_lam": action,
                "dataset_cap_nhat": dataset,
                "muc_uu_tien": priority,
                "ghi_chu": "KhÃ´ng gá»i dá»¯ liá»‡u má»›i náº¿u chÆ°a cÃ³ API/key há»£p lá»‡; khÃ´ng gá»i proxy lÃ  realtime.",
            }
        )
    return pd.DataFrame(rows)


def build_update_queue(source_status: pd.DataFrame) -> pd.DataFrame:
    queued = source_status[
        source_status["trang_thai"].isin(["cÃ³ dá»¯ liá»‡u má»›i chá» cáº­p nháº­t", "cáº§n kiá»ƒm tra", "Ä‘ang lá»—i"])
        | source_status["co_du_lieu_moi"].isin(["CÃ³", "ChÆ°a rÃµ"])
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
            "trang_thai_queue": queued["trang_thai"].map(lambda x: "chá» xá»­ lÃ½" if x != "thiáº¿u API key" else "bá»‹ cháº·n do thiáº¿u API key"),
            "tao_luc": format_vn_time(),
            "ghi_chu": "Khi báº¥m Cáº­p nháº­t dá»¯ liá»‡u, SEA Ä‘á»c queue nÃ y, archive current cÅ©, rebuild báº£ng tá»•ng há»£p vÃ  giá»¯ báº£n á»•n Ä‘á»‹nh náº¿u lá»—i.",
        }
    )


def build_update_queue(source_status: pd.DataFrame) -> pd.DataFrame:
    queued = source_status[
        source_status["trang_thai"].isin(["cÃ³ dá»¯ liá»‡u má»›i chá» cáº­p nháº­t", "cáº§n kiá»ƒm tra", "Ä‘ang lá»—i"])
        | source_status["co_du_lieu_moi"].isin(["CÃ³", "ChÆ°a rÃµ"])
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
            "trang_thai_queue": queued["trang_thai"].map(lambda x: "chá» xá»­ lÃ½" if x != "thiáº¿u API key" else "bá»‹ cháº·n do thiáº¿u API key"),
            "tao_luc": format_vn_time(),
            "ghi_chu": "Khi báº¥m Cáº­p nháº­t dá»¯ liá»‡u, SEA Ä‘á»c queue nÃ y, archive current cÅ©, rebuild báº£ng tá»•ng há»£p vÃ  giá»¯ báº£n á»•n Ä‘á»‹nh náº¿u lá»—i.",
        }
    )
    return out[columns]


def weather_risk_score(temp: float | None, rain: float | None, wind: float | None, humidity: float | None) -> float:
    temp = 28.0 if temp is None or pd.isna(temp) else float(temp)
    rain = 0.0 if rain is None or pd.isna(rain) else float(rain)
    wind = 0.0 if wind is None or pd.isna(wind) else float(wind)
    humidity = 75.0 if humidity is None or pd.isna(humidity) else float(humidity)
    heat_risk = max(0.0, temp - 31.0) * 7.0
    heavy_rain_risk = min(45.0, rain * 6.0)
    wind_risk = min(35.0, wind * 1.35)
    humidity_risk = max(0.0, humidity - 85.0) * 1.2
    return round(min(100.0, heat_risk + heavy_rain_risk + wind_risk + humidity_risk), 2)


def weather_status_short(temp: float | None, rain: float | None, wind: float | None) -> str:
    if temp is None and rain is None and wind is None:
        return "thiếu dữ liệu"
    if rain is not None and rain >= 8:
        return "Mưa đáng chú ý"
    if wind is not None and wind >= 35:
        return "Gió mạnh"
    if temp is not None and temp >= 35:
        return "Nắng nóng"
    return "Ổn định"


def refresh_open_meteo_weather(destinations: pd.DataFrame, fallback: pd.DataFrame) -> pd.DataFrame:
    needed = {"destination_id", "lat", "lng"}
    if destinations.empty or not needed.issubset(destinations.columns):
        return fallback

    rows: list[dict[str, object]] = []
    clean = destinations.dropna(subset=["lat", "lng"]).copy()
    if clean.empty:
        return fallback

    endpoint = (os.getenv("OPEN_METEO") or "https://api.open-meteo.com/v1/forecast").strip()
    if "?" in endpoint:
        endpoint = endpoint.split("?", 1)[0]
    endpoint = endpoint or "https://api.open-meteo.com/v1/forecast"

    for start in range(0, len(clean), 50):
        chunk = clean.iloc[start : start + 50]
        params = {
            "latitude": ",".join(chunk["lat"].astype(str)),
            "longitude": ",".join(chunk["lng"].astype(str)),
            "current": "temperature_2m,precipitation,rain,wind_speed_10m,relative_humidity_2m",
            "timezone": "Asia/Ho_Chi_Minh",
        }
        try:
            response = requests.get(endpoint, params=params, timeout=25)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return fallback

        items = payload if isinstance(payload, list) else [payload]
        for (_, dest_row), item in zip(chunk.iterrows(), items):
            current = item.get("current", {}) if isinstance(item, dict) else {}
            temp = current.get("temperature_2m")
            rain = current.get("precipitation", current.get("rain"))
            wind = current.get("wind_speed_10m")
            humidity = current.get("relative_humidity_2m")
            rows.append(
                {
                    "destination_id": dest_row["destination_id"],
                    "weather_risk_score": weather_risk_score(temp, rain, wind, humidity),
                    "temperature_2m": temp,
                    "precipitation": rain,
                    "rain": current.get("rain", rain),
                    "wind_speed_10m": wind,
                    "relative_humidity_2m": humidity,
                    "weather_status_short": weather_status_short(temp, rain, wind),
                    "collection_time": now_vn(),
                }
            )

    fresh = pd.DataFrame(rows)
    if fresh.empty:
        return fallback
    raw_dir = DATASETS / "raw" / "weather" / "open_meteo_current"
    raw_dir.mkdir(parents=True, exist_ok=True)
    fresh.to_csv(raw_dir / f"current_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv", index=False, encoding="utf-8-sig")
    return fresh


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
                "dung_cho_kpi_nao": "KPI váº­n hÃ nh SEA náº¿u Ä‘Ã£ qua silver/gold; raw dÃ¹ng lÃ m báº±ng chá»©ng nguá»“n.",
                "gioi_han_du_lieu": "Cáº§n Ä‘á»c catalog chi tiáº¿t; khÃ´ng xem schema-only lÃ  dá»¯ liá»‡u tháº­t.",
                "can_cap_nhat_khong": "cÃ³" if kind in {"near_real_time", "missing"} else "theo lá»‹ch",
                "tooltip_giai_thich": "Báº£ng audit tá»± Ä‘á»™ng tá»« file trong repo, phÃ¢n loáº¡i tháº­n trá»ng theo thÆ° má»¥c.",
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
    quality["operational_readiness"] = quality["loai_du_lieu"].map(lambda x: "sáºµn sÃ ng má»™t pháº§n" if x in {"real_data", "mixed"} else "cáº§n bá»• sung")
    if not quality_old.empty:
        for col in quality.columns:
            if col not in quality_old.columns:
                quality_old[col] = ""
        quality = pd.concat([quality_old[quality.columns], quality], ignore_index=True).drop_duplicates("dataset_id", keep="last")

    freshness = audit[["dataset_id", "ten_tieng_viet", "duong_dan", "ngay_cap_nhat", "loai_du_lieu"]].copy()
    freshness["trang_thai_do_moi"] = freshness["loai_du_lieu"].map(lambda x: "má»›i" if x in {"real_data", "near_real_time"} else "cáº§n kiá»ƒm tra")
    freshness["ghi_chu"] = "Thá»i gian lÃ  má»‘c file trong repo; realtime/near-real-time Ä‘Æ°á»£c ghi rÃµ theo nguá»“n."

    missing = pd.DataFrame(
        [
            ["traffic_realtime", "Máº­t Ä‘á»™ giao thÃ´ng theo tuyáº¿n vÃ o Ä‘iá»ƒm Ä‘áº¿n", "partner_api_required", "Cáº§n API giao thÃ´ng/Ä‘á»‘i tÃ¡c Ä‘á»‹a phÆ°Æ¡ng", "Äiá»ƒm Ã¡p lá»±c, Ä‘iá»u phá»‘i"],
            ["crowd_density", "Máº­t Ä‘á»™ khÃ¡ch theo giá» táº¡i bÃ£i biá»ƒn/POI", "partner_api_required", "Cáº§n camera/IoT/telco/Ä‘á»‘i tÃ¡c", "Cáº£nh bÃ¡o quÃ¡ táº£i"],
            ["hotel_occupancy", "CÃ´ng suáº¥t phÃ²ng khÃ¡ch sáº¡n", "partner_api_required", "Cáº§n PMS/OTA partner API", "Ãp lá»±c lÆ°u trÃº, dá»± bÃ¡o"],
            ["ticket_sales_velocity", "Tá»‘c Ä‘á»™ bÃ¡n vÃ© khu vui chÆ¡i", "partner_api_required", "Cáº§n API khu vui chÆ¡i", "Ãp lá»±c vÃ© vÃ  chia khung giá»"],
            ["marine_warning", "SÃ³ng, dÃ²ng cháº£y, cáº£nh bÃ¡o bÃ£o biá»ƒn", "missing", "Cáº§n nguá»“n khÃ­ tÆ°á»£ng biá»ƒn chÃ­nh thá»©c", "Rá»§i ro thá»i tiáº¿t biá»ƒn"],
            ["tourism_revenue_local", "Doanh thu theo Ä‘iá»ƒm Ä‘áº¿n/ngÃ nh", "missing", "Cáº§n thá»‘ng kÃª Ä‘á»‹a phÆ°Æ¡ng hoáº·c Ä‘á»‘i tÃ¡c thanh toÃ¡n", "Hiá»‡u quáº£ kinh táº¿"],
        ],
        columns=["dataset_id", "ten_tieng_viet", "loai_du_lieu", "ly_do_thieu", "dung_cho_kpi_nao"],
    )
    missing["do_tin_cay_hien_tai"] = 0
    missing["tooltip_giai_thich"] = "SEA váº«n hiá»ƒn thá»‹ nhÆ°ng Ä‘Ã¡nh mÃ u xÃ¡m/Ä‘á»™ tin cáº­y tháº¥p cho pháº§n thiáº¿u nguá»“n nÃ y."

    source_catalog = audit[["dataset_id", "ten_tieng_viet", "nguon", "source_url", "loai_du_lieu", "tooltip_giai_thich"]].copy()
    return audit, quality, freshness, missing, source_catalog


def build_kpi_methodology_files() -> pd.DataFrame:
    kpis = [
        ("destination_pressure", "Äiá»ƒm Ã¡p lá»±c Ä‘iá»ƒm Ä‘áº¿n", "0.35*rá»§i ro thá»i tiáº¿t + 0.25*Ã¡p lá»±c giÃ¡ khÃ¡ch sáº¡n + 0.20*Ä‘á»™ háº¥p dáº«n POI + 0.20*rá»§i ro cao Ä‘iá»ƒm", "DÃ¹ng proxy khi thiáº¿u crowd/occupancy; cáº§n kiá»ƒm Ä‘á»‹nh báº±ng dá»¯ liá»‡u Ä‘á»‘i tÃ¡c.", "Äiá»ƒm cao cáº§n cáº£nh bÃ¡o vÃ  Ä‘iá»u phá»‘i."),
        ("coastal_pressure", "Äiá»ƒm Ã¡p lá»±c ven biá»ƒn", "Äiá»ƒm Ã¡p lá»±c Ä‘iá»ƒm Ä‘áº¿n + 10 náº¿u lÃ  ven biá»ƒn, giá»›i háº¡n 100", "Æ¯u tiÃªn trá»ng tÃ¢m SEA lÃ  du lá»‹ch ven biá»ƒn.", "Äiá»ƒm cao cáº§n phÃ¢n luá»“ng bÃ£i biá»ƒn, bÃ£i Ä‘á»—, shuttle."),
        ("peak_risk", "Äiá»ƒm rá»§i ro cao Ä‘iá»ƒm", "0.60*hotel_price_pressure_proxy + 0.40*POI attractiveness", "GiÃ¡/phá»§ dá»‹ch vá»¥ lÃ  proxy cho sá»©c hÃºt vÃ  Ã¡p lá»±c mÃ¹a cao Ä‘iá»ƒm.", "DÃ¹ng Ä‘á»ƒ chia khung giá» vÃ  kÃ­ch hoáº¡t Ä‘iá»ƒm thay tháº¿."),
        ("weather_risk", "Äiá»ƒm rá»§i ro thá»i tiáº¿t", "Open-Meteo: mÆ°a, giÃ³, UV vÃ  mÃ£ thá»i tiáº¿t quy Ä‘á»•i 0-100", "KhÃ´ng thay tháº¿ cáº£nh bÃ¡o khÃ­ tÆ°á»£ng biá»ƒn chÃ­nh thá»©c.", "Äiá»ƒm cao cáº§n cáº£nh bÃ¡o an toÃ n vÃ  trÃ¡nh Ä‘áº©y khÃ¡ch."),
        ("ticket_pressure", "Äiá»ƒm Ã¡p lá»±c vÃ©/khu vui chÆ¡i", "Proxy tá»« máº­t Ä‘á»™ POI attraction vÃ  tráº¡ng thÃ¡i nguá»“n vÃ©", "Thiáº¿u API bÃ¡n vÃ© nÃªn khÃ´ng gá»i lÃ  realtime.", "Äiá»ƒm cao cáº§n vÃ© theo khung giá»/QR/nhÃ¢n sá»± soÃ¡t vÃ©."),
        ("infrastructure_readiness", "Äiá»ƒm sáºµn sÃ ng háº¡ táº§ng", "0.45*service POI + 0.25*khÃ¡ch sáº¡n + 0.20*accessibility + 0.10*data quality", "Proxy cho nÄƒng lá»±c tiáº¿p nháº­n khi thiáº¿u háº¡ táº§ng thá»±c Ä‘á»‹a.", "Äiá»ƒm tháº¥p khÃ´ng nÃªn Ä‘áº©y khÃ¡ch Ä‘áº¡i trÃ ."),
        ("economic_opportunity", "Äiá»ƒm cÆ¡ há»™i kinh táº¿", "0.40*dÆ° Ä‘á»‹a háº¡ táº§ng + 0.25*Ä‘á»™ háº¥p dáº«n + 0.20*chi tiÃªu Ä‘á»‹a phÆ°Æ¡ng + 0.15*kháº£ nÄƒng Ä‘iá»u phá»‘i", "Æ¯u tiÃªn Ä‘iá»ƒm cÃ³ thá»ƒ tÄƒng chi tiÃªu mÃ  khÃ´ng quÃ¡ táº£i.", "Äiá»ƒm cao phÃ¹ há»£p combo, OCOP, lÆ°u trÃº liÃªn vÃ¹ng."),
        ("redistribution", "Äiá»ƒm Ä‘iá»u phá»‘i khÃ¡ch", "Tá»« graph tuyáº¿n: accessibility, weather suitability, capacity proxy, satisfaction", "KhÃ´ng pháº£i Ä‘iá»u phá»‘i realtime náº¿u thiáº¿u traffic/crowd.", "Äiá»ƒm cao lÃ  tuyáº¿n Ä‘á» xuáº¥t Ä‘iá»u phá»‘i."),
        ("investment_priority", "Äiá»ƒm Æ°u tiÃªn Ä‘áº§u tÆ°", "0.40*cÆ¡ há»™i kinh táº¿ + 0.35*(100-háº¡ táº§ng) + 0.25*Ã¡p lá»±c", "Äáº§u tÆ° nÆ¡i vá»«a cÃ³ nhu cáº§u vá»«a ngháº½n háº¡ táº§ng.", "DÃ¹ng cho bÃ£i Ä‘á»—, shuttle, vá»‡ sinh, biá»ƒn chá»‰ dáº«n."),
        ("destination_health", "Äiá»ƒm sá»©c khá»e Ä‘iá»ƒm Ä‘áº¿n", "100 - 0.45*Ã¡p lá»±c - 0.25*thá»i tiáº¿t + 0.30*háº¡ táº§ng", "Sá»©c khá»e giáº£m khi Ã¡p lá»±c/rá»§i ro cao.", "Äiá»ƒm tháº¥p cáº§n giáº£m quáº£ng bÃ¡ vÃ  tÄƒng báº£o vá»‡ mÃ´i trÆ°á»ng."),
    ]
    df = pd.DataFrame(
        kpis,
        columns=["kpi_id", "ten_kpi", "cong_thuc", "vi_sao_hop_ly", "y_nghia_van_hanh"],
    )
    df["thang_do"] = "0-100"
    df["nguong_mau"] = "0-39 xanh, 40-69 vÃ ng, 70-84 cam, 85-100 Ä‘á»; riÃªng háº¡ táº§ng Ä‘áº£o chiá»u theo catalog."
    df["y_nghia_kinh_te"] = "Gáº¯n dá»¯ liá»‡u vá»›i quyáº¿t Ä‘á»‹nh phÃ¢n bá»• khÃ¡ch, doanh thu Ä‘á»‹a phÆ°Æ¡ng vÃ  giáº£m chi phÃ­ xÃ£ há»™i do quÃ¡ táº£i."
    df["loai_du_lieu"] = "mixed/proxy cÃ³ ghi rÃµ giá»›i háº¡n"
    df["do_tin_cay_mac_dinh"] = 65
    df["tooltip_tieng_viet"] = df.apply(lambda r: f"{r['ten_kpi']}: {r['cong_thuc']}. {r['vi_sao_hop_ly']}", axis=1)
    META.mkdir(parents=True, exist_ok=True)
    df.to_csv(META / "kpi_scale_catalog.csv", index=False, encoding="utf-8-sig")
    df.to_csv(META / "kpi_methodology.csv", index=False, encoding="utf-8-sig")
    (META / "confidence_methodology.csv").write_text(
        "cong_thuc,ghi_chu\n"
        "\"0.30*source_reliability + 0.25*freshness_score + 0.20*coverage_score + 0.15*completeness_score + 0.10*proxy_validation_score\","
        "\"Náº¿u khÃ´ng cÃ³ proxy_validation_score thÃ¬ chia láº¡i trá»ng sá»‘ cho 4 thÃ nh pháº§n cÃ²n láº¡i.\"\n",
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
                "coastal_zone": expanded_dest["la_ven_bien"].map(lambda x: "yes" if str(x).lower() in {"cÃ³", "yes", "true"} else "no"),
                "island_zone": expanded_dest["loai_hinh"].map(tourism_type_label).astype(str).str.contains("Ä‘áº£o", case=False, na=False).map(lambda x: "yes" if x else "no"),
                "heritage_zone": expanded_dest["loai_hinh"].map(tourism_type_label).astype(str).str.contains("di sáº£n", case=False, na=False).map(lambda x: "yes" if x else "no"),
                "mountain_zone": expanded_dest["loai_hinh"].map(tourism_type_label).astype(str).str.contains("nÃºi", case=False, na=False).map(lambda x: "yes" if x else "no"),
                "urban_zone": expanded_dest["loai_hinh"].map(tourism_type_label).astype(str).str.contains("Ä‘Ã´ thá»‹", case=False, na=False).map(lambda x: "yes" if x else "no"),
                "mekong_zone": expanded_dest["loai_hinh"].astype(str).str.contains("mekong", case=False, na=False).map(lambda x: "yes" if x else "no"),
                "operational_role": "expanded_national_registry",
            }
        )
    readiness = read_csv(GOLD / "destination_readiness_scores.csv")
    weather = read_csv(GOLD / "weather_risk_features.csv")
    redistribution = read_csv(GOLD / "redistribution_features.csv")
    poi = read_csv(GOLD / "poi_master.csv")
    if dest.empty:
        raise SystemExit("Thiáº¿u data/metadata/destination_registry.csv")
    weather = refresh_open_meteo_weather(dest, weather)

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
            bits.append("rá»§i ro thá»i tiáº¿t cao")
        if row["price_pressure_num"] >= 70:
            bits.append("proxy giÃ¡/lÆ°u trÃº cÄƒng")
        if row["diem_san_sang_ha_tang"] < 40:
            bits.append("háº¡ táº§ng proxy yáº¿u")
        if row["missing_flag"]:
            bits.append("thiáº¿u POI/nguá»“n kiá»ƒm Ä‘á»‹nh")
        return "; ".join(bits) or "Ã¡p lá»±c á»Ÿ má»©c theo dÃµi tá»« dá»¯ liá»‡u hiá»‡n cÃ³"

    def action(row: pd.Series) -> str:
        if row["muc_canh_bao"] in {"Ä‘á»", "cam"}:
            return "PhÃ¢n luá»“ng giao thÃ´ng, tÄƒng shuttle, chia khung giá» vÃ o Ä‘iá»ƒm nÃ³ng, táº¡m giáº£m quáº£ng bÃ¡ Ä‘áº¡i trÃ  vÃ  Ä‘áº©y khÃ¡ch sang Ä‘iá»ƒm thay tháº¿ cÃ³ háº¡ táº§ng tá»‘t hÆ¡n."
        if row["diem_san_sang_ha_tang"] < 40:
            return "KhÃ´ng Ä‘áº©y khÃ¡ch Ä‘áº¡i trÃ ; Æ°u tiÃªn bÃ£i Ä‘á»—, vá»‡ sinh cÃ´ng cá»™ng, biá»ƒn chá»‰ dáº«n, QR vÃ© vÃ  Ä‘iá»ƒm thÃ´ng tin du lá»‹ch."
        if row["muc_canh_bao"] == "xanh":
            return "KÃ­ch cáº§u cÃ³ kiá»ƒm soÃ¡t báº±ng combo lÆ°u trÃº - Äƒn uá»‘ng - tráº£i nghiá»‡m Ä‘á»‹a phÆ°Æ¡ng vÃ  tuyáº¿n liÃªn vÃ¹ng."
        return "Theo dÃµi thá»i tiáº¿t, giÃ¡/lÆ°u trÃº vÃ  sá»± kiá»‡n; chuáº©n bá»‹ shuttle, voucher giá» tháº¥p Ä‘iá»ƒm."

    df["nguyen_nhan_chinh"] = df.apply(reason, axis=1)
    df["hanh_dong_de_xuat"] = df.apply(action, axis=1)
    df["hieu_qua_kinh_te_ky_vong"] = df.apply(
        lambda r: "Giáº£m Ã¡p lá»±c Ä‘iá»ƒm nÃ³ng, tÄƒng chi tiÃªu Äƒn uá»‘ng/váº­n táº£i/lÆ°u trÃº á»Ÿ Ä‘iá»ƒm phá»¥, giáº£m chi phÃ­ xÃ£ há»™i do káº¹t xe vÃ  tráº£i nghiá»‡m xáº¥u."
        if r["muc_canh_bao"] in {"Ä‘á»", "cam"}
        else "TÄƒng doanh thu mÃ¹a tháº¥p Ä‘iá»ƒm vÃ  kÃ©o dÃ i thá»i gian lÆ°u trÃº náº¿u kÃ­ch cáº§u Ä‘Ãºng phÃ¢n khÃºc.",
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
        alerts["trang_thai_thoi_tiet_ngan"] = "á»”n Ä‘á»‹nh"
        alerts.loc[temp.isna() & rain.isna() & wind.isna(), "trang_thai_thoi_tiet_ngan"] = "thiáº¿u dá»¯ liá»‡u"
        alerts.loc[temp >= 35, "trang_thai_thoi_tiet_ngan"] = "Náº¯ng nÃ³ng"
        alerts.loc[wind >= 35, "trang_thai_thoi_tiet_ngan"] = "GiÃ³ máº¡nh"
        alerts.loc[rain >= 8, "trang_thai_thoi_tiet_ngan"] = "MÆ°a Ä‘Ã¡ng chÃº Ã½"
    order = {"Ä‘á»": 0, "cam": 1, "vÃ ng": 2, "xanh": 3, "xÃ¡m": 4}
    alerts["_order"] = alerts["muc_canh_bao"].map(order)
    alerts = alerts.sort_values(["_order", "diem_ap_luc"], ascending=[True, False]).drop(columns="_order").reset_index(drop=True)
    alerts.insert(0, "rank", range(1, len(alerts) + 1))

    forecast_rows = []
    horizons = [("giá»", "24 giá»", "du_bao_24_gio"), ("ngÃ y", "7 ngÃ y", "du_bao_7_ngay"), ("tuáº§n", "30 ngÃ y", "du_bao_30_ngay"), ("thÃ¡ng", "3 thÃ¡ng", "du_bao_3_thang")]
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
                    "muc_canh_bao_du_bao": classify_alert(row[col], row["muc_canh_bao"] == "xÃ¡m"),
                    "drivers": row["nguyen_nhan_chinh"],
                    "recommended_action": row["hanh_dong_de_xuat"],
                    "data_type": row["loai_du_lieu"],
                    "confidence_score": row["do_tin_cay"],
                    "last_updated": now_vn(),
                    "method_note": "Forecast tÃ­nh trÆ°á»›c báº±ng rule/proxy tá»« weather, POI, hotel price pressure vÃ  graph; AI chá»‰ giáº£i thÃ­ch, khÃ´ng tá»± bá»‹a.",
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
        lambda r: "khÃ´ng Ã¡p dá»¥ng"
        if str(r.get("coastal_zone", "")).lower() != "yes"
        else "phÃ¹ há»£p, theo dÃµi mÆ°a/giÃ³"
        if pd.to_numeric(pd.Series([r.get("rui_ro_thoi_tiet")]), errors="coerce").iloc[0] < 40
        else "cáº§n theo dÃµi"
        if pd.to_numeric(pd.Series([r.get("rui_ro_thoi_tiet")]), errors="coerce").iloc[0] < 70
        else "khÃ´ng thuáº­n lá»£i",
        axis=1,
    )
    weather_current["chan_doan_thieu_thoi_tiet"] = weather_current.apply(
        lambda r: ""
        if pd.notna(pd.to_numeric(pd.Series([r.get("nhiet_do_hien_tai")]), errors="coerce").iloc[0])
        else "Thiáº¿u thá»i tiáº¿t: kiá»ƒm tra vi_do/kinh_do, geocode, Open-Meteo call vÃ  bÆ°á»›c ghi gold/current.",
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
            ("Äiá»ƒm Ã¡p lá»±c Ä‘iá»ƒm Ä‘áº¿n", row["diem_ap_luc"]),
            ("Äiá»ƒm rá»§i ro thá»i tiáº¿t", row["rui_ro_thoi_tiet"]),
            ("Äiá»ƒm sáºµn sÃ ng háº¡ táº§ng", row["diem_san_sang_ha_tang"]),
            ("Äiá»ƒm cÆ¡ há»™i kinh táº¿", row["co_hoi_kinh_te"]),
            ("Äiá»ƒm Ä‘iá»u phá»‘i khÃ¡ch", row["kha_nang_dieu_phoi"]),
        ]:
            conf_rows.append(
                {
                    "destination_id": row["destination_id"],
                    "ten_diem_den": row["ten_diem_den"],
                    "metric_name": metric,
                    "metric_score": value,
                    "confidence_score": row["do_tin_cay"],
                    "confidence_label": confidence_label(row["do_tin_cay"]),
                    "confidence_reason": f"Nguá»“n: {row['loai_du_lieu']}; {row['nguyen_nhan_chinh']}",
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
            label = "proxy ráº¥t tá»‘t"
            after = float(row["do_tin_cay"])
        elif pct <= 20:
            label = "proxy tá»‘t, dÃ¹ng Ä‘Æ°á»£c"
            after = float(row["do_tin_cay"]) - 3
        elif pct <= 35:
            label = "cáº§n theo dÃµi"
            after = float(row["do_tin_cay"]) - 8
        else:
            label = "proxy khÃ´ng á»•n Ä‘á»‹nh, giáº£m confidence"
            after = float(row["do_tin_cay"]) - 15
        proxy_rows.append(
            {
                "destination_id": row["destination_id"],
                "ten_diem_den": row["ten_diem_den"],
                "metric_name": "Ãp lá»±c Ä‘iá»ƒm Ä‘áº¿n proxy so vá»›i thá»i tiáº¿t near-real-time",
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
                "method_note": "So sÃ¡nh proxy váº­n hÃ nh vá»›i thÃ nh pháº§n near-real-time hiá»‡n cÃ³; khÃ´ng gá»i proxy lÃ  realtime.",
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
        ticket_catalog["gia_ve_cong_khai"] = "thiáº¿u dá»¯ liá»‡u giÃ¡"
        ticket_catalog["gio_mo_cua"] = "cáº§n Google Maps/Ä‘á»‘i tÃ¡c hoáº·c OSM tag opening_hours"
        ticket_catalog["loai_du_lieu"] = "public_snapshot_osm"
        ticket_catalog["tooltip"] = "Dá»¯ liá»‡u giÃ¡ láº¥y tá»« nguá»“n cÃ´ng khai táº¡i thá»i Ä‘iá»ƒm cáº­p nháº­t náº¿u cÃ³; hiá»‡n chÆ°a pháº£i realtime. Cáº§n API Ä‘á»‘i tÃ¡c Ä‘á»ƒ cáº­p nháº­t tá»± Ä‘á»™ng."

    spending = poi[poi.get("category", pd.Series(dtype=str)).astype(str).isin(["restaurant", "hotel_osm", "parking", "transport_hub"])] if not poi.empty else pd.DataFrame()
    if not spending.empty:
        spending = spending[["destination_id", "destination_name", "poi_name", "category", "lat", "lng", "source_name"]].head(500).rename(
            columns={"destination_name": "ten_diem_den", "poi_name": "ten_poi", "category": "nhom_chi_tieu"}
        )
        spending["goi_y_kinh_te"] = spending["nhom_chi_tieu"].map(
            {
                "restaurant": "ÄÆ°a vÃ o combo Äƒn uá»‘ng Ä‘á»‹a phÆ°Æ¡ng/OCOP vÃ  voucher giá» tháº¥p Ä‘iá»ƒm.",
                "hotel_osm": "Gáº¯n vá»›i combo lÆ°u trÃº liÃªn vÃ¹ng, khÃ´ng dÃ¹ng nhÆ° occupancy tháº­t.",
                "parking": "Æ¯u tiÃªn bÃ£i Ä‘á»— vá»‡ tinh vÃ  shuttle.",
                "transport_hub": "TÄƒng chuyáº¿n shuttle/xe Ä‘iá»‡n vÃ o giá» cao Ä‘iá»ƒm.",
            }
        ).fillna("Khai thÃ¡c nhÆ° Ä‘iá»ƒm chi tiÃªu phá»¥ trá»£.")
    else:
        spending = pd.DataFrame(columns=["destination_id", "ten_diem_den", "ten_poi", "nhom_chi_tieu", "lat", "lng", "source_name", "goi_y_kinh_te"])

    ticket_pressure = alerts[["destination_id", "ten_diem_den", "diem_ap_luc", "do_tin_cay"]].copy()
    attraction_counts = poi_summary[poi_summary["category"].astype(str).str.contains("attraction|beach|tourism", na=False)].groupby("destination_id")["so_luong"].sum().to_dict()
    ticket_pressure["attraction_poi_count"] = ticket_pressure["destination_id"].map(attraction_counts).fillna(0).astype(int)
    ticket_pressure["ticket_pressure_score"] = (ticket_pressure["diem_ap_luc"] * 0.65 + minmax(ticket_pressure["attraction_poi_count"]) * 0.35).round(2)
    ticket_pressure["tooltip"] = "Proxy tá»« Ã¡p lá»±c Ä‘iá»ƒm Ä‘áº¿n vÃ  máº­t Ä‘á»™ POI bÃ¡n vÃ©/Ä‘iá»ƒm tham quan; cáº§n API bÃ¡n vÃ© Ä‘á»ƒ realtime."

    hotel_price = alerts[["destination_id", "ten_diem_den", "diem_ap_luc", "do_tin_cay"]].copy()
    price_lookup = df.set_index("destination_id")["price_pressure_num"].to_dict()
    hotel_price["hotel_price_pressure_score"] = hotel_price["destination_id"].map(price_lookup).fillna(50).astype(float).round(2)
    hotel_price["tooltip"] = "Proxy tá»« snapshot giÃ¡ OTA cÃ´ng khai, khÃ´ng pháº£i cÃ´ng suáº¥t phÃ²ng hay giÃ¡ realtime."

    flight_price = pd.DataFrame(
        [
            {
                "destination_id": row["destination_id"],
                "ten_diem_den": row["ten_diem_den"],
                "flight_price_signal": "thiáº¿u nguá»“n há»£p lá»‡",
                "loai_du_lieu": "partner_api_required",
                "tooltip": "Cáº§n API hÃ ng khÃ´ng/OTA Ä‘Æ°á»£c phÃ©p dÃ¹ng; SEA khÃ´ng bá»‹a tÃ­n hiá»‡u giÃ¡ vÃ© mÃ¡y bay.",
                "last_updated": now_vn(),
            }
            for _, row in alerts.iterrows()
        ]
    )

    actions = []
    for _, row in alerts.iterrows():
        base_problem = "quÃ¡ táº£i/Ã¡p lá»±c cao" if row["muc_canh_bao"] in {"Ä‘á»", "cam"} else "dÆ° Ä‘á»‹a hoáº·c cáº§n theo dÃµi"
        actors = [
            ("CÆ¡ quan quáº£n lÃ½ du lá»‹ch", "Ä‘iá»u chá»‰nh truyá»n thÃ´ng, kÃ­ch cáº§u Ä‘iá»ƒm phá»¥, cÃ´ng bá»‘ cáº£nh bÃ¡o trÃªn dashboard/app"),
            ("CÃ´ng an/giao thÃ´ng Ä‘á»‹a phÆ°Æ¡ng", "phÃ¢n luá»“ng, Ä‘áº·t biá»ƒn bÃ¡o, tÄƒng lá»±c lÆ°á»£ng táº¡i nÃºt vÃ o bÃ£i biá»ƒn/POI"),
            ("Doanh nghiá»‡p du lá»‹ch", "bÃ¡n gÃ³i liÃªn vÃ¹ng, chuyá»ƒn tour sang khung giá» tháº¥p Ä‘iá»ƒm"),
            ("Khu vui chÆ¡i", "chia vÃ© theo khung giá», tÄƒng nhÃ¢n sá»± soÃ¡t vÃ©, Ä‘áº©y QR/e-ticket"),
            ("KhÃ¡ch sáº¡n", "combo lÆ°u trÃº dÃ i hÆ¡n, voucher Äƒn uá»‘ng Ä‘á»‹a phÆ°Æ¡ng, khÃ´ng Ä‘áº©y giÃ¡ khi tráº£i nghiá»‡m giáº£m"),
            ("NhÃ  hÃ ng/OCOP", "voucher giá» tháº¥p Ä‘iá»ƒm, menu combo Ä‘á»‹a phÆ°Æ¡ng, Ä‘iá»ƒm bÃ¡n vá»‡ tinh"),
            ("Váº­n táº£i/shuttle", "tÄƒng shuttle tá»« bÃ£i Ä‘á»— vá»‡ tinh vÃ  tuyáº¿n thay tháº¿"),
        ]
        for actor, act in actors:
            actions.append(
                {
                    "diem_den": row["ten_diem_den"],
                    "van_de": base_problem,
                    "hanh_dong": act,
                    "doi_tuong_thuc_hien": actor,
                    "chi_phi_trien_khai": "tháº¥p-trung bÃ¬nh" if actor not in {"Váº­n táº£i/shuttle", "CÃ´ng an/giao thÃ´ng Ä‘á»‹a phÆ°Æ¡ng"} else "trung bÃ¬nh",
                    "loi_ich_ky_vong": row["hieu_qua_kinh_te_ky_vong"],
                    "logic_kinh_te": "Chuyá»ƒn má»™t pháº§n cáº§u khá»i Ä‘iá»ƒm nÃ³ng, tÄƒng chi tiÃªu á»Ÿ Ä‘iá»ƒm phá»¥ vÃ  giáº£m tá»•n tháº¥t do káº¹t xe/quÃ¡ táº£i.",
                    "kpi_do_luong": "Ä‘iá»ƒm Ã¡p lá»±c; Ä‘iá»ƒm Ä‘iá»u phá»‘i; doanh thu Äƒn uá»‘ng/vÃ©/lÆ°u trÃº; pháº£n há»“i du khÃ¡ch",
                    "muc_uu_tien": row["muc_canh_bao"],
                    "du_lieu_dung": row["loai_du_lieu"],
                    "do_tin_cay": row["do_tin_cay"],
                }
            )
    economic_actions = pd.DataFrame(actions)
    clean_actions = []
    actors = [
        ("ChÃ­nh quyá»n", "Äiá»u chá»‰nh truyá»n thÃ´ng, kÃ­ch cáº§u Ä‘iá»ƒm phá»¥, cÃ´ng bá»‘ cáº£nh bÃ¡o trÃªn dashboard/app", 74, 78),
        ("CÃ´ng an/giao thÃ´ng", "PhÃ¢n luá»“ng táº¡i tuyáº¿n ven biá»ƒn, Ä‘áº·t biá»ƒn bÃ¡o, tÄƒng lá»±c lÆ°á»£ng á»Ÿ nÃºt vÃ o bÃ£i biá»ƒn/POI", 82, 62),
        ("Doanh nghiá»‡p du lá»‹ch", "BÃ¡n gÃ³i liÃªn vÃ¹ng, chuyá»ƒn tour sang khung giá» tháº¥p Ä‘iá»ƒm hoáº·c Ä‘iá»ƒm cÃ²n dÆ° Ä‘á»‹a", 76, 80),
        ("KhÃ¡ch sáº¡n", "Táº¡o combo lÆ°u trÃº dÃ i hÆ¡n, voucher Äƒn uá»‘ng Ä‘á»‹a phÆ°Æ¡ng vÃ  Ä‘iá»u tiáº¿t giÃ¡ theo tráº£i nghiá»‡m", 70, 84),
        ("Khu vui chÆ¡i", "Chia vÃ© theo khung giá», tÄƒng nhÃ¢n sá»± soÃ¡t vÃ©, Ä‘áº©y QR/e-ticket", 73, 82),
        ("NhÃ  hÃ ng/OCOP", "Táº¡o voucher giá» tháº¥p Ä‘iá»ƒm, menu combo Ä‘á»‹a phÆ°Æ¡ng vÃ  Ä‘iá»ƒm bÃ¡n vá»‡ tinh", 66, 86),
        ("Váº­n táº£i/shuttle", "TÄƒng shuttle tá»« bÃ£i Ä‘á»— vá»‡ tinh vÃ  tuyáº¿n thay tháº¿ khi Ä‘iá»ƒm Ã¡p lá»±c tÄƒng", 80, 68),
    ]
    for _, row in alerts.iterrows():
        pressure = float(row.get("diem_ap_luc", 0))
        economy = float(row.get("co_hoi_kinh_te", 0))
        infrastructure = float(row.get("diem_san_sang_ha_tang", 0))
        conf_score = float(row.get("do_tin_cay", 0))
        alert_bonus = 16 if row["muc_canh_bao"] == "Ä‘á»" else 10 if row["muc_canh_bao"] == "cam" else 4 if row["muc_canh_bao"] == "vÃ ng" else 0
        urgent = min(100, max(0, pressure + alert_bonus))
        problem = "Ã¡p lá»±c cao/nguy cÆ¡ quÃ¡ táº£i" if row["muc_canh_bao"] in {"Ä‘á»", "cam"} else "cÃ²n dÆ° Ä‘á»‹a hoáº·c cáº§n theo dÃµi"
        for actor, action_text, impact_base, feasibility_base in actors:
            impact_score = min(100, max(0, 0.50 * economy + 0.35 * pressure + 0.15 * impact_base + alert_bonus))
            feasibility_score = min(100, max(0, 0.45 * infrastructure + 0.35 * feasibility_base + 0.20 * conf_score))
            priority_score = round(0.4 * impact_score + 0.3 * urgent + 0.2 * feasibility_score + 0.1 * conf_score, 2)
            if priority_score >= 80:
                priority = "Cao"
            elif priority_score >= 60:
                priority = "Trung bÃ¬nh"
            else:
                priority = "Tháº¥p"
            cost = "trung bÃ¬nh" if actor in {"CÃ´ng an/giao thÃ´ng", "Váº­n táº£i/shuttle"} else "tháº¥p-trung bÃ¬nh"
            if actor == "ChÃ­nh quyá»n" and infrastructure < 45:
                cost = "cao"
            clean_actions.append(
                {
                    "diem_den": row["ten_diem_den"],
                    "van_de": problem,
                    "hanh_dong": action_text,
                    "doi_tuong_thuc_hien": actor,
                    "chi_phi_trien_khai": cost,
                    "loi_ich_ky_vong": row["hieu_qua_kinh_te_ky_vong"],
                    "logic_kinh_te": "Váº¥n Ä‘á» -> HÃ nh Ä‘á»™ng -> KPI thay Ä‘á»•i -> Hiá»‡u quáº£ kinh táº¿: giáº£m Ã¡p lá»±c táº¡i Ä‘iá»ƒm nÃ³ng, tÄƒng chi tiÃªu Äƒn uá»‘ng/váº­n táº£i/lÆ°u trÃº/vÃ© á»Ÿ vÃ¹ng phá»¥ vÃ  giáº£m chi phÃ­ xÃ£ há»™i do káº¹t xe/quÃ¡ táº£i.",
                    "kpi_do_luong": "Äiá»ƒm Ã¡p lá»±c; Ä‘iá»ƒm Ä‘iá»u phá»‘i; Ä‘iá»ƒm háº¡ táº§ng; cÆ¡ há»™i kinh táº¿; doanh thu Äƒn uá»‘ng/vÃ©/lÆ°u trÃº; pháº£n há»“i du khÃ¡ch",
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
    write_ai_training_examples(alerts, forecast, economic_actions, proxy)

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
        "du lá»‹ch Viá»‡t Nam",
        "du lá»‹ch biá»ƒn Viá»‡t Nam",
        "quÃ¡ táº£i du lá»‹ch",
        "chÃ¡y rá»«ng khu du lá»‹ch",
        "bÃ£o du lá»‹ch",
        "sáº¡t lá»Ÿ Ä‘iá»ƒm du lá»‹ch",
        "lá»… há»™i du lá»‹ch",
        "doanh thu du lá»‹ch",
        "lÆ°á»£ng khÃ¡ch du lá»‹ch",
        "vÃ© khu vui chÆ¡i",
        "giÃ¡ vÃ© du lá»‹ch",
        "du lá»‹ch ÄÃ  Náºµng",
        "du lá»‹ch PhÃº Quá»‘c",
        "du lá»‹ch Nha Trang",
        "du lá»‹ch Háº¡ Long",
        "du lá»‹ch Há»™i An",
    ]
    taxonomy = pd.DataFrame(
        [
            ("environmental_risk", "chÃ¡y rá»«ng, Ã´ nhiá»…m, rÃ¡c tháº£i, sá»± cá»‘ mÃ´i trÆ°á»ng", "giáº£m Destination Health, khÃ´ng recommend Ä‘iá»ƒm Ä‘Ã³"),
            ("weather_disruption", "bÃ£o, mÆ°a lá»›n, ngáº­p, biá»ƒn Ä‘á»™ng", "tÄƒng Weather Risk, cáº£nh bÃ¡o tuyáº¿n/bÃ£i biá»ƒn"),
            ("traffic_disruption", "káº¹t xe, sáº¡t lá»Ÿ, Ã¹n táº¯c, cáº¥m Ä‘Æ°á»ng", "tÄƒng Travel Friction, Ä‘á» xuáº¥t phÃ¢n luá»“ng"),
            ("event_pressure", "lá»… há»™i, concert, sá»± kiá»‡n thá»ƒ thao", "tÄƒng Demand Score, chia khung giá», tÄƒng shuttle"),
            ("capacity_change", "Ä‘Ã³ng/má»Ÿ Ä‘iá»ƒm tham quan, thay Ä‘á»•i sá»©c chá»©a", "cáº­p nháº­t Ã¡p lá»±c vÃ©/háº¡ táº§ng"),
            ("economic_opportunity", "doanh thu, sáº£n pháº©m má»›i, kÃ­ch cáº§u", "tÄƒng cÆ¡ há»™i kinh táº¿, combo Ä‘á»‹a phÆ°Æ¡ng"),
            ("policy_change", "quy Ä‘á»‹nh, phÃ­, chÃ­nh sÃ¡ch visa/du lá»‹ch", "Ä‘iá»u chá»‰nh khuyáº¿n nghá»‹ váº­n hÃ nh"),
            ("ticket_price_change", "giÃ¡ vÃ©, combo, khuyáº¿n mÃ£i", "cáº­p nháº­t ticket pressure vÃ  gá»£i Ã½ giÃ¡"),
        ],
        columns=["event_type", "tu_khoa_nhan_dien", "tac_dong_van_hanh"],
    )
    events = []
    for _, row in alerts.head(12).iterrows():
        event_type = "event_pressure" if row["muc_canh_bao"] in {"Ä‘á»", "cam"} else "economic_opportunity"
        events.append(
            {
                "event_id": f"local_signal_{row['destination_id']}",
                "keyword": f"du lá»‹ch {row['ten_diem_den']}",
                "title": f"TÃ­n hiá»‡u váº­n hÃ nh tá»•ng há»£p cho {row['ten_diem_den']}",
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
            "event_pressure": "tÄƒng Demand Score, tÄƒng shuttle, chia khung giá», Ä‘áº©y Ä‘iá»ƒm phá»¥",
            "economic_opportunity": "Æ°u tiÃªn combo Äƒn uá»‘ng/vÃ©/lÆ°u trÃº náº¿u háº¡ táº§ng Ä‘á»§",
        }
    )
    actions = risk.copy()
    actions["recommended_action"] = actions["operation_signal"]
    actions["owner"] = "Ä‘á»‹a phÆ°Æ¡ng/doanh nghiá»‡p/khu vui chÆ¡i/váº­n táº£i"
    seen = pd.DataFrame({"keyword": keywords, "last_checked": now_vn(), "status": "chÆ°a gá»i API náº¿u thiáº¿u RAPIDAPI_KEY"})
    return news_events, risk, actions, seen, taxonomy


def build_knowledge_base_text(alerts: pd.DataFrame, forecast: pd.DataFrame, actions: pd.DataFrame, proxy: pd.DataFrame) -> str:
    lines = [
        "# Knowledge Base SEA",
        "",
        "Xin chÃ o, tÃ´i lÃ  Trá»£ lÃ½ Ä‘iá»u hÃ nh SEA. TÃ´i cÃ³ thá»ƒ giÃºp báº¡n xem cáº£nh bÃ¡o du lá»‹ch, giáº£i thÃ­ch chá»‰ sá»‘, Ä‘á» xuáº¥t Ä‘iá»u phá»‘i khÃ¡ch vÃ  phÃ¢n tÃ­ch hiá»‡u quáº£ kinh táº¿.",
        "",
        "Quy táº¯c: chá»‰ tráº£ lá»i dá»±a trÃªn báº£ng gold/current; náº¿u thiáº¿u dá»¯ liá»‡u pháº£i nÃ³i rÃµ thiáº¿u dá»¯ liá»‡u, confidence tháº¥p hoáº·c cáº§n API Ä‘á»‘i tÃ¡c.",
        "",
        "## Cáº£nh bÃ¡o Ä‘iá»ƒm Ä‘áº¿n",
    ]
    for _, row in alerts.iterrows():
        lines.append(
            f"- {row['ten_diem_den']} ({row['tinh_thanh']}): cáº£nh bÃ¡o {row['muc_canh_bao']}, Ã¡p lá»±c {row['diem_ap_luc']}, "
            f"thá»i tiáº¿t {row['rui_ro_thoi_tiet']}, háº¡ táº§ng {row['diem_san_sang_ha_tang']}, Ä‘iá»u phá»‘i {row['kha_nang_dieu_phoi']}. "
            f"VÃ¬ sao: {row['nguyen_nhan_chinh']}. NÃªn lÃ m: {row['hanh_dong_de_xuat']}. "
            f"Hiá»‡u quáº£ kinh táº¿: {row['hieu_qua_kinh_te_ky_vong']}. Dá»¯ liá»‡u dÃ¹ng: {row['loai_du_lieu']}. Äá»™ tin cáº­y: {row['do_tin_cay']}."
        )
    lines += ["", "## Forecast", ""]
    for _, row in forecast.head(80).iterrows():
        lines.append(f"- {row['ten_diem_den']} {row['forecast_horizon']}: {row['forecast_demand_score']} ({row['muc_canh_bao_du_bao']}). {row['recommended_action']}")
    lines += ["", "## Kiá»ƒm Ä‘á»‹nh proxy", ""]
    for _, row in proxy.iterrows():
        lines.append(f"- {row['ten_diem_den']}: lá»‡ch {row['percentage_error']}%, {row['reliability_label']}, confidence sau kiá»ƒm Ä‘á»‹nh {row['confidence_after']}.")
    lines += ["", "## Format tráº£ lá»i AI", "TÃ¬nh hÃ¬nh:\nVÃ¬ sao:\nNÃªn lÃ m:\nHiá»‡u quáº£ kinh táº¿:\nDá»¯ liá»‡u dÃ¹ng:\nÄá»™ tin cáº­y:"]
    return "\n".join(lines)


def write_ai_training_examples(alerts: pd.DataFrame, forecast: pd.DataFrame, actions: pd.DataFrame, proxy: pd.DataFrame) -> None:
    examples = []
    for _, row in alerts.head(40).iterrows():
        name = row.get("ten_diem_den", "diem den")
        answer = (
            f"Tinh hinh: {name} dang o muc {row.get('muc_canh_bao')} voi diem ap luc {row.get('diem_ap_luc')}/100.\n"
            f"Vi sao: {row.get('nguyen_nhan_chinh')}.\n"
            f"Du lieu dung: {row.get('loai_du_lieu')}, cap nhat luc {row.get('cap_nhat_lan_cuoi')}.\n"
            f"Do tin cay: {row.get('do_tin_cay')}/100.\n"
            f"Nen lam: {row.get('hanh_dong_de_xuat')}.\n"
            f"Hieu qua kinh te: {row.get('hieu_qua_kinh_te_ky_vong')}."
        )
        examples.append({"instruction": f"Phan tich diem den {name}", "response": answer})
    for _, row in proxy.head(20).iterrows():
        examples.append(
            {
                "instruction": f"Kiem dinh proxy cua {row.get('ten_diem_den')}",
                "response": (
                    f"Tinh hinh: proxy lech {row.get('percentage_error')}%, nhan dinh {row.get('reliability_label')}.\n"
                    f"Du lieu dung: {row.get('data_used_proxy')} va {row.get('data_used_nearrealtime')}.\n"
                    f"Do tin cay sau kiem dinh: {row.get('confidence_after')}."
                ),
            }
        )
    RAG.mkdir(parents=True, exist_ok=True)
    with (RAG / "sea_training_examples.jsonl").open("w", encoding="utf-8") as file:
        for item in examples:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


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
        (EXPORTS_REPORTS / "excel_export_status.txt").write_text("ChÆ°a export Excel Ä‘Æ°á»£c; cáº§n cÃ i openpyxl/xlsxwriter.\n", encoding="utf-8")


def google_sheet_client() -> tuple[object | None, str]:
    try:
        import gspread
    except ImportError:
        return None, "Thiáº¿u package gspread/google-auth. Cháº¡y: pip install -r requirements.txt"
    json_text = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    credential_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    try:
        if json_text:
            return gspread.service_account_from_dict(json.loads(json_text)), ""
        if credential_path:
            return gspread.service_account(filename=credential_path), ""
    except Exception as exc:
        return None, f"KhÃ´ng Ä‘á»c Ä‘Æ°á»£c Google credentials: {exc}"
    return None, "Thiáº¿u GOOGLE_SERVICE_ACCOUNT_JSON hoáº·c GOOGLE_APPLICATION_CREDENTIALS"


def sync_google_sheets_summary(env: dict[str, str]) -> pd.DataFrame:
    now = now_vn()
    sheet_id = env.get("GOOGLE_SHEETS_ID") or os.getenv("GOOGLE_SHEETS_ID", "").strip()
    if not sheet_id:
        status = pd.DataFrame(
            [{"Báº£ng summary": name, "Tráº¡ng thÃ¡i": "Lá»—i", "Sá»‘ dÃ²ng": 0, "Lá»—i": "Thiáº¿u GOOGLE_SHEETS_ID", "Äá»“ng bá»™ lÃºc": now} for name, _ in SHEET_SUMMARY_TABLES]
        )
        status.to_csv(META / "google_sheets_sync_status.csv", index=False, encoding="utf-8-sig")
        return status
    client, client_error = google_sheet_client()
    if client is None:
        status = pd.DataFrame(
            [{"Báº£ng summary": name, "Tráº¡ng thÃ¡i": "Lá»—i", "Sá»‘ dÃ²ng": 0, "Lá»—i": client_error, "Äá»“ng bá»™ lÃºc": now} for name, _ in SHEET_SUMMARY_TABLES]
        )
        status.to_csv(META / "google_sheets_sync_status.csv", index=False, encoding="utf-8-sig")
        return status
    try:
        spreadsheet = client.open_by_key(sheet_id)
    except Exception as exc:
        status = pd.DataFrame(
            [{"Báº£ng summary": name, "Tráº¡ng thÃ¡i": "Lá»—i", "Sá»‘ dÃ²ng": 0, "Lá»—i": f"KhÃ´ng má»Ÿ Ä‘Æ°á»£c Sheet. Kiá»ƒm tra share quyá»n Editor cho service account: {exc}", "Äá»“ng bá»™ lÃºc": now} for name, _ in SHEET_SUMMARY_TABLES]
        )
        status.to_csv(META / "google_sheets_sync_status.csv", index=False, encoding="utf-8-sig")
        return status

    rows = []
    for sheet_name, path in SHEET_SUMMARY_TABLES:
        if not path.exists():
            rows.append({"Báº£ng summary": sheet_name, "Tráº¡ng thÃ¡i": "Lá»—i", "Sá»‘ dÃ²ng": 0, "Lá»—i": f"KhÃ´ng tháº¥y file {path.relative_to(ROOT)}", "Äá»“ng bá»™ lÃºc": now})
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
            rows.append({"Báº£ng summary": sheet_name, "Tráº¡ng thÃ¡i": "ÄÃ£ sync", "Sá»‘ dÃ²ng": len(df), "Lá»—i": "", "Äá»“ng bá»™ lÃºc": now})
        except Exception as exc:
            rows.append({"Báº£ng summary": sheet_name, "Tráº¡ng thÃ¡i": "Lá»—i", "Sá»‘ dÃ²ng": 0, "Lá»—i": str(exc)[:500], "Äá»“ng bá»™ lÃºc": now})
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
    sheet_status = "CÃ³ cáº¥u hÃ¬nh Google Sheets, chá» bÆ°á»›c sync summary" if env.get("GOOGLE_SHEETS_ID") else "ChÆ°a sync vÃ¬ thiáº¿u GOOGLE_SHEETS_ID hoáº·c Google credentials"
    for name, df in tables.items():
        path = CURRENT / f"{name}.csv"
        source_row = source_lookup.get(name)
        source_name = source_row["ten_nguon"] if source_row is not None else "SEA gold/current"
        source_state = source_row["trang_thai"] if source_row is not None else "má»›i nháº¥t"
        rows.append(
            {
                "dataset_id": name,
                "ten_dataset": name.replace("_", " "),
                "duong_dan_current": path.relative_to(ROOT).as_posix(),
                "duong_dan_current_csv": (CURRENT_CSV / f"{name}.csv").relative_to(ROOT).as_posix(),
                "duong_dan_current_parquet": (CURRENT_PARQUET / f"{name}.parquet").relative_to(ROOT).as_posix(),
                "duong_dan_archive_gan_nhat": archive_path,
                "cap_nhat_lan_cuoi": file_update_time(path) or format_vn_time(),
                "mui_gio": "Viá»‡t Nam",
                "trang_thai_du_lieu": source_state,
                "nguon_du_lieu_chinh": source_name,
                "so_dong": len(df),
                "do_tin_cay": round(pd.to_numeric(df.get("do_tin_cay", pd.Series([70])), errors="coerce").mean(), 2) if not df.empty else 0,
                "google_sheets_summary_da_sync": sheet_status,
                "ghi_chu": "Dashboard Ä‘ang dÃ¹ng báº£n current nÃ y. Náº¿u cáº­p nháº­t lá»—i, SEA giá»¯ báº£n current á»•n Ä‘á»‹nh gáº§n nháº¥t vÃ  ghi lá»—i vÃ o pipeline_run_log.",
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
                        "timezone": "Viá»‡t Nam",
                        "step": name,
                        "status": status,
                        "rows": len(df),
                        "current_path": (CURRENT / f"{name}.csv").relative_to(ROOT).as_posix(),
                        "archive_path": LAST_ARCHIVE_DIR.relative_to(ROOT).as_posix() if LAST_ARCHIVE_DIR else "",
                        "google_sheets_summary_da_sync": "sync sau khi rebuild náº¿u cáº¥u hÃ¬nh Google Sheets; fallback CSV local náº¿u lá»—i",
                        "note": "SEA operating pipeline: archive current cÅ©, rebuild CSV/Parquet, KPI/forecast/ranking/recommendation/AI knowledge base, sync Google Sheets summary náº¿u cÃ³ cáº¥u hÃ¬nh.",
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
