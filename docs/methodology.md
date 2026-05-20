# Phương pháp hệ thống

MONEY VERSE được tổ chức như một hệ điều phối kinh tế du lịch ứng dụng AI. Phương pháp là evidence-first: không KPI, model output, thẻ dashboard hoặc khuyến nghị nào được xem là vận hành nếu chưa biết rõ nguồn và coverage.

## Phương pháp quản trị dữ liệu

Mỗi dataset được phân loại:

- `production_ready`: đủ dùng cho quyết định vận hành với nguồn, refresh logic và ý nghĩa rõ ràng.
- `partial`: dùng được cho phân tích hoặc dashboard context, chưa phải tín hiệu vận hành đầy đủ.
- `proxy_based`: dữ liệu quan sát được nhưng chỉ xấp xỉ điều kiện cần đo.
- `schema_only`: bảng tồn tại để giữ contract nhưng chưa có record sử dụng được.
- `missing`: dataset bắt buộc chưa được tích hợp.
- `planned`: nguồn/API đã biết nhưng chưa triển khai.

Các trường evidence cần có:

- `source_name`
- `source_url`
- `collection_time`
- `update_frequency`
- `license_note`
- `collection_method`
- `reliability_score`
- `freshness_score`
- `quality_score`
- `coverage_score`

Evidence hiện nằm ở `datasets/source_catalog.csv`, `data/metadata/dataset_audit.csv`, `data/metadata/data_quality_scores.csv` và `metadata/dataset_status_catalog.csv`.

## Phương pháp KPI

Công thức KPI phải map được tới dữ liệu quan sát hoặc feed đối tác được phê duyệt. Nếu thiếu component thì KPI không hoàn chỉnh.

Ví dụ:

- Congestion Pressure Index = travel-time delay + crowd density + parking pressure + hotspot load.
- Economic Efficiency Index = giá trị kinh tế du lịch / áp lực hạ tầng.
- Redistribution Opportunity Score = năng lực còn trống + accessibility + weather suitability - travel friction.

Threshold không dùng một con số chung cho mọi nơi. Threshold phải dựa vào:

- Sức chứa địa phương.
- Percentile lịch sử cùng mùa.
- Benchmark giữa các điểm đến cùng loại.
- Ràng buộc an toàn, hạ tầng và môi trường.

Khung threshold ban đầu nằm ở `metadata/kpi_thresholds_by_destination.csv`.

## Phương pháp AI

AI được dùng để:

- Dự báo nhu cầu.
- Phát hiện rủi ro quá tải.
- Xếp hạng điểm thay thế an toàn.
- Ước tính tradeoff kinh tế.
- Phân loại sentiment, crowding complaint, cleanliness, queue và service topic.
- Giải thích KPI bằng Ollama/RAG.

AI không phải nguồn sự thật. AI phải truy xuất và trích dẫn metadata được quản trị trước khi trả lời.

## Phương pháp geospatial

Hệ geospatial cần canonical destination ID, POI ID, route edge, capacity layer và threshold địa phương. Repo hiện đã có destination nodes và graph edges; MVP đã bổ sung POI từ OSM/Overpass, nhưng vẫn thiếu capacity layer đầy đủ.

Layer bắt buộc nằm ở `data/metadata/geospatial_layer_catalog.csv`.

## Phương pháp chứng minh kinh tế

Chuỗi chứng minh:

Data -> AI detection -> decision -> coordination mechanism -> economic result.

Proof catalog hiện ở `metadata/economic_proof_catalog.csv`. Phần lớn chuỗi proof vẫn bị chặn vì thiếu revenue, occupancy, infrastructure pressure và mobility feed.
