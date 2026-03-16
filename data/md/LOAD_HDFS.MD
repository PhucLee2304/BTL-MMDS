# Service master
winpty docker exec -it master bash

# Tạo thư mục data
hdfs dfs -mkdir -p /user/taxi/raw
hdfs dfs -mkdir -p /user/taxi/preprocess

# Mở jupyter server
jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root --ServerApp.token='' --ServerApp.password=''