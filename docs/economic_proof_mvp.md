# Chứng minh kinh tế cho MVP

MVP này không tuyên bố đã điều phối realtime hoặc đã chứng minh tăng doanh thu thực tế. Nó chứng minh một điểm hẹp hơn: dữ liệu mở hợp pháp kết hợp với evidence local có thể hỗ trợ quyết định kinh tế du lịch tốt hơn cách làm dựa vào cảm tính.

## MVP chứng minh được gì ngay

Dữ liệu:

- POI thật từ OpenStreetMap/Overpass.
- Thời tiết hiện tại/dự báo thật từ Open-Meteo.
- Evidence khách sạn, giá và review từ snapshot Booking/Traveloka hiện có.
- Quan hệ destination graph.
- Ma sát di chuyển từ OSRM/Google/fallback graph.

AI/Scoring:

- Điểm rủi ro thời tiết.
- Điểm hấp dẫn POI.
- Proxy áp lực giá khách sạn.
- Proxy hài lòng du khách.
- Điểm ma sát di chuyển.
- Điểm sẵn sàng điểm đến.
- Điểm cơ hội điều phối.

Quyết định:

- Xếp hạng điểm đến thay thế cho lập kế hoạch.
- Tránh đẩy thêm khách vào nơi có rủi ro thời tiết cao.
- Ưu tiên điểm có ma sát di chuyển thấp, nền POI/dịch vụ tốt và proxy hài lòng chấp nhận được.
- Xác định dữ liệu nào cần bổ sung trước khi tự động hóa vận hành.

Logic kinh tế:

- Nếu một điểm chính có nguy cơ quá tải, không nên tiếp tục quảng bá duy nhất điểm đó.
- Chuyển sự chú ý sang điểm gần đó có nền dịch vụ và khả năng tiếp cận tốt hơn.
- Điều này giúp tăng khai thác khách sạn, nhà hàng, điểm tham quan và vận tải ở vùng phụ cận.
- Đây là nền cho dynamic pricing và kích hoạt mùa thấp điểm khi đã có booking/revenue data.

## MVP chưa chứng minh được gì

- Chưa chứng minh giảm congestion vì thiếu traffic/crowd density realtime.
- Chưa chứng minh tăng doanh thu vì thiếu revenue/spending chi tiết.
- Chưa chứng minh occupancy thật vì thiếu PMS/OTA partner booking velocity.
- Chưa chứng minh giảm áp lực hạ tầng vì thiếu waste, water, electricity và environment feed.
- Chưa thể dispatch realtime vì chưa có vòng lặp crowd/traffic/booking trực tiếp.

## Ví dụ quyết định kinh tế

Kịch bản:

- Đà Nẵng là điểm nguồn.
- Hội An, Huế và Quy Nhơn là các điểm thay thế.

Evidence MVP:

- Destination graph xác định Đà Nẵng -> Hội An là tuyến friction thấp.
- OSRM/Google/fallback ước tính ma sát di chuyển.
- Open-Meteo ước tính rủi ro thời tiết.
- OSM đếm điểm tham quan, nhà hàng, khách sạn và POI vận tải.
- OTA snapshot cung cấp proxy giá khách sạn và proxy hài lòng.

Logic gợi ý:

- Ưu tiên điểm thay thế có redistribution score cao.
- Tránh điểm có rủi ro thời tiết cao.
- Xem tuyến friction cao là điều phối chiến dịch, không phải điều phối trong ngày.

Giá trị kinh tế:

- Tăng khai thác tài sản du lịch vùng phụ cận.
- Giảm phụ thuộc vào một điểm đến quá tải.
- Tạo cơ sở cho thiết kế package, shuttle và kích hoạt mùa thấp điểm.

## Dữ liệu cần thêm để chứng minh mạnh hơn

- Booking velocity và availability thật.
- Traffic và crowd density realtime.
- Parking và transport load.
- Event attendance.
- Tourism revenue và spending proxy.
- Local business participation.
- Infrastructure và environmental pressure.
