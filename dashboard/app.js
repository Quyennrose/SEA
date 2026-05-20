const destinations = [
  { id: "da_nang", name: "Đà Nẵng", lat: 16.0471, lng: 108.2068, role: "Nguồn quá tải chính và gateway", status: "chưa hoàn chỉnh" },
  { id: "hoi_an", name: "Hội An", lat: 15.8801, lng: 108.338, role: "Điểm thay thế di sản", status: "chưa hoàn chỉnh" },
  { id: "hue", name: "Huế", lat: 16.4637, lng: 107.5909, role: "Mở rộng tuyến di sản", status: "chưa hoàn chỉnh" },
  { id: "quy_nhon", name: "Quy Nhơn", lat: 13.7563, lng: 109.2297, role: "Điểm biển phụ cận còn tiềm năng", status: "chưa hoàn chỉnh" },
  { id: "nha_trang", name: "Nha Trang", lat: 12.2388, lng: 109.1967, role: "Điểm biển lớn", status: "chưa hoàn chỉnh" },
  { id: "phu_quoc", name: "Phú Quốc", lat: 10.2899, lng: 103.984, role: "Đảo có giới hạn capacity", status: "chưa hoàn chỉnh" },
  { id: "ha_long", name: "Hạ Long", lat: 20.9712, lng: 107.0448, role: "Di sản biển", status: "chưa hoàn chỉnh" },
  { id: "cat_ba", name: "Cát Bà", lat: 20.7278, lng: 107.0482, role: "Điểm đảo thay thế", status: "chưa hoàn chỉnh" },
  { id: "ha_noi", name: "Hà Nội", lat: 21.0278, lng: 105.8342, role: "Gateway đô thị", status: "chưa hoàn chỉnh" },
  { id: "ho_chi_minh_city", name: "TP.HCM", lat: 10.8231, lng: 106.6297, role: "Gateway đô thị", status: "chưa hoàn chỉnh" },
  { id: "vung_tau", name: "Vũng Tàu", lat: 10.4114, lng: 107.1362, role: "Điểm biển cuối tuần", status: "chưa hoàn chỉnh" },
  { id: "can_tho", name: "Cần Thơ", lat: 10.0452, lng: 105.7469, role: "Gateway Mekong", status: "chưa hoàn chỉnh" },
  { id: "sa_pa", name: "Sa Pa", lat: 22.3364, lng: 103.8438, role: "Tuyến núi", status: "chưa hoàn chỉnh" },
  { id: "ha_giang", name: "Hà Giang", lat: 22.8233, lng: 104.9836, role: "Tuyến núi", status: "chưa hoàn chỉnh" }
];

const edges = [
  ["da_nang", "hoi_an", "ma sát thấp"],
  ["da_nang", "hue", "ma sát trung bình"],
  ["da_nang", "quy_nhon", "điều phối theo chiến dịch"],
  ["ha_noi", "ninh_binh", "tuyến đi trong ngày"],
  ["ha_noi", "ha_long", "hành lang di sản biển"],
  ["ha_long", "cat_ba", "phụ thuộc phà"],
  ["ho_chi_minh_city", "vung_tau", "hành lang cuối tuần"],
  ["can_tho", "ben_tre", "điểm thay thế Mekong"],
  ["sa_pa", "ha_giang", "thay thế tuyến núi"]
];

const evidenceRows = [
  ["Thời tiết", "production_ready", "Có evidence Open-Meteo lịch sử và có thể refresh."],
  ["Nguồn cung/giá khách sạn", "proxy_based", "Snapshot Booking/Traveloka là proxy hữu ích, không phải occupancy."],
  ["Review", "partial", "Có corpus review; chưa tính sentiment và topic đông đúc."],
  ["Nhu cầu du lịch", "schema_only", "Bảng official demand có khung nhưng chưa có dòng dữ liệu."],
  ["Traffic/crowd/parking", "missing", "Chưa tích hợp feed vận hành realtime."],
  ["Doanh thu du lịch", "missing", "Thiếu revenue, spending và infrastructure pressure chi tiết."]
];

function statusBadge(status) {
  if (status === "production_ready") return "<span class='badge ready'>sẵn sàng</span>";
  if (status === "proxy_based" || status === "partial") return `<span class='badge partial'>${status}</span>`;
  if (status === "schema_only" || status === "missing" || status === "blocked") return `<span class='badge blocked'>${status}</span>`;
  return `<span class='badge info'>${status}</span>`;
}

function fillEvidenceTable() {
  const body = document.querySelector("#evidence-table tbody");
  if (!body) return;
  body.innerHTML = evidenceRows.map(([name, status, note]) => (
    `<tr><td>${name}</td><td>${statusBadge(status)}</td><td>${note}</td></tr>`
  )).join("");
}

function initMap() {
  const mapElement = document.getElementById("map");
  if (!mapElement || typeof L === "undefined") return;

  const map = L.map("map").setView([16.2, 106.4], 6);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "&copy; cộng đồng OpenStreetMap"
  }).addTo(map);

  const byId = Object.fromEntries(destinations.map((d) => [d.id, d]));
  destinations.forEach((d) => {
    L.circleMarker([d.lat, d.lng], {
      radius: 7,
      color: "#247a4d",
      fillColor: "#2f9d62",
      fillOpacity: 0.8,
      weight: 2
    }).addTo(map).bindPopup(`<strong>${d.name}</strong><br>${d.role}<br>${statusBadge(d.status)}`);
  });

  edges.forEach(([from, to, label]) => {
    if (!byId[from] || !byId[to]) return;
    L.polyline([[byId[from].lat, byId[from].lng], [byId[to].lat, byId[to].lng]], {
      color: label.includes("thấp") ? "#247a4d" : "#b66a00",
      weight: 2,
      opacity: 0.75
    }).addTo(map).bindPopup(`${byId[from].name} -> ${byId[to].name}<br>${label}`);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  fillEvidenceTable();
  initMap();
});
