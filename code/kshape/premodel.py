"""
premodel.py — Chuẩn bị dữ liệu cho model training
========================================================
Input:  /user/kshape/feature_engineering  (output của feature_engineering.py)
Output: /user/kshape/model/prepared/tabular    — VectorAssembler cho XGBoost
        /user/kshape/model/prepared/sequence   — Cửa sổ 48 bước cho CNN-LSTM
        /user/kshape/model/prepared/tfrecords  — TFRecord cho TF dataset

Target: pickup_demand tại thời điểm t+1 (next-step prediction per zone)
"""
from __future__ import annotations
import gc, random
from dataclasses import dataclass
from typing import List

import numpy as np, tensorflow as tf
from pyspark.ml.feature import VectorAssembler
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.storagelevel import StorageLevel

# ─── Tiện ích ──────────────────────────────────────────────────────────────────
def stage(name: str):
    print(f"\n{'=' * 80}\n{name}\n{'=' * 80}")

def uniq(xs: List[str]) -> List[str]:
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def seed_all(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)

def cleanup(spark: SparkSession | None = None, *objs: object):
    for o in objs:
        try:
            o.unpersist(blocking=True)
        except Exception:
            pass
    if spark is not None:
        try:
            spark.catalog.clearCache()
        except Exception:
            pass
    gc.collect()

# ─── Config ────────────────────────────────────────────────────────────────────
@dataclass
class Config:
    input_path: str = "/user/kshape/feature_engineering"
    hdfs_work_dir: str = "/user/kshape/model"
    # Spark TFRecord JAR (phải có sẵn trên cluster)
    tfrecord_jar: str = "./lib/spark-tfrecord_2.12-0.7.0.jar"

    time_col: str = "pickup_bin_30m"
    loc_col: str = "PULocationID"
    target_col: str = "pickup_demand"
    # Target thực sự là demand tại t+1 → tạo cột "target_t1" trong pipeline
    target_t1_col: str = "target_t1"
    split_col: str = "dataset_split"
    time_key_col: str = "time_key"

    # Feature cho XGBoost (tabular)
    tabular_features: tuple[str, ...] = (
        "hour", "minute", "day_of_week", "is_weekday", "is_weekend",
        "slot_in_week",
        "demand_t_1", "rolling_mean_24h", "ewma_output",
        "cluster_id",
        "cluster_avg_demand_t", "cluster_demand_t_1",
        "cluster_rolling_mean_24h", "cluster_rolling_std_24h",
        "cluster_diff_t1", "cluster_mean_diff_24h",
        "intra_cluster_similarity", "inter_cluster_similarity",
    )
    # Feature cho CNN-LSTM (chuỗi thời gian)
    sequence_features: tuple[str, ...] = (
        "pickup_demand", "ewma_output", "rolling_mean_24h", "day_of_week",
    )

    split_aliases_to_validation: tuple[str, ...] = ("val", "valid", "validation")
    valid_splits: tuple[str, ...] = ("train", "validation", "test")
    seq_window: int = 48       # 48 bins = 24h lookback
    xgb_num_workers: int = 2
    random_state: int = 42

    def hdfs(self, *parts: str) -> str:
        return "/".join([self.hdfs_work_dir.rstrip("/"), *parts])

    @property
    def spark_jars(self) -> str:
        return self.tfrecord_jar

    @property
    def spark_cp(self) -> str:
        return self.tfrecord_jar

# ─── Scaler stats (lưu/đọc qua Spark HDFS) ────────────────────────────────────
@dataclass
class SequenceScalerStats:
    seq_mean: np.ndarray
    seq_std: np.ndarray
    y_min: float
    y_denom: float

    def to_list(self):
        """Serialize thành list để ghi ra parquet trên HDFS."""
        return {
            "seq_mean": self.seq_mean.tolist(),
            "seq_std":  self.seq_std.tolist(),
            "y_min":    float(self.y_min),
            "y_denom":  float(self.y_denom),
        }

# ─── SparkSession ──────────────────────────────────────────────────────────────
def build_spark(c: Config) -> SparkSession:
    import os
    stage("SPARK RUNTIME")
    abs_tfr = os.path.abspath(c.tfrecord_jar)
    spark_jars = f"{abs_tfr}"
    spark_cp = f"{abs_tfr}"
    print(f"[SPARK JARS] {spark_jars}")
    return (
        SparkSession.builder
        .appName("Premodel")
        .config("spark.jars", spark_jars)
        .config("spark.driver.extraClassPath", spark_cp)
        .config("spark.executor.extraClassPath", spark_cp)
        .config("spark.sql.session.timeZone", "America/New_York")
        .config("spark.sql.files.ignoreCorruptFiles", "true")
        .config("spark.sql.parquet.mergeSchema", "false")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.sql.parquet.enableVectorizedReader", "false")
        .config("spark.master", "yarn")
        .config("spark.submit.deployMode", "client")
        .config("spark.executor.instances", "3")
        .config("spark.executor.cores", "3")
        .config("spark.executor.memory", "8g")
        .config("spark.executor.memoryOverhead", "1g")
        .config("spark.driver.memory", "3g")
        .config("spark.driver.memoryOverhead", "1g")
        .config("spark.sql.shuffle.partitions", "64")
        .getOrCreate()
    )

# ─── DataProcessor ─────────────────────────────────────────────────────────────
class DataProcessor:
    def __init__(self, spark: SparkSession, c: Config):
        self.spark = spark
        self.c = c

    def run(self) -> SequenceScalerStats:
        stage("1/2 — PREPARE DATA")
        raw = clean = seq = None
        try:
            raw = self.spark.read.parquet(self.c.input_path)
            raw.printSchema()
            print(f"Total input rows: {raw.count():,}")

            self._validate(raw)
            clean = self._create_target_t1(raw)
            clean = self._clean(clean)

            self._write_tabular(clean)

            seq = self._build_sequence(clean)
            scaler = self._compute_scaler(seq)
            self._write_sequence_parquet(seq)
            self._write_tfrecord(seq)
            self._save_scaler_hdfs(scaler)

            return scaler
        finally:
            cleanup(self.spark, seq, clean, raw)

    def _validate(self, df: DataFrame):
        """Kiểm tra tất cả cột bắt buộc có trong input."""
        need = {
            self.c.time_col, self.c.loc_col, self.c.target_col, self.c.split_col,
            *self.c.tabular_features, *self.c.sequence_features,
        }
        missing = sorted(need - set(df.columns))
        if missing:
            raise ValueError(f"Input parquet thiếu cột bắt buộc: {missing}")

    def _create_target_t1(self, df: DataFrame) -> DataFrame:
        """Tạo cột target_t1 = pickup_demand tại t+1 cho mỗi zone."""
        stage("CREATE TARGET T+1")
        w = Window.partitionBy(self.c.loc_col).orderBy(self.c.time_col)
        df = df.withColumn(self.c.target_t1_col, F.lead(self.c.target_col, 1).over(w))
        # Bỏ hàng cuối cùng của mỗi zone (không có target t+1)
        df = df.filter(F.col(self.c.target_t1_col).isNotNull())
        print(f"Rows after creating target_t1: {df.count():,}")
        return df

    def _clean(self, df: DataFrame) -> DataFrame:
        """Chọn cột, chuẩn hoá split, fill null, repartition."""
        cols = uniq([
            self.c.time_col, self.c.loc_col, self.c.target_col, self.c.target_t1_col,
            self.c.split_col, *self.c.tabular_features, *self.c.sequence_features,
        ])
        return (
            df.select(*cols)
            .withColumn(self.c.split_col, F.lower(F.trim(F.col(self.c.split_col))))
            .withColumn(
                self.c.split_col,
                F.when(
                    F.col(self.c.split_col).isin(*self.c.split_aliases_to_validation),
                    "validation"
                ).otherwise(F.col(self.c.split_col))
            )
            .dropna(subset=[self.c.time_col, self.c.loc_col, self.c.target_t1_col, self.c.split_col])
            .filter(F.col(self.c.split_col).isin(*self.c.valid_splits))
            .withColumn(self.c.time_key_col, F.date_format(F.col(self.c.time_col), "yyyy-MM-dd HH:mm:ss"))
            .repartition(max(8, self.c.xgb_num_workers * 4), self.c.loc_col)
            .persist(StorageLevel.MEMORY_AND_DISK)
        )

    def _write_tabular(self, clean: DataFrame):
        """Ghi dữ liệu tabular với VectorAssembler cho XGBoost."""
        stage("WRITE TABULAR PARQUET")
        tab = None
        try:
            base = [self.c.time_col, self.c.time_key_col, self.c.loc_col, self.c.split_col, self.c.target_t1_col]
            feats = list(self.c.tabular_features)
            tab = clean.select(*(base + feats)).fillna(0.0, subset=feats)
            tab = (
                VectorAssembler(inputCols=feats, outputCol="features_vector", handleInvalid="keep")
                .transform(tab)
                .select(*base, "features_vector")
            )
            tab.write.mode("overwrite").partitionBy(self.c.split_col).parquet(
                self.c.hdfs("prepared", "tabular")
            )
            print(f"Tabular exported to: {self.c.hdfs('prepared', 'tabular')}")
        finally:
            cleanup(self.spark, tab)

    def _build_sequence(self, clean: DataFrame) -> DataFrame:
        """Xây cửa sổ trượt 48 bước cho mỗi (zone, time)."""
        stage("BUILD SEQUENCE WINDOWS")
        cols = uniq([
            self.c.time_col, self.c.time_key_col, self.c.loc_col,
            self.c.split_col, self.c.target_t1_col, *self.c.sequence_features,
        ])
        w = (
            Window.partitionBy(self.c.loc_col)
            .orderBy(self.c.time_col)
            .rowsBetween(-self.c.seq_window + 1, 0)
        )
        return (
            clean.select(*cols)
            .fillna(0.0, subset=list(self.c.sequence_features))
            .withColumn(
                "_step",
                F.array(*[F.col(x).cast("float") for x in self.c.sequence_features])
            )
            .withColumn(
                "_pair",
                F.struct(F.col(self.c.time_col).alias("ts"), F.col("_step").alias("vals"))
            )
            .withColumn("_window", F.collect_list("_pair").over(w))
            .withColumn(
                "sequence_array",
                F.expr("transform(array_sort(_window), x -> x.vals)")
            )
            .filter(F.size("sequence_array") == self.c.seq_window)
            .select(
                self.c.time_col, self.c.time_key_col, self.c.loc_col,
                self.c.split_col, self.c.target_t1_col, "sequence_array"
            )
            .persist(StorageLevel.MEMORY_AND_DISK)
        )

    def _compute_scaler(self, seq: DataFrame) -> SequenceScalerStats:
        """Tính z-score stats từ tập train (cho chuẩn hoá sequence)."""
        n = len(self.c.sequence_features)
        train_steps = None
        try:
            train_steps = (
                seq.filter(F.col(self.c.split_col) == "train")
                .select(F.explode("sequence_array").alias("step"))
            )
            exprs = [
                e for i in range(n)
                for e in (
                    F.avg(F.col("step")[i]).alias(f"m{i}"),
                    F.stddev_pop(F.col("step")[i]).alias(f"s{i}"),
                )
            ]
            stats = train_steps.agg(*exprs).first()

            y_stats = (
                seq.filter(F.col(self.c.split_col) == "train")
                .agg(
                    F.min(self.c.target_t1_col).alias("mn"),
                    F.max(self.c.target_t1_col).alias("mx"),
                )
                .first()
            )

            mean = np.array(
                [float(stats[f"m{i}"] or 0.0) for i in range(n)], np.float32
            )
            std = np.array(
                [
                    1.0 if stats[f"s{i}"] is None or float(stats[f"s{i}"]) < 1e-6
                    else float(stats[f"s{i}"])
                    for i in range(n)
                ],
                np.float32,
            )
            return SequenceScalerStats(
                mean, std,
                float(y_stats["mn"]),
                max(float(y_stats["mx"]) - float(y_stats["mn"]), 1e-6),
            )
        finally:
            cleanup(self.spark, train_steps)

    def _write_sequence_parquet(self, seq: DataFrame):
        """Ghi sequence dạng flatten ra parquet trên HDFS."""
        flat = None
        try:
            flat = (
                seq.withColumn("sequence_flat", F.flatten("sequence_array"))
                .select(
                    self.c.time_col, self.c.time_key_col, self.c.loc_col,
                    self.c.split_col, self.c.target_t1_col, "sequence_flat"
                )
            )
            flat.write.mode("overwrite").partitionBy(self.c.split_col).parquet(
                self.c.hdfs("prepared", "sequence")
            )
            print(f"Sequence exported to: {self.c.hdfs('prepared', 'sequence')}")
        finally:
            cleanup(self.spark, flat)

    def _write_tfrecord(self, seq: DataFrame):
        """Ghi TFRecord cho TensorFlow dataset."""
        stage("WRITE TFRECORD")
        tfdf = part = None
        try:
            tfdf = (
                seq.withColumn("sequence_flat", F.flatten("sequence_array"))
                .select(
                    F.col(self.c.loc_col).cast("long").alias(self.c.loc_col),
                    F.col(self.c.time_key_col).cast("string").alias(self.c.time_key_col),
                    F.col(self.c.split_col).cast("string").alias(self.c.split_col),
                    F.col(self.c.target_t1_col).cast("float").alias(self.c.target_t1_col),
                    F.expr("transform(sequence_flat, x -> cast(x as float))").alias("sequence_flat"),
                )
            )
            for split in self.c.valid_splits:
                part = tfdf.filter(F.col(self.c.split_col) == split)
                (
                    part.repartition(max(8, self.c.xgb_num_workers * 4), self.c.loc_col)
                    .write.format("tfrecord")
                    .option("recordType", "Example")
                    .mode("overwrite")
                    .save(self.c.hdfs("prepared", "tfrecords", split))
                )
                print(f"  TFRecord [{split}] → {self.c.hdfs('prepared', 'tfrecords', split)}")
                cleanup(self.spark, part)
                part = None
        finally:
            cleanup(self.spark, tfdf, part)

    def _save_scaler_hdfs(self, scaler: SequenceScalerStats):
        """Lưu scaler stats ra HDFS dạng parquet (1 row)."""
        data = scaler.to_list()
        row = self.spark.createDataFrame([{
            "seq_mean":  str(data["seq_mean"]),
            "seq_std":   str(data["seq_std"]),
            "y_min":     data["y_min"],
            "y_denom":   data["y_denom"],
        }])
        row.write.mode("overwrite").parquet(self.c.hdfs("prepared", "scaler_stats"))
        print(f"Scaler stats exported to: {self.c.hdfs('prepared', 'scaler_stats')}")
        print(f"  seq_mean : {data['seq_mean']}")
        print(f"  seq_std  : {data['seq_std']}")
        print(f"  y_min    : {data['y_min']}")
        print(f"  y_denom  : {data['y_denom']}")

# ─── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    c = Config()
    seed_all(c.random_state)
    spark = build_spark(c)
    spark.sparkContext.setLogLevel("ERROR")

    try:
        scaler = DataProcessor(spark, c).run()
        print(f"\n[PREMODEL COMPLETE]")
        print(f"  tabular   : {c.hdfs('prepared', 'tabular')}")
        print(f"  sequence  : {c.hdfs('prepared', 'sequence')}")
        print(f"  tfrecords : {c.hdfs('prepared', 'tfrecords')}")
        print(f"  scaler    : {c.hdfs('prepared', 'scaler_stats')}")
    finally:
        try:
            spark.catalog.clearCache()
        except Exception:
            pass
        try:
            spark.stop()
            print("[INFO] Spark stopped and resources released.")
        except Exception as e:
            print(f"[WARN] spark.stop failed: {e}")
        gc.collect()
