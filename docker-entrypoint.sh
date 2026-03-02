#!/bin/bash
set -e

export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export HADOOP_HOME=/opt/hadoop
export SPARK_HOME=/opt/spark
export HDFS_NAMENODE_USER=root
export HDFS_DATANODE_USER=root
export HDFS_SECONDARYNAMENODE_USER=root
export YARN_RESOURCEMANAGER_USER=root
export YARN_NODEMANAGER_USER=root

echo "========================================="
echo "Starting NYC Taxi Mining Container"
echo "Role: ${NODE_TYPE} / Hostname: $(hostname)"
echo "========================================="

service ssh start || true

NODE_ROLE=${NODE_TYPE:-"worker"}

if [ "$NODE_ROLE" = "master" ]; then
    echo ">>> [MASTER] Starting services using --daemon commands..."

    # Format NameNode nếu chưa format
    if [ ! -f /hadoop_data/namenode/formatted ]; then
        echo ">>> [MASTER] Formatting NameNode..."
        $HADOOP_HOME/bin/hdfs namenode -format -force -nonInteractive
        touch /hadoop_data/namenode/formatted
        echo ">>> [MASTER] Format done."
    fi

    # Start NameNode
    echo ">>> [MASTER] Starting NameNode..."
    $HADOOP_HOME/bin/hdfs --daemon start namenode
    sleep 8

    # Kiểm tra NameNode đã up
    echo ">>> [MASTER] Checking NameNode..."
    for i in $(seq 1 10); do
        if $HADOOP_HOME/bin/hdfs dfs -ls / >/dev/null 2>&1; then
            echo ">>> [MASTER] NameNode is UP!"
            break
        fi
        echo "    Waiting NameNode... ($i/10)"
        sleep 3
    done

    # Start SecondaryNameNode
    echo ">>> [MASTER] Starting SecondaryNameNode..."
    $HADOOP_HOME/bin/hdfs --daemon start secondarynamenode || true

    # Start DataNode trên master
    echo ">>> [MASTER] Starting DataNode on master..."
    $HADOOP_HOME/bin/hdfs --daemon start datanode
    sleep 5

    # Tạo thư mục HDFS
    echo ">>> [MASTER] Creating HDFS directories..."
    $HADOOP_HOME/bin/hdfs dfs -mkdir -p /user/taxi/raw_data    || true
    $HADOOP_HOME/bin/hdfs dfs -mkdir -p /user/taxi/zone_lookup  || true
    $HADOOP_HOME/bin/hdfs dfs -mkdir -p /user/taxi/results      || true
    $HADOOP_HOME/bin/hdfs dfs -mkdir -p /tmp/spark-events       || true
    $HADOOP_HOME/bin/hdfs dfs -chmod -R 777 /user               || true
    $HADOOP_HOME/bin/hdfs dfs -chmod -R 777 /tmp                || true

    # Start ResourceManager
    echo ">>> [MASTER] Starting ResourceManager..."
    $HADOOP_HOME/bin/yarn --daemon start resourcemanager
    sleep 3

    # Start NodeManager trên master
    echo ">>> [MASTER] Starting NodeManager on master..."
    $HADOOP_HOME/bin/yarn --daemon start nodemanager
    sleep 2

    # Start Spark Master
    echo ">>> [MASTER] Starting Spark Master..."
    $SPARK_HOME/sbin/start-master.sh
    sleep 3

    # Start Spark History Server
    echo ">>> [MASTER] Starting Spark History Server..."
    $SPARK_HOME/sbin/start-history-server.sh || true

    echo "========================================="
    echo "MASTER started! Check:"
    echo "  HDFS UI:  http://localhost:9870"
    echo "  YARN UI:  http://localhost:8088"
    echo "  Spark UI: http://localhost:8080"
    echo "  History:  http://localhost:18080"
    echo "========================================="

    # Report sau 40s
    sleep 40
    echo ">>> [MASTER] DataNode report:"
    $HADOOP_HOME/bin/hdfs dfsadmin -report 2>&1 | head -20

elif [ "$NODE_ROLE" = "worker" ]; then
    echo ">>> [WORKER] Starting worker node: $(hostname)"

    # Chờ NameNode sẵn sàng
    echo ">>> [WORKER] Waiting for NameNode at master:9000..."
    for i in $(seq 1 40); do
        if $HADOOP_HOME/bin/hdfs dfs -ls / >/dev/null 2>&1; then
            echo ">>> [WORKER] NameNode is ready! (attempt $i)"
            break
        fi
        echo "    Attempt $i/40 - waiting 5s..."
        sleep 5
    done

    # Start DataNode
    echo ">>> [WORKER] Starting DataNode..."
    $HADOOP_HOME/bin/hdfs --daemon start datanode
    sleep 3

    # Start NodeManager
    echo ">>> [WORKER] Starting NodeManager..."
    $HADOOP_HOME/bin/yarn --daemon start nodemanager
    sleep 3

    # Start Spark Worker
    echo ">>> [WORKER] Starting Spark Worker -> spark://master:7077"
    $SPARK_HOME/sbin/start-worker.sh spark://master:7077

    echo "========================================="
    echo "WORKER $(hostname) started!"
    echo "  DataNode + NodeManager + SparkWorker: running"
    echo "========================================="

else
    echo "WARNING: Unknown NODE_TYPE='${NODE_TYPE}', starting as worker..."
    sleep 20
    $HADOOP_HOME/bin/hdfs --daemon start datanode || true
    $SPARK_HOME/sbin/start-worker.sh spark://master:7077 || true
fi

echo "Container is running."
tail -f /dev/null
