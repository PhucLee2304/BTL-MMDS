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
## Monitoring URL

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