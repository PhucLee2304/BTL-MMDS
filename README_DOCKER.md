## GIỚI THIỆU CẤU HÌNH DOCKER

### 1. Dockerfile.master

- Tạo image cho node master
- Cài đặt Java, Hadoop, Spark, Python, SSH.
- Thiết lập các biến môi trường cho Hadoop/Spark.
- Copy các file cấu hình Hadoop/Spark từ thư mục `config`.
- Mở các port phục vụ giao tiếp và giao diện web.
- Sử dụng script `docker-entrypoint.sh` để khởi động các dịch vụ khi container chạy.
- **Vai trò:** Quản lý cluster, điều phối tài nguyên, cung cấp giao diện quản trị HDFS, YARN, Spark.

### 2. Dockerfile.worker

- Tạo image cho các node worker
- Cài đặt Java, Hadoop, Spark, Python, SSH.
- Thiết lập các biến môi trường cho Hadoop/Spark.
- Copy các file cấu hình Hadoop/Spark từ thư mục `config`.
- Mở các port phục vụ worker.
- Sử dụng script `docker-entrypoint.sh` để khởi động các dịch vụ khi container chạy.
- **Vai trò:** Lưu trữ dữ liệu (DataNode), thực thi các tác vụ tính toán (NodeManager, Spark Worker).

### 3. docker-compose.yml

- Quản lý và khởi động toàn bộ cluster gồm master và các worker.
- Định nghĩa các service: `master`, `worker1`, `worker2`.
- Thiết lập hostname, biến môi trường, volume, network cho từng service.
- Mapping các port cần thiết ra ngoài host để truy cập giao diện web.
- Sử dụng volume để lưu trữ dữ liệu HDFS bền vững.
- Hỗ trợ mở rộng số lượng worker dễ dàng.
- Có thể khởi động cluster với 2 hoặc 3 node tùy nhu cầu.

### 4. docker-entrypoint.sh

- Script entrypoint cho cả master và worker, tự động khởi động các dịch vụ Hadoop/Spark phù hợp với vai trò node.
- Format NameNode nếu là master và chưa format.
- Khởi động các dịch vụ Hadoop (NameNode, DataNode, ResourceManager, NodeManager, SecondaryNameNode).
- Khởi động các dịch vụ Spark (Master, Worker, History Server).
- Tạo các thư mục cần thiết trên HDFS.
- Cho phép cấu hình linh hoạt vai trò node qua biến môi trường `NODE_TYPE`.

---

## BUILD VÀ KHỞI ĐỘNG CLUSTER

### 1. Clone project

```bash
cd <your prj folder>
```

### 2. Build Docker images

```bash
cd docker

# Build images
docker-compose build

# Xem images đã build
docker images | grep taxi-mining
```

### 3. Khởi động cluster

```bash
# Khởi động tất cả services (detached mode)
docker-compose up -d

# Xem logs
docker-compose logs -f

# Xem logs của từng service
docker-compose logs -f master
docker-compose logs -f worker1
```

### 4. Kiểm tra containers đang chạy

```bash
# List containers
docker-compose ps

# Kết quả mong đợi:
# NAME                  STATUS         PORTS
# taxi-mining-master    Up 2 minutes   0.0.0.0:8088->8088/tcp, ...
# taxi-mining-worker1   Up 2 minutes   
# taxi-mining-worker2   Up 2 minutes   

# nếu cần rebuilt
docker-compose down -v
# Xóa images cũ
docker rmi docker-master docker-worker1 taxi-mining-master taxi-mining-worker 2>nul

```

---

## KIỂM TRA HỆ THỐNG

### 1. Kiểm tra Web UIs

Mở trình duyệt và truy cập:

| Service | URL | Mô tả |
|---------|-----|-------|
| **HDFS NameNode** | http://localhost:9870 | Quản lý HDFS |
| **YARN ResourceManager** | http://localhost:8088 | Quản lý jobs |
| **Spark Master** | http://localhost:8080 | Spark cluster UI |
| **Spark History Server** | http://localhost:18080 | Lịch sử Spark jobs |

### 2. Kiểm tra HDFS

```bash
# Vào container master
docker exec -it taxi-mining-master bash

# Test HDFS
hdfs dfs -mkdir /test
echo "Hello HDFS" > /tmp/test.txt
hdfs dfs -put /tmp/test.txt /test/
hdfs dfs -cat /test/test.txt
hdfs dfs -rm -r /test

# Thoát container
exit
```

### 3. Kiểm tra Spark

```bash
# Vào container master
docker exec -it taxi-mining-master bash

# Test Spark job (tính Pi)
spark-submit \
    --class org.apache.spark.examples.SparkPi \
    --master spark://master:7077 \
    $SPARK_HOME/examples/jars/spark-examples_*.jar 100

# PySpark shell
pyspark --master spark://master:7077

# Trong PySpark shell:
>>> rdd = sc.parallelize(range(100))
>>> print(rdd.sum())
>>> exit()

# Thoát container
exit
```