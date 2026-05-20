# Giới hạn hệ thống

Repo này chưa phải trung tâm điều hành du lịch realtime hoàn chỉnh. Đây là nền tảng MVP có governance rõ ràng, tách bạch dữ liệu đã có, dữ liệu proxy, bảng schema-only và feed còn thiếu.

## Dataset còn thiếu hoặc đang bị chặn

- Traffic và thời gian di chuyển realtime: chưa có. Cần Google Maps, HERE, TomTom hoặc API trung tâm giao thông địa phương.
- Crowd density: chưa có. Cần sensor/telco aggregate/ticket gate/Wi-Fi/Bluetooth/camera analytics hoặc manual count hợp pháp.
- Parking occupancy: chưa có. Cần smart parking hoặc dữ liệu từ operator địa phương.
- Booking velocity: chưa có. Cần OTA partner, PMS hoặc channel manager feed.
- Occupancy thật: chưa có. Snapshot OTA không phải occupancy.
- Tourism revenue: chưa có ở mức điểm đến/tháng/doanh nghiệp địa phương.
- Spending proxy: chưa có. Cần survey, payment aggregate, tax hoặc partner data.
- Infrastructure pressure: chưa có. Cần dữ liệu nước, rác, điện, nước thải, emergency service và môi trường.
- Event attendance: chưa có. Bảng event calendar tồn tại nhưng chưa có attendance.
- POI capacity: hiện chưa đủ. MVP đã có POI từ OSM nhưng chưa có sức chứa, giờ mở cửa chuẩn hoặc sensitivity môi trường.
- Marine conditions: chưa có. Weather table chưa bao gồm wave height, current, UV vận hành biển hoặc cảnh báo bão chính thức.

## Dataset proxy

- Dữ liệu OTA hotel là proxy về nguồn cung/giá, không phải occupancy hoặc booking demand.
- Review là corpus trải nghiệm, không phải complaint monitoring realtime.
- Destination graph là quan hệ lập kế hoạch, không phải flow đo trực tiếp.
- Weather history/forecast hữu ích cho rủi ro thời tiết nhưng chưa đủ cho an toàn biển hoặc vận hành sự kiện.

## Dataset schema-only cần giữ lại

Các file sau phải được giữ vì chúng là hợp đồng dữ liệu mục tiêu và chứng minh phần tích hợp còn thiếu:

- `datasets/gold/tourism_demand_monthly.csv`
- `datasets/gold/transport_flow_monthly.csv`
- `datasets/gold/poi_capacity.csv`
- `datasets/gold/events_calendar.csv`

Không xóa các file này. Gắn trạng thái `schema_only` hoặc `awaiting official data integration`.

## Giới hạn dashboard

Dashboard hiện tại là bảng evidence MVP. Nó cố tình hiển thị trạng thái thiếu/chặn/proxy. Không được giới thiệu nó như trung tâm điều hành quốc gia realtime cho tới khi tích hợp được traffic, crowd, booking, revenue và hạ tầng.

## Giới hạn AI

Ollama/RAG có thể giải thích metadata, công thức KPI, limitation và logic scenario. Nó không được tuyên bố biết congestion thật, revenue thật, occupancy thật hoặc crowd density thật nếu nguồn bắt buộc chưa tồn tại.
