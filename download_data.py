import os
import requests

# Tải vào data/raw
target_dir = "data/raw"
if not os.path.exists(target_dir):
    os.makedirs(target_dir)

# Tải dữ liệu năm 2025 (hoặc 2015 như trong file crash test của bạn)
year = 2025 
for m in range(1, 7): # Tải thử 3 tháng đầu để test
    file_name = f"yellow_tripdata_{year}-{m:02d}.parquet"
    url = f"https://d37ci6vzurychx.cloudfront.net/trip-data/{file_name}"
    
    print(f"Đang tải {file_name}...")
    r = requests.get(url)
    with open(os.path.join(target_dir, file_name), 'wb') as f:
        f.write(r.content)

print("Tải xong! Giờ bạn có thể chạy test_malloc.py.")