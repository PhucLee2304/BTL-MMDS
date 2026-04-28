# Dự đoán nhu cầu gọi xe trên tập dữ liệu lớn NYC taxi

Dự án này là bài tập lớn cho môn học Khai phá dữ liệu lớn. Nhóm sử dụng tập dữ liệu NYC yellow taxi trip records trải dài từ năm 2020 đến 2025 với hơn 200 triệu bản ghi để giải quyết bài toán dự đoán nhu cầu đón khách (demand prediction) theo vùng địa lý và khoảng thời gian.

Bài toán được đặt ra như sau: cho trước lịch sử nhu cầu đón khách tại các vùng taxi của thành phố New York, hãy dự đoán số lượt đón khách trong 1 khoảng thời gian tại mỗi vùng. Kết quả dự đoán có thể hỗ trợ các hãng vận tải phân bổ xe một cách hợp lý, giảm thời gian chờ của hành khách và tối ưu hóa lợi nhuận cho tài xế.


## Vì sao chọn đề tài này

Bài toán dự đoán nhu cầu gọi xe đặt ra nhiều thử thách kỹ thuật đặc trưng của lĩnh vực khai phá dữ liệu lớn, khiến nó trở thành một đề tài phù hợp để nhóm vận dụng đồng thời kiến thức lý thuyết và kỹ năng thực hành.

Thứ nhất, quy mô dữ liệu vượt quá khả năng xử lý của một máy tính đơn lẻ. Tập dữ liệu NYC taxi gồm hơn 200 triệu bản ghi với tổng dung lượng nhiều gigabyte. Việc đọc, làm sạch và trích xuất đặc trưng trên khối lượng dữ liệu này buộc nhóm phải sử dụng các công cụ tính toán phân tán thay vì các thư viện đơn luồng truyền thống như pandas hay scikit-learn. Điều này tạo cơ hội để nhóm trực tiếp vận hành và cấu hình một cụm tính toán phân tán từ đầu.

Thứ hai, dữ liệu thực tế chứa nhiều bất thường. Các bản ghi taxi của thành phố New York không phải lúc nào cũng sạch: một số bản ghi có mốc thời gian nằm ngoài phạm vi hợp lý (ví dụ: năm 2028 hoặc 2029 do lỗi thiết bị), một số tệp Parquet giữa các tháng lưu cùng một cột dưới các kiểu dữ liệu khác nhau (INT và BIGINT). Nhóm phải thiết kế quy trình tiền xử lý đủ mạnh để phát hiện và loại bỏ các giá trị ngoại lai (outlier) bằng phương pháp khoảng tứ phân vị (IQR) mà không loại bỏ nhầm dữ liệu có giá trị.

Thứ ba, bài toán có tính chất không gian-thời gian (spatiotemporal) phức tạp. Nhu cầu đón khách không chỉ thay đổi theo giờ trong ngày và ngày trong tuần mà còn phụ thuộc vào vị trí địa lý và mối liên hệ giữa các vùng lân cận. Một sân bay bận rộn vào giờ cao điểm buổi sáng sẽ có mô hình nhu cầu khác hoàn toàn so với khu dân cư ngoại ô vào cùng thời điểm. Việc mô hình hóa đồng thời cả hai chiều không gian và thời gian đòi hỏi các phương pháp vượt ra ngoài hồi quy tuyến tính đơn giản.

Cuối cùng, đề tài này cho phép nhóm kết nối trực tiếp giữa bước xử lý dữ liệu lớn (sử dụng hạ tầng phân tán) và bước xây dựng mô hình dự đoán (sử dụng thuật toán học máy hoặc học sâu), tạo ra một luồng công việc hoàn chỉnh từ dữ liệu thô đến kết quả dự báo.


## Cấu trúc dự án

Thư mục gốc chứa các tệp cấu hình Docker, Hadoop và Spark dành cho cụm ảo (virtual cluster). Cụm ảo gồm ba vùng chứa (container) chạy trên một máy tính duy nhất: một nút chủ (master) kiêm vai trò nút dữ liệu và hai nút trạm (worker). Mục đích của cụm ảo là cho phép mỗi thành viên thử nghiệm mã nguồn độc lập trên máy cá nhân với lượng dữ liệu nhỏ mà không cần tập hợp đủ bốn máy tính.

Thư mục `real_cluster_config` chứa cấu hình riêng biệt cho cụm vật lý (real cluster), nơi mỗi máy tính của thành viên đóng vai trò một nút trong hệ thống phân tán thực sự, kết nối qua mạng nội bộ (LAN). Chi tiết về cụm vật lý được mô tả trong tệp README riêng tại thư mục đó.

Thư mục `code` tập hợp các thư mục con của từng thành viên. Mỗi người tìm hiểu một bài báo khoa học liên quan đến bài toán dự đoán nhu cầu và triển khai thuật toán tương ứng. Các hướng nghiên cứu đang được thực hiện bao gồm mô hình hồi quy kết hợp chuỗi thời gian, phân cụm K-means và K-shape, phân tích đồ thị không gian-thời gian, cùng các kiến trúc mạng nơ-ron.

Thư mục `data` chứa dữ liệu thô dưới dạng tệp Parquet, được nạp lên hệ thống tệp phân tán trước khi xử lý.


## Các thành phần hệ thống và vai trò

### Hadoop HDFS

Hadoop distributed file system (hệ thống tệp phân tán Hadoop) đóng vai trò làm lớp lưu trữ nền tảng cho toàn bộ dự án. Thay vì để dữ liệu nằm trên ổ cứng cục bộ của một máy tính, HDFS chia mỗi tệp thành các khối có kích thước cố định (mặc định 128 MB) và phân tán các khối này trên nhiều nút trong cụm. Mỗi khối được sao chép sang ít nhất một nút khác để đảm bảo dữ liệu vẫn truy cập được khi một máy gặp sự cố.

Vì sao cần HDFS thay vì lưu trữ thông thường: khi tập dữ liệu NYC taxi có dung lượng hàng chục gigabyte, việc đọc tuần tự từ một ổ cứng sẽ tạo nút thắt cổ chai nghiêm trọng. Với HDFS, nhiều nút có thể đọc song song các khối dữ liệu khác nhau, tăng thông lượng đọc lên tỷ lệ thuận với số nút. Ngoài ra, Spark tận dụng tính năng data locality (tính cục bộ dữ liệu) của HDFS để gửi mã tính toán đến đúng nút đang chứa dữ liệu tương ứng, giảm thiểu lưu lượng truyền qua mạng.

HDFS gồm hai thành phần chính. NameNode (nút quản lý tên) chạy trên nút chủ, lưu giữ toàn bộ siêu dữ liệu (metadata) về vị trí các khối và cấu trúc thư mục. DataNode (nút dữ liệu) chạy trên mỗi nút trong cụm, chịu trách nhiệm lưu trữ vật lý các khối dữ liệu và phục vụ yêu cầu đọc ghi từ các ứng dụng.

### YARN

YARN (Yet another resource negotiator) là thành phần quản lý tài nguyên tính toán của cụm. Khi nhiều ứng dụng cùng chạy trên một cụm chung, cần có một trình trọng tài trung tâm để phân bổ bộ nhớ và số lõi xử lý (CPU core) cho từng ứng dụng một cách công bằng và hiệu quả. YARN đảm nhận vai trò đó.

Vì sao cần YARN: trong cụm ảo ba nút, việc quản lý tài nguyên có thể được thực hiện thủ công. Nhưng khi mở rộng lên cụm vật lý bốn máy, mỗi máy có cấu hình phần cứng khác nhau, việc phân bổ thủ công trở nên không khả thi. YARN tự động theo dõi tài nguyên trống trên từng nút và cấp phát các vùng chứa (container) có kích thước phù hợp cho từng tiến trình xử lý.

YARN gồm hai thành phần chính. ResourceManager (trình quản lý tài nguyên) chạy trên nút chủ, tiếp nhận yêu cầu từ các ứng dụng và quyết định phân bổ tài nguyên trên toàn cụm. NodeManager (trình quản lý nút) chạy trên mỗi nút trạm, báo cáo tài nguyên khả dụng lên ResourceManager và giám sát các vùng chứa đang hoạt động trên nút đó.

### Apache Spark

Spark là công cụ xử lý dữ liệu phân tán được dự án sử dụng để thực hiện tất cả các bước từ tiền xử lý đến huấn luyện mô hình. Spark nổi bật nhờ khả năng giữ dữ liệu trung gian trên bộ nhớ (in-memory computing) thay vì ghi xuống đĩa sau mỗi bước tính toán như mô hình MapReduce truyền thống, giúp tăng tốc đáng kể cho các luồng xử lý cần nhiều bước lặp.

Vì sao chọn Spark: bài toán dự đoán nhu cầu yêu cầu nhiều bước xử lý liên tiếp như lọc dữ liệu, gộp nhóm theo vùng và khoảng thời gian, tính toán đặc trưng trượt (rolling features), và huấn luyện mô hình hồi quy. Mỗi bước đều cần đọc kết quả của bước trước. Với MapReduce, kết quả trung gian phải ghi xuống HDFS rồi đọc lại, tạo ra chi phí đĩa rất lớn. Spark giữ các kết quả này trong bộ nhớ, cho phép chuỗi xử lý hoàn tất nhanh hơn hàng chục lần.

Trong dự án, Spark hoạt động ở chế độ Spark-on-YARN, nghĩa là Spark không tự quản lý tài nguyên mà ủy quyền hoàn toàn cho YARN. Khi người dùng gửi một chương trình Spark, YARN sẽ cấp phát các executor (tiến trình thực thi) trên các nút trạm. Mỗi executor là một tiến trình Java độc lập với lượng bộ nhớ và số lõi xử lý cố định, nhận tác vụ (task) từ trình điều khiển (driver) và thực thi song song.


## Luồng thực thi 1 chương trình

### Bước 1: nạp dữ liệu lên HDFS

Dữ liệu thô dưới dạng tệp Parquet được tải từ máy tính cá nhân lên hệ thống tệp phân tán thông qua dòng lệnh HDFS. Ví dụ, để nạp toàn bộ thư mục dữ liệu lên đường dẫn `/user/data/raw` trong HDFS:

```bash
docker exec master hdfs dfs -mkdir -p /user/data/raw
docker exec master hdfs dfs -put /workspace/data/*.parquet /user/data/raw/
```

Khi lệnh `put` được thực thi, NameNode sẽ xác định các DataNode có đủ dung lượng trống, sau đó dữ liệu được truyền trực tiếp từ máy khách đến các DataNode. Mỗi tệp Parquet được chia thành các khối 128 MB, mỗi khối được sao chép và lưu trên nhiều DataNode để đảm bảo khả năng chịu lỗi (fault tolerance).

### Bước 2: gửi chương trình Spark

Chương trình xử lý dữ liệu có thể được gửi thông qua lệnh spark-submit hoặc chạy trực tiếp từ Jupyter Notebook. Với spark-submit, cú pháp cơ bản như sau:

```bash
docker exec master spark-submit \
    --master yarn \
    --deploy-mode client \
    --executor-memory 4g \
    --executor-cores 3 \
    --num-executors 2 \
    /workspace/code/my_script.py
```

Khi lệnh này được gọi, Spark driver (trình điều khiển) khởi động trên nút chủ và gửi yêu cầu đến YARN ResourceManager. ResourceManager kiểm tra tài nguyên trống trên các NodeManager, sau đó cấp phát các vùng chứa YARN để chạy executor. Mỗi executor là một tiến trình JVM được khởi tạo trên nút trạm, sẵn sàng nhận và thực thi các tác vụ.

### Bước 3: thực thi song song

Spark driver phân tích mã nguồn và tạo ra một đồ thị có hướng không chu trình (directed acyclic graph, viết tắt DAG) mô tả các bước tính toán cần thực hiện. DAG này được chia thành các giai đoạn (stage), mỗi giai đoạn gồm nhiều tác vụ song song. Spark gửi các tác vụ đến executor trên nút nào đang chứa khối dữ liệu tương ứng, tối ưu nguyên tắc di chuyển mã đến dữ liệu (move computation to data) thay vì di chuyển dữ liệu đến mã.

Khi giai đoạn hiện tại hoàn tất, nếu giai đoạn tiếp theo cần dữ liệu từ nhiều phân vùng (partition) khác nhau, Spark thực hiện thao tác xáo trộn dữ liệu (shuffle). Trong bước này, mỗi executor ghi kết quả trung gian ra đĩa cục bộ, sau đó các executor khác kéo (pull) dữ liệu cần thiết qua mạng.

### Bước 4: thu thập kết quả

Sau khi tất cả các giai đoạn hoàn tất, kết quả cuối cùng được ghi ngược lại vào HDFS hoặc thu về driver dưới dạng bảng tổng hợp. Các chỉ số đánh giá và biểu đồ trực quan được lưu ra thư mục cục bộ để phục vụ báo cáo.


## Hướng dẫn triển khai cụm ảo

### Yêu cầu phần mềm

Máy tính cần cài đặt Docker Desktop (phiên bản hỗ trợ Docker Compose v2 trở lên). Trên Windows, Docker Desktop yêu cầu kích hoạt WSL2. Dung lượng bộ nhớ RAM tối thiểu nên là 8 GB, khuyến nghị 16 GB để đảm bảo cụm hoạt động ổn định.

### Bước 1: xây dựng ảnh Docker

Mở cửa sổ dòng lệnh tại thư mục gốc của dự án và chạy lệnh sau để xây dựng ảnh cho cả nút chủ và nút trạm:

```bash
docker compose build
```

Quá trình này tải và cài đặt Hadoop 3.3.6, Spark 3.5.0, Java 11, Python 3 cùng các thư viện cần thiết vào bên trong Docker Image. Lần đầu tiên có thể mất 10-20 phút tùy tốc độ mạng; các lần sau sẽ nhanh hơn nhờ bộ nhớ đệm (cache) của Docker.

### Bước 2: khởi động cụm

```bash
docker compose up -d
```

Lệnh này dựng ba vùng chứa: `master`, `worker1` và `worker2`. Tập lệnh khởi động (docker-entrypoint.sh) bên trong mỗi vùng chứa sẽ tự động thực hiện các công việc sau theo thứ tự:

Trên nút chủ: định dạng NameNode (chỉ lần đầu), khởi động NameNode, DataNode, SecondaryNameNode, ResourceManager, NodeManager, Spark Master, Spark Worker và Spark History Server. Tập lệnh cũng tạo sẵn các thư mục cần thiết trong HDFS.

Trên nút trạm: chờ NameNode sẵn sàng, sau đó khởi động DataNode, NodeManager và Spark Worker.

### Bước 3: kiểm tra trạng thái cụm

Sau khi các vùng chứa đã khởi động xong (khoảng 30 giây), kiểm tra trạng thái HDFS:

```bash
docker exec master hdfs dfsadmin -report
```

Kết quả phải hiển thị ba DataNode đang hoạt động (Live datanodes: 3). Có thể kiểm tra thêm qua giao diện web:

- HDFS: http://localhost:9870
- Spark: http://localhost:8080
- YARN: http://localhost:8088

### Bước 4: nạp dữ liệu và chạy thử

Nạp dữ liệu mẫu lên HDFS:

```bash
docker exec master hdfs dfs -mkdir -p /user/data/raw
docker exec master hdfs dfs -put /workspace/data/yellow_tripdata_2024-01.parquet /user/data/raw/
```

Chạy thử chương trình mẫu của Spark để xác nhận cụm hoạt động:

```bash
docker exec master spark-submit \
    --class org.apache.spark.examples.SparkPi \
    --master spark://master:7077 \
    /opt/spark/examples/jars/spark-examples_*.jar 100
```

### Bước 5: truy cập Jupyter Notebook

Jupyter Notebook được khởi động tự động trên nút chủ tại cổng 8888. Truy cập http://localhost:8888 trên trình duyệt để mở giao diện và chạy các notebook trong thư mục `/workspace/code`.

### Dừng và xóa cụm

Để dừng cụm mà giữ lại dữ liệu HDFS:

```bash
docker compose down
```

Để xóa hoàn toàn bao gồm cả dữ liệu đã lưu:

```bash
docker compose down -v
```


## Tổng quan nghiên cứu

### Bài toán dự đoán nhu cầu gọi xe

Bài toán dự đoán nhu cầu đón khách (taxi demand prediction) yêu cầu mô hình nắm bắt được ba yếu tố chính: quy luật chu kỳ thời gian (giờ cao điểm lặp lại mỗi ngày, mô hình cuối tuần khác ngày thường), sự phụ thuộc không gian giữa các vùng lân cận (nhu cầu ở một vùng thường ảnh hưởng đến các vùng kề), và các biến động bất thường (sự kiện đặc biệt, thời tiết). Sự kết hợp đồng thời ba yếu tố này khiến các phương pháp thống kê truyền thống thường không đủ khả năng biểu diễn.

### Mô hình cơ sở

Mô hình cơ sở (baseline) phổ biến nhất cho bài toán dự đoán chuỗi thời gian với dữ liệu lớn là Historical average (trung bình lịch sử), trong đó nhu cầu dự đoán cho một khoảng thời gian được tính bằng giá trị trung bình của cùng khoảng thời gian đó trong các tuần trước. Phương pháp này đơn giản nhưng hiệu quả khi dữ liệu có tính mùa vụ rõ rệt và thường được dùng làm cận dưới để so sánh với các mô hình phức tạp hơn.

Bên cạnh đó, nhóm sử dụng các mô hình hồi quy cây quyết định đã được Spark ML tích hợp sẵn gồm Linear regression (hồi quy tuyến tính), Random forest regressor (hồi quy rừng ngẫu nhiên), và Gradient-boosted tree regressor (hồi quy cây tăng cường gradient) làm cơ sở so sánh. Các mô hình này nhận đầu vào là vector đặc trưng (gồm giờ, ngày trong tuần, tháng, các giá trị trễ và trung bình trượt) và cho ra dự đoán nhu cầu. Ưu điểm của chúng là chạy trực tiếp trên cụm Spark mà không cần thư viện bên ngoài, phù hợp với mục tiêu tận dụng hạ tầng phân tán của đồ án. Ngoài ra có mô hình làm mịn mũ Holt-Winters (exponential smoothing) để so sánh hiệu quả của phương pháp thống kê chuỗi thời gian cổ điển trên tập dữ liệu lớn.

### Hướng nghiên cứu nâng cao

Các nghiên cứu gần đây cho thấy bài toán dự đoán nhu cầu đạt kết quả tốt hơn khi kết hợp mô hình hóa không gian và thời gian trong cùng một kiến trúc. Một số công trình tiêu biểu như:

ST-ResNet (Zhang, Zheng, Qi; AAAI 2017) đề xuất mạng tích chập phần dư (residual convolutional network) với ba nhánh xử lý riêng biệt cho các quy luật thời gian gần, theo chu kỳ ngày và theo xu hướng dài hạn. Mô hình này được đánh giá trên tập dữ liệu luồng người tại New York và Bắc Kinh.

DCRNN (Li, Yu, Shahabi, Liu; ICLR 2018) mô hình hóa dòng giao thông như một quá trình khuếch tán (diffusion process) trên đồ thị có hướng, kết hợp phép tích chập đồ thị với kiến trúc mã hóa-giải mã (encoder-decoder) sử dụng đơn vị hồi quy có cổng (GRU). Công trình này đạt cải thiện 12-15% so với các phương pháp trước đó trên tập dữ liệu giao thông METR-LA.

Các thành viên đang tiếp tục khảo sát và triển khai các biến thể của các kiến trúc trên để tìm ra giải pháp phù hợp nhất cho bài toán dự đoán nhu cầu taxi trên tập dữ liệu NYC.
