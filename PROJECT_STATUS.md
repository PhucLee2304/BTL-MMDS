# Project Status — NYC Taxi Massive Data Mining

Last verified: 2026-03-17

## 0) One‑line summary

Docker Hadoop+Spark cluster is verified running on Windows; analytics/pipeline code is not implemented yet (repo mostly infra + notebooks/docs).

## 1) What exists in this repo (ground truth)

- Cluster orchestration: docker-compose.yml + Dockerfile.master / Dockerfile.worker + docker-entrypoint.sh
- Automation: Makefile
- Docs / notebooks:
  - data/md/RAW_DATA_DESC.md (dataset description)
  - data/md/LOAD_HDFS.MD (how to load data to HDFS)
  - data/md/basic_eda.ipynb (EDA)
  - code/test/test_malloc.ipynb (misc test notebook)
- Raw data folder present: data/raw/yello_tripdata/
- Python “job modules” are currently missing (only code/test/_init_.py exists and is empty)

## 2) Current architecture (verified)

Services/containers (names in docker compose):

- master (mem_limit: 4g)
- worker1 (mem_limit: 3g)
- worker2 (mem_limit: 3g)

Master starts these daemons via entrypoint:

- HDFS: NameNode + SecondaryNameNode
- YARN: ResourceManager
- Spark: Master + HistoryServer

Workers start:

- HDFS: DataNode
- YARN: NodeManager
- Spark: Worker (connects to spark://master:7077)

UI ports exposed on host:

- HDFS NameNode UI: http://localhost:9870
- YARN ResourceManager: http://localhost:8088
- Spark Master UI: http://localhost:8080
- Spark History UI: http://localhost:18080
- Spark App UI (when a job is running): http://localhost:4040
- Jupyter: http://localhost:8888 (installed, but NOT auto-started)

## 3) Verified startup & health checks

Bring up cluster:

- make prep-assets-local (optional but recommended)
- make build
- make up

Quick checks (PowerShell-safe):

- make ps
- docker exec master jps
- docker exec master hdfs dfsadmin -report
- docker exec master python3 -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://master:8080/json/'))['aliveworkers'])"

Note: Makefile target make health currently uses grep on the HOST; on Windows PowerShell this may fail unless grep exists.

## 4) HDFS layout (current vs intended)

Created by master entrypoint on each fresh start:

- /user/taxi/raw_data
- /user/taxi/results
- /spark-logs
- /tmp/spark-events (needed for Spark History Server)

Planned / referenced by docs but NOT auto-created yet:

- /user/taxi/zone_lookup (Makefile has target hdfs-init for this)

## 5) Recent fixes (important for continuity)

- Windows CRLF issue fixed:
  - Added .gitattributes to enforce LF for *.sh and Dockerfiles.
  - Dockerfiles + entrypoint strip CRLF defensively (sed -i 's/\r$//').
  - Symptom previously: /opt/hadoop/etc/hadoop/hadoop-env.sh: line 5: $'\r': command not found and JAVA_HOME “does not exist”.
- Spark History Server stability fixed:
  - Ensure HDFS dir /tmp/spark-events exists before starting HistoryServer.

- Docker image size optimized:
  - Converted Dockerfiles to multi-stage so build cache tarballs do not end up in runtime images.
  - Kept JDK tools (jps) via openjdk-11-jdk-headless.
  - Size reference (local): master ~5.55GB, worker ~5.10GB (down from ~8.07GB / ~7.61GB).

## 6) Workstreams (planned; not implemented in code yet)

Problem tracks (from initial plan):

- A) Graph-Based Busy Zone & Community Detection
- B) Demand Forecasting (zone × time bucket)
- C) Trip Anomaly Detection
- D) Revenue Efficiency & Driver Earning Hotspots

Status: requirements are not formalized in a single guideline file in this repo (PRJ_GUIDELINE.md not found).

## 7) Next actions (concrete, repo-aligned)

1) Decide a canonical “project skeleton” under code/ (jobs/, common/, pipelines/, tests/) and create minimal placeholders.
2) Implement a single end‑to‑end pipeline (sample -> HDFS -> transform -> output) to validate I/O + partitions.
3) Add a shared Spark session factory + I/O helpers + data quality checks.

## 8) Open risks / known gaps

- Jupyter is installed but not started automatically; decide whether to:
  - keep manual start, or
  - start Jupyter in entrypoint.
- Makefile health check portability (grep) is fragile on Windows PowerShell.
- Dataset loading path + schema contracts are not frozen yet (docs exist but no code contract).

