#!/usr/bin/env bash
set -euo pipefail

stop-yarn.sh
stop-dfs.sh

echo "HDFS and YARN stopped."
