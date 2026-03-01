#!/usr/bin/env bash

# Java Home
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64

# Hadoop Configuration
export HADOOP_HOME=/opt/hadoop
export HADOOP_CONF_DIR=/opt/hadoop/etc/hadoop

# Spark Master Configuration
export SPARK_MASTER_HOST=master
export SPARK_MASTER_PORT=7077
export SPARK_MASTER_WEBUI_PORT=8080

# Spark Worker Configuration
export SPARK_WORKER_CORES=2
export SPARK_WORKER_MEMORY=2g
export SPARK_WORKER_PORT=7078
export SPARK_WORKER_WEBUI_PORT=8081

# Spark Driver Configuration
export SPARK_DRIVER_MEMORY=1g

# Python Configuration
export PYSPARK_PYTHON=python3
export PYSPARK_DRIVER_PYTHON=python3

# History Server
export SPARK_HISTORY_OPTS="-Dspark.history.fs.logDirectory=hdfs://master:9000/tmp/spark-events"
