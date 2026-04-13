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
export HADOOP_NICENESS=0
export YARN_NICENESS=0
export HADOOP_NAMENODE_NICENESS=0
export HADOOP_DATANODE_NICENESS=0
export HADOOP_SECONDARYNAMENODE_NICENESS=0
export YARN_RESOURCEMANAGER_NICENESS=0
export YARN_NODEMANAGER_NICENESS=0

# Windows checkouts may introduce CRLF which breaks Hadoop/Spark env scripts.
sed -i 's/\r$//' "$HADOOP_HOME/etc/hadoop/hadoop-env.sh" 2>/dev/null || true
sed -i 's/\r$//' "$SPARK_HOME/conf/spark-env.sh" 2>/dev/null || true

echo "========================================="
echo "Starting NYC Taxi Mining Container"
echo "Role: ${NODE_TYPE} / Hostname: $(hostname)"
echo "========================================="

service ssh start || true

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

echo ">>> [WORKER] Spark standalone worker is disabled (Spark-on-YARN profile)."

echo "========================================="
echo "WORKER $(hostname) is ONLINE"
echo "========================================="

tail -f /dev/null