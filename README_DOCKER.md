# Hướng dẫn Docker Cluster

Tài liệu này mô tả cách build và chạy Hadoop + Spark cluster trong project.

## 1. Yêu cầu

- Docker Desktop (Windows) hoặc Docker Engine (Linux)
- Docker Compose V2 (lệnh docker compose)
- GNU Make (nếu muốn chạy lệnh make)

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
