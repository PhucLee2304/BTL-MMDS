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
    echo ">>> [MASTER] Starting Control Plane services..."

    if [ ! -f /hadoop_data/namenode/formatted ]; then
        echo ">>> [MASTER] First time run: Formatting NameNode..."
        $HADOOP_HOME/bin/hdfs namenode -format -force -nonInteractive
        touch /hadoop_data/namenode/formatted
        echo ">>> [MASTER] Format done."
    fi

    echo ">>> [MASTER] Starting NameNode..."
    $HADOOP_HOME/bin/hdfs --daemon start namenode
    sleep 8

    echo ">>> [MASTER] Checking HDFS availability..."
    for i in $(seq 1 10); do
        if $HADOOP_HOME/bin/hdfs dfs -ls / >/dev/null 2>&1; then
            echo ">>> [MASTER] HDFS is UP!"
            break
        fi
        echo "    Waiting for NameNode... ($i/10)"
        sleep 3
    done

    $HADOOP_HOME/bin/hdfs --daemon start secondarynamenode || true

    echo ">>> [MASTER] Preparing HDFS filesystem..."
    $HADOOP_HOME/bin/hdfs dfs -mkdir -p /user/taxi/raw_data
    $HADOOP_HOME/bin/hdfs dfs -mkdir -p /user/taxi/results
    $HADOOP_HOME/bin/hdfs dfs -mkdir -p /spark-logs
    $HADOOP_HOME/bin/hdfs dfs -chmod -R 777 /user
    $HADOOP_HOME/bin/hdfs dfs -chmod -R 777 /spark-logs

    echo ">>> [MASTER] Starting YARN ResourceManager..."
    $HADOOP_HOME/bin/yarn --daemon start resourcemanager
    sleep 3

    echo ">>> [MASTER] Starting Spark Master..."
    $SPARK_HOME/sbin/start-master.sh
    sleep 2

    echo ">>> [MASTER] Starting Spark History Server..."
    $SPARK_HOME/sbin/start-history-server.sh || true

    echo "========================================="
    echo "MASTER services are ONLINE"
    echo "HDFS UI:    http://localhost:9870"
    echo "Spark UI:   http://localhost:8080"
    echo "History:    http://localhost:18080"
    echo "========================================="

elif [ "$NODE_ROLE" = "worker" ]; then
    echo ">>> [WORKER] Starting computing node: $(hostname)"

    echo ">>> [WORKER] Waiting for NameNode (master:9000)..."
    until $HADOOP_HOME/bin/hdfs dfs -ls / >/dev/null 2>&1; do
        echo "    NameNode is not reachable. Retrying in 5s..."
        sleep 5
    done
    echo ">>> [WORKER] Connected to Master!"

    echo ">>> [WORKER] Starting DataNode..."
    $HADOOP_HOME/bin/hdfs --daemon start datanode
    sleep 2

    echo ">>> [WORKER] Starting NodeManager..."
    $HADOOP_HOME/bin/yarn --daemon start nodemanager
    sleep 2

    echo ">>> [WORKER] Starting Spark Worker..."
    $SPARK_HOME/sbin/start-worker.sh spark://master:7077

    echo "========================================="
    echo "WORKER $(hostname) is ONLINE"
    echo "========================================="
fi

tail -f /dev/null