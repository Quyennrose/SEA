# Data Dictionary

This workspace keeps existing collected files unchanged. New outputs are written under `datasets/raw`, `datasets/bronze`, `datasets/silver`, and `datasets/gold`.

## Common metadata

- `source`: source system or website.
- `source_url`: original URL or local read-only input path.
- `crawl_time`: UTC time when this pipeline fetched or normalized the record.
- `license_note`: source-specific reuse note. Verify the original provider terms before redistribution.
- `source_name`: normalized host/name for crawler-planner outputs.
- `source_category`: planner category such as `official_statistics`, `transport`, `hotel_ota`, `review_poi`, `market_report`, `destination_content`, `weather`, `events`, or `global_benchmark`.
- `confidence_score`: lightweight relevance score based on tourism/transport/weather keywords. It is a routing QA score, not a factual accuracy score.
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

## `bronze/crawler_records`

Relevant HTML seed pages captured by `scrapers/crawler_planner.py --fetch`.

- `record_id`: SHA-256 key from URL and crawl time.
- `source_url`, `source_name`, `source_category`, `crawl_time`
- `data_period`: year detected in the page text when present.
- `province_city`: destination/city detected in the page text when present.
- `raw_text`: visible page text excerpt, capped at 10,000 characters.
- `parsed_fields`: JSON string with extracted numeric tokens for analyst review.
- `confidence_score`, `license_note`

## Required target outputs

- `gold/tourism_demand_monthly`: schema-only until official/API visitor demand data is parsed.
- `gold/transport_flow_monthly`: schema-only until airport/rail/port data is parsed.
- `gold/hotel_inventory_daily`: derived from existing silver hotel inventory.
- `gold/review_sentiment`: derived from existing silver reviews; sentiment is explicitly `not_computed`.
- `gold/poi_capacity`: schema-only until Google/Tripadvisor/Foursquare/OSM API data is collected.
- `gold/events_calendar`: schema-only until event pages are parsed.
- `gold/weather_daily`: derived from existing Open-Meteo weather rows.

## Official raw sources

Official VNAT and CAAV pages are configured in `source_catalog.csv`. Running with `--fetch-official` stores raw HTML by source and tries to parse HTML tables only when the public page exposes them directly. It does not bypass robots.txt, CAPTCHA, login, or image-only content.
