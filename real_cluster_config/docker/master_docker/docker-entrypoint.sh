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

# MASTER_HOST = the LAN IP of the Windows host running this container.
# Docker Desktop on Windows: containers are inside WSL2 VM (192.168.65.x),
# so we use 127.0.0.1 for LOCAL NameNode access (same container),
# but advertise the LAN IP for services that remote nodes connect to.
MASTER_LAN_IP=${MASTER_HOST:-192.168.1.111}
NN_LOCAL_URI=hdfs://127.0.0.1:9000

# Windows checkouts may introduce CRLF which breaks Hadoop/Spark env scripts.
sed -i 's/\r$//' "$HADOOP_HOME/etc/hadoop/hadoop-env.sh" 2>/dev/null || true
sed -i 's/\r$//' "$SPARK_HOME/conf/spark-env.sh" 2>/dev/null || true

# Inject dfs.datanode.hostname into hdfs-site.xml at runtime.
# This tells the DataNode to register with the LAN IP, not Docker's internal IP.
# JVM -D flags via HDFS_DATANODE_OPTS do NOT reliably override this in Hadoop 3.x.
sed -i "s|</configuration>|  <property>\n    <name>dfs.datanode.hostname</name>\n    <value>${MASTER_LAN_IP}</value>\n  </property>\n</configuration>|" "$HADOOP_HOME/etc/hadoop/hdfs-site.xml"
echo ">>> [CONFIG] Injected dfs.datanode.hostname=${MASTER_LAN_IP} into hdfs-site.xml"

echo "========================================="
echo "Starting NYC Taxi Mining Container"
echo "Role: ${NODE_TYPE} / Hostname: $(hostname)"
echo "Master LAN IP: ${MASTER_LAN_IP}"
echo "========================================="

service ssh start || true

echo ">>> [MASTER] Starting Control Plane services..."

if [ ! -f /hadoop_data/namenode/formatted ]; then
    echo ">>> [MASTER] First time run: Formatting NameNode..."
    $HADOOP_HOME/bin/hdfs namenode -format -force -nonInteractive
    touch /hadoop_data/namenode/formatted
    echo ">>> [MASTER] Format done."
fi

echo ">>> [MASTER] Starting NameNode..."
if ! $HADOOP_HOME/bin/hdfs --daemon start namenode; then
    echo ">>> [MASTER][ERROR] Failed to start NameNode. Dumping diagnostics..."
    ls -la "$HADOOP_HOME/logs" || true
    tail -n 200 "$HADOOP_HOME"/logs/*namenode* 2>/dev/null || true
    tail -n 200 "$HADOOP_HOME"/logs/hadoop-*-master-*.out 2>/dev/null || true
    ps -ef | grep -E 'NameNode|namenode' | grep -v grep || true
    exit 1
fi
sleep 8

echo ">>> [MASTER] Checking HDFS availability..."
for i in $(seq 1 10); do
    if $HADOOP_HOME/bin/hdfs dfs -fs "$NN_LOCAL_URI" -ls / >/dev/null 2>&1; then
        echo ">>> [MASTER] HDFS is UP!"
        break
    fi
    echo "    Waiting for NameNode... ($i/10)"
    sleep 3
done

echo ">>> [MASTER] Starting DataNode on master (hybrid mode)..."
echo ">>> [MASTER] DataNode advertised hostname: ${MASTER_LAN_IP}"
export HDFS_DATANODE_OPTS="${HDFS_DATANODE_OPTS} -Ddfs.datanode.address=0.0.0.0:9866 -Ddfs.datanode.ipc.address=0.0.0.0:9867 -Ddfs.datanode.http.address=0.0.0.0:9864"
$HADOOP_HOME/bin/hdfs --daemon start datanode
sleep 2

if ! jps | grep -q "DataNode"; then
    echo ">>> [MASTER][WARN] DataNode process is not running after startup attempt."
    tail -n 200 "$HADOOP_HOME"/logs/*datanode* 2>/dev/null || true
fi

echo ">>> [MASTER] Waiting for at least one live DataNode..."
DN_LIVE=false
for i in $(seq 1 20); do
    DN_REPORT=$($HADOOP_HOME/bin/hdfs dfsadmin -fs "$NN_LOCAL_URI" -report 2>&1 || true)
    if echo "$DN_REPORT" | grep -Eqi "Live datanodes \([1-9][0-9]*\)"; then
        echo ">>> [MASTER] Live DataNode detected."
        DN_LIVE=true
        break
    fi
    if echo "$DN_REPORT" | grep -Eqi "Live datanodes \(0\)"; then
        echo "    No live DataNode yet. Retrying in 3s... ($i/20)"
        sleep 3
        continue
    fi
    if [ $((i % 5)) -eq 0 ]; then
        echo "    DataNode report sample (attempt $i):"
        echo "$DN_REPORT" | head -n 20 || true
    fi
    echo "    DataNode report not ready: $(echo "$DN_REPORT" | tail -n 1). Retrying in 3s... ($i/20)"
    sleep 3
done

if [ "$DN_LIVE" != "true" ]; then
    echo ">>> [MASTER][WARN] No live DataNode detected after timeout. Dumping DataNode diagnostics..."
    tail -n 200 "$HADOOP_HOME"/logs/*datanode* 2>/dev/null || true
    $HADOOP_HOME/bin/hdfs dfsadmin -fs "$NN_LOCAL_URI" -report 2>&1 || true
fi

$HADOOP_HOME/bin/hdfs --daemon start secondarynamenode || true

echo ">>> [MASTER] Waiting for NameNode to leave safe mode..."
SAFE_MODE_OFF=false
for i in $(seq 1 30); do
    SAFE_MODE_STATE=$($HADOOP_HOME/bin/hdfs dfsadmin -fs "$NN_LOCAL_URI" -safemode get 2>/dev/null || true)
    if echo "$SAFE_MODE_STATE" | grep -qi "OFF"; then
        echo ">>> [MASTER] NameNode safe mode is OFF."
        SAFE_MODE_OFF=true
        break
    fi
    echo "    Safe mode still ON. Retrying in 3s... ($i/30)"
    sleep 3
done

if [ "$SAFE_MODE_OFF" != "true" ]; then
    echo ">>> [MASTER] Forcing safe mode OFF after timeout..."
    $HADOOP_HOME/bin/hdfs dfsadmin -fs "$NN_LOCAL_URI" -safemode leave || true
fi

echo ">>> [MASTER] Preparing HDFS filesystem..."
$HADOOP_HOME/bin/hdfs dfs -fs "$NN_LOCAL_URI" -mkdir -p /user
$HADOOP_HOME/bin/hdfs dfs -fs "$NN_LOCAL_URI" -mkdir -p /spark-logs
$HADOOP_HOME/bin/hdfs dfs -fs "$NN_LOCAL_URI" -mkdir -p /tmp/spark-events
$HADOOP_HOME/bin/hdfs dfs -fs "$NN_LOCAL_URI" -chmod -R 777 /user
$HADOOP_HOME/bin/hdfs dfs -fs "$NN_LOCAL_URI" -chmod -R 777 /spark-logs
$HADOOP_HOME/bin/hdfs dfs -fs "$NN_LOCAL_URI" -chmod -R 777 /tmp/spark-events

echo ">>> [MASTER] Starting YARN ResourceManager..."
$HADOOP_HOME/bin/yarn --daemon start resourcemanager
sleep 3

echo ">>> [MASTER] Starting NodeManager on master (hybrid mode)..."
$HADOOP_HOME/bin/yarn --daemon start nodemanager
sleep 2

echo ">>> [MASTER] Spark standalone daemons are disabled (Spark-on-YARN profile)."

echo ">>> [MASTER] Starting Spark History Server..."
$SPARK_HOME/sbin/start-history-server.sh || true

echo "========================================="
echo "MASTER services are ONLINE"
echo "HDFS UI:    http://${MASTER_LAN_IP}:9870"
echo "YARN UI:    http://${MASTER_LAN_IP}:8088"
echo "History:    http://${MASTER_LAN_IP}:18080"
echo "========================================="

tail -f /dev/null