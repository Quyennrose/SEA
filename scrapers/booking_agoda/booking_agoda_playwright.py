import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}

BOOKING_DESTINATIONS = [
    "Vietnam",
    "Ha Noi, Vietnam",
    "Ho Chi Minh City, Vietnam",
    "Da Nang, Vietnam",
    "Hoi An, Quang Nam, Vietnam",
    "Hue, Vietnam",
    "Nha Trang, Vietnam",
    "Phu Quoc, Vietnam",
    "Da Lat, Vietnam",
    "Sa Pa, Vietnam",
    "Ha Long, Quang Ninh, Vietnam",
    "Vung Tau, Vietnam",
    "Quy Nhon, Vietnam",
    "Mui Ne, Phan Thiet, Vietnam",
    "Can Tho, Vietnam",
    "Ninh Binh, Vietnam",
    "Con Dao, Ba Ria - Vung Tau, Vietnam",
    "My Khe Beach, Da Nang, Vietnam",
    "Son Tra, Da Nang, Vietnam",
    "Ngu Hanh Son, Da Nang, Vietnam",
    "Non Nuoc Beach, Da Nang, Vietnam",
    "Nam O, Da Nang, Vietnam",
    "Hoi An, Quang Nam, Vietnam",
]
AGODA_URL = "https://www.agoda.com/vi-vn/search?city=19099"
MAX_BOOKING_CARDS_PER_PAGE = 25
MAX_BOOKING_PAGES_PER_DESTINATION = 5
MAX_BOOKING_REVIEW_PAGES = 80

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_ROOT = PROJECT_ROOT / "datasets"
BOOKING_DIR = DATASET_ROOT / "booking"
AGODA_DIR = DATASET_ROOT / "agoda"
BOOKING_OUTPUT = BOOKING_DIR / "booking_hotels.csv"
BOOKING_REVIEWS_OUTPUT = BOOKING_DIR / "booking_reviews.csv"
AGODA_OUTPUT = AGODA_DIR / "agoda_hotels.csv"
STATUS_FIELDNAMES = ["source", "source_url", "source_status", "collected_at", "rows", "note"]

FIELDNAMES = [
    "source",
    "destination",
    "name",
    "price",
    "rating",
    "review",
    "location",
    "url",
    "source_url",
    "source_status",
    "collected_at",
    "raw_text",
]

REVIEW_FIELDNAMES = [
    "source",
    "destination",
    "hotel_name",
    "rating",
    "review_text",
    "review_source_type",
    "reviewer_country",
    "traveler_type",
    "hotel_url",
    "source_url",
    "source_status",
    "collected_at",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def booking_search_url(destination: str, offset: int = 0) -> str:
    return (
        "https://www.booking.com/searchresults.html?"
        f"ss={quote_plus(destination)}&dest_type=city&group_adults=2&no_rooms=1"
        f"&group_children=0&order=review_score_and_price&offset={offset}"
    )


def safe_text(element) -> str:
    if not element:
        return ""
    return " ".join(element.inner_text().split())


def save_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def save_reviews(path: Path, rows: list[dict]) -> None:
    deduped_rows = []
    seen = set()
    for row in rows:
        key = (row.get("hotel_url", ""), row.get("review_text", ""))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        deduped_rows.append(row)

    rows = deduped_rows

    if not rows:
        if path.exists():
            path.unlink()
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=REVIEW_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def remove_failed_dataset(source_dir: Path) -> None:
    if not source_dir.exists():
        return

    for path in source_dir.rglob("*"):
        if path.is_file():
            path.unlink()

    for path in sorted(source_dir.rglob("*"), reverse=True):
        if path.is_dir():
            path.rmdir()

    source_dir.rmdir()


def save_status(path: Path, source: str, source_url: str, source_status: str, rows: int, note: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=STATUS_FIELDNAMES)
        writer.writeheader()
        writer.writerow(
            {
                "source": source,
                "source_url": source_url,
                "source_status": source_status,
                "collected_at": now_utc(),
                "rows": rows,
                "note": note,
            }
        )


def save_debug(page, source: str, prefix: str) -> None:
    debug_dir = DATASET_ROOT / source / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    html_file = debug_dir / f"{prefix}.html"
    screenshot_file = debug_dir / f"{prefix}.png"
    html_file.write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(screenshot_file), full_page=True)
    print(f"Saved debug files: {html_file} and {screenshot_file}")


def goto_page(page, url: str, source: str) -> bool:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)
        return True
    except PlaywrightTimeoutError:
        print(f"{source}: timeout while loading {url}")
        return False


def scrape_booking_destination(page, destination: str) -> list[dict]:
    print("\n--- Booking.com ---")
    print(f"Destination: {destination}")
    rows = []
    seen_urls = set()

    for page_index in range(MAX_BOOKING_PAGES_PER_DESTINATION):
        url = booking_search_url(destination, offset=page_index * MAX_BOOKING_CARDS_PER_PAGE)
        if not goto_page(page, url, "booking"):
            save_debug(page, "booking", f"booking_timeout_{safe_filename(destination)}_{page_index}")
            break

        cards = page.query_selector_all("div[data-testid='property-card']")
        if not cards:
            if page_index == 0:
                save_debug(page, "booking", f"booking_no_cards_{safe_filename(destination)}")
            break

        new_rows = 0
        for card in cards[:MAX_BOOKING_CARDS_PER_PAGE]:
            name = card.query_selector("div[data-testid='title']")
            price = (
                card.query_selector("span[data-testid='price-and-discounted-price']")
                or card.query_selector("span[data-testid*='price']")
                or card.query_selector("span[class*='price']")
            )
            review = card.query_selector("div[data-testid='review-score']")
            location = card.query_selector("span[data-testid='address']")
            link = card.query_selector("a[data-testid='title-link']") or card.query_selector("a[href]")
            hotel_url = link.get_attribute("href") if link else ""
            key = hotel_url or safe_text(name)
            if key in seen_urls:
                continue
            seen_urls.add(key)
            new_rows += 1
            rows.append(
                {
                    "source": "booking",
                    "destination": destination,
                    "name": safe_text(name),
                    "price": safe_text(price),
                    "rating": safe_text(review),
                    "review": "",
                    "location": safe_text(location),
                    "url": hotel_url,
                    "source_url": url,
                    "source_status": "public_playwright",
                    "collected_at": now_utc(),
                    "raw_text": " | ".join(card.inner_text().split())[:500],
                }
            )

        if new_rows == 0:
            break

    print(f"Booking: scraped {len(rows)} rows.")
    return rows


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")[:80]


def scrape_booking(page) -> list[dict]:
    rows = []
    for destination in BOOKING_DESTINATIONS:
        rows.extend(scrape_booking_destination(page, destination))

    status = "public_playwright" if rows else "blocked_no_cards"
    save_status(
        BOOKING_DIR / "booking_scrape_status.csv",
        "booking",
        "; ".join(booking_search_url(destination) for destination in BOOKING_DESTINATIONS),
        status,
        len(rows),
        f"destinations={len(BOOKING_DESTINATIONS)}",
    )
    return rows


def extract_quoted_reviews(text: str) -> list[str]:
    reviews = []
    for pattern in [r"“([^”]{20,1000})”", r'"([^"]{20,1000})"']:
        for match in re.findall(pattern, text):
            cleaned = " ".join(match.split())
            if cleaned and cleaned not in reviews:
                reviews.append(cleaned)
    return reviews


COUNTRY_NAMES = [
    "Việt Nam",
    "Vietnam",
    "United States",
    "United Kingdom",
    "Australia",
    "Canada",
    "France",
    "Germany",
    "Netherlands",
    "Singapore",
    "Thailand",
    "Malaysia",
    "Indonesia",
    "India",
    "China",
    "Japan",
    "South Korea",
    "Korea",
    "Russia",
    "Spain",
    "Italy",
]


def infer_reviewer_country(page_text: str, review_text: str) -> str:
    review_index = page_text.find(review_text)
    if review_index < 0:
        return ""
    context = page_text[review_index : review_index + 500]
    for country in COUNTRY_NAMES:
        if country.lower() in context.lower():
            return country
    return ""


def traveler_type(country: str) -> str:
    if not country:
        return ""
    return "domestic" if country.lower() in {"việt nam", "vietnam"} else "international"


def scrape_booking_reviews(page, hotels: list[dict]) -> list[dict]:
    reviews = []

    for hotel in hotels[:MAX_BOOKING_REVIEW_PAGES]:
        hotel_url = hotel.get("url", "")
        if not hotel_url:
            continue

        if not goto_page(page, hotel_url, "booking-review"):
            continue

        page_text = page.locator("body").inner_text(timeout=10000)
        extracted_reviews = extract_quoted_reviews(page_text)

        for review_text in extracted_reviews:
            country = infer_reviewer_country(page_text, review_text)
            reviews.append(
                {
                    "source": "booking",
                    "destination": hotel.get("destination", ""),
                    "hotel_name": hotel.get("name", ""),
                    "rating": hotel.get("rating", ""),
                    "review_text": review_text,
                    "review_source_type": "hotel_page_public_review",
                    "reviewer_country": country,
                    "traveler_type": traveler_type(country),
                    "hotel_url": hotel_url,
                    "source_url": hotel.get("source_url", ""),
                    "source_status": "public_playwright",
                    "collected_at": now_utc(),
                }
            )

    print(f"Booking: extracted {len(reviews)} public review rows.")
    return reviews


def scrape_agoda(page) -> list[dict]:
    print("\n--- Agoda ---")
    if not goto_page(page, AGODA_URL, "agoda"):
        save_debug(page, "agoda", "agoda_timeout")
        save_status(AGODA_DIR / "agoda_scrape_status.csv", "agoda", AGODA_URL, "timeout", 0)
        return []

    cards = page.query_selector_all(
        "div[data-selenium='hotel-card'], "
        "div[data-testid*='hotel-card'], "
        "div[data-testid*='property-card'], "
        "div[class*='HotelCard']"
    )
    if not cards:
        save_debug(page, "agoda", "agoda_no_cards")
        print("Agoda: no property cards found; wrote empty CSV with header.")
        save_status(AGODA_DIR / "agoda_scrape_status.csv", "agoda", AGODA_URL, "blocked_no_cards", 0)
        return []

    rows = []
    for card in cards[:30]:
        name = (
            card.query_selector("h3")
            or card.query_selector("div[class*='HotelName']")
            or card.query_selector("div[class*='hotel-name']")
        )
        price = (
            card.query_selector("div[class*='Price'] span")
            or card.query_selector("span[class*='price']")
            or card.query_selector("span[data-selenium='price']")
        )
        location = card.query_selector("span[class*='Location']") or card.query_selector("div[class*='location']")
        rating = card.query_selector("[data-selenium*='rating']") or card.query_selector("span[class*='rating']")
        link = card.query_selector("a[href]")
        rows.append(
            {
                "source": "agoda",
                "name": safe_text(name),
                "price": safe_text(price),
                "rating": safe_text(rating),
                "review": "",
                "location": safe_text(location),
                "url": link.get_attribute("href") if link else "",
                "source_url": AGODA_URL,
                "source_status": "public_playwright",
                "collected_at": now_utc(),
                "raw_text": " | ".join(card.inner_text().split())[:500],
            }
        )

    print(f"Agoda: scraped {len(rows)} rows.")
    save_status(AGODA_DIR / "agoda_scrape_status.csv", "agoda", AGODA_URL, "public_playwright", len(rows))
    return rows


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS["User-Agent"], locale="vi-VN")
        page = context.new_page()

        booking_rows = scrape_booking(page)
        save_rows(BOOKING_OUTPUT, booking_rows)
        save_reviews(BOOKING_REVIEWS_OUTPUT, scrape_booking_reviews(page, booking_rows))

        agoda_rows = scrape_agoda(page)
        if agoda_rows:
            save_rows(AGODA_OUTPUT, agoda_rows)
        else:
            remove_failed_dataset(AGODA_DIR)

        browser.close()


if __name__ == "__main__":
    main()
