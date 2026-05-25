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

echo "Đang chờ NameNode mở cổng 9000..."
sleep 10

hdfs dfs -mkdir -p /spark-logs /user/spark
hdfs dfs -chmod -R 1777 /spark-logs /user/spark

echo "HDFS and YARN started."

echo "HDFS and YARN started."
