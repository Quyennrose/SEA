import json
import math
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "datasets"
GOLD = DATASETS / "gold"
RAW = DATASETS / "raw"
META = ROOT / "data" / "metadata"
EVIDENCE = DATASETS / "evidence_archive"

DESTINATIONS = META / "destination_registry.csv"
HOTELS = GOLD / "hotel_inventory_daily.csv"
REVIEWS = GOLD / "review_sentiment.csv"
WEATHER_DAILY = GOLD / "weather_daily.csv"
EDGES = META / "destination_network_edges.csv"

USER_AGENT = "MONEY-VERSE-tourism-mvp/1.0 (research; contact: local)"
REQUEST_TIMEOUT = 40


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def backup_existing(path: Path):
    if not path.exists():
        return
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = EVIDENCE / f"{path.stem}_legacy_{stamp}{path.suffix}"
    shutil.copy2(path, target)


def read_csv(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, **kwargs)


def minmax(series: pd.Series) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce")
    if series.dropna().empty:
        return pd.Series([None] * len(series), index=series.index)
    lo = series.min()
    hi = series.max()
    if hi == lo:
        return pd.Series([50.0] * len(series), index=series.index)
    return ((series - lo) / (hi - lo) * 100).round(2)


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def overpass_query(destination_id, lat, lng, radius=7000):
    query = f"""
    [out:json][timeout:35];
    (
      node(around:{radius},{lat},{lng})["tourism"];
      way(around:{radius},{lat},{lng})["tourism"];
      relation(around:{radius},{lat},{lng})["tourism"];
      node(around:{radius},{lat},{lng})["amenity"~"restaurant|cafe|bus_station|ferry_terminal|parking"];
      way(around:{radius},{lat},{lng})["amenity"~"restaurant|cafe|bus_station|ferry_terminal|parking"];
      node(around:{radius},{lat},{lng})["aeroway"~"aerodrome|terminal"];
      way(around:{radius},{lat},{lng})["aeroway"~"aerodrome|terminal"];
      node(around:{radius},{lat},{lng})["natural"="beach"];
      way(around:{radius},{lat},{lng})["natural"="beach"];
      node(around:{radius},{lat},{lng})["leisure"~"beach_resort|park"];
      way(around:{radius},{lat},{lng})["leisure"~"beach_resort|park"];
    );
    out center tags 80;
    """
    url = "https://overpass-api.de/api/interpreter"
    response = requests.post(
        url,
        data={"data": query},
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    raw_dir = RAW / "geospatial" / "overpass"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{destination_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    raw_path.write_text(response.text, encoding="utf-8")
    return response.json(), str(raw_path.relative_to(ROOT))


def classify_poi(tags):
    if tags.get("natural") == "beach" or tags.get("leisure") == "beach_resort":
        return "beach"
    if tags.get("tourism") in {"attraction", "museum", "viewpoint", "zoo", "theme_park", "gallery"}:
        return "attraction"
    if tags.get("tourism") in {"hotel", "guest_house", "hostel", "apartment", "resort"}:
        return "hotel_osm"
    if tags.get("amenity") in {"restaurant", "cafe"}:
        return "restaurant"
    if tags.get("amenity") in {"bus_station", "ferry_terminal"}:
        return "transport_hub"
    if tags.get("aeroway") in {"aerodrome", "terminal"}:
        return "airport"
    if tags.get("amenity") == "parking":
        return "parking"
    if tags.get("tourism"):
        return f"tourism_{tags.get('tourism')}"
    return "other"


def build_poi_master(destinations: pd.DataFrame) -> pd.DataFrame:
    rows = []
    errors = []
    targets = destinations.head(12).copy()
    for _, dest in targets.iterrows():
        dest_id = dest["destination_id"]
        lat = float(dest["lat"])
        lng = float(dest["lng"])
        try:
            payload, raw_path = overpass_query(dest_id, lat, lng)
            for item in payload.get("elements", []):
                tags = item.get("tags", {})
                poi_lat = item.get("lat") or item.get("center", {}).get("lat")
                poi_lng = item.get("lon") or item.get("center", {}).get("lon")
                name = tags.get("name") or tags.get("name:en") or tags.get("name:vi")
                if not poi_lat or not poi_lng or not name:
                    continue
                category = classify_poi(tags)
                rows.append(
                    {
                        "poi_id": f"osm_{item.get('type')}_{item.get('id')}",
                        "source_name": "OpenStreetMap Overpass API",
                        "source_url": "https://overpass-api.de/api/interpreter",
                        "collection_time": now_utc(),
                        "update_frequency": "on_demand_mvp",
                        "license_note": "OpenStreetMap data under ODbL; attribution required.",
                        "collection_method": "Overpass around destination coordinates",
                        "destination_id": dest_id,
                        "destination_name": dest["canonical_name"],
                        "poi_name": name,
                        "category": category,
                        "lat": round(float(poi_lat), 7),
                        "lng": round(float(poi_lng), 7),
                        "distance_to_destination_km": round(haversine_km(lat, lng, float(poi_lat), float(poi_lng)), 2),
                        "osm_type": item.get("type"),
                        "osm_id": item.get("id"),
                        "tags_json": json.dumps(tags, ensure_ascii=False),
                        "capacity_status": "missing_capacity",
                        "quality_score": 70,
                        "freshness_score": 80,
                        "reliability_score": 70,
                        "coverage_score": 55,
                    }
                )
            time.sleep(1.0)
        except Exception as exc:
            errors.append({"destination_id": dest_id, "error": str(exc), "collection_time": now_utc()})
    if errors:
        err_dir = DATASETS / "logs"
        err_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(errors).to_csv(err_dir / "mvp_overpass_errors.csv", index=False)
    return pd.DataFrame(rows)


def fetch_open_meteo_current(destinations: pd.DataFrame) -> pd.DataFrame:
    rows = []
    ids = destinations["destination_id"].tolist()
    names = destinations["canonical_name"].tolist()
    lats = destinations["lat"].astype(float).tolist()
    lngs = destinations["lng"].astype(float).tolist()
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": ",".join(map(str, lats)),
        "longitude": ",".join(map(str, lngs)),
        "current": "temperature_2m,relative_humidity_2m,precipitation,rain,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,precipitation_sum,rain_sum,wind_speed_10m_max,uv_index_max",
        "timezone": "Asia/Ho_Chi_Minh",
        "forecast_days": 3,
    }
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        payload = response.json()
        raw_dir = RAW / "weather" / "open_meteo_forecast"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"forecast_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        raw_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        forecasts = payload if isinstance(payload, list) else [payload]
        for idx, item in enumerate(forecasts):
            current = item.get("current", {})
            daily = item.get("daily", {})
            precip = float(current.get("precipitation") or 0)
            rain = float(current.get("rain") or 0)
            wind = float(current.get("wind_speed_10m") or 0)
            code = int(current.get("weather_code") or 0)
            uv_values = daily.get("uv_index_max") or []
            uv = max([float(v) for v in uv_values if v is not None], default=0)
            risk = min(100, precip * 8 + rain * 8 + wind * 1.8 + uv * 4 + (25 if code >= 60 else 0))
            rows.append(
                {
                    "destination_id": ids[idx],
                    "destination_name": names[idx],
                    "lat": lats[idx],
                    "lng": lngs[idx],
                    "collection_time": now_utc(),
                    "source_name": "Open-Meteo Forecast API",
                    "source_url": response.url,
                    "update_frequency": "on_demand_mvp",
                    "license_note": "Open-Meteo public API; attribution required.",
                    "collection_method": "forecast endpoint by destination coordinate",
                    "temperature_2m": current.get("temperature_2m"),
                    "relative_humidity_2m": current.get("relative_humidity_2m"),
                    "precipitation": current.get("precipitation"),
                    "rain": current.get("rain"),
                    "weather_code": current.get("weather_code"),
                    "wind_speed_10m": current.get("wind_speed_10m"),
                    "uv_index_max_3d": uv,
                    "weather_risk_score": round(risk, 2),
                    "risk_method": "min(100, precipitation*8 + rain*8 + wind*1.8 + uv*4 + severe_weather_code_bonus)",
                    "quality_score": 86,
                    "freshness_score": 90,
                    "reliability_score": 85,
                    "coverage_score": 90,
                    "limitation": "Weather risk is not marine risk; wave height/current/storm warning not included.",
                }
            )
    except Exception as exc:
        # Fallback to latest local historical weather evidence. This is not realtime.
        weather = read_csv(WEATHER_DAILY, usecols=["province", "latitude", "longitude", "date", "temperature_2m", "precipitation", "rain", "weather_code", "wind_speed_10m"])
        latest = weather.sort_values("date").groupby("province").tail(1) if not weather.empty else pd.DataFrame()
        for _, dest in destinations.iterrows():
            match = latest[latest["province"].str.lower() == str(dest["province_or_city"]).lower()] if not latest.empty else pd.DataFrame()
            row = match.iloc[0].to_dict() if not match.empty else {}
            precip = float(row.get("precipitation") or 0)
            rain = float(row.get("rain") or 0)
            wind = float(row.get("wind_speed_10m") or 0)
            code = int(row.get("weather_code") or 0)
            risk = min(100, precip * 8 + rain * 8 + wind * 1.8 + (25 if code >= 60 else 0))
            rows.append(
                {
                    "destination_id": dest["destination_id"],
                    "destination_name": dest["canonical_name"],
                    "lat": dest["lat"],
                    "lng": dest["lng"],
                    "collection_time": now_utc(),
                    "source_name": "local weather_daily fallback",
                    "source_url": str(WEATHER_DAILY.relative_to(ROOT)),
                    "update_frequency": "batch_historical",
                    "license_note": "Open-Meteo public API; attribution required.",
                    "collection_method": f"fallback after API error: {exc}",
                    "temperature_2m": row.get("temperature_2m"),
                    "relative_humidity_2m": None,
                    "precipitation": row.get("precipitation"),
                    "rain": row.get("rain"),
                    "weather_code": row.get("weather_code"),
                    "wind_speed_10m": row.get("wind_speed_10m"),
                    "uv_index_max_3d": None,
                    "weather_risk_score": round(risk, 2),
                    "risk_method": "historical fallback: min(100, precipitation*8 + rain*8 + wind*1.8 + severe_weather_code_bonus)",
                    "quality_score": 70,
                    "freshness_score": 35,
                    "reliability_score": 85,
                    "coverage_score": 75,
                    "limitation": "Fallback is historical/local evidence, not current forecast.",
                }
            )
    return pd.DataFrame(rows)


def build_hotel_review_features(destinations: pd.DataFrame):
    hotels = read_csv(HOTELS, usecols=["source", "property_name", "location_text", "rating", "review_count", "price_amount", "price_currency", "date"])
    reviews = read_csv(REVIEWS, usecols=["property_name", "rating", "review_text", "sentiment_method"])

    out = []
    for _, dest in destinations.iterrows():
        name = str(dest["canonical_name"]).lower()
        province = str(dest["province_or_city"]).lower()
        h = hotels[
            hotels["location_text"].astype(str).str.lower().str.contains(name, regex=False, na=False)
            | hotels["location_text"].astype(str).str.lower().str.contains(province, regex=False, na=False)
        ] if not hotels.empty else pd.DataFrame()
        r = reviews[
            reviews["property_name"].astype(str).str.lower().isin(h["property_name"].astype(str).str.lower())
        ] if not h.empty and not reviews.empty else pd.DataFrame()
        avg_price = pd.to_numeric(h.get("price_amount", pd.Series(dtype=float)), errors="coerce").median() if not h.empty else None
        hotel_count = len(h)
        avg_rating = pd.to_numeric(h.get("rating", pd.Series(dtype=float)), errors="coerce").mean() if not h.empty else None
        review_rating = pd.to_numeric(r.get("rating", pd.Series(dtype=float)), errors="coerce").mean() if not r.empty else None
        out.append(
            {
                "destination_id": dest["destination_id"],
                "destination_name": dest["canonical_name"],
                "hotel_records": hotel_count,
                "median_hotel_price_proxy": round(avg_price, 2) if pd.notna(avg_price) else None,
                "avg_hotel_rating_proxy": round(avg_rating, 2) if pd.notna(avg_rating) else None,
                "review_records": len(r),
                "tourist_satisfaction_proxy": round(review_rating * 10, 2) if pd.notna(review_rating) else (round(avg_rating * 10, 2) if pd.notna(avg_rating) else None),
                "source_name": "local OTA hotel/review evidence",
                "source_url": "datasets/gold/hotel_inventory_daily.csv;datasets/gold/review_sentiment.csv",
                "collection_time": now_utc(),
                "update_frequency": "batch_snapshot",
                "license_note": "OTA platform terms must be reviewed before redistribution.",
                "collection_method": "destination text match against hotel location/property review evidence",
                "limitation": "Hotel price pressure is a proxy; no true occupancy or booking velocity.",
            }
        )
    df = pd.DataFrame(out)
    df["hotel_price_pressure_proxy"] = minmax(df["median_hotel_price_proxy"])
    return df


def build_scores(destinations, poi, weather, hotel_review):
    poi_counts = poi.groupby(["destination_id", "category"]).size().unstack(fill_value=0) if not poi.empty else pd.DataFrame()
    rows = []
    for _, dest in destinations.iterrows():
        dest_id = dest["destination_id"]
        counts = poi_counts.loc[dest_id].to_dict() if dest_id in poi_counts.index else {}
        attraction_count = sum(counts.get(k, 0) for k in ["attraction", "beach", "restaurant", "hotel_osm", "tourism_viewpoint", "tourism_museum"])
        service_count = sum(counts.get(k, 0) for k in ["restaurant", "hotel_osm", "transport_hub", "airport", "parking"])
        rows.append(
            {
                "destination_id": dest_id,
                "destination_name": dest["canonical_name"],
                "poi_total": int(sum(counts.values())) if counts else 0,
                "attraction_poi_count": int(attraction_count),
                "service_poi_count": int(service_count),
                "poi_attractiveness_raw": attraction_count * 1.0 + service_count * 0.4,
            }
        )
    readiness = pd.DataFrame(rows)
    readiness["poi_attractiveness_score"] = minmax(readiness["poi_attractiveness_raw"])
    readiness = readiness.merge(weather[["destination_id", "weather_risk_score", "quality_score", "freshness_score", "reliability_score", "coverage_score"]], on="destination_id", how="left", suffixes=("", "_weather"))
    readiness = readiness.merge(hotel_review[["destination_id", "hotel_records", "review_records", "hotel_price_pressure_proxy", "tourist_satisfaction_proxy"]], on="destination_id", how="left")
    readiness["destination_readiness_score"] = (
        readiness["poi_attractiveness_score"].fillna(0) * 0.30
        + (100 - readiness["weather_risk_score"].fillna(50)) * 0.25
        + readiness["tourist_satisfaction_proxy"].fillna(50) * 0.20
        + minmax(readiness["hotel_records"]).fillna(0) * 0.15
        + readiness["quality_score"].fillna(50) * 0.10
    ).round(2)
    readiness["data_status"] = readiness.apply(
        lambda r: "mvp_proxy_ready" if r["poi_total"] > 0 and pd.notna(r["weather_risk_score"]) else "partial_missing_poi_or_weather",
        axis=1,
    )
    readiness["source_name"] = "OpenStreetMap/Open-Meteo/local OTA proxy"
    readiness["source_url"] = "datasets/gold/poi_master.csv;datasets/gold/weather_risk_features.csv;datasets/gold/hotel_inventory_daily.csv;datasets/gold/review_sentiment.csv"
    readiness["collection_time"] = now_utc()
    readiness["limitation"] = "Readiness is an MVP proxy; no live crowd, occupancy, revenue or infrastructure pressure."
    return readiness


def route_minutes(origin, destination, fallback_minutes):
    google_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if google_key:
        try:
            url = "https://maps.googleapis.com/maps/api/distancematrix/json"
            params = {
                "origins": f"{origin['lat']},{origin['lng']}",
                "destinations": f"{destination['lat']},{destination['lng']}",
                "mode": "driving",
                "key": google_key,
            }
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            payload = response.json()
            value = payload["rows"][0]["elements"][0]
            if value.get("status") == "OK":
                return round(value["duration"]["value"] / 60, 1), "Google Distance Matrix API", response.url
        except Exception:
            pass
    try:
        url = (
            "https://router.project-osrm.org/route/v1/driving/"
            f"{origin['lng']},{origin['lat']};{destination['lng']},{destination['lat']}"
        )
        params = {"overview": "false", "alternatives": "false", "steps": "false"}
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        payload = response.json()
        routes = payload.get("routes") or []
        if routes:
            raw_dir = RAW / "mobility" / "osrm"
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_path = raw_dir / f"route_{origin['destination_id']}_{destination['destination_id']}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
            raw_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            return round(routes[0]["duration"] / 60, 1), "OSRM public route API", str(raw_path.relative_to(ROOT))
    except Exception:
        pass
    return fallback_minutes, "destination_graph_fallback", str(EDGES.relative_to(ROOT))


def build_redistribution(destinations, readiness):
    edges = read_csv(EDGES)
    if edges.empty:
        return pd.DataFrame()
    dlookup = destinations.set_index("destination_id").to_dict("index")
    rlookup = readiness.set_index("destination_id").to_dict("index")
    rows = []
    for _, edge in edges.iterrows():
        origin = edge["origin_id"]
        alt = edge["destination_id"]
        if origin not in dlookup or alt not in dlookup:
            continue
        fallback_minutes = pd.to_numeric(edge.get("approx_travel_time_minutes"), errors="coerce")
        origin_node = {"destination_id": origin, "lat": dlookup[origin]["lat"], "lng": dlookup[origin]["lng"]}
        alt_node = {"destination_id": alt, "lat": dlookup[alt]["lat"], "lng": dlookup[alt]["lng"]}
        travel_minutes, route_source_name, route_source_url = route_minutes(origin_node, alt_node, fallback_minutes)
        travel_friction = min(100, (float(travel_minutes) / 360) * 100) if pd.notna(travel_minutes) and travel_minutes > 0 else 90
        alt_ready = rlookup.get(alt, {})
        weather_suitability = max(0, 100 - float(alt_ready.get("weather_risk_score") or 50))
        underutilized_capacity_proxy = max(0, 100 - float(alt_ready.get("hotel_price_pressure_proxy") or 50))
        accessibility = max(0, 100 - travel_friction)
        poi_attr = float(alt_ready.get("poi_attractiveness_score") or 0)
        satisfaction = float(alt_ready.get("tourist_satisfaction_proxy") or 50)
        score = (
            underutilized_capacity_proxy * 0.25
            + accessibility * 0.25
            + weather_suitability * 0.20
            + poi_attr * 0.15
            + satisfaction * 0.15
        )
        rows.append(
            {
                "origin_id": origin,
                "alternative_id": alt,
                "relationship_type": edge.get("relationship_type"),
                "approx_travel_time_minutes": edge.get("approx_travel_time_minutes"),
                "route_time_minutes": travel_minutes,
                "route_source_name": route_source_name,
                "route_source_url": route_source_url,
                "travel_modes": edge.get("transport_modes"),
                "travel_friction_score": round(travel_friction, 2),
                "underutilized_capacity_proxy": round(underutilized_capacity_proxy, 2),
                "accessibility_score": round(accessibility, 2),
                "weather_suitability_score": round(weather_suitability, 2),
                "poi_attractiveness_score": round(poi_attr, 2),
                "tourist_satisfaction_proxy": round(satisfaction, 2),
                "redistribution_opportunity_score": round(score, 2),
                "data_status": "mvp_proxy_not_realtime",
                "source_name": "destination graph + OSM/Open-Meteo/local OTA proxy",
                "source_url": "data/metadata/destination_network_edges.csv;datasets/gold/destination_readiness_scores.csv",
                "collection_time": now_utc(),
                "limitation": "No live traffic, crowd density, true occupancy, booking velocity, revenue or capacity. Use for planning, not realtime dispatch.",
            }
        )
    return pd.DataFrame(rows)


def main():
    GOLD.mkdir(parents=True, exist_ok=True)
    destinations = read_csv(DESTINATIONS)
    if destinations.empty:
        raise SystemExit("destination_registry.csv is required")

    outputs = [
        GOLD / "poi_master.csv",
        GOLD / "weather_risk_features.csv",
        GOLD / "redistribution_features.csv",
        GOLD / "destination_readiness_scores.csv",
    ]
    for output in outputs:
        backup_existing(output)

    poi = build_poi_master(destinations)
    poi.to_csv(GOLD / "poi_master.csv", index=False)
    if not poi.empty:
        poi.to_parquet(GOLD / "poi_master.parquet", index=False)

    weather = fetch_open_meteo_current(destinations)
    weather.to_csv(GOLD / "weather_risk_features.csv", index=False)
    if not weather.empty:
        weather.to_parquet(GOLD / "weather_risk_features.parquet", index=False)

    hotel_review = build_hotel_review_features(destinations)
    readiness = build_scores(destinations, poi, weather, hotel_review)
    readiness.to_csv(GOLD / "destination_readiness_scores.csv", index=False)
    readiness.to_parquet(GOLD / "destination_readiness_scores.parquet", index=False)

    redistribution = build_redistribution(destinations, readiness)
    redistribution.to_csv(GOLD / "redistribution_features.csv", index=False)
    if not redistribution.empty:
        redistribution.to_parquet(GOLD / "redistribution_features.parquet", index=False)

    summary = {
        "collection_time": now_utc(),
        "poi_rows": len(poi),
        "weather_rows": len(weather),
        "readiness_rows": len(readiness),
        "redistribution_rows": len(redistribution),
        "note": "MVP proxy features only; no realtime traffic/crowd/booking/revenue.",
    }
    (GOLD / "mvp_build_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
