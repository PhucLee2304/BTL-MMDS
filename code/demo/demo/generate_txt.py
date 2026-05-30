import pandas as pd

df = pd.read_csv(r'd:\Document\MMDS\BTL-MMDS\data\raw\taxi_zone_lookup.csv')
zones = df.set_index('LocationID')['Zone'].to_dict()
spatio_ids = [13, 43, 48, 50, 68, 75, 79, 87, 90, 100, 107, 113, 114, 132, 137, 138, 140, 141, 142, 143, 144, 148, 151, 158, 161, 162, 163, 164, 166, 170, 186, 211, 229, 230, 231, 233, 234, 236, 237, 238, 239, 246, 249, 262, 263, 264]

with open(r'd:\Document\MMDS\BTL-MMDS\code\demo\demo\valid_locations.txt', 'w', encoding='utf-8') as f:
    f.write('DANH SÁCH LOCATION HỢP LỆ CHO TỪNG MÔ HÌNH\n')
    f.write('='*50 + '\n\n')
    f.write('1. Mô hình KShape Ensemble:\n')
    f.write('- Khả dụng: Tất cả 265 locations.\n\n')
    f.write('2. Mô hình Spatiotemporal Bundle và Holt-Winters:\n')
    f.write('- Khả dụng: 46 locations (Đây là danh sách các vùng có lưu lượng xe taxi cao nhất, các vùng nhỏ lẻ đã bị filter trong quá trình tiền xử lý).\n')
    f.write('- Chi tiết các locations:\n')
    for loc_id in spatio_ids:
        zone_name = zones.get(loc_id, "Unknown")
        f.write(f'  + ID {loc_id}: {zone_name}\n')
