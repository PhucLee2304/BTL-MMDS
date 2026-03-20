# Service master
winpty docker exec -it master bash

# Tạo thư mục data
hdfs dfs -mkdir -p /user/data/raw  
hdfs dfs -mkdir -p /user/data/preprocess  

# Load raw data into HDFS
hdfs dfs -put /workspace/data/raw/* /user/data/raw/  

# Mở jupyter server
nohup jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root --ServerApp.token='' --ServerApp.password='' > jupyter.log 2>&1 &  

# Xem jupyter log
tail -f jupyter.log  

# Kill jupyter
pkill -9 -f "/usr/local/bin/jupyter-lab"