#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="/home/tiennd3886/BTL-MMDS/data/raw"

mkdir -p "$TARGET_DIR"

cd "$TARGET_DIR"

for year in {2020..2025}; do
    for m in {1..12}; do
        month=$(printf "%02d" "$m")
        
        fileName="yellow_tripdata_${year}-${month}.parquet"
        url="https://d37ci6vzurychx.cloudfront.net/trip-data/$fileName"
        
        # Bỏ qua nếu file đã tồn tại và dung lượng > 100KB (để không tải lại file đã thành công)
        if [ -f "$fileName" ] && [ $(stat -c%s "$fileName") -gt 100000 ]; then
            echo "Skipping $fileName (already downloaded and valid)."
            continue
        fi
        
        echo "Downloading $fileName..."
        
        # Sử dụng curl để tải file, cờ -L để tự động chuyển hướng link nếu có, -sS để ẩn thanh tiến trình nhưng hiện lỗi nếu sập
        curl -L "$url" -o "$fileName"
        
        # Ngủ 2 giây để tránh bị CloudFront chặn (HTTP 403)
        sleep 2
    done
done

echo "All downloads completed in $TARGET_DIR"