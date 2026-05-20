# Hệ sinh thái dữ liệu vận hành du lịch Việt Nam

Thư mục `data/` là lớp thiết kế và metadata cho **Tourism Operating System for Vietnam**. Dữ liệu thật đã crawl/tải về nằm chủ yếu trong `datasets/`; `data/` mô tả cách chuẩn hóa, đánh giá chất lượng, xây KPI, thiết kế geospatial, AI và dashboard vận hành.

## Vai trò của `data/`

- Lưu registry nguồn dữ liệu, dataset, KPI, destination, graph, geospatial layer và model AI.
- Làm chuẩn để chuyển dữ liệu từ `datasets/` sang hệ thống vận hành thông minh.
- Không chứa số liệu giả để lấp bảng trống.
- Tách rõ dữ liệu đã có, dữ liệu thiếu và dữ liệu chỉ mới ở mức schema.

## Blueprint và registry

- `metadata/tourism_operating_system_blueprint.md`: blueprint tổng thể gồm 12 output yêu cầu.
- `metadata/dataset_audit.csv`: audit toàn bộ dataset hiện có.
- `metadata/data_quality_scores.csv`: `quality_score`, `freshness_score`, `reliability_score`, `coverage_score`.
- `metadata/missing_dataset_registry.csv`: dữ liệu còn thiếu theo demand, mobility, hotel capacity, review, weather/environment, event và economic.
- `metadata/kpi_catalog_operational.csv`: KPI có nguồn dữ liệu và quyết định vận hành đi kèm.
- `metadata/destination_registry.csv`: destination master mở rộng toàn quốc.
- `metadata/destination_aliases.csv`: chuẩn hóa tên điểm đến.
- `metadata/destination_network_edges.csv`: graph kết nối điểm đến cho điều phối khách.
- `metadata/geospatial_layer_catalog.csv`: các layer GIS bắt buộc.
- `metadata/ai_model_registry.csv`: kiến trúc model AI và Ollama/RAG.

## Luồng dữ liệu mục tiêu

1. `raw`: dữ liệu gốc từ API, CSV, HTML, XLS, PDF hoặc GIS.
2. `bronze`: dữ liệu giữ gần với cấu trúc nguồn.
3. `silver`: dữ liệu đã chuẩn hóa schema, ID, source và timestamp.
4. `gold`: dữ liệu tổng hợp cho dashboard, mô hình và vận hành.
5. `features`: đặc trưng cho AI.
6. `models`: artifact dự báo, congestion, recommendation, pricing/incentive và NLP.
7. `outputs`: forecast, heatmap, dashboard và policy report.
8. `metadata`: catalog, KPI, audit, quality, graph và blueprint.

## Chuẩn hóa bắt buộc

Destination:

- Dùng `destination_id` ổn định, ví dụ `da_nang`.
- Ánh xạ alias như `Da Nang`, `Đà Nẵng`, `Danang`, `DN`.
- Không join dữ liệu bằng text tự do nếu chưa qua alias table.

Time:

- Timestamp dùng UTC ở ingestion.
- Dashboard có thể hiển thị theo `Asia/Ho_Chi_Minh`.
- Mọi bảng phải khai báo granularity: realtime, hourly, daily, monthly.

Geospatial:

- POI phải có lat/lng, province, vùng du lịch, tuyến/cluster, coastal/island/heritage/mountain flags và accessibility score.
- Capacity phải có nguồn: chính thức, operator, sensor, OSM proxy hoặc analyst estimate có kiểm định.

Duplicate/entity resolution:

- Cùng khách sạn xuất hiện ở Booking và Traveloka phải merge qua `canonical_property_id`.
- Cùng POI xuất hiện ở Google Places và OSM phải merge qua tên chuẩn, vị trí, category và source confidence.

## Trạng thái dữ liệu hiện tại

Mạnh:

- Thời tiết lịch sử theo tỉnh từ Open-Meteo.
- Hotel inventory và giá proxy từ OTA.
- Review corpus đã loại reviewer name ở silver/gold.

Yếu hoặc thiếu:

- Arrival demand chính thức chưa được parse thành bảng gold.
- Không có mobility/traffic/crowd realtime.
- Không có POI master, capacity, lat/lng đầy đủ.
- Không có booking velocity hoặc occupancy thật.
- Không có event attendance.
- Không có tourism revenue/local business participation/infrastructure pressure.

## Nguyên tắc vận hành

- Nếu thiếu nguồn, ghi `blocked` hoặc `schema_only`; không tự bịa dữ liệu.
- Dashboard phải hiển thị coverage và freshness, không chỉ hiển thị chỉ số.
- AI assistant chỉ giải thích dựa trên RAG từ metadata, source catalog và dữ liệu đã audit.
- Mỗi khuyến nghị điều phối phải kiểm tra capacity, weather, safety, satisfaction, infrastructure và economic tradeoff.
