# Ghi chú dữ liệu

Thư mục này lưu toàn bộ dữ liệu đã thu thập và dữ liệu sau xử lý. Các file được chia theo lớp để dễ kiểm tra nguồn, lịch sử crawl và kết quả chuẩn hóa.

## Cấu trúc lớp dữ liệu

- `raw/`: file gốc tải từ nguồn, ví dụ HTML, JSON, PDF hoặc file dữ liệu.
- `bronze/`: dữ liệu giữ gần với cấu trúc ban đầu của từng nguồn.
- `silver/`: dữ liệu đã chuẩn hóa schema, có metadata nguồn.
- `gold/`: dữ liệu tổng hợp hoặc dữ liệu phục vụ dashboard, mô hình và phân tích.
- `logs/`: log riêng của crawler planner.
- `source_catalog.csv`: danh mục nguồn đã cấu hình.
- `crawl_plan.csv`: danh sách seed URL, phân loại nguồn và trạng thái ưu tiên API.
- `crawl_log.csv`: log chạy pipeline chính.
- `data_dictionary.md`: mô tả schema và ý nghĩa các trường.

Các nguồn chính thống như VNAT, CAAV hoặc ACV được lưu vào `raw/` trước. Nếu trang chỉ chứa layout, form hoặc chưa có endpoint dữ liệu rõ ràng thì không đưa lên `bronze` hoặc `silver`.

## Traveloka

- `traveloka/traveloka_hotels_full.csv`
- `traveloka/traveloka_reviews.csv`
- `traveloka/debug/`

Dữ liệu Traveloka hiện được dùng để chuẩn hóa sang:

- `bronze/traveloka/hotels/`
- `bronze/traveloka/reviews/`
- `silver/hotels_inventory.*`
- `silver/public_reviews.*`

## Booking

- `booking/booking_hotels.csv`
- `booking/booking_reviews.csv`
- `booking/booking_scrape_status.csv`

Dữ liệu Booking hiện được dùng để chuẩn hóa sang:

- `bronze/booking/hotels/`
- `bronze/booking/reviews/`
- `silver/hotels_inventory.*`
- `silver/public_reviews.*`

## Weather

- `weather/weather_today_vietnam.csv`
- `weather/weather_archive_vietnam.csv`
- `weather/weather_all_vietnam.csv`
- `weather/weather_scrape_status.csv`

Nguồn thời tiết được lấy từ Open-Meteo. Bảng tổng hợp theo tháng nằm ở:

- `gold/weather_monthly_by_province.csv`
- `gold/weather_monthly_by_province.parquet`

## Output chuẩn hóa

- `silver/hotels_inventory.csv` và `.parquet`: danh sách khách sạn từ Booking và Traveloka.
- `silver/public_reviews.csv` và `.parquet`: review công khai, không đưa tên người review vào lớp silver/gold.
- `gold/hotel_supply_by_source_province.csv` và `.parquet`: tổng hợp nguồn cung khách sạn theo nguồn và tỉnh.
- `gold/weather_monthly_by_province.csv` và `.parquet`: đặc trưng thời tiết theo tháng và tỉnh.
- `gold/hotel_inventory_daily.csv` và `.parquet`: dữ liệu khách sạn dạng daily snapshot từ lớp silver.
- `gold/review_sentiment.csv` và `.parquet`: dữ liệu review, sentiment chưa được tính và được đánh dấu `not_computed`.
- `gold/weather_daily.csv` và `.parquet`: dữ liệu thời tiết chi tiết từ file Open-Meteo hiện có.

Các bảng dưới đây hiện chỉ có schema khi chưa có dữ liệu/API đủ điều kiện:

- `gold/tourism_demand_monthly.*`
- `gold/transport_flow_monthly.*`
- `gold/poi_capacity.*`
- `gold/events_calendar.*`

Các bảng schema-only không chứa số liệu tự tạo.

## Nguyên tắc lưu dữ liệu

- Không sửa trực tiếp dữ liệu gốc đã thu thập.
- Không tự tạo số liệu để lấp bảng trống.
- Mỗi record ở lớp chuẩn hóa cần có `source_url`, `crawl_time` và `license_note`.
- Nếu nguồn chưa đủ chắc để parse, chỉ lưu raw và ghi log.
- Với nguồn cần API hoặc quyền partner, chỉ cấu hình seed và ghi chú trạng thái, không scrape tùy tiện.
