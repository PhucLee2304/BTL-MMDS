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

# Each DataNode must use a UNIQUE port so NameNode can distinguish them.
# Docker Desktop containers all share gateway 172.18.0.1; without unique ports
# NameNode sees all DataNodes as "172.18.0.1:SAME_PORT" → treats them as one.
# Use WORKER_DN_PORT from .env (9872 for 112, 9882 for 113, 9892 for 114).
DN_PORT=${WORKER_DN_PORT:-9872}
DN_IPC_PORT=$((DN_PORT + 1))   # e.g. 9873
DN_HTTP_PORT=$((DN_PORT + 2))  # e.g. 9874

# Windows checkouts may introduce CRLF which breaks Hadoop/Spark env scripts.
sed -i 's/\r$//' "$HADOOP_HOME/etc/hadoop/hadoop-env.sh" 2>/dev/null || true
sed -i 's/\r$//' "$SPARK_HOME/conf/spark-env.sh" 2>/dev/null || true

# Sync spark-env.sh and spark-defaults.conf from the shared /workspace/config
# volume into Spark's live conf dir so updates (e.g. SPARK_LOCAL_IP) take
# effect without a full Docker image rebuild.
if [ -f /workspace/config/spark/spark-env.sh ]; then
    cp /workspace/config/spark/spark-env.sh "$SPARK_HOME/conf/spark-env.sh"
    sed -i 's/\r$//' "$SPARK_HOME/conf/spark-env.sh"
    chmod 755 "$SPARK_HOME/conf/spark-env.sh"
    echo ">>> [CONFIG] Synced spark-env.sh from /workspace/config"
fi
if [ -f /workspace/config/spark/spark-defaults.conf ]; then
    cp /workspace/config/spark/spark-defaults.conf "$SPARK_HOME/conf/spark-defaults.conf"
    sed -i 's/\r$//' "$SPARK_HOME/conf/spark-defaults.conf"
    echo ">>> [CONFIG] Synced spark-defaults.conf from /workspace/config"
fi

# Inject DataNode config into hdfs-site.xml at runtime (only once per fresh volume).
# dfs.datanode.hostname → LAN IP to use for client connections
# dfs.datanode.address  → bind address including port (unique per node!)
# These must be XML properties; JVM -D flags are ignored by Hadoop 3.x config.
if ! grep -q '<name>dfs.datanode.hostname</name>' "$HADOOP_HOME/etc/hadoop/hdfs-site.xml"; then
    sed -i "s|</configuration>|  <property>\n    <name>dfs.datanode.hostname</name>\n    <value>${DN_ADVERTISED_HOST}</value>\n  </property>\n  <property>\n    <name>dfs.datanode.address</name>\n    <value>0.0.0.0:${DN_PORT}</value>\n  </property>\n  <property>\n    <name>dfs.datanode.ipc.address</name>\n    <value>0.0.0.0:${DN_IPC_PORT}</value>\n  </property>\n  <property>\n    <name>dfs.datanode.http.address</name>\n    <value>0.0.0.0:${DN_HTTP_PORT}</value>\n  </property>\n</configuration>|" "$HADOOP_HOME/etc/hadoop/hdfs-site.xml"
    echo ">>> [CONFIG] Injected DataNode config: hostname=${DN_ADVERTISED_HOST}, port=${DN_PORT}"
else
    echo ">>> [CONFIG] DataNode config already in hdfs-site.xml (skipping)"
fi

if ! grep -q '<name>yarn.nodemanager.hostname</name>' "$HADOOP_HOME/etc/hadoop/yarn-site.xml"; then
    sed -i "s|</configuration>|  <property>\n    <name>yarn.nodemanager.hostname</name>\n    <value>${DN_ADVERTISED_HOST}</value>\n  </property>\n</configuration>|" "$HADOOP_HOME/etc/hadoop/yarn-site.xml"
    echo ">>> [CONFIG] Injected yarn.nodemanager.hostname=${DN_ADVERTISED_HOST} into yarn-site.xml"
fi

echo "========================================="
echo "Starting NYC Taxi Mining Container"
echo "Role: ${NODE_TYPE} / Hostname: $(hostname)"
echo "NameNode: ${NN_HOST}:${NN_PORT}"
echo "Advertised IP: ${DN_ADVERTISED_HOST}"
echo "DataNode Port: ${DN_PORT}"
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

echo ">>> [WORKER] Starting DataNode (port ${DN_PORT})..."
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
echo "  DataNode port: ${DN_PORT}"
echo "========================================="

tail -f /dev/null