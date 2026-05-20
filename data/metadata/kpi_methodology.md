# Phương pháp KPI cho MVP

Tài liệu này định nghĩa các KPI có thể tính ngay bằng dữ liệu mở hợp pháp và evidence local hiện có. Đây là KPI hỗ trợ quyết định ở mức MVP, không phải chỉ số điều hành realtime.

## Nhóm evidence

- Dữ liệu mở quan sát được: POI từ OpenStreetMap/Overpass và thời tiết từ Open-Meteo.
- Evidence local: snapshot khách sạn/review từ Booking và Traveloka đã có trong repo.
- Proxy tuyến đường: Google Distance Matrix nếu có `GOOGLE_MAPS_API_KEY`, nếu không dùng OSRM public route API, cuối cùng mới fallback về destination graph.
- Feed sản xuất còn thiếu: traffic realtime, crowd density, booking velocity, occupancy thật, doanh thu, spending, áp lực hạ tầng.

## Điểm rủi ro thời tiết

Công thức:

`min(100, precipitation*8 + rain*8 + wind_speed_10m*1.8 + uv_index_max_3d*4 + severe_weather_code_bonus)`

Nguồn dữ liệu:

- Open-Meteo Forecast API.
- `datasets/gold/weather_daily.csv` chỉ dùng fallback nếu API lỗi.

Độ tin cậy:

- Cao cho thời tiết phổ thông.
- Trung bình cho vận hành du lịch vì chưa có sóng biển, dòng chảy, cảnh báo bão chính thức.

Vì sao hợp lý:

- Mưa, gió và UV ảnh hưởng trực tiếp tới du lịch ngoài trời, bãi biển, sự kiện và di chuyển.

Giới hạn:

- Không phải điểm an toàn biển.
- Không thay thế cảnh báo bão chính thức.

Threshold:

- MVP dùng percentile/proxy.
- Xanh: dưới p60 theo lịch sử địa phương.
- Vàng: p60-p85.
- Đỏ: trên p85 hoặc có cảnh báo chính thức.

## Điểm hấp dẫn POI

Công thức:

`minmax(attraction_poi_count + service_poi_count*0.4)`

Nguồn dữ liệu:

- OpenStreetMap/Overpass API.

Độ tin cậy:

- Trung bình. OSM là dữ liệu thật nhưng độ phủ khác nhau theo địa phương.

Vì sao hợp lý:

- Điểm đến có nhiều điểm tham quan, nhà hàng, khách sạn và dịch vụ thường có khả năng hấp thụ khách tốt hơn.

Giới hạn:

- Số lượng POI không đồng nghĩa với sức chứa hoặc chất lượng.
- Nơi OSM thiếu dữ liệu có thể bị đánh giá thấp.

Threshold:

- Dùng percentile trong cùng nhóm điểm đến sau khi QA độ phủ.

## Proxy áp lực giá khách sạn

Công thức:

`minmax(median_hotel_price_proxy by destination)`

Nguồn dữ liệu:

- Evidence Booking/Traveloka local trong `datasets/gold/hotel_inventory_daily.csv`.

Độ tin cậy:

- Trung bình thấp cho áp lực nhu cầu.
- Đây là proxy giá, không phải occupancy hay booking velocity.

Vì sao hợp lý:

- Giá hiển thị cao có thể phản ánh nhu cầu mạnh hoặc phân khúc cao hơn, nhưng không chứng minh được occupancy.

Giới hạn:

- Cần QA tiền tệ và điều khoản nền tảng.
- Không có availability thật, room count hoặc booking velocity.

Threshold:

- Dùng percentile theo loại điểm đến và mùa khi có đủ nhiều snapshot.

## Proxy hài lòng du khách

Công thức:

`mean(review/hotel rating) * 10`

Nguồn dữ liệu:

- Rating khách sạn/review từ Booking và Traveloka.

Độ tin cậy:

- Trung bình cho proxy chất lượng khách sạn.
- Thấp cho mức hài lòng toàn điểm đến.

Vì sao hợp lý:

- Rating là tín hiệu chất lượng công khai và quan sát được.

Giới hạn:

- Chưa chạy sentiment model.
- Thiếu satisfaction của POI, nhà hàng, vận tải và sự kiện.

Threshold:

- Dùng percentile theo loại điểm đến sau khi đủ coverage review.

## Điểm ma sát di chuyển

Công thức:

`min(100, route_time_minutes / 360 * 100)`

Nguồn dữ liệu:

- Google Distance Matrix API nếu cấu hình `GOOGLE_MAPS_API_KEY`.
- OSRM public route API nếu không có Google key.
- Destination graph fallback nếu route API lỗi.

Độ tin cậy:

- Trung bình khi có OSRM/Google route.
- Thấp hơn nếu fallback về graph estimate.

Vì sao hợp lý:

- Thời gian di chuyển ngắn làm việc điều phối khách dễ chấp nhận hơn.

Giới hạn:

- Không phải traffic realtime.
- OSRM không phản ánh đầy đủ phà, thời tiết xấu, kẹt xe hoặc giới hạn vận hành.

Threshold:

- Điều phối trong ngày: ưu tiên friction thấp đến trung bình.
- Điều phối dạng campaign: friction cao vẫn có thể chấp nhận.

## Điểm cơ hội điều phối

Công thức:

`0.25*underutilized_capacity_proxy + 0.25*accessibility + 0.20*weather_suitability + 0.15*poi_attractiveness + 0.15*tourist_satisfaction_proxy`

Nguồn dữ liệu:

- Destination graph.
- OSRM/Google/fallback route time.
- Open-Meteo weather risk.
- OSM POI score.
- OTA hotel/review proxy.

Độ tin cậy:

- Trung bình cho lập kế hoạch.
- Chưa đủ điều kiện dispatch realtime.

Vì sao hợp lý:

- Điểm thay thế tốt cần dễ đến, thời tiết phù hợp, đủ hấp dẫn, giá không quá căng và có tín hiệu hài lòng chấp nhận được.

Giới hạn:

- Chưa có capacity realtime, crowd, booking, doanh thu hoặc áp lực hạ tầng.

Threshold:

- Xếp hạng theo score.
- Không kích hoạt nếu thời tiết rủi ro cao hoặc capacity chưa rõ ở điểm nhạy cảm.

## Điểm sẵn sàng điểm đến

Công thức:

`0.30*poi_attractiveness + 0.25*(100-weather_risk) + 0.20*tourist_satisfaction_proxy + 0.15*hotel_record_score + 0.10*data_quality`

Nguồn dữ liệu:

- OSM/Overpass POI.
- Open-Meteo.
- Evidence local khách sạn/review.
- Data quality score.

Độ tin cậy:

- Trung bình ở mức proxy sẵn sàng MVP.

Vì sao hợp lý:

- Một điểm đến sẵn sàng cần có tài sản/dịch vụ du lịch, thời tiết chấp nhận được, evidence hài lòng, evidence lưu trú và chất lượng dữ liệu đủ tốt.

Giới hạn:

- Chưa bao gồm crowding thật, occupancy thật, doanh thu, môi trường hoặc áp lực hạ tầng.

Threshold:

- Dùng percentile địa phương và phân nhóm loại điểm đến. Không so trực tiếp đảo, núi, đô thị và di sản nếu chưa chuẩn hóa theo nhóm.
