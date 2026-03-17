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

### HDFS NameNode UI  
**URL:** http://master:9870  

- Giao diện quản trị HDFS.  
- Hiển thị trạng thái cluster (dung lượng, số DataNode, block).  
- Duyệt filesystem HDFS trên web.  
- Kiểm tra tình trạng DataNode và replication.

---

### HDFS DataNode UI  
**URL:** http://worker-node:9864  

- Giao diện của từng DataNode.  
- Hiển thị block được lưu trên node.  
- Kiểm tra dung lượng và trạng thái node.

---

### YARN ResourceManager UI  
**URL:** http://master:8088  

- Giao diện quản lý tài nguyên YARN.  
- Hiển thị application đang chạy hoặc đã hoàn thành.  
- Theo dõi container, CPU, memory.  
- Xem log và trạng thái job.

---

### YARN NodeManager UI  
**URL:** http://worker-node:8042  

- Giao diện NodeManager trên mỗi worker.  
- Hiển thị container đang chạy.  
- Kiểm tra log container.

---

### Spark Master UI  
**URL:** http://master:8080  

- Giao diện quản lý Spark Standalone cluster.  
- Hiển thị worker nodes, CPU cores, memory.  
- Theo dõi các Spark applications.

---

### Spark Worker UI  
**URL:** http://worker-node:8081  

- Giao diện của Spark worker.  
- Hiển thị executor và job chạy trên node.

---

### Spark Application UI  
**URL:** http://master:4040  

- Giao diện chi tiết Spark job đang chạy.  
- Hiển thị DAG, stages, tasks, thời gian thực thi và shuffle data.  

**Lưu ý:**  
- `4040` – job đầu tiên  
- `4041` – job thứ hai  
- `4042` – job thứ ba  

---

### Spark History Server UI  
**URL:** http://master:18080  

- Lưu và xem lại thông tin Spark jobs đã hoàn thành.  
- Hiển thị DAG, stages và tasks của job.
Beta
0 / 0
used queries
1


### 2. Kiểm tra HDFS

```bash
# Vào container master
winpty docker exec -it master bash

jps
hdfs dfsadmin -report
yarn node -list
spark-submit --master spark://master:7077 --class org.apache.spark.examples.SparkPi $SPARK_HOME/examples/jars/spark-examples_2.12-3.5.0.jar 10

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

# Hướng dẫn Docker Cluster

Tài liệu này mô tả cách build và chạy Hadoop + Spark cluster trong project.

## 2. Chuẩn bị artifact local để build nhanh

Mục tiêu: tải sẵn Hadoop/Spark archives và GraphFrames JAR về máy local trước, để build lại nhanh hơn khi gặp lỗi hoặc cần rebuild nhiều lần.

Chạy bằng make:

```bash
make prep-assets-local
```

Git Bash (không cần make):

```bash
bash .docker-cache/prefetch_docker_assets.sh
```

Sau khi xong, dữ liệu cache nằm ở:

- .docker-cache/jars/
- .docker-cache/dist/

## 3. Build image

Build nhanh theo luồng đề xuất (prefetch + build):

Nếu đã prefetch trước đó, có thể build trực tiếp:

```bash
make build
```

Lệnh thay thế (không cần make):

```bash
docker compose build
```

Ghi chú:

- Dockerfile ưu tiên đọc Hadoop/Spark/JAR từ cache local.
- Nếu cache chưa có đủ file, Dockerfile sẽ fallback sang tải online cho các file này.
- Python packages luôn cài online trong quá trình build image.
- Hadoop archive: hadoop-3.3.6.tar.gz
- Spark archive: spark-3.5.0-bin-hadoop3.tgz

## 4. Khởi động cluster

```bash
make up
```

Lệnh thay thế (không cần make):

```bash
docker compose up -d
```

## 5. Kiểm tra nhanh

```bash
make ps
make logs-master
make health
```

Lệnh thay thế (không cần make):

```bash
docker compose ps
docker compose logs -f master
docker exec master hdfs dfsadmin -report
docker exec master curl -s http://master:8080/json/ | grep -o '"aliveworkers":[0-9]*'
```

### Có thể bị loỗi CRLF/LF: fix voới .gitattributes:

Thêm file .gitattributes để Git không checkout CRLF cho .sh

```.gitattributes
* text=auto

*.sh text eol=lf
Dockerfile* text eol=lf
docker-compose.yml text eol=lf
```

## 6. Truy cập UI

- HDFS NameNode: <http://localhost:9870>
- YARN ResourceManager: <http://localhost:8088>
- Spark Master UI: <http://localhost:8080>
- Spark History: <http://localhost:18080>
- Spark App UI (job đang chạy): <http://localhost:4040>
- Jupyter: <http://localhost:8888>

## 7. Vào container

```bash
make exec-master
make exec-worker1
make exec-worker2
```

Lệnh thay thế (không cần make):

```bash
docker exec -it master bash
docker exec -it worker1 bash
docker exec -it worker2 bash
```

## 8. Test Spark nhanh

```bash
make test-spark
```

Lệnh thay thế (không cần make):

```bash
docker exec master spark-submit \
  --class org.apache.spark.examples.SparkPi \
  --master spark://master:7077 \
  /opt/spark/examples/jars/spark-examples_*.jar 100
```

## 9. Dừng và dọn dẹp

Dừng cluster (giữ volume):

```bash
make stop
```

Lệnh thay thế (không cần make):

```bash
docker compose stop
```

Tắt và xóa container:

```bash
make down
```

Lệnh thay thế (không cần make):

```bash
docker compose down
```

Xóa cả volumes và prune hệ thống Docker:

```bash
make clean
```

Lệnh thay thế (không cần make):

```bash
docker compose down -v
docker system prune -f
```

## Lưu ý cho Windows

- Nếu dùng Git Bash, bạn có thể chạy trực tiếp script bash và toàn bộ lệnh docker compose.
- Nếu dùng PowerShell và chưa có make, hãy dùng các lệnh thay thế ở từng mục.
