# Metadata Layer

Thư mục này là lớp governance vận hành ở root repo. Nó bổ sung cho `data/metadata/` và tập trung vào trạng thái triển khai, threshold địa phương và economic proof.

Files:

- `dataset_status_catalog.csv`: trạng thái dataset, mức realtime, blocker và next action.
- `kpi_thresholds_by_destination.csv`: phương pháp threshold theo địa phương, dựa trên capacity, percentile lịch sử hoặc benchmark cùng loại destination.
- `economic_proof_catalog.csv`: chuỗi Data -> AI -> Decision -> Coordination -> Economic Result.

Nguyên tắc:

- Không xóa dataset cũ.
- Không biến proxy thành observed data.
- Không tạo occupancy, crowd density, congestion hoặc revenue giả.
- Nếu thiếu nguồn, ghi rõ `missing`, `schema_only`, `blocked` hoặc `proxy_based`.
