#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/.docker-cache/dist"
JARS_DIR="${ROOT_DIR}/.docker-cache/jars"

mkdir -p "${DIST_DIR}" "${JARS_DIR}"

if command -v curl >/dev/null 2>&1; then
  DOWNLOADER="curl"
elif command -v wget >/dev/null 2>&1; then
  DOWNLOADER="wget"
else
  echo "Need curl or wget to prefetch assets." >&2
  exit 1
fi

download_file() {
  local dest="$1"
  shift
  local urls=("$@")
  local tmp="${dest}.part"

  if [ -s "${dest}" ]; then
    if [[ "${dest}" == *.tar.gz || "${dest}" == *.tgz ]]; then
      if tar -tzf "${dest}" >/dev/null 2>&1; then
        echo "${dest} already exists, skipping download"
        return
      fi
      echo "${dest} is corrupted, re-downloading"
      rm -f "${dest}"
    else
      echo "${dest} already exists, skipping download"
      return
    fi
  fi

  rm -f "${tmp}"
  for url in "${urls[@]}"; do
    echo "Downloading ${url} -> ${dest}"
    if [ "${DOWNLOADER}" = "curl" ]; then
      if curl -fL --retry 3 --connect-timeout 20 --max-time 0 "${url}" -o "${tmp}"; then
        mv "${tmp}" "${dest}"
        return
      fi
    else
      if wget -q --tries=3 --timeout=60 "${url}" -O "${tmp}"; then
        mv "${tmp}" "${dest}"
        return
      fi
    fi
    rm -f "${tmp}"
  done

  echo "Failed to download: ${dest}" >&2
  exit 1
}

echo ">>> Downloading Hadoop and Spark archives to local cache..."
download_file \
  "${DIST_DIR}/hadoop-3.3.6.tar.gz" \
  "https://dlcdn.apache.org/hadoop/common/hadoop-3.3.6/hadoop-3.3.6.tar.gz" \
  "https://archive.apache.org/dist/hadoop/common/hadoop-3.3.6/hadoop-3.3.6.tar.gz"

download_file \
  "${DIST_DIR}/spark-3.5.0-bin-hadoop3.tgz" \
  "https://dlcdn.apache.org/spark/spark-3.5.0/spark-3.5.0-bin-hadoop3.tgz" \
  "https://archive.apache.org/dist/spark/spark-3.5.0/spark-3.5.0-bin-hadoop3.tgz"

echo ">>> Downloading GraphFrames jar to local cache..."
download_file \
  "${JARS_DIR}/graphframes-0.8.3-spark3.5-s_2.12.jar" \
  "https://repos.spark-packages.org/graphframes/graphframes/0.8.3-spark3.5-s_2.12/graphframes-0.8.3-spark3.5-s_2.12.jar"

echo ">>> Prefetch complete. Cached assets in .docker-cache/dist and .docker-cache/jars"
