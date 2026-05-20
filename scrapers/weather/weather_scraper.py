# Install before running:
# pip install openmeteo-requests requests-cache retry-requests numpy pandas

from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import time

import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry


START_DATE = "2021-05-01"
END_DATE = date.today().isoformat()
TIMEZONE = "Asia/Ho_Chi_Minh"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "datasets" / "weather"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
BATCH_SIZE = 10
BATCH_DELAY_SECONDS = 70

HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "weather_code",
    "wind_speed_10m",
]

LOCATIONS = [
    ("An Giang", 10.5216, 105.1259),
    ("Ba Ria - Vung Tau", 10.5417, 107.2429),
    ("Bac Giang", 21.2731, 106.1946),
    ("Bac Kan", 22.1470, 105.8348),
    ("Bac Lieu", 9.2940, 105.7278),
    ("Bac Ninh", 21.1861, 106.0763),
    ("Ben Tre", 10.2434, 106.3756),
    ("Binh Dinh", 13.7820, 109.2190),
    ("Binh Duong", 11.3254, 106.4770),
    ("Binh Phuoc", 11.7512, 106.7235),
    ("Binh Thuan", 10.9333, 108.1000),
    ("Ca Mau", 9.1768, 105.1524),
    ("Can Tho", 10.0452, 105.7469),
    ("Cao Bang", 22.6666, 106.2639),
    ("Da Nang", 16.0544, 108.2022),
    ("Dak Lak", 12.7100, 108.2378),
    ("Dak Nong", 12.2646, 107.6098),
    ("Dien Bien", 21.3860, 103.0230),
    ("Dong Nai", 10.9453, 106.8246),
    ("Dong Thap", 10.4938, 105.6882),
    ("Gia Lai", 13.9833, 108.0000),
    ("Ha Giang", 22.8025, 104.9784),
    ("Ha Nam", 20.5835, 105.9229),
    ("Ha Noi", 21.0278, 105.8342),
    ("Ha Tinh", 18.3559, 105.8877),
    ("Hai Duong", 20.9373, 106.3146),
    ("Hai Phong", 20.8449, 106.6881),
    ("Hau Giang", 9.7579, 105.6413),
    ("Hoa Binh", 20.6861, 105.3131),
    ("Hung Yen", 20.6464, 106.0511),
    ("Khanh Hoa", 12.2388, 109.1967),
    ("Kien Giang", 10.0125, 105.0809),
    ("Kon Tum", 14.3497, 108.0005),
    ("Lai Chau", 22.3862, 103.4703),
    ("Lam Dong", 11.9404, 108.4583),
    ("Lang Son", 21.8537, 106.7615),
    ("Lao Cai", 22.4809, 103.9755),
    ("Long An", 10.6956, 106.2431),
    ("Nam Dinh", 20.4388, 106.1621),
    ("Nghe An", 18.6796, 105.6813),
    ("Ninh Binh", 20.2506, 105.9745),
    ("Ninh Thuan", 11.6739, 108.8629),
    ("Phu Tho", 21.2684, 105.2046),
    ("Phu Yen", 13.0882, 109.0929),
    ("Quang Binh", 17.4689, 106.6223),
    ("Quang Nam", 15.5394, 108.0191),
    ("Quang Ngai", 15.1214, 108.8044),
    ("Quang Ninh", 21.0064, 107.2925),
    ("Quang Tri", 16.7500, 107.2000),
    ("Soc Trang", 9.6025, 105.9739),
    ("Son La", 21.1022, 103.7289),
    ("Tay Ninh", 11.3352, 106.1099),
    ("Thai Binh", 20.4463, 106.3366),
    ("Thai Nguyen", 21.5672, 105.8252),
    ("Thanh Hoa", 19.8067, 105.7852),
    ("Thua Thien Hue", 16.4637, 107.5909),
    ("Tien Giang", 10.4493, 106.3421),
    ("Ho Chi Minh City", 10.8231, 106.6297),
    ("Tra Vinh", 9.9347, 106.3453),
    ("Tuyen Quang", 21.7767, 105.2280),
    ("Vinh Long", 10.2537, 105.9722),
    ("Vinh Phuc", 21.3089, 105.6049),
    ("Yen Bai", 21.7168, 104.8986),
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_client():
    cache_path = str(OUTPUT_DIR / ".openmeteo_cache")
    cache_session = requests_cache.CachedSession(cache_path, expire_after=3600)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    return openmeteo_requests.Client(session=retry_session)


def hourly_to_dataframe(response, variables, province, latitude, longitude, source):
    hourly = response.Hourly()
    dates = pd.date_range(
        start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
        end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
        freq=pd.Timedelta(seconds=hourly.Interval()),
        inclusive="left",
    ).tz_convert(TIMEZONE)

    hourly_data = {
        "province": province,
        "latitude": latitude,
        "longitude": longitude,
        "source": source,
        "source_status": "public_open_meteo_api",
        "collected_at": now_utc(),
        "date": dates,
    }

    for index, variable in enumerate(variables):
        hourly_data[variable] = hourly.Variables(index).ValuesAsNumpy()

    return pd.DataFrame(hourly_data)


def fetch_archive_weather(client, latitude, longitude, start_date, end_date):
    latest_archive_date = min(date.fromisoformat(end_date), date.today() - timedelta(days=1))
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": latest_archive_date.isoformat(),
        "hourly": HOURLY_VARIABLES,
        "timezone": TIMEZONE,
    }
    return client.weather_api("https://archive-api.open-meteo.com/v1/archive", params=params)[0]


def fetch_forecast_weather(client, latitude, longitude):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": HOURLY_VARIABLES,
        "timezone": TIMEZONE,
        "forecast_days": 1,
    }
    return client.weather_api("https://api.open-meteo.com/v1/forecast", params=params)[0]


def fetch_archive_weather_batch(client, locations, start_date, end_date):
    latest_archive_date = min(date.fromisoformat(end_date), date.today() - timedelta(days=1))
    params = {
        "latitude": [location[1] for location in locations],
        "longitude": [location[2] for location in locations],
        "start_date": start_date,
        "end_date": latest_archive_date.isoformat(),
        "hourly": HOURLY_VARIABLES,
        "timezone": TIMEZONE,
    }
    return client.weather_api("https://archive-api.open-meteo.com/v1/archive", params=params)


def fetch_forecast_weather_batch(client, locations):
    params = {
        "latitude": [location[1] for location in locations],
        "longitude": [location[2] for location in locations],
        "hourly": HOURLY_VARIABLES,
        "timezone": TIMEZONE,
        "forecast_days": 1,
    }
    return client.weather_api("https://api.open-meteo.com/v1/forecast", params=params)


def chunks(items, size):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def save_csv(dataframe, filename):
    output_path = OUTPUT_DIR / filename
    dataframe.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def main():
    client = create_client()
    archive_frames = []
    today_frames = []
    status_rows = []

    location_batches = list(chunks(LOCATIONS, BATCH_SIZE))
    for batch_index, location_batch in enumerate(location_batches, start=1):
        batch_names = ", ".join(location[0] for location in location_batch)
        print(f"Fetching weather batch: {batch_names}")
        try:
            archive_responses = fetch_archive_weather_batch(client, location_batch, START_DATE, END_DATE)
            forecast_responses = fetch_forecast_weather_batch(client, location_batch)

            for location, archive_response, forecast_response in zip(location_batch, archive_responses, forecast_responses):
                province, latitude, longitude = location
                archive_frames.append(
                    hourly_to_dataframe(archive_response, HOURLY_VARIABLES, province, latitude, longitude, "archive")
                )
                today_frames.append(
                    hourly_to_dataframe(forecast_response, HOURLY_VARIABLES, province, latitude, longitude, "forecast")
                )
                status_rows.append(
                    {
                        "province": province,
                        "latitude": latitude,
                        "longitude": longitude,
                        "source_status": "public_open_meteo_api",
                        "collected_at": now_utc(),
                        "note": "",
                    }
                )
        except Exception as exc:
            print(f"Weather batch failed: {exc}")
            for province, latitude, longitude in location_batch:
                status_rows.append(
                    {
                        "province": province,
                        "latitude": latitude,
                        "longitude": longitude,
                        "source_status": "request_failed",
                        "collected_at": now_utc(),
                        "note": str(exc),
                    }
                )

        if batch_index < len(location_batches):
            print(f"Waiting {BATCH_DELAY_SECONDS}s to respect Open-Meteo rate limits.")
            time.sleep(BATCH_DELAY_SECONDS)

    archive_dataframe = pd.concat(archive_frames, ignore_index=True) if archive_frames else pd.DataFrame()
    today_dataframe = pd.concat(today_frames, ignore_index=True) if today_frames else pd.DataFrame()
    combined_dataframe = (
        pd.concat([archive_dataframe, today_dataframe], ignore_index=True)
        .drop_duplicates(subset=["province", "date"], keep="last")
        if not archive_dataframe.empty or not today_dataframe.empty
        else pd.DataFrame()
    )

    archive_path = save_csv(archive_dataframe, "weather_archive_vietnam.csv")
    today_path = save_csv(today_dataframe, "weather_today_vietnam.csv")
    combined_path = save_csv(combined_dataframe, "weather_all_vietnam.csv")
    status_path = save_csv(pd.DataFrame(status_rows), "weather_scrape_status.csv")

    print("Saved files:")
    print(archive_path)
    print(today_path)
    print(combined_path)
    print(status_path)


if __name__ == "__main__":
    main()
