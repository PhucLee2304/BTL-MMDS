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
export HADOOP_NAMENODE_NICENESS=0
export HADOOP_DATANODE_NICENESS=0
export HADOOP_SECONDARYNAMENODE_NICENESS=0
NN_HOST=${MASTER_HOST:-192.168.1.111}
NN_PORT=9000
NN_URI=hdfs://${NN_HOST}:${NN_PORT}
DN_ADVERTISED_HOST=${WORKER_HOST_IP:-$(hostname)}

# Windows checkouts may introduce CRLF which breaks Hadoop/Spark env scripts.
sed -i 's/\r$//' "$HADOOP_HOME/etc/hadoop/hadoop-env.sh" 2>/dev/null || true
sed -i 's/\r$//' "$SPARK_HOME/conf/spark-env.sh" 2>/dev/null || true

echo "========================================="
echo "Starting NYC Taxi Mining Container"
echo "Role: ${NODE_TYPE} / Hostname: $(hostname)"
echo "NameNode: ${NN_HOST}:${NN_PORT}"
echo "Advertised IP: ${DN_ADVERTISED_HOST}"
echo "========================================="

service ssh start || true

echo ">>> [WORKER] Starting computing node: $(hostname)"

echo ">>> [WORKER] Waiting for NameNode (${NN_HOST}:${NN_PORT})..."
attempt=0
until timeout 8s $HADOOP_HOME/bin/hdfs dfs -fs "$NN_URI" -ls / >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if timeout 2s bash -c "</dev/tcp/${NN_HOST}/${NN_PORT}" >/dev/null 2>&1; then
        echo "    NameNode TCP is reachable but HDFS not ready yet. Retrying in 5s... (attempt ${attempt})"
    else
        echo "    Cannot reach ${NN_HOST}:${NN_PORT} from worker. Retrying in 5s... (attempt ${attempt})"
    fi
    sleep 5
done
echo ">>> [WORKER] Connected to Master!"

echo ">>> [WORKER] Starting DataNode..."
# Advertise the real LAN IP so NameNode and clients can reach this DataNode
export HDFS_DATANODE_OPTS="${HDFS_DATANODE_OPTS} -Ddfs.datanode.hostname=${DN_ADVERTISED_HOST} -Ddfs.datanode.address=0.0.0.0:9866 -Ddfs.datanode.ipc.address=0.0.0.0:9867 -Ddfs.datanode.http.address=0.0.0.0:9864"
echo ">>> [WORKER] DataNode advertised host: ${DN_ADVERTISED_HOST}"
$HADOOP_HOME/bin/hdfs --daemon start datanode
sleep 2

echo ">>> [WORKER] Starting NodeManager..."
$HADOOP_HOME/bin/yarn --daemon start nodemanager
sleep 2

echo ">>> [WORKER] Spark standalone worker is disabled (Spark-on-YARN profile)."

echo "========================================="
echo "WORKER $(hostname) is ONLINE"
echo "  Advertised IP: ${DN_ADVERTISED_HOST}"
echo "========================================="

tail -f /dev/null