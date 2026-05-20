# Giải thích dashboard

Bảng điều khiển vận hành kinh tế du lịch thông minh được xây như một dashboard MVP, không phải visualization trang trí.

## Các trang

### Overview

Hiển thị:

- Destination Health Index.
- Demand Index.
- Congestion Index.
- Economic Efficiency.
- Revenue Stability.
- Satisfaction Score.

Nếu dataset bắt buộc còn thiếu, thẻ phải hiển thị `blocked`, `schema_only` hoặc `proxy_based`.

### Map

Dùng Leaflet/OpenStreetMap và destination graph để hiển thị:

- Điểm đến.
- Tuyến điều phối.
- Layer congestion/economic còn thiếu.
- Điểm đến có weather data.
- Các heatmap cần bổ sung trong tương lai.

Bản đồ hiện tại không phải live heatmap vì chưa có crowd density và traffic feed.

### Economy

Hiển thị:

- KPI kinh tế nào đang bị chặn.
- Evidence nào cần để chứng minh revenue, occupancy, spending và infrastructure pressure.
- Trạng thái chuỗi chứng minh kinh tế.

### Gợi ý AI

Hiển thị logic gợi ý cho các scenario như Đà Nẵng quá tải. Trang này giải thích AI có thể đề xuất gì ở MVP và dữ liệu nào còn cần trước khi tự động hóa vận hành.

## Quy tắc toàn vẹn dữ liệu

Dashboard không được tự điền ùn tắc realtime, doanh thu, occupancy, crowd density hoặc áp lực môi trường bằng số giả. Thiếu dữ liệu là một trạng thái hợp lệ cần hiển thị rõ.
