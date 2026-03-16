# Guideline Đề Tài Môn Massive Data Mining

Bộ dữ liệu sử dụng: NYC TLC Yellow Taxi Trip Records.

## Mục tiêu tổng thể

Nhóm xây dựng hệ thống phân tích dữ liệu taxi quy mô lớn trên Hadoop + Spark để giải 4 bài toán thực tế:

- Tìm các vùng giao thông trọng điểm và cụm di chuyển nhộn nhịp.
- Dự báo nhu cầu taxi theo khung giờ/khu vực để hỗ trợ điều phối.
- Phát hiện chuyến đi bất thường để hỗ trợ kiểm soát chất lượng và gian lận.
- Đánh giá hiệu quả doanh thu - tip - quãng đường để tối ưu vận hành.

Toàn bộ bài toán triển khai trên hệ thống phân tán Docker cluster (1 master + 2 worker), đầu ra gồm bảng kết quả parquet/csv, notebook tổng hợp, và báo cáo cuối kỳ.

## Hiện trạng hạ tầng (đã hoàn thành)

- Đã sẵn sàng mini cluster: HDFS, YARN, Spark Master, Spark History, Jupyter.
- Đã có image master/worker với Java 11, Hadoop 3.3.6, Spark 3.5.0, PySpark, GraphFrames.
- Đã có cơ chế khởi động tự động bằng entrypoint, bao gồm format NameNode lần đầu.
- Đã có Makefile cho build/up/down/logs/health/test.
- Đã có tài liệu dữ liệu ban đầu tại data/md/.

## Đề xuất 4 bài toán cho 4 thành viên

### Bài toán A - Graph-Based Busy Zone & Community Detection

#### Vấn đề thực tế

Cơ quan quản lý cần biết khu vực nào là hub giao thông và cụm khu vực nào tương tác mạnh để quy hoạch điểm đón/trả và phân bổ hạ tầng.

#### Đầu vào

- Trường chính: PULocationID, DOLocationID, tpep_pickup_datetime, fare_amount, tip_amount, total_amount.

#### Ý tưởng xử lý

- ETL tạo cạnh có hướng có trọng số w(i,j) theo số chuyến, doanh thu, tip.
- Chạy PageRank để xếp hạng độ quan trọng zone.
- Chạy Label Propagation hoặc Louvain để tìm community.

#### Đầu ra

- Bảng xếp hạng top zone theo PageRank.
- Bảng cụm zone và thống kê nội bộ cụm.
- File kết quả phục vụ vẽ bản đồ (zone_id -> cluster_id, pagerank_score).

#### Phụ trách

- Thành viên 1 (Lead Graph).

### Bài toán B - Demand Forecasting theo Zone x Time Bucket

#### Vấn đề thực tế (B)

Doanh nghiệp taxi cần dự báo nhu cầu theo giờ để bố trí tài xế, giảm thời gian chờ, giảm chuyến rỗng.

#### Đầu vào (B)

- Trường chính: tpep_pickup_datetime, PULocationID, passenger_count, trip_distance.
- Feature thời gian: hour, day_of_week, weekend, holiday_flag (nếu có).

#### Ý tưởng xử lý (B)

- Tạo demand series theo (zone, hour).
- Baseline: Moving Average hoặc Seasonal naive.
- Mở rộng: Spark ML Regression (GBT/RandomForest) để dự báo demand count.

#### Đầu ra (B)

- Bảng dự báo demand 24h/7 ngày tiếp theo theo zone.
- Metric đánh giá: MAE, RMSE, MAPE theo zone trọng điểm.
- Danh sách cảnh báo zone có nguy cơ quá tải theo khung giờ.

#### Phụ trách (B)

- Thành viên 2 (Lead Forecasting).

### Bài toán C - Anomaly Detection cho Chuyến Đi Bất Thường

#### Vấn đề thực tế (C)

Cần phát hiện bản ghi bất thường (giá cước quá cao/thấp, tốc độ phi lý, tip ratio bất thường) để hỗ trợ kiểm soát chất lượng dữ liệu và nghiệp vụ.

#### Đầu vào (C)

- Trường chính: trip_distance, fare_amount, tip_amount, total_amount, duration (từ pickup/dropoff), payment_type.

#### Ý tưởng xử lý (C)

- Tiền xử lý: lọc giá trị âm, null, bản ghi hư hỏng.
- Xây feature: fare_per_mile, fare_per_min, tip_ratio, speed_mph.
- Rule-based + statistical threshold (IQR/Z-score theo bucket thời gian/khu vực).
- Mở rộng tùy chọn: Isolation Forest trên mẫu đã downsample.

#### Đầu ra (C)

- Bảng anomaly có score và reason_code.
- Top pattern bất thường cần review.
- Báo cáo chất lượng dữ liệu theo ngày/tháng.

#### Phụ trách (C)

- Thành viên 3 (Lead Quality & Anomaly).

### Bài toán D - Revenue Efficiency & Driver Earning Hotspots

#### Vấn đề thực tế (D)

Tài xế và đơn vị vận hành cần biết khu vực/khung giờ nào tạo doanh thu và tip hiệu quả nhất để tối ưu khai thác.

#### Đầu vào (D)

- Trường chính: PULocationID, DOLocationID, tpep_pickup_datetime, total_amount, tip_amount, trip_distance, trip_duration.

#### Ý tưởng xử lý (D)

- Tổng hợp KPI theo (zone, hour): median fare, median tip, revenue_per_mile, revenue_per_min.
- Xếp hạng hotspot theo nhiều tiêu chí có trọng số.
- Tách weekday/weekend và cao điểm/thấp điểm.

#### Đầu ra (D)

- Bảng hotspot doanh thu/tip theo giờ.
- Dashboard notebook: top 20 zone theo hiệu quả khai thác.
- Đề xuất khung giờ - khu vực ưu tiên hoạt động.

#### Phụ trách (D)

- Thành viên 4 (Lead Revenue Analytics).

## Kiến trúc code đề xuất (dùng chung)

### Cấu trúc thư mục

```text
code/
  common/
    config.py
    spark_session.py
    schemas.py
    io_utils.py
    quality_checks.py
  jobs/
    graph/
      build_graph_edges.py
      run_pagerank.py
      run_community_detection.py
    forecasting/
      build_demand_features.py
      train_demand_model.py
      predict_demand.py
    anomaly/
      build_anomaly_features.py
      detect_anomalies.py
    revenue/
      build_revenue_kpis.py
      rank_hotspots.py
  notebooks/
    01_eda.ipynb
    02_graph_results.ipynb
    03_forecasting_results.ipynb
    04_anomaly_results.ipynb
    05_revenue_results.ipynb
  tests/
    test_data_quality.py
    test_transforms.py
    test_metrics.py
  pipelines/
    run_all.sh
    run_graph.sh
    run_forecasting.sh
    run_anomaly.sh
    run_revenue.sh
```

### Chức năng bắt buộc cần code

- common/spark_session.py: khởi tạo SparkSession, config serializer, config tối ưu cơ bản.
- common/io_utils.py: đọc/ghi parquet-csv và xử lý hdfs path resolver.
- common/quality_checks.py: validate schema, null ratio, range check.
- Mỗi job trong jobs/* phải có 4 bước rõ ràng: load_input(), transform(), compute_metrics(), save_output().
- Mỗi job phải hỗ trợ CLI argument: input path, output path, date range, mode.

### Chuẩn dữ liệu đầu ra

- Raw: /user/taxi/raw_data
- Zone lookup: /user/taxi/zone_lookup
- Silver cleaned: /user/taxi/silver/trips_cleaned
- Gold by problem:
  - /user/taxi/gold/graph/
  - /user/taxi/gold/forecasting/
  - /user/taxi/gold/anomaly/
  - /user/taxi/gold/revenue/

### Chuẩn log và metrics

- Mỗi job ghi metric json vào /user/taxi/results/metrics/{job_name}/{run_date}.json
- Metric tối thiểu: input_rows, output_rows, duration_sec, null_rate, fail_count.

## Kế hoạch triển khai theo giai đoạn

### Giai đoạn 1 - Data Foundation (1 tuần)

- Chuẩn hóa schema + data quality checks.
- Tạo cleaned layer dùng chung cho 4 bài toán.

### Giai đoạn 2 - Parallel Development (2 tuần)

- 4 thành viên phát triển song song 4 bài toán đã phân công.
- Mỗi nhánh phải có notebook kết quả tạm thời + file metrics.

### Giai đoạn 3 - Integration & Evaluation (1 tuần)

- Đồng bộ đầu ra vào /gold.
- Đánh giá metric, so sánh kết quả, kiểm thử pipeline.

### Giai đoạn 4 - Report & Demo (1 tuần)

- Chốt dashboard/notebook tổng hợp.
- Hoàn thành báo cáo cuối kỳ: bài toán, phương pháp, kết quả, hạn chế, hướng mở rộng.

## Definition of Done cho mỗi bài toán

- Chạy được trên cluster bằng lệnh pipeline.
- Có output parquet/csv trên HDFS.
- Có notebook phân tích và hình/plot kết quả.
- Có metric đánh giá rõ ràng.
- Có tài liệu assumptions, limitation, hướng cải tiến.

## Rủi ro và giảm thiểu

- Rủi ro chất lượng dữ liệu (missing, outlier): giải quyết bằng quality gate trước khi train/analyze.
- Rủi ro tài nguyên cluster: benchmark mẫu nhỏ trước, tối ưu partition/cache.
- Rủi ro lệch metric giữa thành viên: thống nhất schema output và metric dictionary ngay từ đầu.

## Lưu ý vận hành

- Ưu tiên Spark DataFrame API, hạn chế UDF nếu không cần thiết.
- Ghi dữ liệu dạng parquet + partition theo năm/tháng/ngày khi phù hợp.
