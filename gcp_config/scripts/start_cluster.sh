#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=../cluster.env
source "$ROOT_DIR/cluster.env"

if [[ ! -d /data/hdfs/nn/current ]]; then
  hdfs namenode -format
fi

start-dfs.sh
start-yarn.sh

echo "Đang chờ NameNode thoát Safe Mode hoàn toàn..."
hdfs dfsadmin -safemode wait

hdfs dfs -mkdir -p /spark-logs /user/spark
hdfs dfs -chmod -R 1777 /spark-logs /user/spark

echo "HDFS and YARN started."
