# SEA - Hệ thống điều hành kinh tế du lịch ven biển Việt Nam

SEA là hệ thống sử dụng dữ liệu, bản đồ số và AI để theo dõi toàn cảnh du lịch Việt Nam, đặc biệt là các điểm đến ven biển. Hệ thống giúp phát hiện điểm đến có áp lực cao, dự báo nhu cầu, đề xuất điều phối khách, gợi ý vé/combo/ăn uống/hạ tầng và giải thích hiệu quả kinh tế kỳ vọng.

Repo: https://github.com/Quyennrose/SEA

SEA không chỉ trực quan hóa dữ liệu. SEA biến dữ liệu thành quyết định điều hành: cảnh báo điểm nóng, dự báo nhu cầu, điều phối khách, đề xuất vé/combo/ăn uống/hạ tầng và chứng minh hiệu quả kinh tế cho du lịch ven biển Việt Nam.

## Mục tiêu vận hành

Chuỗi chứng minh của SEA:

`Dữ liệu -> Phân tích -> KPI -> Dự báo -> Cảnh báo -> Điều phối -> Hành động -> Hiệu quả kinh tế`

SEA trả lời các câu hỏi chính:

- Điểm nào đang đỏ/cam/vàng/xanh hoặc thiếu dữ liệu?
- Vì sao điểm đó có màu cảnh báo hiện tại?
- Dữ liệu nào chứng minh cảnh báo?
- Dữ liệu có mới không, thiếu gì, độ tin cậy bao nhiêu?
- Nếu không điều phối thì có nguy cơ quá tải, kẹt xe hoặc giảm trải nghiệm không?
- Nên điều phối khách từ đâu sang đâu?
- Chính quyền, công an/giao thông, doanh nghiệp, khách sạn, khu vui chơi, nhà hàng và vận tải nên làm gì?
- Hành động đó tạo hiệu quả kinh tế như thế nào?

## Vì sao tập trung du lịch ven biển

Du lịch ven biển là nhóm có nhu cầu cao theo mùa, chịu ảnh hưởng mạnh của thời tiết, dễ quá tải cục bộ và có chuỗi chi tiêu lớn: lưu trú, ăn uống, vé, shuttle, bãi đỗ, OCOP và trải nghiệm liên vùng. SEA ưu tiên các điểm ven biển như Đà Nẵng, Hạ Long, Nha Trang, Phú Quốc, Hội An, Quy Nhơn, Vũng Tàu, Mũi Né, Cát Bà, Sầm Sơn, Cửa Lò, Côn Đảo và Lý Sơn, sau đó mở rộng cho toàn quốc.

## Dữ liệu sử dụng

Dashboard chỉ đọc dữ liệu đã xử lý ở `datasets/gold/current/`. Raw data được giữ nguyên trong `datasets/raw/`.

Nguồn dữ liệu:

- OSM/Overpass: POI, bãi biển, khách sạn, nhà hàng, bãi đỗ, khu vui chơi.
- Open-Meteo: thời tiết hiện tại, dự báo và tín hiệu rủi ro thời tiết.
- OSRM/OpenRouteService nếu có: tuyến điều phối và thời gian di chuyển.
- RapidAPI Google SERP nếu có key: tin tức, báo cáo, tín hiệu thị trường.
- RapidAPI Maps Extractor nếu có key: business info, rating, review nếu endpoint hỗ trợ.
- Positionstack nếu có key: geocode địa chỉ/POI/khách sạn.
- Booking/Traveloka/public snapshot nếu có trong repo: proxy giá và lưu trú.
- Google Sheets: chỉ dùng để xem nhanh summary, không phải kho raw chính.

Không gọi proxy là realtime. Không xem bảng trống hoặc schema-only là dữ liệu thật. Nếu thiếu API key, pipeline bỏ qua nguồn đó, ghi trạng thái thiếu cấu hình và không làm dashboard crash.

## Realtime, near-realtime và proxy

- **Realtime:** dữ liệu trực tiếp, cập nhật liên tục từ đối tác như camera, cảm biến, traffic, ticket sales hoặc occupancy. SEA chỉ gọi là realtime khi thật sự có nguồn này.
- **Near-realtime:** dữ liệu gần hiện tại từ API hoặc nguồn online như thời tiết, route, review, tin tức. Đây không phải dữ liệu đo trực tiếp liên tục.
- **Proxy:** chỉ số ước lượng có kiểm soát khi chưa có dữ liệu đo trực tiếp. Ví dụ chưa có số người realtime ở bãi biển, SEA dùng thời tiết, cuối tuần, mật độ khách sạn, POI, tin tức và giá để ước lượng nguy cơ đông.

## KPI và thang đo

Tất cả KPI dùng thang 0-100.

## Màu cảnh báo dùng chung

Dashboard dùng một cấu hình màu duy nhất tại `dashboard/theme/colors.py`. Không biểu đồ nào tự chọn palette riêng cho cảnh báo vận hành.

- Xanh: còn dư địa / bình thường.
- Vàng: cần theo dõi.
- Cam: áp lực cao.
- Đỏ: nguy cơ quá tải / ưu tiên xử lý.
- Tím nhạt/xanh xám: thiếu dữ liệu.

Hàm dùng chung:

- `get_alert_color(muc_canh_bao)`: đổi mức cảnh báo sang màu chuẩn.
- `get_score_color(score, is_reverse=False, missing=False)`: đổi điểm 0-100 sang màu chuẩn.

Logic áp lực: thiếu dữ liệu -> tím nhạt/xanh xám, 0-39 -> xanh, 40-69 -> vàng, 70-84 -> cam, 85-100 -> đỏ.

Logic hạ tầng (`is_reverse=True`, vì điểm càng cao càng tốt): thiếu dữ liệu -> tím nhạt/xanh xám, 0-39 -> đỏ, 40-69 -> vàng, 70-84 -> xanh nhạt, 85-100 -> xanh.

Các phần đang gọi chung màu này gồm ranking, marker bản đồ, thẻ hành động, KPI trong hồ sơ điểm đến, bar chart, donut/pie chart, heatmap và forecast.

## Ranking mở rộng

Ranking toàn quốc không được đọc danh sách 24 điểm mẫu. Nguồn hiện hành là:

- `datasets/gold/current/danh_sach_diem_den_mo_rong.csv`
- `datasets/gold/current/xep_hang_canh_bao_toan_quoc.csv`

Seed list tối thiểu bao phủ tỉnh/thành ven biển Việt Nam, thành phố du lịch lớn, đảo/khu biển nổi bật, điểm di sản và đô thị du lịch liên quan. Nếu dashboard thấy danh sách dưới 50 điểm, nó hiển thị cảnh báo: `Danh sách điểm đến còn thiếu, cần chạy mở rộng dữ liệu.`

File ranking hiện có thêm cột thời tiết:

- `nhiet_do_hien_tai`
- `kha_nang_mua`
- `gio`
- `trang_thai_thoi_tiet_ngan`
- `cap_nhat_thoi_tiet_luc`

Bảng thời tiết được ghi riêng để dashboard và hồ sơ điểm đến đọc trực tiếp:

- `datasets/gold/current/thoi_tiet_hien_tai.csv`
- `datasets/gold/current/du_bao_thoi_tiet_7_ngay.csv`

## API và thời tiết

Dashboard đọc trực tiếp `.env` ở gốc repo bằng `load_dotenv(ROOT / ".env", override=True)`. Không dùng thư mục cấu hình lồng bên trong repo. Trang `API & Sheet` lấy trạng thái chính từ `os.getenv` sau khi load `.env`; nếu có key thì hiển thị `Đã cấu hình`, nếu thiếu thì hiển thị `Thiếu cấu hình`.

Nút `Kiểm tra lại API` đọc lại `.env`, kiểm tra live khi có thể, ghi lại `data/metadata/api_source_catalog.csv` và cập nhật thời điểm kiểm tra cuối.

Open-Meteo không cần key và được dùng cho thời tiết hiện tại, dự báo 24 giờ, forecast 7 ngày, điểm thời tiết, bản đồ và hồ sơ điểm đến. UI dùng nhãn tiếng Việt: `Nhiệt độ hiện tại`, `Khả năng mưa`, `Gió`, `Phù hợp đi biển`, `Cập nhật thời tiết lúc`.

## Hồ sơ điểm đến

Từ `Ranking`, bấm `Xem hồ sơ` để mở dashboard riêng của điểm đến. Từ `Bản đồ`, bấm marker để mở URL dạng:

```text
?page=profile&destination=Ha%20Long
```

Trang hồ sơ lọc theo điểm đến đang chọn và gom KPI, thời tiết, forecast, POI/dịch vụ, hạ tầng, điều phối, hành động, hiệu quả kinh tế, dữ liệu thiếu và độ tin cậy.

Ngưỡng cảnh báo:

- 0-39: xanh, còn dư địa.
- 40-69: vàng, cần theo dõi.
- 70-84: cam, áp lực cao.
- 85-100: đỏ, nguy cơ quá tải.
- Tím nhạt/xanh xám: thiếu dữ liệu, chưa đủ căn cứ đánh giá.

Riêng hạ tầng:

- 0-39: hạ tầng yếu, không nên đẩy khách đại trà.
- 40-69: chỉ điều phối có kiểm soát.
- 70-84: có thể nhận thêm khách có quản lý.
- 85-100: hạ tầng tốt.

Các KPI chính:

- Điểm áp lực điểm đến.
- Điểm áp lực ven biển.
- Điểm rủi ro thời tiết.
- Điểm áp lực vé/khu vui chơi.
- Điểm sẵn sàng hạ tầng.
- Điểm cơ hội kinh tế.
- Điểm điều phối khách.
- Điểm ưu tiên đầu tư.
- Điểm sức khỏe điểm đến.
- Áp lực giá và lưu trú.

Phương pháp nằm trong:

- `data/metadata/kpi_methodology.csv`
- `data/metadata/kpi_scale_catalog.csv`
- `data/metadata/confidence_methodology.csv`

## Độ tin cậy

Độ tin cậy cho biết SEA tự tin đến mức nào với một chỉ số. Công thức:

`confidence_score = 0.30*source_reliability + 0.25*freshness_score + 0.20*coverage_score + 0.15*completeness_score + 0.10*proxy_validation_score`

Nếu không có proxy validation thì trọng số được phân bổ lại cho bốn phần còn lại.

Dashboard hiển thị:

- Cao
- Khá
- Trung bình
- Thấp

Tooltip giải thích nguồn dữ liệu, loại dữ liệu, độ mới, độ phủ, mức đầy đủ và proxy đã được kiểm định chưa.

## Kiểm định proxy

Bảng chính:

- `datasets/gold/current/kiem_dinh_proxy.csv`
- `datasets/gold/current/proxy_vs_nearrealtime_comparison.csv`

Công thức:

- `do_lech_tuyet_doi = abs(diem_proxy - diem_near_realtime)`
- `do_lech_phan_tram = abs(diem_proxy - diem_near_realtime) / max(diem_near_realtime, 1) * 100`

Ngưỡng:

- <= 10%: proxy rất tốt.
- 10-20%: proxy tốt.
- 20-35%: cần theo dõi.
- > 35%: proxy không ổn định, giảm độ tin cậy.

## Cấu trúc thư mục

```text
datasets/
  raw/
    news/
    search_results/
    api/
    tickets/
    osm/
    weather/
  bronze/
  silver/
  gold/
    current/
    archive/
    current_csv/
    current_parquet/
data/
  metadata/
  logs/
exports/
  csv/
  excel/
  reports/
dashboard/
scrapers/
rag/
docs/
.github/workflows/
```

Quy tắc:

- `datasets/gold/current/`: bản mới nhất dashboard đang dùng.
- `datasets/gold/archive/yyyy-mm-dd/`: bản cũ trước mỗi lần cập nhật.
- `datasets/raw/`: dữ liệu gốc, không xóa.
- `exports/csv/` và `exports/excel/`: file cho người xem/giám khảo tải.
- Google Sheets chỉ sync summary, không sync raw data lớn.

## Cấu hình `.env`

SEA đọc trực tiếp file `.env` ở gốc repo bằng `load_dotenv(ROOT / ".env", override=True)`. Dashboard hiển thị trạng thái `Đã đọc cấu hình từ: .env` và kiểm tra API bằng giá trị `os.getenv` sau khi load file này.

File mẫu nằm ở `.env.example`:

```env
RAPIDAPI_KEY=
RAPIDAPI_SERP_HOST=google-serp-search-api.p.rapidapi.com
POSITIONSTACK_API_KEY=
OPENROUTESERVICE_API_KEY=
RAPIDAPI_GOOGLE_MAPS_HOST=google-maps-extractor2.p.rapidapi.com
RAPIDAPI_GOOGLE_PLACES_HOST=
GOOGLE_SHEETS_ID=
GOOGLE_APPLICATION_CREDENTIALS=
GOOGLE_SERVICE_ACCOUNT_JSON=
SYNC_FULL_DATA_TO_SHEETS=false
GEMINI_API_KEY=
AI_PROVIDER=gemini
GEMINI_MODEL=gemini-2.5-flash
OPEN_METEO=https://api.open-meteo.com/v1/forecast?latitude=16.1667&longitude=107.8333&hourly=temperature_2m
```

Không commit file `.env` ở gốc repo. `.gitignore` đã chặn secret; `.env.example` chỉ chứa biến mẫu, không chứa key thật.

## Chạy pipeline

```powershell
python .\scrapers\sea_operating_pipeline.py
```

Pipeline thực hiện:

1. Tạo/cập nhật danh sách điểm đến mở rộng toàn quốc.
2. Archive bản `gold/current` cũ vào `datasets/gold/archive/yyyy-mm-dd/`.
3. Ghi bản mới vào `datasets/gold/current/`, `current_csv/`, `current_parquet/`.
4. Rebuild KPI, forecast, ranking, proxy validation và đề xuất hành động.
5. Cập nhật freshness, source monitor, update queue và pipeline log.
6. Rebuild knowledge base cho trợ lý SEA.
7. Xuất file tải CSV/Excel cho dashboard.

## Chạy dashboard

```powershell
streamlit run .\dashboard\app.py
```

Menu dashboard:

- Tổng quan
- Bản đồ
- Ranking
- Hồ sơ điểm đến
- Dự báo
- Điều phối
- Vé & chi tiêu
- Hiệu quả kinh tế
- Dữ liệu
- Cập nhật
- API & Sheet
- Giải thích
- Trợ lý SEA

Mọi thời gian hiển thị theo giờ Việt Nam dạng `dd/mm/yyyy HH:MM`, ví dụ `20/05/2026 14:38`.

## Bản đồ điều hành

Trang Bản đồ có:

- Marker tròn rõ màu, có viền.
- Legend lớn: đỏ, cam, vàng, xanh, thiếu dữ liệu.
- Bộ lọc mức cảnh báo, loại điểm, loại dữ liệu và điểm cần xử lý.
- Layer bật/tắt: điểm đến, POI/khách sạn/ăn uống, tuyến điều phối, heatmap áp lực, heatmap POI.
- Hover marker: tên điểm đến, mức cảnh báo, điểm áp lực, nhiệt độ hiện tại, dự báo 7 ngày, lý do chính.
- Click marker: mở panel hồ sơ điểm đến bên phải.

Nếu điểm thiếu dữ liệu, panel ghi rõ điểm này thiếu nguồn quan trọng như tọa độ, thời tiết, POI, khách sạn, tuyến di chuyển, vé/khu vui chơi, tin tức hoặc cập nhật gần đây.

## Hồ sơ điểm đến

Trang Hồ sơ điểm đến cho từng điểm như Hạ Long, Đà Nẵng, Nha Trang, Phú Quốc hoặc bất kỳ điểm nào trong ranking.

Nội dung:

- Tình hình hiện tại: mức cảnh báo, thời tiết, áp lực, lý do màu cảnh báo.
- Chỉ số vận hành: áp lực, hạ tầng, thời tiết, cơ hội kinh tế, điều phối, sức khỏe điểm đến, độ tin cậy.
- Biểu đồ riêng: forecast, calendar heatmap, hạ tầng vs áp lực, cơ hội kinh tế.
- Hạ tầng và dịch vụ: khách sạn, nhà hàng, khu vui chơi, POI, điểm yếu hạ tầng.
- Điều phối: điểm nguồn/đích, thời gian di chuyển, lý do chọn điểm thay thế.
- Hành động kinh tế: ai cần làm, chi phí, KPI tác động, hiệu quả kỳ vọng.
- Dữ liệu & độ tin cậy: dữ liệu thật, near-realtime, proxy, dữ liệu thiếu, nguồn, cập nhật lần cuối.

## Dự báo

Forecast nằm ở:

- `datasets/gold/current/forecast_demand_scores.csv`

Dashboard hiển thị:

- Line chart: dự báo SEA, trung bình mùa vụ nếu có, lịch sử cùng kỳ nếu có, vùng bất định nếu có.
- Calendar heatmap: ngày xanh/vàng/cam/đỏ theo áp lực dự kiến.
- Top 10 điểm rủi ro tăng trong 7 ngày tới.
- Top 10 điểm có cơ hội kích cầu.

Nếu chưa đủ lịch sử 3-5 năm, SEA hiển thị rõ đây là proxy forecast dựa trên thời tiết, cuối tuần, POI, khách sạn và tin tức; độ tin cậy thấp hơn.

## Điều phối khách

Trang Điều phối trả lời:

- Điểm nào đang áp lực?
- Điểm nào còn dư địa?
- Nên chuyển từ đâu sang đâu?
- Đi mất bao lâu?
- Vì sao điều phối như vậy?
- Hiệu quả kinh tế là gì?

Biểu đồ gồm bảng tuyến, bản đồ tuyến, Sankey, bar chart lợi ích điều phối và scatter áp lực vs hạ tầng.

## Hành động và hiệu quả kinh tế

Bảng chính:

- `datasets/gold/current/de_xuat_hieu_qua_kinh_te.csv`
- `datasets/gold/current/economic_action_recommendations.csv`

Mỗi đề xuất theo format:

```text
Vấn đề:
Hành động:
KPI dự kiến thay đổi:
Hiệu quả kinh tế:
Dữ liệu chứng minh:
Độ tin cậy:
```

Dashboard hiển thị dạng action cards, nhóm theo chính quyền, công an/giao thông, doanh nghiệp du lịch, khách sạn, khu vui chơi, nhà hàng/OCOP và vận tải/shuttle.

## Trung tâm cập nhật dữ liệu

Các file vận hành:

- `data/metadata/source_monitor_status.csv`
- `data/metadata/data_freshness_status.csv`
- `data/metadata/update_queue.csv`
- `data/metadata/pipeline_run_log.csv`
- `data/metadata/source_check_log.csv`
- `data/metadata/trang_thai_nguon_du_lieu.csv`
- `data/metadata/trang_thai_do_moi_du_lieu.csv`
- `data/metadata/hang_cho_cap_nhat.csv`
- `data/metadata/nhat_ky_pipeline.csv`

Dashboard hiển thị:

- Dữ liệu mới nhất.
- Cần cập nhật.
- Có dữ liệu mới chờ xử lý.
- Cập nhật lỗi.
- Lần kiểm tra cuối.
- Lần cập nhật thành công cuối.
- Dataset bị ảnh hưởng.
- Bấm cập nhật sẽ làm gì.

Khi bấm **Cập nhật dữ liệu**, SEA:

1. Kiểm tra nguồn.
2. Tải dữ liệu mới nếu có.
3. Lưu bản cũ vào archive.
4. Ghi bản mới vào current.
5. Tính lại KPI.
6. Tính lại forecast.
7. Cập nhật ranking.
8. Cập nhật AI knowledge base.
9. Đồng bộ Google Sheets summary nếu đã cấu hình.

Nếu lỗi, SEA giữ bản current ổn định gần nhất và ghi lỗi vào nhật ký.

## Google Sheets

Google Sheets chỉ sync summary cần thiết:

- Tổng quan cập nhật.
- Nguồn dữ liệu.
- Dữ liệu mới cập nhật.
- Dữ liệu cũ gần đây.
- Ranking toàn quốc.
- Dự báo.
- Kiểm định proxy.
- Hiệu quả kinh tế.

Để ghi được lên Google Sheets cần đủ 3 điều kiện:

- `GOOGLE_SHEETS_ID`: ID của file Sheet.
- Credentials service account: dùng `GOOGLE_APPLICATION_CREDENTIALS` trỏ tới file JSON, hoặc `GOOGLE_SERVICE_ACCOUNT_JSON` chứa nguyên JSON.
- Sheet phải được share quyền Editor cho email `client_email` trong service account JSON.

Nếu thiếu package sync, chạy:

```powershell
pip install -r requirements.txt
```

Nếu chưa cấu hình `GOOGLE_SHEETS_ID` hoặc credentials, dashboard hiển thị lỗi cụ thể:

`Chưa cấu hình Google Sheets. SEA vẫn chạy bình thường; có thể tải CSV/Excel từ Kho dữ liệu.`

## Trạng thái API

Trang API & Sheet hiển thị:

- Tên nguồn.
- Vai trò.
- Biến môi trường.
- Trạng thái cấu hình.
- Kết quả kiểm tra.
- Lần kiểm tra cuối.
- Ảnh hưởng nếu thiếu.
- Nguồn thay thế.

Nếu thiếu key, SEA ghi:

`Thiếu cấu hình. Nguồn này chưa được cấu hình nên SEA sẽ bỏ qua và dùng nguồn thay thế nếu có. Điều này có thể làm giảm độ phủ hoặc độ mới dữ liệu.`

## Trợ lý SEA

Trợ lý SEA là chatbox nổi góc phải dưới và có trang riêng.

Lời chào:

`Xin chào, tôi là trợ lý SEA. Bạn có thể hỏi tôi về cảnh báo du lịch, thời tiết, dữ liệu cập nhật, dự báo, điều phối khách và hiệu quả kinh tế.`

Câu trả lời theo format:

```text
Tình hình:
Vì sao:
Dữ liệu dùng:
Độ tin cậy:
Nên làm:
Hiệu quả kinh tế:
```

Trợ lý đọc knowledge base đã build sẵn và các bảng current/metadata đã xử lý. Nếu thiếu dữ liệu, trợ lý nói rõ cần bổ sung gì, không trả lời chung chung.

## GitHub Actions

Workflow:

- `.github/workflows/data_monitor.yml`

Workflow chạy tự động mỗi 6 giờ và hỗ trợ `workflow_dispatch`. Các bước chính:

- Lịch tự động: `0 */6 * * *` UTC, tương đương khoảng 01:00, 07:00, 13:00, 19:00 Asia/Ho_Chi_Minh.
- API key lấy từ GitHub Actions Secrets, không commit `.env`.
- Workflow chạy `python scrapers/sea_operating_pipeline.py`.
- Sau khi chạy, workflow commit lại `datasets/gold/current`, `datasets/gold/current_csv`, `datasets/gold/current_parquet`, `data/metadata`, `exports` và `rag`.
- Google Sheets được đồng bộ nếu đã cấu hình `GOOGLE_SHEETS_ID` và `GOOGLE_SERVICE_ACCOUNT_JSON` trong GitHub Secrets.
- Open-Meteo không cần key; workflow dùng biến `OPEN_METEO` trong GitHub Actions Variables nếu có, nếu không thì dùng endpoint mặc định.

```powershell
python scrapers/source_monitor.py
python scrapers/build_destination_registry.py
python scrapers/google_serp_news_monitor.py
python scrapers/news_monitor.py
python scrapers/check_freshness.py
python scrapers/fetch_ticket_data.py
python scrapers/fetch_api_geocoding.py
python scrapers/build_kpi_scores.py
python scrapers/build_forecast.py
python scrapers/build_action_recommendations.py
python rag/build_knowledge_base.py
```

## Giới hạn hiện tại

SEA hiện vẫn có nhiều nguồn proxy và public snapshot. Những nguồn cần bổ sung để nâng độ tin cậy:

- Crowd/camera/cảm biến tại điểm nóng.
- Traffic realtime.
- Occupancy khách sạn từ đối tác.
- Doanh số vé/khu vui chơi theo giờ.
- API giá phòng và vé máy bay hợp lệ.
- Dữ liệu chi tiêu thực tế theo vùng.
- Lịch sử 3-5 năm đầy đủ cho forecast mùa vụ.

Khi thiếu dữ liệu thật, SEA hiển thị “thiếu dữ liệu”, giảm độ tin cậy và đề xuất nguồn/API cần bổ sung.

## Bảo mật API key

- Không hard-code API key.
- Không commit `.env`.
- Không in key lên dashboard.
- Nếu thiếu key, pipeline ghi trạng thái thiếu cấu hình và dùng fallback nếu có.
