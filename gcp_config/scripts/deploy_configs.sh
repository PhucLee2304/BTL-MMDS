#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=../cluster.env
source "$ROOT_DIR/cluster.env"

HADOOP_CONF_DIR="${HADOOP_CONF_DIR:-$HADOOP_HOME/etc/hadoop}"
SPARK_CONF_DIR="$SPARK_HOME/conf"
REMOTE_HADOOP_CONF_DIR="~/hadoop-3.3.6/etc/hadoop"
REMOTE_SPARK_CONF_DIR="~/spark-3.5.1-bin-hadoop3/conf"

copy_hadoop_local() {
  cp -f "$ROOT_DIR/hadoop/"*.xml "$HADOOP_CONF_DIR/"
  cp -f "$ROOT_DIR/hadoop/workers" "$HADOOP_CONF_DIR/"
  cp -f "$ROOT_DIR/hadoop/hadoop-env.sh" "$HADOOP_CONF_DIR/"
}

copy_spark_local() {
  cp -f "$ROOT_DIR/spark/spark-defaults.conf" "$SPARK_CONF_DIR/"
  cp -f "$ROOT_DIR/spark/spark-env.sh" "$SPARK_CONF_DIR/"
}

prepare_dirs_remote() {
  local node="$1"
  # Thêm dấu \ trước $USER để máy Worker tự nhận diện đúng tên user của nó, thay vì lấy tên tiennd của máy Master
  ssh -t "$WORKER_SSH_USER@$node" "sudo mkdir -p /data/hdfs/nn /data/hdfs/dn /data/hadoop/tmp /data/spark/logs && sudo chown -R \$USER:\$USER /data/hdfs /data/hadoop /data/spark"
  ssh "$WORKER_SSH_USER@$node" "mkdir -p $REMOTE_HADOOP_CONF_DIR $REMOTE_SPARK_CONF_DIR"
}

copy_remote() {
  local node="$1"
  # Đã gỡ bỏ lệnh mkdir dư thừa (do hàm prepare_dirs_remote đã gọi ở trên)
  
  # Sử dụng REMOTE_HADOOP_CONF_DIR thay vì HADOOP_CONF_DIR để đường dẫn ~ được bảo toàn khi đẩy sang Worker
  tar -C "$ROOT_DIR/hadoop" -cf - . | ssh "$WORKER_SSH_USER@$node" "tar -C $REMOTE_HADOOP_CONF_DIR -xf -"
  tar -C "$ROOT_DIR/spark" -cf - . | ssh "$WORKER_SSH_USER@$node" "tar -C $REMOTE_SPARK_CONF_DIR -xf -"
}

mkdir -p "$HADOOP_CONF_DIR" "$SPARK_CONF_DIR"
copy_hadoop_local
copy_spark_local

for node in $WORKERS_ONLY; do
  prepare_dirs_remote "$node"
  copy_remote "$node"
done

# Ensure local data/log dirs exist on master (also a worker).
sudo mkdir -p /data/hdfs/nn /data/hdfs/dn /data/hadoop/tmp /data/spark/logs
sudo chown -R "$USER:$USER" /data/hdfs /data/hadoop /data/spark

echo "Configs deployed to master and workers."