# Demand Prediction (2025H1) - Spark Distributed Notebook

This folder contains distributed demand-prediction notebooks aligned with paper.md, adapted for ZoneID and 2025 first-half data.

## Files

- `paper.md`: summary of the original research and adaptation notes.
- `demand_prediction_2025H1.ipynb`: original all-in-one distributed notebook.
- `feature_engineering_2025H1.ipynb`: split notebook 1 (feature engineering).
- `training_sparkml_2025H1.ipynb`: split notebook 2 (Spark ML training/evaluation).
- `baseline_holt_winters_2025H1.ipynb`: Holt-Winters benchmark by zone.
- `readme.md`: run guide (this file).

## Data Assumptions

- Input data is stored in HDFS parquet files at:
  - `/user/data/raw/*.parquet`
- The notebook filters internally to:
  - `2025-01-01 00:00:00 <= pickup_time < 2025-07-01 00:00:00`
- Expected columns (at least):
  - `PULocationID`
  - one pickup timestamp column among:
    - `tpep_pickup_datetime`
    - `lpep_pickup_datetime`
    - `pickup_datetime`

## Output Locations (HDFS)

Spark ML split pipeline writes results to:

- `/user/data/feature_engineering/demand_prediction_2025H1_dense_10m`
- `/user/data/feature_engineering/demand_prediction_2025H1_features`
- `/user/data/results/demand_prediction/2025H1_sparkml/metrics`
- `/user/data/results/demand_prediction/2025H1_sparkml/predictions`

Holt-Winters benchmark writes:

- `/user/data/results/demand_prediction/2025H1_holt_winters/metrics`
- `/user/data/results/demand_prediction/2025H1_holt_winters/predictions`

The original all-in-one notebook writes:

- `/user/data/results/demand_prediction/2025H1/metrics`
- `/user/data/results/demand_prediction/2025H1/predictions`

## How To Run

1. Start cluster from project root:

```bash
docker compose up -d
```

2. Enter master container:

```bash
docker exec -it master bash
```

3. Start Jupyter on master (if not started):

```bash
nohup jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root --ServerApp.token='' --ServerApp.password='' > jupyter.log 2>&1 &
```

4. Open Jupyter in browser:

- `http://localhost:8888`

5. Preferred run order (split version):

- `/workspace/code/demand_prediction/feature_engineering_2025H1.ipynb`
- `/workspace/code/demand_prediction/training_sparkml_2025H1.ipynb`
- `/workspace/code/demand_prediction/baseline_holt_winters_2025H1.ipynb`

Alternative:

- `/workspace/code/demand_prediction/demand_prediction_2025H1.ipynb`

Run all cells from top to bottom in each notebook.

## Distributed Execution Notes

- Spark session is pinned to standalone master:
  - `spark://master:7077`
- Heavy steps run distributed on Spark (split feature/training notebooks):
  - read parquet, 10-minute aggregation, dense time-grid generation, feature engineering, train/test split, model training (Spark ML), batch predictions.
- Small pandas conversion is used only for plotting a few zones.
- Holt-Winters notebook is a benchmark: data prep is distributed; fitting is local on driver for selected top-demand zones.

## Worker Utilization Cells

All new notebooks include a `cluster_util(stage_name)` helper and stage checkpoints to print:

- alive workers
- active apps
- cores used / total by worker
- memory used / total by worker

## Validate That Workers Are Used

From host:

- Spark Master UI: `http://localhost:8080`
- Spark App UI (running job): `http://localhost:4040`
- Spark History UI (completed jobs): `http://localhost:18080`

From master container:

```bash
jps
python3 -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://master:8080/json/'))['aliveworkers'])"
```

## Model Set In Notebook

- Linear Regression (Spark ML)
- Random Forest Regressor (Spark ML)
- GBT Regressor (Spark ML)

Note: the paper mentions XGBoost. In this distributed notebook, GBT is used as a boosted-tree baseline fully inside Spark ML to keep execution distributed.

## Troubleshooting

- If notebook runs local accidentally, print and verify:
  - `spark.sparkContext.master`
  - expected: `spark://master:7077`
- If no rows after filtering, verify HDFS data contains 2025-01 to 2025-06.
- If UI 4040 is empty, check 4041/4042 for parallel/recent apps.
