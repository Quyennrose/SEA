import argparse
import csv
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import pandas as pd
from pandas.api.types import is_object_dtype, is_string_dtype
import requests
from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASETS_ROOT = PROJECT_ROOT / "datasets"
RAW_ROOT = DATASETS_ROOT / "raw"
BRONZE_ROOT = DATASETS_ROOT / "bronze"
SILVER_ROOT = DATASETS_ROOT / "silver"
GOLD_ROOT = DATASETS_ROOT / "gold"
CRAWL_LOG = DATASETS_ROOT / "crawl_log.csv"
SOURCE_CATALOG = DATASETS_ROOT / "source_catalog.csv"
DATA_DICTIONARY = DATASETS_ROOT / "data_dictionary.md"

USER_AGENT = "MONEY-VERSE-tourism-data-pipeline/1.0 (+non-commercial research; respects robots.txt)"
REQUEST_TIMEOUT_SECONDS = 45
REQUEST_DELAY_SECONDS = 1.0

LOG_FIELDS = [
    "crawl_time",
    "source",
    "dataset",
    "source_url",
    "raw_path",
    "output_path",
    "status",
    "rows",
    "license_note",
    "error",
]

SOURCE_ROWS = [
    {
        "source": "vietnam_tourism_statistics",
        "dataset": "international_arrivals_by_market",
        "source_url": "https://thongke.tourism.vn/index.php/statistic/stat/6?input-type=4&nam=2021%2C2022%2C2023%2C2024%2C2025%2C2026&rowcode=14&share=99&type=type1",
        "layer": "raw",
        "license_note": "Official public statistics portal of Vietnam National Authority of Tourism; verify reuse requirements before redistribution.",
        "collection_note": "Official statistics page. The portal exposes an XLS export in the browser UI; this pipeline stores the raw HTML and parses tables only if present.",
    },
    {
        "source": "vietnam_tourism_statistics",
        "dataset": "international_arrivals_by_transport",
        "source_url": "https://thongke.tourism.vn/index.php/statistic/stat/6?input-type=4&nam=2021%2C2022%2C2023%2C2024%2C2025%2C2026&rowcode=17&share=99&type=type1",
        "layer": "raw",
        "license_note": "Official public statistics portal of Vietnam National Authority of Tourism; verify reuse requirements before redistribution.",
        "collection_note": "Official statistics page for air/road/sea arrivals.",
    },
    {
        "source": "vietnam_tourism_statistics",
        "dataset": "domestic_visitors_by_group",
        "source_url": "https://thongke.tourism.vn/index.php/statistic/stat/13?input-type=4&nam=2021%2C2022%2C2023%2C2024%2C2025%2C2026&rowcode=24&share=99&type=type1",
        "layer": "raw",
        "license_note": "Official public statistics portal of Vietnam National Authority of Tourism; verify reuse requirements before redistribution.",
        "collection_note": "Official statistics page for domestic visitor groups.",
    },
    {
        "source": "vietnam_tourism_news",
        "dataset": "monthly_international_arrival_articles",
        "source_url": "https://vietnamtourism.vn/index.php/news/cat/20",
        "layer": "raw",
        "license_note": "Official Vietnam National Authority of Tourism news/statistics pages; article content is copyrighted by the publisher.",
        "collection_note": "Collects public article index and linked monthly statistic pages; image-only tables are not OCRed.",
    },
    {
        "source": "civil_aviation_authority_vietnam",
        "dataset": "aviation_passenger_news",
        "source_url": "https://caa.gov.vn/hoat-dong-nganh.htm",
        "layer": "raw",
        "license_note": "Official Civil Aviation Authority of Vietnam public news pages; use as source-attributed official text.",
        "collection_note": "Collects public pages only. Numerical extraction from narrative articles requires manual QA.",
    },
    {
        "source": "booking",
        "dataset": "hotels",
        "source_url": "datasets/booking/booking_hotels.csv",
        "layer": "bronze/silver",
        "license_note": "Previously collected public Booking.com data in this workspace. Review Booking.com terms before redistribution.",
        "collection_note": "Existing file is read-only input; pipeline does not overwrite it.",
    },
    {
        "source": "booking",
        "dataset": "reviews",
        "source_url": "datasets/booking/booking_reviews.csv",
        "layer": "bronze/silver",
        "license_note": "Previously collected public Booking.com review snippets in this workspace. Review Booking.com terms before redistribution.",
        "collection_note": "Existing file is read-only input; reviewer names are not emitted in silver/gold.",
    },
    {
        "source": "traveloka",
        "dataset": "hotels",
        "source_url": "datasets/traveloka/traveloka_hotels_full.csv",
        "layer": "bronze/silver",
        "license_note": "Previously collected public Traveloka data in this workspace. Review Traveloka terms before redistribution.",
        "collection_note": "Existing file is read-only input; pipeline does not overwrite it.",
    },
    {
        "source": "traveloka",
        "dataset": "reviews",
        "source_url": "datasets/traveloka/traveloka_reviews.csv",
        "layer": "bronze/silver",
        "license_note": "Previously collected public Traveloka review snippets in this workspace. Review Traveloka terms before redistribution.",
        "collection_note": "Existing file is read-only input; reviewer names are not emitted in silver/gold.",
    },
    {
        "source": "open_meteo",
        "dataset": "weather",
        "source_url": "datasets/weather/weather_all_vietnam.csv",
        "layer": "bronze/gold",
        "license_note": "Previously collected Open-Meteo public API data; Open-Meteo attribution required.",
        "collection_note": "Existing file is read-only input; monthly aggregates are produced for forecasting features.",
    },
]

PROVINCE_CODES_63 = {
    "ha noi": "01",
    "ha giang": "02",
    "cao bang": "04",
    "bac kan": "06",
    "tuyen quang": "08",
    "lao cai": "10",
    "dien bien": "11",
    "lai chau": "12",
    "son la": "14",
    "yen bai": "15",
    "hoa binh": "17",
    "thai nguyen": "19",
    "lang son": "20",
    "quang ninh": "22",
    "bac giang": "24",
    "phu tho": "25",
    "vinh phuc": "26",
    "bac ninh": "27",
    "hai duong": "30",
    "hai phong": "31",
    "hung yen": "33",
    "thai binh": "34",
    "ha nam": "35",
    "nam dinh": "36",
    "ninh binh": "37",
    "thanh hoa": "38",
    "nghe an": "40",
    "ha tinh": "42",
    "quang binh": "44",
    "quang tri": "45",
    "thua thien hue": "46",
    "hue": "46",
    "da nang": "48",
    "quang nam": "49",
    "quang ngai": "51",
    "binh dinh": "52",
    "phu yen": "54",
    "khanh hoa": "56",
    "ninh thuan": "58",
    "binh thuan": "60",
    "kon tum": "62",
    "gia lai": "64",
    "dak lak": "66",
    "dak nong": "67",
    "lam dong": "68",
    "binh phuoc": "70",
    "tay ninh": "72",
    "binh duong": "74",
    "dong nai": "75",
    "ba ria - vung tau": "77",
    "ba ria vung tau": "77",
    "ho chi minh city": "79",
    "tp ho chi minh": "79",
    "long an": "80",
    "tien giang": "82",
    "ben tre": "83",
    "tra vinh": "84",
    "vinh long": "86",
    "dong thap": "87",
    "an giang": "89",
    "kien giang": "91",
    "can tho": "92",
    "hau giang": "93",
    "soc trang": "94",
    "bac lieu": "95",
    "ca mau": "96",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value.strip("_").lower()[:120] or "unknown"


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    replacements = {
        "đ": "d",
        "á": "a",
        "à": "a",
        "ả": "a",
        "ã": "a",
        "ạ": "a",
        "ă": "a",
        "ắ": "a",
        "ằ": "a",
        "ẳ": "a",
        "ẵ": "a",
        "ặ": "a",
        "â": "a",
        "ấ": "a",
        "ầ": "a",
        "ẩ": "a",
        "ẫ": "a",
        "ậ": "a",
        "é": "e",
        "è": "e",
        "ẻ": "e",
        "ẽ": "e",
        "ẹ": "e",
        "ê": "e",
        "ế": "e",
        "ề": "e",
        "ể": "e",
        "ễ": "e",
        "ệ": "e",
        "í": "i",
        "ì": "i",
        "ỉ": "i",
        "ĩ": "i",
        "ị": "i",
        "ó": "o",
        "ò": "o",
        "ỏ": "o",
        "õ": "o",
        "ọ": "o",
        "ô": "o",
        "ố": "o",
        "ồ": "o",
        "ổ": "o",
        "ỗ": "o",
        "ộ": "o",
        "ơ": "o",
        "ớ": "o",
        "ờ": "o",
        "ở": "o",
        "ỡ": "o",
        "ợ": "o",
        "ú": "u",
        "ù": "u",
        "ủ": "u",
        "ũ": "u",
        "ụ": "u",
        "ư": "u",
        "ứ": "u",
        "ừ": "u",
        "ử": "u",
        "ữ": "u",
        "ự": "u",
        "ý": "y",
        "ỳ": "y",
        "ỷ": "y",
        "ỹ": "y",
        "ỵ": "y",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text)


def province_code_from_text(value: object) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    for province, code in sorted(PROVINCE_CODES_63.items(), key=lambda item: len(item[0]), reverse=True):
        if province in text:
            return code
    return ""


def number_from_text(value: object) -> float | None:
    if value is None:
        return None
    text = str(value)
    match = re.search(r"[-+]?\d+(?:[.,]\d+)*", text)
    if not match:
        return None
    token = match.group(0).replace(".", "").replace(",", ".")
    try:
        return float(token)
    except ValueError:
        return None


def init_dirs() -> None:
    for path in [RAW_ROOT, BRONZE_ROOT, SILVER_ROOT, GOLD_ROOT]:
        path.mkdir(parents=True, exist_ok=True)


def append_log(row: dict) -> None:
    CRAWL_LOG.parent.mkdir(parents=True, exist_ok=True)
    exists = CRAWL_LOG.exists()
    with CRAWL_LOG.open("a", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=LOG_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in LOG_FIELDS})


def write_source_catalog() -> None:
    with SOURCE_CATALOG.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(SOURCE_ROWS[0].keys()))
        writer.writeheader()
        writer.writerows(SOURCE_ROWS)


def can_fetch(session: requests.Session, url: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    try:
        response = session.get(robots_url, timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})
        if response.status_code >= 400:
            return True, f"robots_unavailable_status_{response.status_code}"
        parser.parse(response.text.splitlines())
        return parser.can_fetch(USER_AGENT, url), "robots_checked"
    except requests.RequestException as exc:
        return False, f"robots_check_failed: {exc}"


def fetch_official_sources() -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8"})

    for source in SOURCE_ROWS:
        if not str(source["source_url"]).startswith("http"):
            continue
        crawl_time = now_utc()
        raw_dir = RAW_ROOT / source["source"] / source["dataset"]
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"{crawl_time.replace(':', '').replace('+', 'Z')}.html"
        status = "failed"
        rows = 0
        error = ""

        try:
            allowed, robots_note = can_fetch(session, source["source_url"])
            if not allowed:
                raise RuntimeError(f"robots disallows fetch or robots check failed: {robots_note}")

            response = session.get(source["source_url"], timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            raw_path.write_bytes(response.content)

            status = "raw_saved_parse_not_configured"
            output_path = ""
        except Exception as exc:
            error = str(exc)
            output_path = ""
        finally:
            append_log(
                {
                    "crawl_time": crawl_time,
                    "source": source["source"],
                    "dataset": source["dataset"],
                    "source_url": source["source_url"],
                    "raw_path": str(raw_path if raw_path.exists() else ""),
                    "output_path": str(output_path),
                    "status": status,
                    "rows": rows,
                    "license_note": source["license_note"],
                    "error": error,
                }
            )
            time.sleep(REQUEST_DELAY_SECONDS)


def parse_html_tables_with_bs4(html: str) -> list[pd.DataFrame]:
    soup = BeautifulSoup(html, "html.parser")
    frames = []
    for table in soup.select("table"):
        rows = []
        for tr in table.select("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in tr.select("th, td")]
            if cells:
                rows.append(cells)
        if not rows:
            continue
        max_width = max(len(row) for row in rows)
        padded_rows = [row + [""] * (max_width - len(row)) for row in rows]
        frames.append(pd.DataFrame(padded_rows))
    return frames


def read_existing_csv(path: Path, source: str, dataset: str) -> pd.DataFrame:
    if not path.exists():
        append_log(
            {
                "crawl_time": now_utc(),
                "source": source,
                "dataset": dataset,
                "source_url": str(path),
                "status": "missing_existing_input",
                "rows": 0,
                "error": f"{path} does not exist",
            }
        )
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig")


def save_frame(frame: pd.DataFrame, path: Path, source: str, dataset: str, source_url: str, license_note: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output_frame = frame.copy()
    for column in output_frame.columns:
        if is_object_dtype(output_frame[column]) or is_string_dtype(output_frame[column]):
            output_frame[column] = output_frame[column].map(lambda value: "" if pd.isna(value) else str(value))
    output_frame.to_csv(path.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    output_frame.to_parquet(path.with_suffix(".parquet"), index=False)
    append_log(
        {
            "crawl_time": now_utc(),
            "source": source,
            "dataset": dataset,
            "source_url": source_url,
            "output_path": f"{path.with_suffix('.csv')} | {path.with_suffix('.parquet')}",
            "status": "ok",
            "rows": len(frame),
            "license_note": license_note,
        }
    )


def normalize_hotels() -> pd.DataFrame:
    hotel_frames = []

    traveloka_path = DATASETS_ROOT / "traveloka" / "traveloka_hotels_full.csv"
    traveloka = read_existing_csv(traveloka_path, "traveloka", "hotels")
    if not traveloka.empty:
        traveloka_bronze = traveloka.copy()
        traveloka_bronze["crawl_time"] = traveloka_bronze.get("collected_at", "")
        traveloka_bronze["license_note"] = "Previously collected public Traveloka data; review Traveloka terms before redistribution."
        save_frame(
            traveloka_bronze,
            BRONZE_ROOT / "traveloka" / "hotels" / "traveloka_hotels_full",
            "traveloka",
            "hotels_bronze",
            str(traveloka_path),
            traveloka_bronze["license_note"].iloc[0],
        )
        hotel_frames.append(
            pd.DataFrame(
                {
                    "source": "traveloka",
                    "property_id": traveloka.get("id", ""),
                    "property_name": traveloka.get("name", ""),
                    "accommodation_type": traveloka.get("accommodation_type", ""),
                    "location_text": traveloka.get("location", ""),
                    "province_code": traveloka.get("location", "").map(province_code_from_text),
                    "district_code": "",
                    "rating": traveloka.get("rating", ""),
                    "rating_label": traveloka.get("rating_label", ""),
                    "review_count": traveloka.get("review_count", ""),
                    "room_type": "",
                    "price_amount": traveloka.get("price", "").map(number_from_text),
                    "price_currency": traveloka.get("price_currency", ""),
                    "availability_note": "",
                    "url": traveloka.get("url", ""),
                    "source_url": traveloka.get("source_url", ""),
                    "crawl_time": traveloka.get("collected_at", ""),
                    "license_note": "Previously collected public Traveloka data; review Traveloka terms before redistribution.",
                }
            )
        )

    booking_path = DATASETS_ROOT / "booking" / "booking_hotels.csv"
    booking = read_existing_csv(booking_path, "booking", "hotels")
    if not booking.empty:
        booking_bronze = booking.copy()
        booking_bronze["crawl_time"] = booking_bronze.get("collected_at", "")
        booking_bronze["license_note"] = "Previously collected public Booking.com data; review Booking.com terms before redistribution."
        save_frame(
            booking_bronze,
            BRONZE_ROOT / "booking" / "hotels" / "booking_hotels",
            "booking",
            "hotels_bronze",
            str(booking_path),
            booking_bronze["license_note"].iloc[0],
        )
        hotel_frames.append(
            pd.DataFrame(
                {
                    "source": "booking",
                    "property_id": "",
                    "property_name": booking.get("name", ""),
                    "accommodation_type": "",
                    "location_text": booking.get("location", "").fillna("").where(booking.get("location", "").fillna("") != "", booking.get("destination", "")),
                    "province_code": booking.get("destination", "").map(province_code_from_text),
                    "district_code": "",
                    "rating": booking.get("rating", ""),
                    "rating_label": "",
                    "review_count": booking.get("rating", "").map(number_from_text),
                    "room_type": "",
                    "price_amount": booking.get("price", "").map(number_from_text),
                    "price_currency": "",
                    "availability_note": "",
                    "url": booking.get("url", ""),
                    "source_url": booking.get("source_url", ""),
                    "crawl_time": booking.get("collected_at", ""),
                    "license_note": "Previously collected public Booking.com data; review Booking.com terms before redistribution.",
                }
            )
        )

    if not hotel_frames:
        return pd.DataFrame()

    hotels = pd.concat(hotel_frames, ignore_index=True)
    hotels["record_id"] = hotels.apply(
        lambda row: hashlib.sha256(f"{row.get('source', '')}|{row.get('url', '')}|{row.get('property_name', '')}".encode("utf-8")).hexdigest(),
        axis=1,
    )
    columns = ["record_id"] + [column for column in hotels.columns if column != "record_id"]
    hotels = hotels[columns]
    save_frame(
        hotels,
        SILVER_ROOT / "hotels_inventory",
        "booking_traveloka",
        "hotels_inventory_silver",
        "existing_booking_and_traveloka_csv",
        "Derived from existing public OTA CSVs; check each platform's terms before redistribution.",
    )
    return hotels


def normalize_reviews() -> pd.DataFrame:
    review_frames = []

    traveloka_path = DATASETS_ROOT / "traveloka" / "traveloka_reviews.csv"
    traveloka = read_existing_csv(traveloka_path, "traveloka", "reviews")
    if not traveloka.empty:
        traveloka_bronze = traveloka.copy()
        traveloka_bronze["crawl_time"] = traveloka_bronze.get("collected_at", "")
        traveloka_bronze["license_note"] = "Previously collected public Traveloka reviews; review Traveloka terms before redistribution."
        save_frame(
            traveloka_bronze,
            BRONZE_ROOT / "traveloka" / "reviews" / "traveloka_reviews",
            "traveloka",
            "reviews_bronze",
            str(traveloka_path),
            traveloka_bronze["license_note"].iloc[0],
        )
        review_frames.append(
            pd.DataFrame(
                {
                    "source": "traveloka",
                    "property_id": traveloka.get("hotel_id", ""),
                    "property_name": traveloka.get("hotel_name", ""),
                    "rating": traveloka.get("rating", ""),
                    "review_text": traveloka.get("review_text", ""),
                    "reviewer_country": traveloka.get("reviewer_country", ""),
                    "traveler_type": traveloka.get("traveler_type", ""),
                    "url": traveloka.get("hotel_url", ""),
                    "source_url": traveloka.get("source_url", ""),
                    "crawl_time": traveloka.get("collected_at", ""),
                    "license_note": "Previously collected public Traveloka reviews; reviewer names excluded from silver/gold.",
                }
            )
        )

    booking_path = DATASETS_ROOT / "booking" / "booking_reviews.csv"
    booking = read_existing_csv(booking_path, "booking", "reviews")
    if not booking.empty:
        booking_bronze = booking.copy()
        booking_bronze["crawl_time"] = booking_bronze.get("collected_at", "")
        booking_bronze["license_note"] = "Previously collected public Booking.com reviews; review Booking.com terms before redistribution."
        save_frame(
            booking_bronze,
            BRONZE_ROOT / "booking" / "reviews" / "booking_reviews",
            "booking",
            "reviews_bronze",
            str(booking_path),
            booking_bronze["license_note"].iloc[0],
        )
        review_frames.append(
            pd.DataFrame(
                {
                    "source": "booking",
                    "property_id": "",
                    "property_name": booking.get("hotel_name", ""),
                    "rating": booking.get("rating", ""),
                    "review_text": booking.get("review_text", ""),
                    "reviewer_country": booking.get("reviewer_country", ""),
                    "traveler_type": booking.get("traveler_type", ""),
                    "url": booking.get("hotel_url", ""),
                    "source_url": booking.get("source_url", ""),
                    "crawl_time": booking.get("collected_at", ""),
                    "license_note": "Previously collected public Booking.com reviews; reviewer names excluded from silver/gold.",
                }
            )
        )

    if not review_frames:
        return pd.DataFrame()

    reviews = pd.concat(review_frames, ignore_index=True)
    reviews["record_id"] = reviews.apply(
        lambda row: hashlib.sha256(f"{row.get('source', '')}|{row.get('url', '')}|{row.get('review_text', '')}".encode("utf-8")).hexdigest(),
        axis=1,
    )
    reviews = reviews[["record_id"] + [column for column in reviews.columns if column != "record_id"]]
    save_frame(
        reviews,
        SILVER_ROOT / "public_reviews",
        "booking_traveloka",
        "public_reviews_silver",
        "existing_booking_and_traveloka_review_csv",
        "Derived from existing public OTA review snippets; reviewer names excluded.",
    )
    return reviews


def aggregate_weather() -> pd.DataFrame:
    weather_path = DATASETS_ROOT / "weather" / "weather_all_vietnam.csv"
    weather = read_existing_csv(weather_path, "open_meteo", "weather")
    if weather.empty:
        return pd.DataFrame()

    weather["date"] = pd.to_datetime(weather["date"], errors="coerce")
    weather = weather.dropna(subset=["date"])
    weather["month"] = weather["date"].dt.to_period("M").astype(str)
    weather["province_code"] = weather["province"].map(province_code_from_text)
    weather["district_code"] = ""
    for column in ["temperature_2m", "relative_humidity_2m", "precipitation", "rain", "wind_speed_10m"]:
        weather[column] = pd.to_numeric(weather[column], errors="coerce")

    monthly = (
        weather.groupby(["province", "province_code", "district_code", "month"], dropna=False)
        .agg(
            temperature_2m_avg=("temperature_2m", "mean"),
            relative_humidity_2m_avg=("relative_humidity_2m", "mean"),
            precipitation_sum=("precipitation", "sum"),
            rain_sum=("rain", "sum"),
            wind_speed_10m_avg=("wind_speed_10m", "mean"),
            observations=("date", "count"),
        )
        .reset_index()
    )
    monthly["source"] = "open_meteo"
    monthly["source_url"] = str(weather_path)
    monthly["crawl_time"] = now_utc()
    monthly["license_note"] = "Open-Meteo public API data; attribution required."

    save_frame(
        monthly,
        GOLD_ROOT / "weather_monthly_by_province",
        "open_meteo",
        "weather_monthly_by_province_gold",
        str(weather_path),
        "Open-Meteo public API data; attribution required.",
    )
    return monthly


def build_hotel_gold(hotels: pd.DataFrame) -> None:
    if hotels.empty:
        return
    hotels = hotels.copy()
    hotels["rating_numeric"] = hotels["rating"].map(number_from_text)
    hotels["review_count_numeric"] = pd.to_numeric(hotels["review_count"], errors="coerce")
    gold = (
        hotels.groupby(["source", "province_code"], dropna=False)
        .agg(
            properties=("record_id", "nunique"),
            avg_rating=("rating_numeric", "mean"),
            total_review_count=("review_count_numeric", "sum"),
            avg_price=("price_amount", "mean"),
        )
        .reset_index()
    )
    gold["month"] = pd.to_datetime(hotels["crawl_time"], errors="coerce").dt.to_period("M").astype(str).mode().iloc[0]
    gold["source_url"] = "existing_booking_and_traveloka_csv"
    gold["crawl_time"] = now_utc()
    gold["license_note"] = "Aggregated from existing public OTA CSVs; check each platform's terms before redistribution."
    save_frame(
        gold,
        GOLD_ROOT / "hotel_supply_by_source_province",
        "booking_traveloka",
        "hotel_supply_by_source_province_gold",
        "existing_booking_and_traveloka_csv",
        "Aggregated from existing public OTA CSVs; check each platform's terms before redistribution.",
    )


def write_data_dictionary() -> None:
    DATA_DICTIONARY.write_text(
        """# Data Dictionary

This workspace keeps existing collected files unchanged. New outputs are written under `datasets/raw`, `datasets/bronze`, `datasets/silver`, and `datasets/gold`.

## Common metadata

- `source`: source system or website.
- `source_url`: original URL or local read-only input path.
- `crawl_time`: UTC time when this pipeline fetched or normalized the record.
- `license_note`: source-specific reuse note. Verify the original provider terms before redistribution.
- `province_code`: Vietnam 63-province historical administrative code when the source text matches confidently. New 34-province mapping after 2025 is not inferred.
- `district_code`: left blank unless an official district/commune code is provided by the source. Vietnam's post-2025 model removed district level, so this pipeline does not invent district codes.

## `silver/hotels_inventory`

Standardized hotel/property rows from existing Booking and Traveloka CSVs.

- `record_id`: SHA-256 key from source, URL, and property name.
- `property_id`, `property_name`, `accommodation_type`, `location_text`
- `rating`, `rating_label`, `review_count`
- `room_type`, `price_amount`, `price_currency`, `availability_note`
- common metadata columns.

## `silver/public_reviews`

Public review snippets from existing Booking and Traveloka CSVs. Reviewer names are excluded from silver/gold outputs.

- `record_id`: SHA-256 key from source, URL, and review text.
- `property_id`, `property_name`, `rating`, `review_text`
- `reviewer_country`, `traveler_type`, `url`
- common metadata columns.

## `gold/hotel_supply_by_source_province`

Monthly aggregate hotel supply features by source and province code.

- `source`, `province_code`, `month`
- `properties`, `avg_rating`, `total_review_count`, `avg_price`
- common metadata columns.

## `gold/weather_monthly_by_province`

Monthly weather features by province from existing Open-Meteo data.

- `province`, `province_code`, `district_code`, `month`
- `temperature_2m_avg`, `relative_humidity_2m_avg`
- `precipitation_sum`, `rain_sum`, `wind_speed_10m_avg`
- `observations`
- common metadata columns.

## Official raw sources

Official VNAT and CAAV pages are configured in `source_catalog.csv`. Running with `--fetch-official` stores raw HTML by source and tries to parse HTML tables only when the public page exposes them directly. It does not bypass robots.txt, CAPTCHA, login, or image-only content.
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Vietnam tourism data lake pipeline.")
    parser.add_argument("--fetch-official", action="store_true", help="Fetch configured official public web pages into raw/.")
    parser.add_argument("--skip-existing", action="store_true", help="Skip normalization of existing local CSV files.")
    args = parser.parse_args()

    init_dirs()
    write_source_catalog()

    if args.fetch_official:
        fetch_official_sources()

    hotels = pd.DataFrame()
    if not args.skip_existing:
        hotels = normalize_hotels()
        normalize_reviews()
        aggregate_weather()
        build_hotel_gold(hotels)

    write_data_dictionary()
    print(f"Wrote source catalog: {SOURCE_CATALOG}")
    print(f"Wrote crawl log: {CRAWL_LOG}")
    print(f"Wrote data dictionary: {DATA_DICTIONARY}")


if __name__ == "__main__":
    main()
