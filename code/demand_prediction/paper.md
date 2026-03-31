### 1\. Giới thiệu về nghiên cứu (Introduction)

  * **Tên đề tài**: Chiến lược phân loại để dự báo nhu cầu taxi Vàng (Yellow-Taxi) và các công cụ trực quan hóa. (A classification strategy for the Yellow-Taxi demand prediction and visualization tools - Ayoub BERDEDDOUCH - July 7-9th 2021)
  * **Mục tiêu**: Khám phá sự biến đổi không-thời gian của các chuyến xe taxi Vàng tại thành phố New York (NYC). Nghiên cứu tập trung vào việc dự báo mật độ (số lượng) các lượt đón khách (pickups) tại các khu vực khác nhau nhằm hỗ trợ quản lý đội xe và ra quyết định.

### 2\. Dữ liệu và các trường dữ liệu sử dụng (Data)

  * **Nguồn dữ liệu**: Bộ dữ liệu mở từ Ủy ban Taxi và Limousine (TLC) của NYC.
  * **Quy mô**: Khoảng 10 triệu bản ghi mỗi tháng.
  * **Các bước xử lý dữ liệu gốc**:
      * Loại bỏ các giá trị ngoại lai (outliers) và dữ liệu thiếu.
      * Giới hạn dữ liệu trong phạm vi tọa độ của NYC (bounding box).
      * Kỹ thuật đặc trưng (Feature engineering).
  * **Các trường dữ liệu quan trọng trong nghiên cứu gốc**:
      * Tọa độ đón khách (Pickup Latitude/Longitude).
      * Thời gian đón khách (Pickup-time).

### 3\. Kỹ thuật sử dụng và Ý nghĩa

  * **Phân cụm (Clustering)**: Sử dụng thuật toán **KMeans Mini batch** để chia dữ liệu thành 40 cụm dựa trên tọa độ kinh độ và vĩ độ của điểm đón. Ý nghĩa: Chia thành phố thành các vùng khu vực nhỏ để dự báo chi tiết hơn.
  * **Xử lý chuỗi thời gian**:
      * Chuyển thời gian đón khách sang định dạng UNIX Timestamp và chia vào các thùng (bins) thời gian 10 phút cho mỗi cụm.
      * Sử dụng các mô hình cơ sở để làm mịn dữ liệu: SMA, WMA, EWMA, Holt-Winter và biến đổi Fourier.
  * **Mô hình dự báo**:
      * Sử dụng các thuật toán: Hồi quy tuyến tính (Linear Regression), Rừng ngẫu nhiên (Random Forest), và XGBoost Regression.
      * Dữ liệu được chia theo tỷ lệ 70% huấn luyện và 30% kiểm tra cho mỗi khu vực.
      * Áp dụng phương pháp **Holt-Winter (Triple Exponential Smoothing)** và tinh chỉnh tham số (Alpha, Beta, Gamma) để giảm sai số.

### 4\. Kết quả đạt được

  * **Sai số dự báo (MAPE)**: Sau khi tinh chỉnh tham số, sai số giảm đáng kể xuống mức khoảng 2%.
  * **Mô hình tốt nhất**: **Random Forest** đạt kết quả dự báo tốt nhất với MAPE là 2.4%.
  * **Khả năng ứng dụng**: Dự báo chính xác mật độ theo từng khu vực tại Manhattan trong các khung giờ 10 phút, hỗ trợ tối ưu hóa quản lý đội xe.

### 5\. Kế hoạch tái lập nghiên cứu với dữ liệu mới (Chỉ có ZoneID)

Do dữ liệu mới không còn kinh độ/vĩ độ mà thay bằng **ZoneID**, AI cần thực hiện theo các bước sau để đảm bảo sát với nghiên cứu gốc nhất:

  * **Thay thế bước Phân cụm (Clustering)**:
      * Thay vì dùng KMeans để tạo ra 40 cụm từ tọa độ, hãy sử dụng trực tiếp các **ZoneID** làm đơn vị phân vùng khu vực.
      * Nếu số lượng ZoneID quá lớn so với 40 cụm trong nghiên cứu, có thể nhóm các ZoneID theo Quận (Borough) hoặc dựa trên sự tương đồng về mật độ lịch sử để đạt được số lượng vùng tương đương.
  * **Xử lý chuỗi thời gian theo ZoneID**:
      * Tổng hợp số lượng pickups cho mỗi `ZoneID` theo khoảng thời gian 10 phút tương tự như cách chia bin trong nghiên cứu gốc.
      * Xử lý dữ liệu thiếu cho các bin thời gian không có lượt đón trong từng vùng (Zone).
  * **Áp dụng mô hình dự báo**:
      * Tiếp tục sử dụng **Holt-Winter** để làm mịn và nắm bắt tính mùa vụ của từng vùng (ZoneID).
      * Huấn luyện các mô hình **Random Forest** và **XGBoost** với biến mục tiêu là mật độ pickups trong mỗi ZoneID.
  * **Đánh giá**: Sử dụng chỉ số **MAPE** để so sánh với kết quả 2.4% - 3% trong nghiên cứu gốc nhằm xác nhận độ chính xác của phương pháp mới.
