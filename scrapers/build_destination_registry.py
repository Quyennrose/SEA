from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "data" / "metadata"
CURRENT = ROOT / "datasets" / "gold" / "current"


def now_vn_text() -> str:
    return datetime.now().astimezone().strftime("%d/%m/%Y %H:%M")


REGION_LABELS = {
    "central_coast": "Duyên hải miền Trung",
    "central_coast_islands": "Đảo miền Trung",
    "central_highlands": "Tây Nguyên",
    "mekong_delta": "Đồng bằng sông Cửu Long",
    "mekong_islands": "Đảo Tây Nam Bộ",
    "northeast": "Đông Bắc",
    "north_central_coast": "Bắc Trung Bộ",
    "northern_mountains": "Miền núi phía Bắc",
    "red_river_delta": "Đồng bằng sông Hồng",
    "south_central_coast": "Nam Trung Bộ",
    "southeast": "Đông Nam Bộ",
    "southeast_islands": "Đảo Đông Nam Bộ",
}

TOURISM_TYPE_LABELS = {
    "coastal": "biển",
    "beach": "bãi biển",
    "urban": "đô thị",
    "heritage": "di sản",
    "island": "đảo",
    "mountain": "núi",
    "nature": "tự nhiên",
    "gateway": "cửa ngõ",
    "mekong": "Mekong",
}


def region_label(value: object) -> str:
    text = str(value).strip()
    return REGION_LABELS.get(text.lower(), text)


def tourism_type_label(value: object) -> str:
    text = str(value).strip()
    parts = [part.strip() for part in text.replace(",", ";").split(";") if part.strip()]
    return "; ".join(TOURISM_TYPE_LABELS.get(part.lower(), part) for part in parts)


BASE_DESTINATIONS = [
    ("ha_long", "Hạ Long", "Quảng Ninh", "Đông Bắc", "biển;di sản;đô thị", 20.9712, 107.0448, "có"),
    ("co_to", "Cô Tô", "Quảng Ninh", "Đông Bắc", "đảo;biển", 20.9736, 107.7657, "có"),
    ("tra_co", "Trà Cổ", "Quảng Ninh", "Đông Bắc", "bãi biển;biên giới", 21.4644, 108.0142, "có"),
    ("cat_ba", "Cát Bà", "Hải Phòng", "Đông Bắc", "đảo;biển;tự nhiên", 20.7278, 107.0482, "có"),
    ("do_son", "Đồ Sơn", "Hải Phòng", "Đồng bằng sông Hồng", "bãi biển;đô thị", 20.7149, 106.7894, "có"),
    ("thinh_long", "Thịnh Long", "Nam Định", "Đồng bằng sông Hồng", "bãi biển", 20.0333, 106.2833, "có"),
    ("hai_tien", "Hải Tiến", "Thanh Hóa", "Bắc Trung Bộ", "bãi biển", 19.8605, 105.9297, "có"),
    ("sam_son", "Sầm Sơn", "Thanh Hóa", "Bắc Trung Bộ", "bãi biển", 19.7419, 105.9020, "có"),
    ("cua_lo", "Cửa Lò", "Nghệ An", "Bắc Trung Bộ", "bãi biển", 18.7929, 105.7220, "có"),
    ("thien_cam", "Thiên Cầm", "Hà Tĩnh", "Bắc Trung Bộ", "bãi biển", 18.2597, 106.1053, "có"),
    ("nhat_le", "Nhật Lệ", "Quảng Bình", "Bắc Trung Bộ", "bãi biển", 17.4833, 106.6233, "có"),
    ("phong_nha", "Phong Nha - Kẻ Bàng", "Quảng Bình", "Bắc Trung Bộ", "di sản;tự nhiên", 17.5903, 106.2830, "không"),
    ("cua_tung", "Cửa Tùng", "Quảng Trị", "Bắc Trung Bộ", "bãi biển", 17.1012, 107.1028, "có"),
    ("lang_co", "Lăng Cô", "Huế", "Duyên hải miền Trung", "bãi biển;đầm phá", 16.2383, 108.0789, "có"),
    ("hue", "Huế", "Huế", "Duyên hải miền Trung", "di sản;đô thị", 16.4637, 107.5909, "không"),
    ("da_nang", "Đà Nẵng", "Đà Nẵng", "Duyên hải miền Trung", "biển;đô thị;cửa ngõ", 16.0471, 108.2068, "có"),
    ("my_khe", "Mỹ Khê", "Đà Nẵng", "Duyên hải miền Trung", "bãi biển", 16.0544, 108.2478, "có"),
    ("ba_na", "Bà Nà Hills", "Đà Nẵng", "Duyên hải miền Trung", "khu vui chơi;núi", 15.9950, 107.9970, "không"),
    ("hoi_an", "Hội An", "Quảng Nam", "Duyên hải miền Trung", "di sản;biển", 15.8801, 108.3380, "có"),
    ("cu_lao_cham", "Cù Lao Chàm", "Quảng Nam", "Duyên hải miền Trung", "đảo;biển", 15.9550, 108.5100, "có"),
    ("tam_ky", "Tam Kỳ", "Quảng Nam", "Duyên hải miền Trung", "đô thị;biển", 15.5736, 108.4740, "có"),
    ("ly_son", "Lý Sơn", "Quảng Ngãi", "Đảo miền Trung", "đảo;biển", 15.3833, 109.1167, "có"),
    ("sa_huynh", "Sa Huỳnh", "Quảng Ngãi", "Duyên hải miền Trung", "bãi biển", 14.6723, 109.0588, "có"),
    ("quy_nhon", "Quy Nhơn", "Bình Định", "Nam Trung Bộ", "biển;đô thị", 13.7563, 109.2297, "có"),
    ("ky_co", "Kỳ Co", "Bình Định", "Nam Trung Bộ", "bãi biển", 13.8950, 109.2910, "có"),
    ("tuy_hoa", "Tuy Hòa", "Phú Yên", "Nam Trung Bộ", "biển;đô thị", 13.0955, 109.3209, "có"),
    ("ghenh_da_dia", "Gành Đá Đĩa", "Phú Yên", "Nam Trung Bộ", "di sản địa chất;biển", 13.3533, 109.2930, "có"),
    ("nha_trang", "Nha Trang", "Khánh Hòa", "Nam Trung Bộ", "biển;đô thị", 12.2388, 109.1967, "có"),
    ("cam_ranh", "Cam Ranh", "Khánh Hòa", "Nam Trung Bộ", "biển;sân bay", 11.9020, 109.2207, "có"),
    ("binh_ba", "Bình Ba", "Khánh Hòa", "Nam Trung Bộ", "đảo;biển", 11.8535, 109.2300, "có"),
    ("vinh_hy", "Vĩnh Hy", "Ninh Thuận", "Nam Trung Bộ", "vịnh;biển", 11.7183, 109.1900, "có"),
    ("phan_rang", "Phan Rang - Tháp Chàm", "Ninh Thuận", "Nam Trung Bộ", "biển;văn hóa", 11.5826, 108.9912, "có"),
    ("mui_ne", "Mũi Né", "Bình Thuận", "Nam Trung Bộ", "biển;thể thao", 10.9333, 108.2833, "có"),
    ("phan_thiet", "Phan Thiết", "Bình Thuận", "Nam Trung Bộ", "biển;đô thị", 10.9804, 108.2615, "có"),
    ("la_gi", "La Gi", "Bình Thuận", "Nam Trung Bộ", "bãi biển", 10.6599, 107.7722, "có"),
    ("vung_tau", "Vũng Tàu", "Bà Rịa - Vũng Tàu", "Đông Nam Bộ", "biển;đô thị", 10.4114, 107.1362, "có"),
    ("ho_tram", "Hồ Tràm", "Bà Rịa - Vũng Tàu", "Đông Nam Bộ", "bãi biển;resort", 10.4770, 107.4260, "có"),
    ("con_dao", "Côn Đảo", "Bà Rịa - Vũng Tàu", "Đảo Đông Nam Bộ", "đảo;biển;di sản", 8.6864, 106.6082, "có"),
    ("can_gio", "Cần Giờ", "TP Hồ Chí Minh", "Đông Nam Bộ", "biển;sinh thái", 10.4111, 106.9547, "có"),
    ("phu_quoc", "Phú Quốc", "Kiên Giang", "Đảo Tây Nam Bộ", "đảo;biển", 10.2899, 103.9840, "có"),
    ("ha_tien", "Hà Tiên", "Kiên Giang", "Tây Nam Bộ", "biển;cửa khẩu", 10.3831, 104.4875, "có"),
    ("nam_du", "Nam Du", "Kiên Giang", "Đảo Tây Nam Bộ", "đảo;biển", 9.6840, 104.3540, "có"),
    ("hon_son", "Hòn Sơn", "Kiên Giang", "Đảo Tây Nam Bộ", "đảo;biển", 9.8100, 104.6300, "có"),
    ("bac_lieu", "Bạc Liêu", "Bạc Liêu", "Đồng bằng sông Cửu Long", "biển;văn hóa", 9.2940, 105.7244, "có"),
    ("ca_mau_dat_mui", "Đất Mũi Cà Mau", "Cà Mau", "Đồng bằng sông Cửu Long", "sinh thái;biển", 8.6208, 104.7314, "có"),
    ("ha_noi", "Hà Nội", "Hà Nội", "Đồng bằng sông Hồng", "đô thị;di sản;cửa ngõ", 21.0278, 105.8342, "không"),
    ("ninh_binh", "Ninh Bình", "Ninh Bình", "Đồng bằng sông Hồng", "di sản;tự nhiên", 20.2506, 105.9745, "không"),
    ("sa_pa", "Sa Pa", "Lào Cai", "Miền núi phía Bắc", "núi;tự nhiên", 22.3364, 103.8438, "không"),
    ("ha_giang", "Hà Giang", "Hà Giang", "Miền núi phía Bắc", "núi;tự nhiên", 22.8233, 104.9836, "không"),
    ("moc_chau", "Mộc Châu", "Sơn La", "Miền núi phía Bắc", "núi;tự nhiên", 20.8297, 104.6946, "không"),
    ("mai_chau", "Mai Châu", "Hòa Bình", "Miền núi phía Bắc", "cộng đồng;núi", 20.6629, 105.0830, "không"),
    ("tam_dao", "Tam Đảo", "Vĩnh Phúc", "Trung du miền núi Bắc Bộ", "núi;nghỉ dưỡng", 21.4569, 105.6442, "không"),
    ("ba_vi", "Ba Vì", "Hà Nội", "Đồng bằng sông Hồng", "sinh thái;núi", 21.0820, 105.3740, "không"),
    ("ho_chi_minh_city", "TP Hồ Chí Minh", "TP Hồ Chí Minh", "Đông Nam Bộ", "đô thị;cửa ngõ", 10.8231, 106.6297, "không"),
    ("da_lat", "Đà Lạt", "Lâm Đồng", "Tây Nguyên", "núi;đô thị", 11.9404, 108.4583, "không"),
    ("buon_ma_thuot", "Buôn Ma Thuột", "Đắk Lắk", "Tây Nguyên", "văn hóa;tự nhiên", 12.6667, 108.0500, "không"),
    ("pleiku", "Pleiku", "Gia Lai", "Tây Nguyên", "văn hóa;tự nhiên", 13.9718, 108.0151, "không"),
    ("can_tho", "Cần Thơ", "Cần Thơ", "Đồng bằng sông Cửu Long", "mekong;đô thị", 10.0452, 105.7469, "không"),
    ("ben_tre", "Bến Tre", "Bến Tre", "Đồng bằng sông Cửu Long", "mekong;sinh thái", 10.2434, 106.3756, "không"),
    ("an_giang", "An Giang", "An Giang", "Đồng bằng sông Cửu Long", "mekong;di sản;tự nhiên", 10.5216, 105.1259, "không"),
    ("chau_doc", "Châu Đốc", "An Giang", "Đồng bằng sông Cửu Long", "tâm linh;mekong", 10.7050, 105.1167, "không"),
    ("soc_trang", "Sóc Trăng", "Sóc Trăng", "Đồng bằng sông Cửu Long", "văn hóa;mekong", 9.6025, 105.9739, "có"),
    ("tra_vinh", "Trà Vinh", "Trà Vinh", "Đồng bằng sông Cửu Long", "văn hóa;biển", 9.9347, 106.3453, "có"),
]


def build_destination_registry() -> pd.DataFrame:
    CURRENT.mkdir(parents=True, exist_ok=True)
    existing = pd.read_csv(META / "destination_registry.csv", dtype=str, encoding="utf-8-sig") if (META / "destination_registry.csv").exists() else pd.DataFrame()
    rows = []
    for dest_id, name, province, region, tourism_type, lat, lng, coastal in BASE_DESTINATIONS:
        rows.append(
            {
                "ma_diem_den": dest_id,
                "ten_diem_den": name,
                "tinh_thanh": province,
                "vung": region,
                "loai_hinh": tourism_type,
                "vi_do": lat,
                "kinh_do": lng,
                "la_ven_bien": coastal,
                "nguon_du_lieu": "destination_registry hiện có + danh mục điểm đến du lịch Việt Nam mở rộng",
                "loai_du_lieu": "mixed_public_registry",
                "do_tin_cay": 65,
                "cap_nhat_lan_cuoi": now_vn_text(),
            }
        )
    expanded = pd.DataFrame(rows)

    if not existing.empty:
        mapped = pd.DataFrame(
            {
                "ma_diem_den": existing.get("destination_id", ""),
                "ten_diem_den": existing.get("canonical_name", ""),
                "tinh_thanh": existing.get("province_or_city", ""),
                "vung": existing.get("region", "").map(region_label),
                "loai_hinh": existing.get("tourism_types", "").map(tourism_type_label),
                "vi_do": existing.get("lat", ""),
                "kinh_do": existing.get("lng", ""),
                "la_ven_bien": existing.get("coastal_zone", "").map(lambda x: "có" if str(x).lower() == "yes" else "không"),
                "nguon_du_lieu": "destination_registry hiện có",
                "loai_du_lieu": "real_data_registry",
                "do_tin_cay": 80,
                "cap_nhat_lan_cuoi": now_vn_text(),
            }
        )
        expanded = pd.concat([expanded, mapped], ignore_index=True)

    expanded = expanded.drop_duplicates("ma_diem_den", keep="first").sort_values(["la_ven_bien", "vung", "tinh_thanh", "ten_diem_den"], ascending=[False, True, True, True])
    expanded.to_csv(CURRENT / "danh_sach_diem_den_mo_rong.csv", index=False, encoding="utf-8-sig")
    return expanded


def main() -> None:
    df = build_destination_registry()
    print(f"Đã ghi {len(df)} điểm đến vào datasets/gold/current/danh_sach_diem_den_mo_rong.csv")


if __name__ == "__main__":
    main()
