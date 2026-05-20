# Tourism Operating System for Vietnam

This blueprint turns the current repository into the specification for a real tourism operations platform, not a decorative dashboard. It is grounded in the data that exists in `datasets/` as of 2026-05-19 and explicitly marks the data that is still missing.

## 1. Dataset Audit Report

The detailed audit is machine-readable in `data/metadata/dataset_audit.csv`.

Current usable assets:

- Hotel supply and price proxies: Booking and Traveloka raw/bronze/silver tables with 25,622 normalized hotel rows.
- Tourist experience corpus: 5,332 public review rows after removing reviewer names from silver/gold.
- Weather: 2,212,800 weather rows and 3,050 monthly province aggregates from Open-Meteo.
- Governance metadata: source catalog, API registry, feature formulas, and initial KPI framework.

Critical limitations:

- `tourism_demand_monthly`, `transport_flow_monthly`, `poi_capacity`, and `events_calendar` are schema-only. They must not be used as if they contain evidence.
- Hotel data has no true occupancy, no room count, sparse province mapping, no lat/lng, and no duplicate merge across OTA sources.
- Review sentiment is not computed; the `review_sentiment` table is a target table with `not_computed` model status.
- No live traffic, crowd density, parking, ferry/bus/rail load, event attendance, environmental load, or local revenue data exists yet.

## 2. Missing Dataset Report

The missing dataset registry is in `data/metadata/missing_dataset_registry.csv`.

Minimum production blockers:

- Destination master and alias table.
- POI master with lat/lng, opening hours, category, capacity, environmental sensitivity, and accessibility score.
- Traffic/travel-time feed from Google Maps, TomTom, HERE, or a local traffic center.
- Crowd density and parking occupancy for beaches, heritage cores, event venues, and transport hubs.
- Monthly visitor arrivals by destination, origin market, and transport mode.
- OTA or hotel partner booking velocity, availability, ADR, and occupancy proxy.
- Flight, rail, bus, and ferry schedules/status.
- Event calendar with expected attendance.
- Tourism revenue, local business participation, and infrastructure/environmental pressure.

## 3. Data Quality Report

Quality scores are in `data/metadata/data_quality_scores.csv`.

Scoring policy:

- `quality_score`: completeness, schema maturity, and operational usability.
- `freshness_score`: how recent and refreshable the data is.
- `reliability_score`: source trust and collection stability.
- `coverage_score`: geographic and domain coverage.

Important interpretation:

- Weather is model-ready for seasonality and operational weather context.
- Hotel inventory is dashboard-partial: useful for supply views, not enough for occupancy or true capacity.
- Reviews are dashboard-partial until sentiment/topic models are implemented.
- Demand, transport, POI, and events are blocked because their target tables have zero rows.

## 4. KPI Catalog

The operational KPI catalog is in `data/metadata/kpi_catalog_operational.csv`.

Every KPI follows this rule:

- It must map to an observed source or audited partner feed.
- It must state what decision it supports.
- It must allow local thresholds. A safe beach threshold, a ferry threshold, a mountain road threshold, and a city-center threshold are not interchangeable.
- If source coverage is missing, the KPI is unavailable, not estimated with invented values.

Core KPI families:

- Demand: tourist arrivals, booking pressure, search trend index, demand surge score.
- Congestion: congestion index, beach density, queue time, hotspot pressure.
- Redistribution: redistribution effectiveness, alternative uptake, tourist flow balance.
- Economic: revenue stability, occupancy rate, average spending, stay duration, off-season revenue.
- Infrastructure: infrastructure stress, transport overload, environmental pressure.
- Experience: sentiment score, complaint frequency, overcrowding dissatisfaction.

## 5. Dashboard Architecture

The dashboard should be an operations console with five working surfaces.

Realtime Operation Map:

- Layers: congestion, crowd density, hotel load, weather risk, event pressure, parking, transport load, environmental pressure, recommended alternatives.
- Required data: POI master, traffic, crowd density, transport, parking, weather, event, hotel partner feeds.
- Current status: blocked by missing POI/mobility layers; weather layer can be implemented first.

Demand Forecast Panel:

- Shows predicted arrivals, booking surge, search trends, flight demand, event impact, and uncertainty.
- Current status: blocked until `tourism_demand_monthly`, search trends, booking velocity, and flight data are populated.

Economic Panel:

- Shows tourism revenue, occupancy, ADR/RevPAR where licensed, average spending, local business participation, off-season revenue, and revenue stability.
- Current status: blocked until GSO/local revenue and partner occupancy/spending data are ingested.

Redistribution Engine:

- Shows overloaded nodes, underused alternatives, graph travel friction, recommendation reason, capacity constraints, and incentive options.
- Must never recommend a destination with unsafe weather, insufficient capacity, low satisfaction, or high environmental stress.

Destination Health Panel:

- Destination Health Index = congestion health + environment health + satisfaction health + infrastructure health + economic sustainability.
- Each component must show data coverage. If environment data is missing, the health index is incomplete.

## 6. Geospatial System Design

Layer catalog: `data/metadata/geospatial_layer_catalog.csv`.

Required standards:

- Every POI must have `poi_id`, `destination_id`, lat/lng, district or equivalent local area, province, tourism region, route/cluster, coastal/island/heritage/mountain flags, opening hours, capacity source, and accessibility score.
- Every destination must map aliases to a canonical `destination_id`.
- Every route edge must store travel time, transport modes, friction, cost class, capacity constraints, and whether it supports same-day or campaign-level redistribution.

Map products:

- Heatmap by POI/zone and time window.
- Tourist flow map across destination graph edges.
- Alternative routing map with friction and safety filters.
- Attraction clusters by category and capacity.
- Underutilized zones with unused capacity and acceptable satisfaction.
- Coastal overload zones using beach polygons, tide/marine safety, lifeguard coverage, and crowd density.

## 7. Destination Graph Design

Nodes are in `data/metadata/destination_registry.csv`.

Aliases are in `data/metadata/destination_aliases.csv`.

Initial graph edges are in `data/metadata/destination_network_edges.csv`.

Graph logic:

- Same-day redistribution only for low to medium friction edges such as Da Nang to Hoi An or Ho Chi Minh City to Vung Tau.
- Campaign-level redistribution for high-friction alternatives such as Da Nang to Quy Nhon or Sa Pa to Ha Giang.
- Island routes must include ferry/flight capacity and weather constraints.
- Mountain routes must include travel-time volatility, road safety, and emergency access.

## 8. AI Model Architecture

Model registry: `data/metadata/ai_model_registry.csv`.

Architecture:

- Forecasting service for destination demand and transport inflow.
- Spatiotemporal congestion service for POIs, beaches, roads, parking, and hubs.
- Redistribution ranker using destination graph, capacity, travel friction, weather, satisfaction, and economic balance.
- Economic optimizer for off-season revenue, local participation, and infrastructure pressure.
- NLP service for multilingual sentiment, topic modeling, and overcrowding complaint detection.
- RAG assistant using Ollama for KPI explanations, local policy Q&A, intervention justification, and scenario analysis.

Ollama integration:

- Store governed knowledge in a local vector index: KPI catalog, dataset audit, quality scores, source catalog, model cards, SOPs, and policy documents.
- Use Ollama as the local LLM endpoint for explanations, not as the source of facts.
- Retrieval must return the exact dataset, KPI formula, freshness, and coverage status before the assistant answers.
- Assistant answers must separate fact, inference, and recommendation.

## 9. Localized Tourism Strategy

Coastal tourism:

- Priority destinations: Da Nang, Nha Trang, Quy Nhon, Mui Ne, Vung Tau, Sam Son, Cua Lo.
- Operational focus: beach density, weather/marine risk, parking, road access, lifeguard coverage, waste/water pressure.

Heritage tourism:

- Priority destinations: Hoi An, Hue, Ha Long, Ninh Binh, An Giang, Con Dao.
- Operational focus: queue time, carrying capacity, cultural sensitivity, group scheduling, night economy balancing.

Mountain tourism:

- Priority destinations: Ha Giang, Sa Pa, Moc Chau, Da Lat.
- Operational focus: road friction, weather risk, emergency access, viewpoint crowding, homestay capacity.

Urban tourism:

- Priority destinations: Ha Noi, Ho Chi Minh City, Da Nang, Can Tho.
- Operational focus: event pressure, public transport, hotel demand, crowd dispersion, weekend gateways.

Island tourism:

- Priority destinations: Phu Quoc, Con Dao, Ly Son, Cat Ba.
- Operational focus: flight/ferry capacity, marine weather, waste/water limits, beach density, emergency capacity.

Mekong tourism:

- Priority destinations: Can Tho, An Giang, Ben Tre.
- Operational focus: festival spikes, river transport, small business participation, seasonal water/weather conditions.

## 10. Economic Operation Framework

The system optimizes economic value under capacity constraints.

Operating questions:

- Are high visitor counts creating local revenue or only infrastructure pressure?
- Which destination has unused capacity and acceptable satisfaction?
- Which off-season event or route can increase revenue without triggering environmental stress?
- Which incentive is better: discount, shuttle, event rescheduling, bundled ticket, or OTA/package promotion?

Evaluation metrics:

- Revenue stability.
- Off-season revenue growth.
- Average spending.
- Stay duration.
- Local business participation.
- Occupancy target-band compliance.
- Infrastructure stress avoided.
- Redistribution effectiveness with satisfaction preserved.

## 11. Realtime Tourism Intelligence Framework

Operating loop:

1. Sense: ingest live traffic, crowd, parking, weather, transport, booking, event, review/social, and infrastructure feeds.
2. Diagnose: compute pressure, capacity, satisfaction, and risk indexes with data quality flags.
3. Decide: forecast overload and rank safe alternatives.
4. Act: publish operator alerts, visitor guidance, shuttle/traffic actions, time-slot changes, and incentive recommendations.
5. Learn: compare baseline versus post-intervention load, revenue, satisfaction, and infrastructure stress.

Alert states:

- Green: within local threshold.
- Amber: pressure rising; prepare staffing and communication.
- Red: capacity breach expected or observed; activate rerouting and operational controls.
- Black: safety/environment constraint breached; stop promotion and escalate to authority SOP.

## 12. Tourism Operating System Blueprint

Production services:

- Data lakehouse with raw, bronze, silver, gold, feature, model, and output layers.
- Entity resolution service for hotels, POIs, events, destinations, and transport hubs.
- Geospatial service with map tiles, routing, isochrones, and spatial joins.
- Feature store for demand, congestion, economic, infrastructure, sentiment, and redistribution features.
- Model serving for forecasting, congestion, recommendation, pricing/incentive optimization, and NLP.
- Operations dashboard for local authorities and destination management organizations.
- Partner portal for hotels, transport operators, attractions, and event organizers.
- Ollama/RAG assistant for explainability and policy questions.
- Governance layer for source terms, quality scores, model versions, thresholds, and audit logs.

Current implementation path:

1. Fix geospatial standardization for hotels and destinations using `destination_registry.csv` and `destination_aliases.csv`.
2. Add POI master from OSM/Overpass plus official attraction lists.
3. Populate demand and transport gold tables from official XLS/API sources.
4. Implement sentiment/topic classification for `public_reviews`.
5. Add traffic/crowd/parking feeds for one pilot region, preferably Da Nang - Hoi An - Hue.
6. Build the first operation map with weather, hotel supply, POI capacity, and graph alternatives.
7. Add Ollama RAG over the metadata and KPI catalog.
8. Validate economic value by measuring redistribution uptake, congestion reduction, satisfaction preservation, and off-season revenue impact.
