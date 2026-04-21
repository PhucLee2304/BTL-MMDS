export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export HADOOP_HOME=/opt/hadoop
export HADOOP_CONF_DIR=/opt/hadoop/etc/hadoop
export YARN_CONF_DIR=/opt/hadoop/etc/hadoop
export SPARK_DRIVER_MEMORY=3g
export SPARK_EXECUTOR_MEMORY=3g
export SPARK_EXECUTOR_CORES=3
export SPARK_HISTORY_OPTS="-Dspark.history.fs.logDirectory=hdfs://192.168.1.111:9000/spark-logs"
export PYSPARK_PYTHON=python3
export PYSPARK_DRIVER_PYTHON=python3
# Force executors to bind on 0.0.0.0 (all interfaces) inside Docker.
# Without this, Spark resolves the NodeManager's advertised LAN IP (192.168.1.x)
# and tries to bind on it, but that IP doesn't exist inside the container.
export SPARK_LOCAL_IP=0.0.0.0
