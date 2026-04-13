#!/usr/bin/env bash

export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export HADOOP_HOME=/opt/hadoop
export HADOOP_CONF_DIR=/opt/hadoop/etc/hadoop
export HADOOP_LOG_DIR=/opt/hadoop/logs

export HDFS_NAMENODE_USER=root
export HDFS_DATANODE_USER=root
export HDFS_SECONDARYNAMENODE_USER=root
export YARN_RESOURCEMANAGER_USER=root
export YARN_NODEMANAGER_USER=root

# Containers usually do not have CAP_SYS_NICE; keep daemon priority at default.
export HADOOP_NICENESS=0
export YARN_NICENESS=0
export HADOOP_NAMENODE_NICENESS=0
export HADOOP_DATANODE_NICENESS=0
export HADOOP_SECONDARYNAMENODE_NICENESS=0
export YARN_RESOURCEMANAGER_NICENESS=0
export YARN_NODEMANAGER_NICENESS=0