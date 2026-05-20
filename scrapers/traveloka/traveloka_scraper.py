import csv
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

BASE_URL = "https://www.traveloka.com"
DISCOVERY_URL = "https://www.traveloka.com/en-en/hotel/vietnam"
SEED_SEARCH_URLS = [
    "https://www.traveloka.com/en-en/hotel/vietnam/region/hanoi-10009843",
]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = PROJECT_ROOT / "datasets" / "traveloka"
OUTPUT_FILE = DATASET_DIR / "traveloka_hotels_full.csv"
REVIEWS_OUTPUT_FILE = DATASET_DIR / "traveloka_reviews.csv"
REQUEST_DELAY_SECONDS = 0.2
MAX_RETRIES = 4
REQUEST_TIMEOUT_SECONDS = 60
DEBUG_DIR = DATASET_DIR / "debug"
DATASET_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR.mkdir(exist_ok=True)


PRICE_RE = re.compile(r"\b(?:USD|VND|SGD|THB|MYR|PHP|IDR)\s*[\d,.]+|₫\s*[\d,.]+")
RATING_RE = re.compile(r"^(?:10(?:\.0)?|[1-9](?:\.\d)?)$")
REVIEW_RE = re.compile(r"^\(([\d,.]+)\)$")
FIELDNAMES = [
    "id",
    "name",
    "display_name",
    "rating",
    "rating_label",
    "review_count",
    "star_rating",
    "accommodation_type",
    "location",
    "price_currency",
    "price",
    "base_fare",
    "taxes",
    "fees",
    "features",
    "highlighted_review",
    "reviewer_name",
    "travel_theme",
    "main_image",
    "url",
    "source_url",
    "source",
    "source_status",
    "collected_at",
]

REVIEW_FIELDNAMES = [
    "source",
    "hotel_id",
    "hotel_name",
    "rating",
    "rating_label",
    "review_count",
    "review_text",
    "reviewer_name",
    "reviewer_country",
    "traveler_type",
    "travel_theme",
    "hotel_url",
    "source_url",
    "source_status",
    "collected_at",
]


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def safe_print(value: str = "") -> None:
    try:
        print(value)
    except UnicodeEncodeError:
        print(value.encode("ascii", errors="replace").decode("ascii"))


def collected_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_html(session: requests.Session, url: str) -> str:
    return fetch_text(session, url)


def fetch_text(session: requests.Session, url: str) -> str:
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code == 403:
                last_error = requests.HTTPError(f"403 Client Error: Forbidden for url: {url}")
                wait_seconds = max(3, REQUEST_DELAY_SECONDS * attempt * 10)
                safe_print(f"403 blocked on attempt {attempt}/{MAX_RETRIES}. Waiting {wait_seconds}s.")
                time.sleep(wait_seconds)
                continue

            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            wait_seconds = max(2, REQUEST_DELAY_SECONDS * attempt * 5)
            safe_print(f"Request failed on attempt {attempt}/{MAX_RETRIES}: {exc}. Waiting {wait_seconds}s.")
            time.sleep(wait_seconds)

    if last_error:
        raise last_error

    raise RuntimeError(f"Could not fetch {url}")


def card_lines(card: Tag) -> list[str]:
    raw_lines = card.get_text("\n", strip=True).splitlines()
    return [clean_text(line) for line in raw_lines if clean_text(line)]


def find_listing_card(anchor: Tag) -> Tag | None:
    current = anchor
    for _ in range(10):
        current = current.parent
        if not isinstance(current, Tag):
            return None

        text = current.get_text(" ", strip=True)
        if "Price around" in text and "See Availability" in text and len(text) < 5000:
            return current

    return None


def parse_card(anchor: Tag, card: Tag, source_url: str) -> dict | None:
    name = clean_text(anchor.get_text(" ", strip=True))
    if not name or name.startswith(("Hotels near", "Cheap hotels", "Best hotels")):
        return None

    lines = card_lines(card)
    if name not in lines:
        lines.insert(0, name)

    price_match = PRICE_RE.search(card.get_text(" ", strip=True))
    price = price_match.group(0) if price_match else ""

    rating = ""
    review_count = ""
    location = ""
    accommodation_type = ""

    try:
        name_idx = lines.index(name)
    except ValueError:
        name_idx = 0

    for line in lines[name_idx + 1 :]:
        if not rating and RATING_RE.match(line):
            rating = line
            continue
        if not review_count:
            review_match = REVIEW_RE.match(line)
            if review_match:
                review_count = review_match.group(1)
                continue
        if not accommodation_type and line in {"Hotels", "Apartments", "Villas", "Resorts", "Hostels", "Guest Houses"}:
            accommodation_type = line
            continue
        if accommodation_type and not location and line not in {"Price around", "See Availability", "0+"}:
            if line.startswith("No. ") and " in " in line:
                continue
            location = line
            break

    href = anchor.get("href", "")
    return {
        "id": "",
        "name": name,
        "display_name": name,
        "rating": rating,
        "rating_label": "",
        "review_count": review_count,
        "star_rating": "",
        "accommodation_type": accommodation_type,
        "location": location,
        "price_currency": "",
        "price": price,
        "base_fare": "",
        "taxes": "",
        "fees": "",
        "features": "",
        "highlighted_review": "",
        "reviewer_name": "",
        "travel_theme": "",
        "main_image": "",
        "url": urljoin(BASE_URL, href),
        "source_url": source_url,
        "source": "traveloka",
        "source_status": "public_json_fallback_html",
        "collected_at": collected_at(),
    }


def parse_hotels(html: str, source_url: str) -> list[dict]:
    json_hotels = parse_hotels_from_next_data(html, source_url)
    if json_hotels:
        return json_hotels

    soup = BeautifulSoup(html, "html.parser")
    hotels = []
    seen = set()

    for anchor in soup.select("a[href*='/hotel/']"):
        card = find_listing_card(anchor)
        if not card:
            continue

        hotel = parse_card(anchor, card, source_url)
        if not hotel or hotel["name"] in seen:
            continue

        seen.add(hotel["name"])
        hotels.append(hotel)

    return hotels


def parse_money(rate_display: dict, currency_code: str) -> tuple[str, str, str, str, str]:
    if not isinstance(rate_display, dict):
        return currency_code, "", "", "", ""

    decimals = int(float(rate_display.get("numOfDecimalPoint") or 0))

    def convert(value: str | None) -> str:
        if value in (None, ""):
            return ""
        number = float(value)
        if decimals:
            number = number / (10**decimals)
        return f"{number:.{decimals}f}"

    return (
        currency_code,
        convert(rate_display.get("totalFare")),
        convert(rate_display.get("baseFare")),
        convert(rate_display.get("taxes")),
        convert(rate_display.get("fees")),
    )


def parse_hotels_from_next_data(html: str, source_url: str) -> list[dict]:
    try:
        if html.lstrip().startswith("{"):
            data = json.loads(html)
        else:
            soup = BeautifulSoup(html, "html.parser")
            script = soup.find("script", id="__NEXT_DATA__")
            if not script or not script.string:
                return []
            data = json.loads(script.string)
    except json.JSONDecodeError:
        return []

    page_props = data.get("pageProps") or data.get("props", {}).get("pageProps", {})
    initial_data = page_props.get("initialData", {})
    raw_context = page_props.get("rawAppContext", {})
    currency_code = raw_context.get("currencyCode") or ""
    hotel_results = initial_data.get("seoViewSearchList", {}).get("hotelListResult") or []
    hotels = []

    for item in hotel_results:
        if not isinstance(item, dict):
            continue

        assets = item.get("assets") or []
        main_asset = next((asset for asset in assets if asset.get("isMain") or asset.get("main")), assets[0] if assets else {})
        features = ", ".join(
            feature.get("text", "")
            for feature in (item.get("hotelFeatures") or [])
            if isinstance(feature, dict) and feature.get("text")
        )
        price_currency, price, base_fare, taxes, fees = parse_money(item.get("rateDisplay") or {}, currency_code)
        link_url = item.get("seo", {}).get("linkUrl") or ""

        hotels.append(
            {
                "id": item.get("id") or "",
                "name": item.get("name") or item.get("displayName") or "",
                "display_name": item.get("displayName") or item.get("name") or "",
                "rating": item.get("userRating") or "",
                "rating_label": item.get("userRatingInfo") or "",
                "review_count": item.get("numReviews") or "",
                "star_rating": item.get("starRating") or "",
                "accommodation_type": item.get("accommodationType") or "",
                "location": item.get("location") or "",
                "price_currency": price_currency,
                "price": price,
                "base_fare": base_fare,
                "taxes": taxes,
                "fees": fees,
                "features": features,
                "highlighted_review": item.get("highlightedReview") or "",
                "reviewer_name": item.get("reviewerName") or "",
                "travel_theme": item.get("travelTheme") or "",
                "main_image": main_asset.get("url") or main_asset.get("thumbnailUrl") or "",
                "url": urljoin(BASE_URL, link_url),
                "source_url": source_url,
                "source": "traveloka",
                "source_status": "public_next_json",
                "collected_at": collected_at(),
            }
        )

    return hotels


def parse_max_page(html: str) -> int:
    try:
        data = json.loads(html) if html.lstrip().startswith("{") else None
    except json.JSONDecodeError:
        data = None

    if data:
        page_props = data.get("pageProps") or data.get("props", {}).get("pageProps", {})
        initial_data = page_props.get("initialData", {})
        search_list = initial_data.get("seoViewSearchList", {})
        total_hotels = int(search_list.get("totalHotel") or 0)
        item_per_page = int(initial_data.get("itemPerPage") or 21)
        if total_hotels and item_per_page:
            return (total_hotels + item_per_page - 1) // item_per_page

    soup = BeautifulSoup(html, "html.parser")
    max_page = 1

    for anchor in soup.select("a[href]"):
        text = clean_text(anchor.get_text(" ", strip=True)).replace(",", "")
        if text.isdigit():
            max_page = max(max_page, int(text))

    return max_page


def page_url(base_url: str, page: int) -> str:
    if page == 1:
        return f"{base_url}?viewType=list"

    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}/{page}?viewType=list"


def parse_build_id(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return ""

    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return ""

    return data.get("buildId") or ""


def load_build_id(session: requests.Session, base_url: str) -> str:
    cache_file = DEBUG_DIR / "traveloka_full.html"
    legacy_cache_file = PROJECT_ROOT / "debug" / "traveloka_full.html"

    if cache_file.exists():
        build_id = parse_build_id(cache_file.read_text(encoding="utf-8"))
        if build_id:
            return build_id
    if legacy_cache_file.exists():
        html = legacy_cache_file.read_text(encoding="utf-8")
        build_id = parse_build_id(html)
        if build_id:
            cache_file.write_text(html, encoding="utf-8")
            return build_id

    html = fetch_html(session, page_url(base_url, 1))
    cache_file.write_text(html, encoding="utf-8")
    return parse_build_id(html)


def discover_vietnam_search_urls(session: requests.Session) -> list[str]:
    html = fetch_html(session, DISCOVERY_URL)
    (DEBUG_DIR / "traveloka_vietnam_discovery.html").write_text(html, encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    seen = set()

    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        if "/hotel/vietnam/region/" not in href and "/hotel/vietnam/city/" not in href:
            continue

        url = urljoin(BASE_URL, href.split("?")[0])
        if url in seen:
            continue

        seen.add(url)
        urls.append(url)

    for url in SEED_SEARCH_URLS:
        if url not in seen:
            urls.insert(0, url)
            seen.add(url)

    return urls


def next_data_url(base_url: str, build_id: str, page: int) -> str:
    parsed = urlparse(base_url)
    data_path = parsed.path.lstrip("/")
    if page > 1:
        data_path = f"{data_path.rstrip('/')}/{page}"
    return f"{parsed.scheme}://{parsed.netloc}/_next/data/{build_id}/{data_path}.json?viewType=list"


def save_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def save_review_csv(rows: list[dict], path: Path) -> None:
    review_rows = []
    for row in rows:
        review_text = row.get("highlighted_review", "")
        if not review_text:
            continue
        review_rows.append(
            {
                "source": "traveloka",
                "hotel_id": row.get("id", ""),
                "hotel_name": row.get("name", ""),
                "rating": row.get("rating", ""),
                "rating_label": row.get("rating_label", ""),
                "review_count": row.get("review_count", ""),
                "review_text": review_text,
                "reviewer_name": row.get("reviewer_name", ""),
                "reviewer_country": "",
                "traveler_type": "",
                "travel_theme": row.get("travel_theme", ""),
                "hotel_url": row.get("url", ""),
                "source_url": row.get("source_url", ""),
                "source_status": row.get("source_status", "public_next_json"),
                "collected_at": row.get("collected_at", collected_at()),
            }
        )

    if not review_rows:
        if path.exists():
            path.unlink()
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=REVIEW_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(review_rows)


def load_existing_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def main() -> None:
    all_hotels = load_existing_rows(OUTPUT_FILE)
    seen_urls = {hotel["url"] or hotel["name"] for hotel in all_hotels}
    if all_hotels:
        safe_print(f"Loaded {len(all_hotels)} existing rows from {OUTPUT_FILE}.")

    with requests.Session() as session:
        search_urls = discover_vietnam_search_urls(session)
        safe_print(f"Discovered {len(search_urls)} Traveloka Vietnam region/city URLs.")

        for base_url in search_urls:
            safe_print(f"Fetching Traveloka data: {base_url}")
            build_id = load_build_id(session, base_url)
            if not build_id:
                raise RuntimeError("Could not find Traveloka Next.js build id.")

            first_data = fetch_text(session, next_data_url(base_url, build_id, 1))
            max_page = parse_max_page(first_data)
            safe_print(f"Detected {max_page} pages.")

            for page in range(1, max_page + 1):
                url = next_data_url(base_url, build_id, page)
                page_data = first_data if page == 1 else fetch_text(session, url)
                hotels = parse_hotels(page_data, page_url(base_url, page))

                if not hotels:
                    debug_file = DEBUG_DIR / f"traveloka_debug_page_{page}.json"
                    debug_file.write_text(page_data, encoding="utf-8")
                    safe_print(f"Page {page}: no hotel records. Saved debug data: {debug_file}")
                    continue

                new_hotels = []
                for hotel in hotels:
                    key = hotel["url"] or hotel["name"]
                    if key in seen_urls:
                        continue
                    seen_urls.add(key)
                    new_hotels.append(hotel)

                all_hotels.extend(new_hotels)
                save_csv(all_hotels, OUTPUT_FILE)
                safe_print(
                    f"Page {page}/{max_page}: {len(new_hotels)} new hotels "
                    f"({len(all_hotels)} total)."
                )

                if page < max_page:
                    time.sleep(REQUEST_DELAY_SECONDS)

    save_csv(all_hotels, OUTPUT_FILE)
    save_review_csv(all_hotels, REVIEWS_OUTPUT_FILE)

    for idx, hotel in enumerate(all_hotels[:20], start=1):
        safe_print(
            f"{idx}. {hotel['name']} | {hotel['rating'] or 'N/A'} | "
            f"{hotel['review_count'] or 'N/A'} reviews | {hotel['price'] or 'N/A'} | "
            f"{hotel['location'] or 'N/A'}"
        )

    if all_hotels:
        safe_print(f"\nSaved {len(all_hotels)} rows to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
