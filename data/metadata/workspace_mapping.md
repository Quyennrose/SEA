# Workspace Mapping

This repository now has two complementary data areas:

- `datasets/`: the real collected bronze/silver/gold data lake already used by the current scrapers and normalization scripts.
- `data/`: the full Tourism Operating System contract for future multi-source operations, feature engineering, model artifacts, dashboards, heatmaps, forecasts, policy reports, and metadata.

Use `datasets/` for existing Booking, Traveloka, Open-Meteo, VNAT, CAAV, and airport raw/processed outputs. Use `data/metadata/api_registry.json` to decide which source to connect next, then write approved new extracts into the matching `data/raw/<domain>/` folder or extend the existing `datasets/` pipeline when the source should become part of the bronze/silver/gold lake.

