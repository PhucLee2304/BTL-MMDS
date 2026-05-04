# Cấu hình và triển khai cụm vật lý

Thư mục này chứa toàn bộ cấu hình, tập lệnh (script), và tệp mô tả hạ tầng cần thiết để dựng một cụm tính toán phân tán trên nhiều máy tính vật lý. Khác với cụm ảo chạy trên một máy đơn lẻ, cấu hình tại đây kết nối bốn máy tính của các thành viên nhóm thông qua mạng nội bộ (LAN) để hình thành một hệ thống xử lý dữ liệu lớn thực thụ.


## Vì sao xây dựng cụm vật lý

Thứ nhất, cụm vật lý cho phép nhóm kiểm chứng khả năng mở rộng theo chiều ngang (horizontal scaling). Khi thêm một máy tính mới vào cụm, tổng dung lượng lưu trữ HDFS, tổng bộ nhớ RAM dành cho Spark executor, và tổng số lõi xử lý đều tăng lên tương ứng. Nhóm có thể đo lường trực tiếp liệu thời gian xử lý có giảm gần tuyến tính khi tăng số nút hay không, từ đó đánh giá hiệu quả thực tế của kiến trúc phân tán.

Thứ hai, cụm ảo che giấu hoàn toàn vấn đề truyền dữ liệu qua mạng. Trong cụm ảo, ba vùng chứa giao tiếp qua mạng ảo nội bộ (bridge network) của Docker với băng thông gần như không giới hạn và độ trễ gần bằng 0. Điều này không phản ánh đúng thực tế vận hành, nơi mà bước shuffle (xáo trộn dữ liệu giữa các executor) phải truyền hàng gigabyte dữ liệu qua kết nối mạng Wi-Fi hoặc Ethernet với băng thông hữu hạn. Cụm vật lý buộc nhóm phải đối mặt và tối ưu cho nút thắt cổ chai mạng thực tế.

Thứ ba, cụm vật lý tạo cơ hội áp dụng mô hình MapReduce ở quy mô thực tế. Spark sử dụng nội bộ mô hình map-shuffle-reduce cho nhiều phép toán tổng hợp (aggregation), và hiệu quả của mô hình này chỉ bộc lộ rõ khi dữ liệu thực sự nằm rải rác trên nhiều ổ cứng vật lý khác nhau. Các bước tiền xử lý như đếm số lượt đón khách theo vùng và khoảng thời gian, tính toán trung bình trượt (rolling average), hoặc gộp nhóm (group by) theo mã vùng taxi đều là các phép toán kiểu MapReduce điển hình, và cụm vật lý cho phép quan sát hành vi song song hóa thực sự của chúng.

Cuối cùng, quá trình triển khai và vận hành cụm vật lý phát sinh nhiều vấn đề kỹ thuật hạ tầng mà nhóm phải giải quyết trực tiếp, từ cấu hình tường lửa (firewall), thiết lập định tuyến mạng (network routing), đến xử lý sự khác biệt phần cứng giữa các máy. Đây là những kỹ năng thực tế không thể thu được từ cụm ảo.


## Cấu trúc thư mục

```
real_cluster_config/
  config/
    hadoop/         # Tệp cấu hình HDFS và YARN (core-site.xml, hdfs-site.xml, yarn-site.xml, ...)
    spark/          # Tệp cấu hình Spark (spark-defaults.conf, spark-env.sh)
    proxy.py        # Tập lệnh Python đóng vai trò cầu nối mạng giữa Docker NAT và ứng dụng Spark
  docker/
    master_docker/  # Dockerfile, docker-compose.yml, tập lệnh khởi động, tệp biến môi trường cho nút chủ
    worker_docker/  # Dockerfile, docker-compose.yml, tập lệnh khởi động, tệp biến môi trường cho nút trạm
```


## Các thành phần và cách chúng vận hành

### Kiến trúc mạng

Mỗi máy tính vật lý chạy một vùng chứa Docker duy nhất. Vùng chứa này nằm bên trong máy ảo WSL2 trên Windows, với địa chỉ IP nội bộ thuộc dải 172.18.0.x do Docker cấp. Tuy nhiên, các nút trong cụm cần giao tiếp bằng địa chỉ IP mạng LAN thực (ví dụ: 192.168.1.111, 192.168.1.112) để có thể truyền dữ liệu qua mạng vật lý.

Khoảng cách giữa hai lớp mạng này tạo ra một bài toán kỹ thuật: khi Spark executor bên trong Docker cố gắng chiếm dụng (bind) một cổng (port) trên địa chỉ IP LAN, hệ điều hành Linux bên trong vùng chứa sẽ từ chối vì địa chỉ đó không thuộc bất kỳ giao diện mạng nào mà nó biết.

Giải pháp được triển khai gồm hai tầng. Tầng thứ nhất là kỹ thuật bí danh vòng lặp (loopback alias): tập lệnh khởi động thêm địa chỉ IP LAN của máy chủ làm bí danh trên giao diện loopback (lo:0) bên trong vùng chứa, cho phép các ứng dụng Java chiếm dụng cổng trên địa chỉ đó. Tầng thứ hai là tập lệnh cầu nối mạng (proxy.py): khi gói tin từ máy bên ngoài đến, Docker Desktop thực hiện chuyển đổi địa chỉ mạng (NAT), thay đổi địa chỉ đích từ IP LAN sang IP nội bộ 172.18.0.x. Tuy nhiên Spark lại chỉ lắng nghe trên IP LAN (loopback alias). Tập lệnh proxy.py lắng nghe trên giao diện mạng thật của vùng chứa (eth0) và chuyển tiếp lưu lượng đến giao diện loopback, đảm bảo dữ liệu shuffle đến đúng đích.

### Phân bổ cổng dịch vụ

Trên cụm vật lý, mỗi nút chỉ chạy một vùng chứa Docker, nhưng vùng chứa đó phải mở nhiều cổng cho các dịch vụ khác nhau. Các cổng quan trọng bao gồm:

Nhóm cổng HDFS gồm cổng 9000 (NameNode RPC, chỉ trên nút chủ), 9870 (NameNode HTTP UI), và các cổng 9866, 9867, 9864 (DataNode truyền dữ liệu, IPC, HTTP). Mỗi nút trạm sử dụng bộ cổng DataNode riêng biệt (ví dụ: 9872/9873/9874 cho nút trạm thứ nhất, 9882/9883/9884 cho nút trạm thứ hai) để NameNode phân biệt được các DataNode khi chúng kết nối qua cùng một cổng gateway Docker.

Nhóm cổng YARN gồm cổng 8088 (ResourceManager UI), 8030-8033 (các dịch vụ nội bộ ResourceManager), và 8040-8042 (NodeManager).

Nhóm cổng Spark gồm cổng 7078 (driver), 7079 (BlockManager của driver), và 7080 (BlockManager của executor). Việc tách riêng cổng BlockManager giữa driver và executor ngăn chặn xung đột khi cả hai chạy trên cùng một nút.

### Quản lý tài nguyên

Cấu hình YARN trong `yarn-site.xml` quy định mỗi NodeManager được cấp 8192 MB bộ nhớ và 8 lõi xử lý ảo. Giới hạn cấp phát tối đa (scheduler maximum allocation) cũng được đặt là 8192 MB để cho phép executor có đủ bộ nhớ hoạt động.

Cấu hình Spark trong `spark-defaults.conf` quy định mỗi executor sử dụng 4 GB bộ nhớ chính cộng thêm 1024 MB bộ nhớ phụ trội (memory overhead), tổng cộng 5120 MB mỗi executor. Cụm được cấu hình với hai executor cố định (static allocation), mỗi executor ba lõi, tạo ra sáu tác vụ song song tại bất kỳ thời điểm nào.


## Hướng dẫn triển khai cụm vật lý

### Yêu cầu

Tất cả các máy tính phải kết nối chung một mạng LAN (Wi-Fi hoặc Ethernet) và có thể ping được lẫn nhau. Mỗi máy cần cài đặt Docker Desktop với WSL2 đã kích hoạt. RAM tối thiểu khuyến nghị là 8 GB trên mỗi máy.

Cần cấu hình cố định trước:
- Máy đóng vai trò nút chủ (ví dụ: 192.168.1.111).
- Địa chỉ IP LAN của từng máy trạm (ví dụ: 192.168.1.112, 192.168.1.113, 192.168.1.114).
- Bộ cổng DataNode duy nhất cho mỗi máy trạm.

Test ping giữa các máy theo ip cố định trên, nếu không ping được kiểm tra: Tại mục Inbound Rules (Windows Defender Firewall), tìm dòng File and Printer Sharing (Echo Request - ICMPv4-In), xác nhận đã Enable Rule (public and private network).

Mở các port cần thiết bằng cách chạy script: '.\scripts\open_firewall_ports.ps1' (nếu không chạy dược có thể thử chạy lệnh sau trước: 'Set-ExecutionPolicy RemoteSigned -Scope CurrentUser', sau đó chạy lại script)

### Bước 1: chuẩn bị mã nguồn

Tất cả các máy cần có cùng một phiên bản mã nguồn. Sử dụng Git để đồng bộ

### Bước 2: cấu hình tệp biến môi trường

Trên máy nút chủ, tạo hoặc chỉnh sửa tệp `real_cluster_config/docker/master_docker/.env`:

Trên mỗi máy nút trạm, tạo hoặc chỉnh sửa tệp `real_cluster_config/docker/worker_docker/.env`. Ví dụ cho máy trạm tại 192.168.1.112:

```env
MASTER_HOST=192.168.1.111
DN_ADVERTISED_HOST=192.168.1.112
WORKER_DN_PORT=9872
WORKER_DN_IPC_PORT=9873
WORKER_DN_HTTP_PORT=9874
```

Mỗi máy trạm phải sử dụng bộ cổng DataNode khác nhau. Máy trạm thứ hai có thể dùng 9882/9883/9884, máy trạm thứ ba dùng 9892/9893/9894.

### Bước 3: xây dựng ảnh Docker trên nút chủ

Trên máy đóng vai trò nút chủ, chạy lệnh sau từ thư mục `real_cluster_config/docker/master_docker`:

```bash
cd real_cluster_config/docker/master_docker
docker compose up -d --build
```

Cờ `--build` bắt buộc phải có để Docker nhúng tập lệnh khởi động (bao gồm logic loopback alias và proxy) vào bên trong ảnh. Lần đầu tiên xây dựng có thể mất 15-20 phút.

Sau khi vùng chứa khởi động xong, kiểm tra nhật ký:

```bash
docker logs -f master
```

Chờ đến khi thấy dòng `MASTER services are ONLINE` cùng với thông báo `Live DataNode detected`.

### Bước 4: xây dựng ảnh Docker trên mỗi nút trạm

Trên mỗi máy trạm, chạy lệnh tương tự từ thư mục worker:

```bash
cd real_cluster_config/docker/worker_docker
docker compose up -d --build
```

Kiểm tra nhật ký để xác nhận nút trạm đã kết nối thành công đến NameNode:

```bash
docker logs -f worker
```

Chờ đến khi thấy dòng `WORKER services are ONLINE` và `Connected to Master`.

### Bước 5: xác nhận cụm hoạt động

Trên nút chủ, kiểm tra trạng thái HDFS:

```bash
docker exec master hdfs dfs -fs hdfs://127.0.0.1:9000 -ls /
docker exec master hdfs dfsadmin -fs hdfs://127.0.0.1:9000 -report
```

Kết quả report phải hiển thị tất cả DataNode đang hoạt động (Live datanodes) với dung lượng khả dụng lớn hơn 0.

Kiểm tra trạng thái YARN:

```bash
docker exec master yarn node -list
```

Kết quả phải liệt kê tất cả NodeManager đã đăng ký, mỗi nút hiển thị với địa chỉ IP LAN tương ứng.

Ngoài ra có thể kiểm tra qua giao diện web:
- HDFS UI: http://192.168.1.111:9870
- YARN UI: http://192.168.1.111:8088

### Bước 6: nạp dữ liệu và chạy chương trình

Nạp dữ liệu thô lên HDFS:

```bash
docker exec master hdfs dfs -mkdir -p /user/data/raw
docker exec master hdfs dfs -put /workspace/data/*.parquet /user/data/raw/
```

Kiểm tra dữ liệu đã nạp thành công:

```bash
docker exec master hdfs dfs -ls /user/data/raw
```

Truy cập Jupyter Notebook tại http://192.168.1.111:8888 và chạy các notebook xử lý dữ liệu. Spark sẽ tự động gửi tác vụ đến các executor trên toàn bộ cụm thông qua YARN.


## Xử lý sự cố thường gặp

Nếu executor báo lỗi `BindException: Cannot assign requested address`, kiểm tra xem tập lệnh khởi động đã thực thi lệnh `ifconfig lo:0` thành công chưa bằng cách chạy `docker exec master ifconfig lo:0` và xác nhận địa chỉ IP LAN xuất hiện.

Nếu xuất hiện lỗi `FetchFailedException` trong quá trình shuffle, kiểm tra tập lệnh proxy đang chạy bằng lệnh `docker exec master bash -c "ps -ef | grep proxy"`. Nếu proxy không chạy, kiểm tra nhật ký tại `/tmp/proxy_7080.log` bên trong vùng chứa.

Nếu DataNode báo dung lượng 0 byte, nguyên nhân thường là do Docker bind-mount trên hệ thống tệp 9p (Windows) khiến Java trả về giá trị 0 cho getTotalSpace(). Giải pháp là sử dụng Docker named volume thay vì bind-mount cho thư mục dữ liệu DataNode, đã được cấu hình sẵn trong docker-compose.yml.

Nếu NameNode nhận diện nhiều DataNode là cùng một nút, nguyên nhân là các DataNode dùng chung cổng mặc định. Đảm bảo mỗi nút trạm có bộ cổng DataNode riêng biệt trong tệp .env.
