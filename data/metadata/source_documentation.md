# Source Documentation

## Collection Status

The ecosystem is organized into three status classes:

- `existing_local_data_available`: real files already exist under `datasets/` and can be normalized or joined.
- `configured_raw_collection`: seed URLs and raw capture exist, but structured parsing still needs QA or official export access.
- `planned_requires_access`: API key, paid subscription, local government feed, or platform partner terms are required before collection.

## Priority Source Classes

1. Official public statistics: VNAT, GSO, CAAV, airports, railway and local government portals.
2. Open realtime APIs: Open-Meteo, NASA POWER, OSM/Overpass, OpenSky where suitable.
3. Commercial APIs: Google Maps, TomTom, HERE, AviationStack, Amadeus, STR, AirDNA.
4. OTA and social platforms: Booking, Agoda, Traveloka, Expedia, YouTube, Reddit, TikTok, Instagram, Facebook. Use approved APIs or partner access when required.

## Destination Keys

Use the canonical destination names in `data/README.md`. When the source reports province-level data, map as follows:

- Da Nang: Da Nang
- Hoi An: Quang Nam
- Hue: Thua Thien Hue / Hue
- Quy Nhon: Binh Dinh
- Nha Trang: Khanh Hoa
- Phu Quoc: Kien Giang
- Ha Long: Quang Ninh
- Ninh Binh: Ninh Binh
- Da Lat: Lam Dong
- Sa Pa: Lao Cai

## Data Quality Assessment

Each feed should be scored with:

- `completeness`: required fields populated.
- `timeliness`: delay between real-world event and available record.
- `spatial_resolution`: destination, zone, POI, route, or coordinate precision.
- `temporal_resolution`: realtime, hourly, daily, monthly, quarterly, annual.
- `license_risk`: low for open/official data, high for restricted platform data.
- `bias_risk`: sample bias from OTA, social, reviews, or mobile/device coverage.
- `operational_readiness`: whether the feed can support automated decisions.

## Security And Privacy

- Store only public or contract-approved data.
- Avoid personal data in silver, gold, feature, model, and output layers.
- Aggregate social and review signals before operational use.
- Do not expose raw platform content in dashboards unless the license permits it.

## Current Workspace Links

- `datasets/source_catalog.csv`: current configured source catalog.
- `datasets/crawl_plan.csv`: current seed/API planning table.
- `datasets/data_dictionary.md`: current bronze/silver/gold schema notes.
- `datasets/gold/`: current model-ready outputs from real available data.

