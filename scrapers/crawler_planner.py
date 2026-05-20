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
import requests
from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASETS_ROOT = PROJECT_ROOT / "datasets"
RAW_ROOT = DATASETS_ROOT / "raw"
BRONZE_ROOT = DATASETS_ROOT / "bronze"
GOLD_ROOT = DATASETS_ROOT / "gold"
LOGS_ROOT = DATASETS_ROOT / "logs"
SEED_FILE = PROJECT_ROOT / "seed_urls.yaml"
CRAWL_PLAN = DATASETS_ROOT / "crawl_plan.csv"
CRAWL_RECORDS = BRONZE_ROOT / "crawler_records"
CRAWL_LOG = LOGS_ROOT / "crawler_log.csv"
USER_AGENT = "MONEY-VERSE-crawler-planner/1.0 (+tourism research; respects robots.txt)"
REQUEST_TIMEOUT_SECONDS = 35
REQUEST_DELAY_SECONDS = 1.0

KEYWORDS = {
    "tourism",
    "visitors",
    "arrival",
    "arrivals",
    "domestic",
    "international",
    "hotel",
    "occupancy",
    "adr",
    "revpar",
    "passenger",
    "airport",
    "railway",
    "festival",
    "weather",
    "review",
    "du lịch",
    "khách",
    "lưu trú",
    "hàng không",
    "sân bay",
    "đường sắt",
    "lễ hội",
}

API_HINTS = {
    "developers.google.com",
    "tripadvisor-content-api.readme.io",
    "location.foursquare.com",
    "overpass-api.de",
    "open-meteo.com",
    "power.larc.nasa.gov",
    "dev.meteostat.net",
    "data.worldbank.org",
}

RESTRICTED_FETCH_CATEGORIES = {"hotel_ota", "review_poi", "market_report"}

CATEGORY_MAP = {
    "official_statistics": "official_statistics",
    "transport_air": "transport",
    "transport_ground": "transport",
    "hotel_ota": "hotel_ota",
    "review_poi_api": "review_poi",
    "hotel_market_reports": "market_report",
    "destination_official": "destination_content",
    "weather": "weather",
    "events_holidays": "events",
    "global_benchmark": "global_benchmark",
}

LOG_FIELDS = [
    "crawl_time",
    "source_name",
    "category",
    "source_url",
    "raw_path",
    "output_path",
    "status",
    "robots_note",
    "confidence_score",
    "error",
]

RECORD_FIELDS = [
    "record_id",
    "source_url",
    "source_name",
    "source_category",
    "crawl_time",
    "data_period",
    "province_city",
    "raw_text",
    "parsed_fields",
    "confidence_score",
    "license_note",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("_").lower()[:120] or "unknown"


def parse_seed_yaml(path: Path) -> dict[str, list[str]]:
    seeds: dict[str, list[str]] = {}
    current = ""
    parent = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if not raw_line.startswith(" ") and raw_line.endswith(":"):
            current = raw_line[:-1].strip()
            parent = current
            seeds.setdefault(current, [])
            continue
        stripped = raw_line.strip()
        if stripped.endswith(":") and parent == "destination_searches":
            current = f"destination_searches.{stripped[:-1]}"
            seeds.setdefault(current, [])
            continue
        if stripped.startswith("- ") and current:
            seeds.setdefault(current, []).append(stripped[2:].strip())
    return seeds


def source_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.replace("www.", "") or slugify(url)


def source_category(seed_group: str) -> str:
    root_group = seed_group.split(".", 1)[0]
    return CATEGORY_MAP.get(root_group, root_group)


def is_api_source(url: str) -> bool:
    host = urlparse(url).netloc.replace("www.", "")
    return any(host == hint or host.endswith(f".{hint}") for hint in API_HINTS)


def license_note_for(category: str, source_name: str) -> str:
    if category in {"official_statistics", "transport", "weather", "events", "destination_content"}:
        return f"Public source from {source_name}; verify official reuse terms before redistribution."
    if category in {"hotel_ota", "review_poi"}:
        return f"API/partner access preferred for {source_name}; scrape only if robots.txt and terms allow."
    if category == "market_report":
        return f"Research/report source from {source_name}; copyright likely applies, store raw and cite source."
    return f"Source {source_name}; verify license before reuse."


def terms_candidates(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    base = f"{parsed.scheme}://{parsed.netloc}"
    return " | ".join([f"{base}/terms", f"{base}/terms-of-use", f"{base}/privacy"])


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


def content_type_to_extension(content_type: str, url: str) -> str:
    lowered = content_type.lower()
    if "pdf" in lowered or url.lower().endswith(".pdf"):
        return ".pdf"
    if "csv" in lowered or url.lower().endswith(".csv"):
        return ".csv"
    if "excel" in lowered or "spreadsheet" in lowered or re.search(r"\.xlsx?$", url.lower()):
        return ".xlsx" if "xlsx" in lowered or url.lower().endswith(".xlsx") else ".xls"
    if "json" in lowered or url.lower().endswith(".json"):
        return ".json"
    return ".html"


def html_text(content: bytes) -> str:
    soup = BeautifulSoup(content, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


def relevant_score(text: str) -> float:
    lowered = text.lower()
    hits = sum(1 for keyword in KEYWORDS if keyword in lowered)
    return min(1.0, hits / 5)


def extract_period(text: str) -> str:
    match = re.search(r"\b(20[1-2][0-9])\b", text)
    return match.group(1) if match else ""


def extract_city(text: str) -> str:
    cities = [
        "Ha Noi",
        "Hanoi",
        "Ho Chi Minh",
        "Da Nang",
        "Hoi An",
        "Hue",
        "Nha Trang",
        "Phu Quoc",
        "Da Lat",
        "Sa Pa",
        "Sapa",
        "Ha Long",
        "Ninh Binh",
        "Can Tho",
    ]
    lowered = text.lower()
    for city in cities:
        if city.lower() in lowered:
            return city
    return ""


def parsed_fields(text: str) -> str:
    numbers = re.findall(r"(?<!\w)(?:\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)(?:\s?%|\s?million|\s?triệu|\s?nghìn)?", text[:5000], flags=re.IGNORECASE)
    return json.dumps({"numbers": numbers[:20]}, ensure_ascii=False)


def append_log(row: dict) -> None:
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)
    exists = CRAWL_LOG.exists()
    with CRAWL_LOG.open("a", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=LOG_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in LOG_FIELDS})


def save_dataframe(frame: pd.DataFrame, base_path: Path) -> None:
    base_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(base_path.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    frame.to_parquet(base_path.with_suffix(".parquet"), index=False)


def build_plan(seeds: dict[str, list[str]]) -> pd.DataFrame:
    rows = []
    for seed_group, urls in seeds.items():
        if seed_group.startswith("destination_searches."):
            for keyword in urls:
                rows.append(
                    {
                        "seed_group": seed_group,
                        "source_category": "hotel_ota" if "Booking" in keyword or "Agoda" in keyword else "review_poi",
                        "source_name": keyword,
                        "source_url": "",
                        "query": keyword,
                        "api_preferred": "yes" if "Google Maps" in keyword else "unknown",
                        "crawl_action": "manual_or_api_required",
                        "terms_review_status": "manual_required",
                        "terms_url_candidates": "",
                        "license_note": "Search keyword only; use official API/partner access where required.",
                    }
                )
            continue

        category = source_category(seed_group)
        for url in urls:
            name = source_name_from_url(url)
            rows.append(
                {
                    "seed_group": seed_group,
                    "source_category": category,
                    "source_name": name,
                    "source_url": url,
                    "query": "",
                    "api_preferred": "yes" if is_api_source(url) else "no",
                    "crawl_action": "api_or_raw_file_preferred" if is_api_source(url) else "check_robots_then_fetch_seed",
                    "terms_review_status": "manual_required",
                    "terms_url_candidates": terms_candidates(url),
                    "license_note": license_note_for(category, name),
                }
            )
    return pd.DataFrame(rows)


def fetch_seed_pages(plan: pd.DataFrame, limit: int, include_restricted: bool) -> pd.DataFrame:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8"})
    records = []
    fetched = 0

    for row in plan.to_dict("records"):
        url = row.get("source_url", "")
        if not url or row.get("api_preferred") == "yes":
            continue
        if row.get("source_category") in RESTRICTED_FETCH_CATEGORIES and not include_restricted:
            append_log(
                {
                    "crawl_time": now_utc(),
                    "source_name": row["source_name"],
                    "category": row["source_category"],
                    "source_url": url,
                    "status": "skipped_terms_or_api_required",
                    "robots_note": "",
                    "confidence_score": "",
                    "error": "Restricted category requires explicit --include-restricted and prior terms/API review.",
                }
            )
            continue
        if limit and fetched >= limit:
            break

        crawl_time = now_utc()
        status = "failed"
        robots_note = ""
        raw_path = ""
        error = ""
        confidence = 0.0

        try:
            allowed, robots_note = can_fetch(session, url)
            if not allowed:
                status = "robots_disallowed"
                raise RuntimeError(robots_note)

            response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            extension = content_type_to_extension(response.headers.get("Content-Type", ""), url)
            raw_dir = RAW_ROOT / slugify(row["source_category"]) / slugify(row["source_name"])
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_path_obj = raw_dir / f"{crawl_time.replace(':', '').replace('+', 'Z')}{extension}"
            raw_path_obj.write_bytes(response.content)
            raw_path = str(raw_path_obj)
            fetched += 1

            if extension == ".html":
                text = html_text(response.content)
                confidence = relevant_score(text)
                if confidence <= 0:
                    status = "raw_saved_irrelevant_html"
                else:
                    status = "raw_saved_relevant_html"
                    record_id = hashlib.sha256(f"{url}|{crawl_time}".encode("utf-8")).hexdigest()
                    records.append(
                        {
                            "record_id": record_id,
                            "source_url": url,
                            "source_name": row["source_name"],
                            "source_category": row["source_category"],
                            "crawl_time": crawl_time,
                            "data_period": extract_period(text),
                            "province_city": extract_city(text),
                            "raw_text": text[:10000],
                            "parsed_fields": parsed_fields(text),
                            "confidence_score": confidence,
                            "license_note": row["license_note"],
                        }
                    )
            else:
                status = f"raw_saved_{extension.lstrip('.')}"
        except Exception as exc:
            if status == "failed":
                error = str(exc)
            else:
                error = str(exc)
        finally:
            append_log(
                {
                    "crawl_time": crawl_time,
                    "source_name": row["source_name"],
                    "category": row["source_category"],
                    "source_url": url,
                    "raw_path": raw_path,
                    "output_path": str(CRAWL_RECORDS.with_suffix(".parquet")) if records else "",
                    "status": status,
                    "robots_note": robots_note,
                    "confidence_score": confidence,
                    "error": error,
                }
            )
            time.sleep(REQUEST_DELAY_SECONDS)

    frame = pd.DataFrame(records, columns=RECORD_FIELDS)
    if not frame.empty:
        save_dataframe(frame, CRAWL_RECORDS)
    return frame


def empty_target(name: str, columns: list[str]) -> None:
    frame = pd.DataFrame(columns=columns)
    save_dataframe(frame, GOLD_ROOT / name)
    append_log(
        {
            "crawl_time": now_utc(),
            "source_name": "target_builder",
            "category": "gold",
            "source_url": "",
            "output_path": str((GOLD_ROOT / name).with_suffix(".parquet")),
            "status": "no_data_schema_only",
            "robots_note": "",
            "confidence_score": "",
            "error": "",
        }
    )


def build_target_outputs() -> None:
    silver_hotels = DATASETS_ROOT / "silver" / "hotels_inventory.csv"
    if silver_hotels.exists():
        hotels = pd.read_csv(silver_hotels, dtype=str, encoding="utf-8-sig")
        hotels["date"] = pd.to_datetime(hotels.get("crawl_time", ""), errors="coerce").dt.date.astype(str)
        save_dataframe(hotels, GOLD_ROOT / "hotel_inventory_daily")
    else:
        empty_target(
            "hotel_inventory_daily",
            ["date", "source", "property_id", "property_name", "province_code", "district_code", "price_amount", "rating", "review_count", "source_url", "crawl_time", "license_note"],
        )

    reviews_path = DATASETS_ROOT / "silver" / "public_reviews.csv"
    if reviews_path.exists():
        reviews = pd.read_csv(reviews_path, dtype=str, encoding="utf-8-sig")
        reviews["sentiment_score"] = ""
        reviews["sentiment_method"] = "not_computed"
        save_dataframe(reviews, GOLD_ROOT / "review_sentiment")
    else:
        empty_target("review_sentiment", ["source_url", "source_name", "crawl_time", "review_text", "sentiment_score", "sentiment_method"])

    weather_source = DATASETS_ROOT / "weather" / "weather_all_vietnam.csv"
    if weather_source.exists():
        weather = pd.read_csv(weather_source, dtype=str, encoding="utf-8-sig")
        weather["date"] = pd.to_datetime(weather.get("date", ""), errors="coerce").dt.date.astype(str)
        save_dataframe(weather, GOLD_ROOT / "weather_daily")
    else:
        empty_target("weather_daily", ["date", "province", "province_code", "weather_metric", "value", "source_url", "crawl_time", "license_note"])

    empty_target("tourism_demand_monthly", ["month", "source_name", "visitor_type", "market", "transport_mode", "province_city", "value", "unit", "source_url", "crawl_time", "license_note"])
    empty_target("transport_flow_monthly", ["month", "source_name", "transport_type", "airport_station_port", "domestic_passengers", "international_passengers", "source_url", "crawl_time", "license_note"])
    empty_target("poi_capacity", ["source_name", "poi_name", "province_city", "category", "rating", "review_count", "opening_hours", "ticket_price", "latitude", "longitude", "source_url", "crawl_time", "license_note"])
    empty_target("events_calendar", ["event_name", "province_city", "start_date", "end_date", "event_type", "source_url", "crawl_time", "license_note"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawler planner for Vietnam tourism data sources.")
    parser.add_argument("--seed-file", default=str(SEED_FILE), help="Path to seed_urls.yaml.")
    parser.add_argument("--plan-only", action="store_true", help="Only write crawl_plan.csv.")
    parser.add_argument("--fetch", action="store_true", help="Fetch seed pages after robots.txt checks.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum pages to fetch in this run. Use 0 for no limit.")
    parser.add_argument("--include-restricted", action="store_true", help="Allow fetching hotel_ota/review_poi/market_report pages after manual terms review.")
    parser.add_argument("--build-targets", action="store_true", help="Build required target parquet/csv outputs from available real data.")
    args = parser.parse_args()

    seeds = parse_seed_yaml(Path(args.seed_file))
    plan = build_plan(seeds)
    save_dataframe(plan, CRAWL_PLAN.with_suffix(""))
    print(f"Wrote crawl plan: {CRAWL_PLAN}")

    if args.fetch and not args.plan_only:
        records = fetch_seed_pages(plan, args.limit, args.include_restricted)
        print(f"Fetched relevant records: {len(records)}")

    if args.build_targets:
        build_target_outputs()
        print(f"Wrote target outputs under: {GOLD_ROOT}")


if __name__ == "__main__":
    main()
