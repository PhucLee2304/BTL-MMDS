# NYC Yellow Taxi Data - Cấu trúc dữ liệu

Tài liệu này mô tả chi tiết các trường thông tin trong tập dữ liệu Taxi & Limousine Commission Trip Record (Yellow Taxi) tại New York City.

## 1. Thông tin chung
- **Nguồn:** [New York City Taxi and Limousine Commission (TLC).](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)
- **Định dạng dữ liệu:** Parquet.
- **Đơn vị khoảng cách:** Miles (Dặm).
- **Đơn vị tiền tệ:** USD.

## 2. Chi tiết các trường dữ liệu (Data Schema)

| Trường (Field) | Kiểu dữ liệu | Mô tả |
| :--- | :--- | :--- |
| `VendorID` | Integer | ID nhà cung cấp dịch vụ (1 = Creative Mobile Technologies, 2 = VeriFone Inc). |
| `tpep_pickup_datetime` | Long | Thời gian đón khách (Unix Timestamp - Milliseconds). |
| `tpep_dropoff_datetime` | Long | Thời gian trả khách (Unix Timestamp - Milliseconds). |
| `passenger_count` | Integer | Số lượng hành khách trên chuyến xe. |
| `trip_distance` | Float | Quãng đường di chuyển (tính bằng dặm). |
| `RatecodeID` | Integer | Mã biểu giá (1 = Standard, 2 = JFK, 3 = Newark, 4 = Nassau/Westchester, 5 = Negotiated fare, 6 = Group ride). |
| `store_and_fwd_flag` | String | Cờ lưu tạm dữ liệu trên bộ nhớ xe trước khi gửi về máy chủ (Y = store and forward, N = not a store and forward trip). |
| `PULocationID` | Integer | ID vùng đón khách (TLC Taxi Zone). |
| `DOLocationID` | Integer | ID vùng trả khách (TLC Taxi Zone). |
| `payment_type` | Integer | Phương thức thanh toán (1 = Credit card, 2 = Cash, 3 = No charge, 4 = Dispute, 5 = Unknown, 6 = Voided trip). |
| `fare_amount` | Float | Giá cước tính theo thời gian và khoảng cách. |
| `extra` | Float | Các khoản phụ phí (ví dụ: phí giờ cao điểm, phí ban đêm). |
| `mta_tax` | Float | Thuế MTA ($0.50). |
| `tip_amount` | Float | Tiền tip (Chỉ ghi nhận được khi thanh toán bằng thẻ). |
| `tolls_amount` | Float | Tổng phí cầu đường đã trả. |
| `improvement_surcharge` | Float | Phụ phí cải thiện hạ tầng. |
| `total_amount` | Float | **Tổng số tiền khách trả** (bao gồm tất cả các loại thuế, phí và tip). |
| `congestion_surcharge` | Float | Phụ phí ùn tắc giao thông. |
| `Airport_fee` | Float | Phí sân bay. |
| `cbd_congestion_fee` | Float | Phí ùn tắc khu vực trung tâm Manhattan (Central Business District). |