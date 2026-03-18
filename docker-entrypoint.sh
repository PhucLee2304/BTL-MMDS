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

# Windows checkouts may introduce CRLF which breaks Hadoop/Spark env scripts.
sed -i 's/\r$//' "$HADOOP_HOME/etc/hadoop/hadoop-env.sh" 2>/dev/null || true
sed -i 's/\r$//' "$SPARK_HOME/conf/spark-env.sh" 2>/dev/null || true

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

    echo ">>> [MASTER] Waiting for NameNode to leave safe mode..."
    for i in $(seq 1 30); do
        SAFE_MODE_STATE=$($HADOOP_HOME/bin/hdfs dfsadmin -safemode get 2>/dev/null || true)
        if echo "$SAFE_MODE_STATE" | grep -qi "OFF"; then
            echo ">>> [MASTER] NameNode safe mode is OFF."
            break
        fi
        echo "    Safe mode still ON. Retrying in 3s... ($i/30)"
        sleep 3
    done

    echo ">>> [MASTER] Preparing HDFS filesystem..."
    # $HADOOP_HOME/bin/hdfs dfs -mkdir -p /user/taxi/raw_data
    # $HADOOP_HOME/bin/hdfs dfs -mkdir -p /user/taxi/results
    $HADOOP_HOME/bin/hdfs dfs -mkdir -p /user
    $HADOOP_HOME/bin/hdfs dfs -mkdir -p /spark-logs
    $HADOOP_HOME/bin/hdfs dfs -mkdir -p /tmp/spark-events
    $HADOOP_HOME/bin/hdfs dfs -chmod -R 777 /user
    $HADOOP_HOME/bin/hdfs dfs -chmod -R 777 /spark-logs
    $HADOOP_HOME/bin/hdfs dfs -chmod -R 777 /tmp/spark-events

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