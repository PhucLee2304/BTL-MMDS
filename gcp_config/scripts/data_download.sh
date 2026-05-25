#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="/home/tiennd3886/BTL-MMDS/data/raw"

mkdir -p "$TARGET_DIR"

cd "$TARGET_DIR"

for year in {2015..2025}; do
    for m in {1..12}; do
        month=$(printf "%02d" "$m")
        
        fileName="yellow_tripdata_${year}-${month}.parquet"
        url="https://d37ci6vzurychx.cloudfront.net/trip-data/$fileName"
        
        echo "Downloading $fileName..."
        
        # Sử dụng curl để tải file, cờ -L để tự động chuyển hướng link nếu có, -sS để ẩn thanh tiến trình nhưng hiện lỗi nếu sập
        curl -L "$url" -o "$fileName"
    done
done

echo "All downloads completed in $TARGET_DIR"