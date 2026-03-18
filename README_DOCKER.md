# Hướng dẫn chay Docker Cluster

Tài liệu này mô tả cách build và chạy Hadoop + Spark cluster trong project.  
  
Lưu ý (*): các lệnh trong này nên được chạy ở thư mục gốc của dự án (là thư mục chứa các file cấu hình docker, .gitignore, .gitattributes), do đó cần cd tới thư mục gốc dự án (mỗi máy sẽ có đường dẫn khác nhau)

Nếu trong master cần thêm thư viện python, thực hiện (Sau buơc ## 4. Khởi động cluster):  

- Vào master bash

```bash  
docker exec --it master bash  
```  

- Dùng pip đã được cài trong master để cài các thư viện python như thông thường  

```bash  
pip install <tên gói cần cài>  
```  

Lệnh pip list --format=freeze | ForEach-Object { ($_ -split '==')[0] } > requirements.txt  

- Thoát môi trường bash của master:  

```bash  
exit  
```  

## 2. Chuẩn bị artifact local để build nhanh

Mục tiêu: tải sẵn Hadoop/Spark archives và GraphFrames JAR về máy local trước, để build lại nhanh hơn khi gặp lỗi hoặc cần rebuild nhiều lần.

Thực hiện copy lệnh sau, dán vào cmd và enter để chạy, Lưu ý (*):
```bash
bash .docker-cache/prefetch_docker_assets.sh
```

Sau khi xong, các file Hadoop/Spark archives và GraphFrames JAR nằm ở thư mục gốc của dự án

## 3. Build image

```bash
docker compose build
```

## 4. Khởi động cluster

```bash
docker compose up -d
```

## 5. Kiểm tra nhanh

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
- Spark App UI (job đang chạy): <http://localhost:4040> , caá app khaác là 4041, 4042, ...
- Jupyter: <http://localhost:8888> caần chaạy:

```bash
nohup jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root --ServerApp.token='' --ServerApp.password='' > jupyter.log 2>&1 &  
```

## 7. Vào container

```bash
docker exec -it master bash
docker exec -it worker1 bash
docker exec -it worker2 bash
```

## 8. Test Spark nhanh

```bash
docker exec master spark-submit \
  --class org.apache.spark.examples.SparkPi \
  --master spark://master:7077 \
  /opt/spark/examples/jars/spark-examples_*.jar 100
```

## 9. Dừng và dọn dẹp

```bash
docker compose stop
```

Tắt và xóa container:

```bash
docker compose down
```

```bash
docker compose down -v
docker system prune -f
```

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
docker exec -it master bash

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
