"""
model.py — Train XGBoost + CNN-LSTM + Ridge Ensemble, compute metrics
====================================================================
Input:  /user/kshape/model/prepared/{tabular,sequence,tfrecords,scaler_stats}
Output: /user/kshape/model/models/         — XGBoost, Ridge models
        /user/kshape/model/predictions/    — y_hat(zone, time) per split
        /user/kshape/model/metrics/        — parquet metrics table

Target: target_t1 = pickup_demand at t+1 per zone
Metrics: RMSE, MAE, sMAPE, MAPE (non-zero), R2
"""
from __future__ import annotations
import ast, gc, random
from dataclasses import dataclass
from typing import Dict, List

import numpy as np, pandas as pd, tensorflow as tf
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.regression import LinearRegression
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from xgboost.spark import SparkXGBRegressor
from pyspark.ml.functions import vector_to_array

# ─── Utilities ─────────────────────────────────────────────────────────────────
def stage(name: str):
    print(f"\n{'=' * 80}\n{name}\n{'=' * 80}")

def seed_all(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)

def nonneg(x: np.ndarray) -> np.ndarray:
    return np.maximum(np.asarray(x, dtype=np.float32), 0.0)

def cleanup(spark: SparkSession | None = None, *objs: object, clear_tf: bool = False):
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
    if clear_tf:
        try:
            tf.keras.backend.clear_session()
        except Exception:
            pass
    gc.collect()

def compute_metrics(df: DataFrame, pred_col: str, y_col: str) -> Dict[str, float | None]:
    """
    Compute metrics on Spark DataFrame:
    - RMSE: sqrt(mean((y - y_hat)^2))
    - MAE:  mean(|y - y_hat|)
    - MAPE: mean(|y - y_hat| / y) * 100  (only when y > 0)
    - sMAPE: mean(2|y - y_hat| / (|y| + |y_hat| + eps)) * 100
    - R2: 1 - SS_res / SS_tot  (correct formula)
    """
    row = df.select(
        F.avg(F.abs(F.col(y_col) - F.col(pred_col))).alias("MAE"),
        F.sqrt(F.avg(F.pow(F.col(y_col) - F.col(pred_col), 2))).alias("RMSE"),
        (
            F.avg(
                F.when(F.col(y_col) > 0, F.abs((F.col(y_col) - F.col(pred_col)) / F.col(y_col)))
            ) * 100
        ).alias("MAPE"),
        (
            F.avg(
                2 * F.abs(F.col(pred_col) - F.col(y_col))
                / (F.abs(F.col(y_col)) + F.abs(F.col(pred_col)) + F.lit(1e-6))
            ) * 100
        ).alias("sMAPE"),
        # R2 = 1 - SS_res / SS_tot
        F.avg(F.pow(F.col(y_col) - F.col(pred_col), 2)).alias("ss_res_mean"),
        F.variance(F.col(y_col)).alias("var_y"),
    ).first()

    r2 = None
    if row["var_y"] is not None and row["var_y"] > 0:
        r2 = 1.0 - float(row["ss_res_mean"]) / float(row["var_y"])

    return {
        "RMSE":  float(row["RMSE"])  if row["RMSE"]  is not None else None,
        "MAE":   float(row["MAE"])   if row["MAE"]   is not None else None,
        "MAPE":  float(row["MAPE"])  if row["MAPE"]  is not None else None,
        "sMAPE": float(row["sMAPE"]) if row["sMAPE"] is not None else None,
        "R2":    float(r2)           if r2            is not None else None,
    }

def copy_dir_to_hdfs(spark: SparkSession, local_dir: str, hdfs_dir: str):
    """Upload local directory to HDFS."""
    import os
    jvm = spark._jvm
    fs = jvm.org.apache.hadoop.fs.FileSystem.get(spark._jsc.hadoopConfiguration())
    dst = jvm.org.apache.hadoop.fs.Path(hdfs_dir)
    if not fs.exists(dst):
        fs.mkdirs(dst)
    for name in sorted(os.listdir(local_dir)):
        src = os.path.join(local_dir, name)
        if os.path.isfile(src):
            fs.copyFromLocalFile(
                False, True,
                jvm.org.apache.hadoop.fs.Path("file://" + os.path.abspath(src)),
                jvm.org.apache.hadoop.fs.Path(f"{hdfs_dir.rstrip('/')}/{name}"),
            )

# ─── Config ────────────────────────────────────────────────────────────────────
@dataclass
class Config:
    hdfs_work_dir: str = "/user/kshape/model"
    tfrecord_jar: str = "/home/tiennd3886/lib/spark-tfrecord_2.12-0.7.0.jar"

    time_col: str = "pickup_bin_30m"
    loc_col: str = "PULocationID"
    target_col: str = "target_t1"  # target = demand at t+1
    split_col: str = "dataset_split"
    time_key_col: str = "time_key"

    sequence_features: tuple[str, ...] = (
        "pickup_demand", "ewma_output", "rolling_mean_24h", "day_of_week",
    )
    valid_splits: tuple[str, ...] = ("train", "validation", "test")

    seq_window: int = 48
    batch_size: int = 1024
    shuffle_buffer: int = 8192
    epochs: int = 1
    early_stopping_patience: int = 5
    random_state: int = 42

    # Ridge ensemble
    ridge_alpha: float = 1.0

    # XGBoost
    xgb_num_workers: int = 3
    xgb_n_estimators: int = 10
    xgb_max_depth: int = 5
    xgb_learning_rate: float = 0.03
    xgb_subsample: float = 0.85
    xgb_colsample_bytree: float = 0.85

    pred_rows_per_file: int = 200_000

    def hdfs(self, *parts: str) -> str:
        return "/".join([self.hdfs_work_dir.rstrip("/"), *parts])

    @property
    def spark_jars(self) -> str:
        return self.tfrecord_jar

    @property
    def spark_cp(self) -> str:
        return self.tfrecord_jar

# ─── Scaler ────────────────────────────────────────────────────────────────────
@dataclass
class SequenceScalerStats:
    seq_mean: np.ndarray
    seq_std: np.ndarray
    y_min: float
    y_denom: float

    @classmethod
    def from_hdfs(cls, spark: SparkSession, path: str) -> "SequenceScalerStats":
        """Read scaler stats from parquet on HDFS (written by premodel.py)."""
        row = spark.read.parquet(path).first()
        return cls(
            np.asarray(ast.literal_eval(row["seq_mean"]), dtype=np.float32),
            np.asarray(ast.literal_eval(row["seq_std"]),  dtype=np.float32),
            float(row["y_min"]),
            float(row["y_denom"]),
        )

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
        .appName("ModelTraining")
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
        .config("spark.executor.memory", "6g")
        .config("spark.executor.memoryOverhead", "2g")
        .config("spark.driver.memory", "3g")
        .config("spark.driver.memoryOverhead", "1g")
        .config("spark.sql.shuffle.partitions", "200")
        .getOrCreate()
    )

# ─── 1. XGBoost Trainer ───────────────────────────────────────────────────────
class XGBoostTrainer:
    def __init__(self, spark: SparkSession, c: Config):
        self.spark = spark
        self.c = c
        self.model = None

    def run(self):
        stage("1/3 — TRAIN XGBOOST")
        full = train = part = pred = None
        try:
            full = self.spark.read.parquet(self.c.hdfs("prepared", "tabular"))
            train = full.filter(F.col(self.c.split_col) == "train")

            self.model = SparkXGBRegressor(
                features_col="features_vector",
                label_col=self.c.target_col,
                prediction_col="xgb_pred",
                num_workers=self.c.xgb_num_workers,
                n_estimators=self.c.xgb_n_estimators,
                max_depth=self.c.xgb_max_depth,
                learning_rate=self.c.xgb_learning_rate,
                subsample=self.c.xgb_subsample,
                colsample_bytree=self.c.xgb_colsample_bytree,
                objective="reg:squarederror",
                random_state=self.c.random_state,
                tree_method="hist",
                eval_metric="mae",
                missing=0.0,
            ).fit(train)

            # Export XGBoost model to HDFS (needed for demo inference)
            self.model.write().overwrite().save(self.c.hdfs("models", "spark_xgb_model"))
            print(f"XGBoost model saved to: {self.c.hdfs('models', 'spark_xgb_model')}")

            # Predict on all splits
            for split in self.c.valid_splits:
                part = full.filter(F.col(self.c.split_col) == split)
                pred = (
                    self.model.transform(part)
                    .select(
                        self.c.time_col, self.c.time_key_col, self.c.loc_col,
                        self.c.split_col, self.c.target_col, "xgb_pred",
                    )
                )
                pred.write.mode("overwrite").parquet(
                    self.c.hdfs("predictions", "xgb", split)
                )
                print(f"  XGBoost predictions [{split}] exported.")
                cleanup(self.spark, part, pred)
                part = pred = None
        finally:
            self.model = None
            cleanup(self.spark, full, train, part, pred)

# ─── 2. CNN-LSTM Trainer ──────────────────────────────────────────────────────
class CNNLSTMTrainer:
    def __init__(self, spark: SparkSession, c: Config, scaler: SequenceScalerStats):
        self.spark = spark
        self.c = c
        self.scaler = scaler
        self.n_features = len(c.sequence_features)

    def run(self):
        stage("2/3 — TRAIN CNN-LSTM (DISTRIBUTED)")
        from spark_tensorflow_distributor import MirroredStrategyRunner
        import os

        # Dọn dẹp model cũ trước khi training để tránh nhầm lẫn
        self._cleanup_before_training()

        c = self.c
        scaler = self.scaler
        hdfs_uri = self.spark._jsc.hadoopConfiguration().get("fs.defaultFS")
        n_features = self.n_features
        local_model_dir = "/tmp/cnn_model_export"

        def train_fn():
            import os
            import shutil
            import tensorflow as tf
            import subprocess
            try:
                import tensorflow_io as tfio
            except ImportError:
                print("WARNING: tensorflow_io not found. HDFS reading may fail.")

            strategy = tf.distribute.MultiWorkerMirroredStrategy()
            
            options = tf.data.Options()
            options.experimental_distribute.auto_shard_policy = tf.data.experimental.AutoShardPolicy.DATA

            def parse(example):
                mean = tf.constant(scaler.seq_mean.reshape(1, -1), tf.float32)
                std  = tf.constant(scaler.seq_std.reshape(1, -1),  tf.float32)
                y_min = tf.constant(scaler.y_min,   tf.float32)
                y_den = tf.constant(scaler.y_denom, tf.float32)
                
                spec = {
                    c.loc_col:      tf.io.FixedLenFeature([], tf.int64),
                    c.time_key_col: tf.io.FixedLenFeature([], tf.string),
                    c.split_col:    tf.io.FixedLenFeature([], tf.string),
                    c.target_col:   tf.io.FixedLenFeature([1], tf.float32),
                    "sequence_flat":     tf.io.FixedLenFeature([c.seq_window * n_features], tf.float32),
                }
                ex = tf.io.parse_single_example(example, spec)
                seq = (tf.reshape(ex["sequence_flat"], [c.seq_window, n_features]) - mean) / std
                y = (ex[c.target_col][0] - y_min) / y_den
                return (seq, y)

            def get_dataset(split, shuffle=False):
                import glob
                hdfs_dir = c.hdfs('prepared', 'tfrecords', split)
                local_dir = f"/tmp/tfrecords_cache_{split}"
                
                # Copy from HDFS to local to avoid TF HDFS UnimplementedError
                if not os.path.exists(local_dir) or not glob.glob(f"{local_dir}/part-*"):
                    os.makedirs(local_dir, exist_ok=True)
                    cmd = f"hdfs dfs -get {hdfs_dir}/part-* {local_dir}/ 2>/dev/null || hadoop fs -get {hdfs_dir}/part-* {local_dir}/ 2>/dev/null || $HADOOP_HOME/bin/hdfs dfs -get {hdfs_dir}/part-* {local_dir}/"
                    subprocess.run(cmd, shell=True)
                
                pattern = f"{local_dir}/part-*"
                files = tf.io.gfile.glob(pattern)
                ds = tf.data.TFRecordDataset(files, num_parallel_reads=tf.data.AUTOTUNE)
                ds = ds.with_options(options).map(parse, num_parallel_calls=tf.data.AUTOTUNE)
                if shuffle:
                    ds = ds.shuffle(c.shuffle_buffer)
                return ds.batch(c.batch_size).prefetch(tf.data.AUTOTUNE)

            with strategy.scope():
                inp = tf.keras.layers.Input((c.seq_window, n_features))
                x = tf.keras.layers.Conv1D(64, 3, padding="causal", activation="relu")(inp)
                x = tf.keras.layers.BatchNormalization()(x)
                x = tf.keras.layers.Dropout(0.20)(x)
                x = tf.keras.layers.LSTM(64)(x)
                x = tf.keras.layers.Dense(32, activation="relu")(x)
                out = tf.keras.layers.Dense(1, activation="linear")(x)
                model = tf.keras.Model(inp, out)
                model.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="mae", metrics=["mae"])

                train_ds = get_dataset("train", shuffle=True)
                val_ds = get_dataset("validation", shuffle=False)

                # Custom training loop to bypass Keras 3 model.fit() incompatibility with tf.distribute
                loss_fn = tf.keras.losses.MeanAbsoluteError(reduction=tf.keras.losses.Reduction.NONE)
                optimizer = tf.keras.optimizers.Adam(1e-3)

                def compute_loss(labels, predictions):
                    per_example_loss = loss_fn(labels, predictions)
                    return tf.nn.compute_average_loss(per_example_loss, global_batch_size=c.batch_size)

                def train_step(inputs):
                    x, y = inputs
                    with tf.GradientTape() as tape:
                        predictions = model(x, training=True)
                        loss = compute_loss(y, predictions)
                    gradients = tape.gradient(loss, model.trainable_variables)
                    optimizer.apply_gradients(zip(gradients, model.trainable_variables))
                    return loss

                def test_step(inputs):
                    x, y = inputs
                    predictions = model(x, training=False)
                    loss = compute_loss(y, predictions)
                    return loss

                @tf.function
                def distributed_train_step(dataset_inputs):
                    per_replica_losses = strategy.run(train_step, args=(dataset_inputs,))
                    return strategy.reduce(tf.distribute.ReduceOp.SUM, per_replica_losses, axis=None)

                @tf.function
                def distributed_test_step(dataset_inputs):
                    per_replica_losses = strategy.run(test_step, args=(dataset_inputs,))
                    return strategy.reduce(tf.distribute.ReduceOp.SUM, per_replica_losses, axis=None)

                dist_train_ds = strategy.experimental_distribute_dataset(train_ds)
                dist_val_ds = strategy.experimental_distribute_dataset(val_ds)

                best_val_loss = float('inf')
                patience_counter = 0
                best_weights = None

                for epoch in range(c.epochs):
                    train_loss = 0.0
                    train_batches = 0
                    for x in dist_train_ds:
                        train_loss += distributed_train_step(x)
                        train_batches += 1
                    train_loss = float(train_loss) / train_batches if train_batches > 0 else 0.0

                    val_loss = 0.0
                    val_batches = 0
                    for x in dist_val_ds:
                        val_loss += distributed_test_step(x)
                        val_batches += 1
                    val_loss = float(val_loss) / val_batches if val_batches > 0 else 0.0

                    print(f"Epoch {epoch+1}/{c.epochs} - loss: {train_loss:.4f} - val_loss: {val_loss:.4f}")

                    if val_loss < best_val_loss:
                        best_val_loss = val_loss
                        best_weights = model.get_weights()
                        patience_counter = 0
                    else:
                        patience_counter += 1
                        if patience_counter >= c.early_stopping_patience:
                            print(f"Early stopping at epoch {epoch+1}")
                            break
                
                if best_weights is not None:
                    model.set_weights(best_weights)

            # Xác định chief worker qua TF_CONFIG JSON (chỉ worker index 0 mới lưu model)
            import json as _json
            _tf_config_str = os.environ.get('TF_CONFIG', '{}')
            try:
                _tf_config = _json.loads(_tf_config_str)
                _task_index = int(_tf_config.get('task', {}).get('index', 0))
                is_chief = (_task_index == 0)
            except Exception:
                is_chief = True  # Không có TF_CONFIG → chạy local → coi là chief

            if is_chief:
                shutil.rmtree(local_model_dir, ignore_errors=True)
                os.makedirs(local_model_dir, exist_ok=True)
                model.save(os.path.join(local_model_dir, "cnn_lstm.keras"))

                hdfs_dst = c.hdfs("models", "cnn_lstm.keras")
                cmd_rm = f"hdfs dfs -rm -f {hdfs_dst} 2>/dev/null || hadoop fs -rm -f {hdfs_dst} 2>/dev/null || $HADOOP_HOME/bin/hdfs dfs -rm -f {hdfs_dst}"
                subprocess.run(cmd_rm, shell=True)

                local_file = os.path.join(local_model_dir, "cnn_lstm.keras")
                cmd_put = f"hdfs dfs -put {local_file} {hdfs_dst} 2>/dev/null || hadoop fs -put {local_file} {hdfs_dst} 2>/dev/null || $HADOOP_HOME/bin/hdfs dfs -put {local_file} {hdfs_dst}"
                result = subprocess.run(cmd_put, shell=True)
                if result.returncode != 0:
                    raise RuntimeError(f"[ERROR] Upload cnn_lstm.keras lên HDFS thất bại: {hdfs_dst}")
                print(f"CNN-LSTM model saved to: {hdfs_dst}")

        print("Starting distributed training across workers...")
        MirroredStrategyRunner(
            num_slots=3, 
            local_mode=False,
            use_gpu=False,
            use_custom_strategy=True
        ).run(train_fn)

        # Tự động kiểm tra và khôi phục cnn_lstm.keras lên HDFS nếu bị thiếu
        self._ensure_model_on_hdfs()

        print("Starting distributed inference for CNN-LSTM...")
        for split in self.c.valid_splits:
            self._predict(split)

    def _cleanup_before_training(self):
        """
        Dọn dẹp trước khi training để tránh nhầm lẫn model cũ/mới:
        - Xóa cnn_lstm.keras cũ trên HDFS
        - Xóa /tmp/cnn_model_export/ trên tất cả worker
        - Xóa cache TFRecord /tmp/tfrecords_cache_* trên tất cả worker
          (tránh DataLossError do file bị truncated/corrupted từ lần chạy trước)
        - Xóa cache inference cnn_lstm_inf_*.keras cũ trên tất cả worker
        """
        import subprocess
        hdfs_dst = self.c.hdfs("models", "cnn_lstm.keras")
        workers = ["hadoop-worker-1", "hadoop-worker-2", "hadoop-worker-3"]

        print("[CLEANUP] Dọn dẹp model cũ trước khi training...")

        # 1. Xóa model cũ trên HDFS
        r = subprocess.run(f"hdfs dfs -rm -f {hdfs_dst}", shell=True,
                           capture_output=True)
        if r.returncode == 0:
            print(f"  [HDFS] Đã xóa: {hdfs_dst}")
        else:
            print(f"  [HDFS] Không có file cũ hoặc xóa thất bại (bỏ qua).")

        # 2. Xóa model export, TFRecord cache và inference cache trên từng worker
        for worker in workers:
            clean_cmd = (
                "rm -rf /tmp/cnn_model_export "
                "&& rm -rf /tmp/tfrecords_cache_* "   # ← tránh DataLossError
                "&& rm -f /tmp/cnn_lstm_inf_*.keras"
            )
            r = subprocess.run(f"ssh {worker} '{clean_cmd}'", shell=True,
                               capture_output=True)
            status = "OK" if r.returncode == 0 else "WARN"
            print(f"  [{status}] [{worker}] Đã dọn model export, TFRecord cache và inference cache.")

        print("[CLEANUP] Hoàn tất. Bắt đầu training mới...")

    def _ensure_model_on_hdfs(self):
        """
        Đảm bảo cnn_lstm.keras mới nhất đã được upload lên HDFS.
        Vì _cleanup_before_training() đã xóa model cũ trước khi training,
        nếu file vẫn chưa có trên HDFS → lỗi upload trong train_fn
        → tự động tìm và upload từ worker.
        """
        import subprocess
        hdfs_dst = self.c.hdfs("models", "cnn_lstm.keras")
        local_file = "/tmp/cnn_model_export/cnn_lstm.keras"
        workers = ["hadoop-worker-1", "hadoop-worker-2", "hadoop-worker-3"]

        # Kiểm tra file đã tồn tại trên HDFS chưa (do chief upload trong train_fn)
        check = subprocess.run(
            f"hdfs dfs -test -e {hdfs_dst}", shell=True
        )
        if check.returncode == 0:
            print(f"[OK] cnn_lstm.keras đã được upload lên HDFS: {hdfs_dst}")
            return

        print(f"[WARN] cnn_lstm.keras KHÔNG tồn tại trên HDFS. Đang tìm trên các worker...")

        for worker in workers:
            check_worker = subprocess.run(
                f"ssh {worker} 'test -f {local_file}'", shell=True
            )
            if check_worker.returncode != 0:
                print(f"  [{worker}] Không tìm thấy file.")
                continue

            print(f"  [{worker}] Tìm thấy file! Đang upload lên HDFS...")
            upload = subprocess.run(
                f"ssh {worker} 'hdfs dfs -put -f {local_file} {hdfs_dst}'",
                shell=True
            )
            if upload.returncode == 0:
                print(f"  [{worker}] Upload thành công: {hdfs_dst}")
                return
            else:
                print(f"  [{worker}] Upload thất bại, thử worker tiếp theo...")

        raise RuntimeError(
            "[ERROR] Không tìm thấy cnn_lstm.keras trên bất kỳ worker nào. "
            "Vui lòng train lại CNN-LSTM."
        )

    def _predict(self, split: str):
        """Distributed predict using PySpark mapInPandas."""
        mean = self.scaler.seq_mean
        std = self.scaler.seq_std
        y_min = self.scaler.y_min
        y_den = self.scaler.y_denom
        model_hdfs_path = self.c.hdfs("models", "cnn_lstm.keras")
        n_features = self.n_features
        window = self.c.seq_window
        c = self.c

        def predict_batch(iterator):
            import tensorflow as tf
            import numpy as np
            import tempfile
            import os
            import subprocess
            import pandas as pd

            tmp_dir = tempfile.gettempdir()
            local_model_path = os.path.join(tmp_dir, f"cnn_lstm_inf_{os.getpid()}.keras")
            
            if not os.path.exists(local_model_path):
                cmd_get = f"hdfs dfs -get -f {model_hdfs_path} {local_model_path} 2>/dev/null || hadoop fs -get -f {model_hdfs_path} {local_model_path} 2>/dev/null || $HADOOP_HOME/bin/hdfs dfs -get -f {model_hdfs_path} {local_model_path}"
                subprocess.run(cmd_get, shell=True, check=True)
                
            model = tf.keras.models.load_model(local_model_path)

            for pdf in iterator:
                seqs = np.vstack(pdf['sequence_flat'].values) 
                seqs = seqs.reshape(-1, window, n_features)
                seqs = (seqs - mean) / std

                preds_raw = model.predict(seqs, batch_size=1024, verbose=0).squeeze(-1)
                preds = np.maximum(preds_raw * y_den + y_min, 0.0)
                
                yield pd.DataFrame({
                    c.time_col: pdf[c.time_col],
                    c.time_key_col: pdf[c.time_key_col],
                    c.loc_col: pdf[c.loc_col],
                    c.split_col: pdf[c.split_col],
                    c.target_col: pdf[c.target_col],
                    "cnn_lstm_pred": preds.astype(np.float32)
                })

        seq_df = self.spark.read.parquet(self.c.hdfs("prepared", "sequence"))
        part = seq_df.filter(F.col(self.c.split_col) == split)
        
        schema = f"{self.c.time_col} timestamp, {self.c.time_key_col} string, {self.c.loc_col} long, " \
                 f"{self.c.split_col} string, {self.c.target_col} float, cnn_lstm_pred float"
                 
        pred = part.mapInPandas(predict_batch, schema=schema)
        pred.write.mode("overwrite").parquet(self.c.hdfs("predictions", "cnn_lstm", split))
        print(f"  CNN-LSTM predictions [{split}] exported via distributed inference.")


# ─── 3. Ridge Ensemble ────────────────────────────────────────────────────────
class EnsembleTrainer:
    def __init__(self, spark: SparkSession, c: Config):
        self.spark = spark
        self.c = c
        self.model = None
        self.assembler = VectorAssembler(
            inputCols=["xgb_pred", "cnn_lstm_pred"],
            outputCol="meta_features",
        )

    def run(self) -> Dict[str, Dict[str, float | None]]:
        stage("3/3 — TRAIN RIDGE ENSEMBLE")
        all_metrics = {}
        val_base = val_vec = base = vec = pred = None
        try:
            # Fit Ridge on validation set
            val_base = self._merge_predictions("validation")
            val_vec = self.assembler.transform(val_base)
            self.model = LinearRegression(
                featuresCol="meta_features",
                labelCol=self.c.target_col,
                predictionCol="ensemble_pred",
                regParam=self.c.ridge_alpha,
            ).fit(val_vec)
            self.model.write().overwrite().save(self.c.hdfs("models", "spark_ridge_meta_model"))
            print(f"Ridge model saved to: {self.c.hdfs('models', 'spark_ridge_meta_model')}")

            # Evaluate on each split
            for split in self.c.valid_splits:
                base = self._merge_predictions(split)
                vec = self.assembler.transform(base)
                pred = (
                    self.model.transform(vec)
                    .withColumn("ensemble_pred", F.greatest("ensemble_pred", F.lit(0.0)))
                )
                pred.write.mode("overwrite").parquet(
                    self.c.hdfs("predictions", "ensemble", split)
                )

                m_xgb = compute_metrics(base, "xgb_pred",       self.c.target_col)
                m_cnn = compute_metrics(base, "cnn_lstm_pred",   self.c.target_col)
                m_ens = compute_metrics(pred, "ensemble_pred",   self.c.target_col)

                all_metrics[f"xgb_{split}"] = m_xgb
                all_metrics[f"cnn_{split}"] = m_cnn
                all_metrics[f"ens_{split}"] = m_ens

                print(f"\n--- {split.upper()} ---")
                for name, m in [("XGBoost", m_xgb), ("CNN-LSTM", m_cnn), ("Ensemble", m_ens)]:
                    print(f"  {name:10s} | RMSE={m['RMSE']:8.3f} MAE={m['MAE']:8.3f} "
                          f"MAPE={m['MAPE']:7.2f}% sMAPE={m['sMAPE']:7.2f}% R2={m['R2']:.5f}")

                cleanup(self.spark, base, vec, pred)
                base = vec = pred = None

            return all_metrics
        finally:
            self.model = None
            cleanup(self.spark, val_base, val_vec, base, vec, pred)

    def _merge_predictions(self, split: str) -> DataFrame:
        """Join XGBoost + CNN-LSTM predictions for the same split."""
        xgb_df = self.spark.read.parquet(
            self.c.hdfs("predictions", "xgb", split)
        ).alias("xgb")
        cnn_df = self.spark.read.parquet(
            self.c.hdfs("predictions", "cnn_lstm", split)
        ).alias("cnn")
        return (
            cnn_df.join(
                xgb_df,
                on=[self.c.loc_col, self.c.time_key_col, self.c.split_col],
                how="inner",
            )
            .select(
                F.col(f"xgb.{self.c.time_col}").alias(self.c.time_col),
                F.col(f"cnn.{self.c.time_key_col}").alias(self.c.time_key_col),
                F.col(f"cnn.{self.c.loc_col}").alias(self.c.loc_col),
                F.col(f"cnn.{self.c.split_col}").alias(self.c.split_col),
                F.col(f"cnn.{self.c.target_col}").alias(self.c.target_col),
                F.col("xgb.xgb_pred").cast("double").alias("xgb_pred"),
                F.col("cnn.cnn_lstm_pred").cast("double").alias("cnn_lstm_pred"),
            )
        )

# ─── 4. Save metrics & metadata to HDFS ──────────────────────────────────────
def save_metrics_to_hdfs(spark: SparkSession, all_metrics: Dict, c: Config):
    """Convert metrics dict to DataFrame and write to HDFS."""
    rows = []
    for key, m in all_metrics.items():
        parts = key.split("_", 1)
        rows.append({
            "model":  parts[0],
            "split":  parts[1],
            "RMSE":   m.get("RMSE"),
            "MAE":    m.get("MAE"),
            "MAPE":   m.get("MAPE"),
            "sMAPE":  m.get("sMAPE"),
            "R2":     m.get("R2"),
        })
    pdf = pd.DataFrame(rows)
    sdf = spark.createDataFrame(pdf)
    sdf.write.mode("overwrite").parquet(c.hdfs("metrics"))
    print(f"\nMetrics table saved to: {c.hdfs('metrics')}")

def save_metadata_to_hdfs(spark: SparkSession, c: Config, scaler: SequenceScalerStats, all_metrics: Dict):
    """Export pipeline config, scaler stats, and metrics to a JSON for demo use."""
    import json, os, shutil
    local_meta_dir = "/tmp/metadata_export"
    shutil.rmtree(local_meta_dir, ignore_errors=True)
    os.makedirs(local_meta_dir, exist_ok=True)

    metadata = {
        "config": {
            "tabular_features": [
                "hour", "minute", "day_of_week", "is_weekday", "is_weekend",
                "slot_in_week", "demand_t_1", "rolling_mean_24h", "ewma_output",
                "cluster_id", "cluster_avg_demand_t", "cluster_demand_t_1",
                "cluster_rolling_mean_24h", "cluster_rolling_std_24h",
                "cluster_diff_t1", "cluster_mean_diff_24h",
                "intra_cluster_similarity", "inter_cluster_similarity"
            ],
            "sequence_features": list(c.sequence_features),
            "seq_window": c.seq_window,
            "ridge_alpha": c.ridge_alpha,
            "models_dir": c.hdfs("models"),
            "feature_lookup_path": c.hdfs("demo", "feature_lookup"),
            "sequence_lookup_path": c.hdfs("demo", "sequence_lookup"),
        },
        "scaler_stats": {
            "seq_mean": scaler.seq_mean.tolist(),
            "seq_std":  scaler.seq_std.tolist(),
            "y_min":    float(scaler.y_min),
            "y_denom":  float(scaler.y_denom),
        },
        "metrics": all_metrics,
    }

    with open(os.path.join(local_meta_dir, "pipeline_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    copy_dir_to_hdfs(spark, local_meta_dir, c.hdfs("models"))
    shutil.rmtree(local_meta_dir, ignore_errors=True)
    print(f"Pipeline metadata saved to: {c.hdfs('models', 'pipeline_metadata.json')}")

def export_feature_lookup(spark: SparkSession, c: Config):
    """
    Export feature lookup table for demo inference.

    The demo cannot recompute historical lag/rolling/cluster features on the fly
    for a single raw trip. Instead, for any (PULocationID, pickup_bin_30m) key
    in the test set, this lookup table provides:
      - All 18 tabular features needed by XGBoost
      - The 48-step sequence (flattened) needed by CNN-LSTM

    Demo flow:
        (PULocationID, pickup_datetime)
            -> round to pickup_bin_30m
            -> lookup tabular features   -> XGBoost  -> xgb_pred
            -> lookup sequence_flat      -> CNN-LSTM  -> cnn_lstm_pred
            -> Ridge Ensemble            -> pickup_demand
    """
    stage("EXPORT FEATURE LOOKUP TABLE FOR DEMO")

    # ── Tabular feature lookup: key = (PULocationID, pickup_bin_30m) ──────────
    tabular_features = [
        "hour", "minute", "day_of_week", "is_weekday", "is_weekend",
        "slot_in_week", "demand_t_1", "rolling_mean_24h", "ewma_output",
        "cluster_id", "cluster_avg_demand_t", "cluster_demand_t_1",
        "cluster_rolling_mean_24h", "cluster_rolling_std_24h",
        "cluster_diff_t1", "cluster_mean_diff_24h",
        "intra_cluster_similarity", "inter_cluster_similarity",
    ]
    tab = spark.read.parquet(c.hdfs("prepared", "tabular"))
    # Reconstruct individual feature columns from features_vector using vector_to_array
    tab = tab.withColumn("features_array", vector_to_array("features_vector"))
    for i, feat in enumerate(tabular_features):
        tab = tab.withColumn(feat, F.col("features_array")[i])

    feat_lookup = (
        tab
        .filter(F.col(c.split_col) == "test")
        .select(
            F.col(c.loc_col).alias("PULocationID"),
            F.col(c.time_col).alias("pickup_bin_30m"),
            F.col(c.target_col).alias("target_t1"),
            *tabular_features,
        )
    )
    feat_lookup.write.mode("overwrite").partitionBy("PULocationID").parquet(
        c.hdfs("demo", "feature_lookup")
    )
    print(f"Feature lookup (tabular) exported to: {c.hdfs('demo', 'feature_lookup')}")
    cleanup(spark, tab, feat_lookup)

    # ── Sequence lookup: key = (PULocationID, pickup_bin_30m) ─────────────────
    seq = spark.read.parquet(c.hdfs("prepared", "sequence"))
    seq_lookup = (
        seq
        .filter(F.col(c.split_col) == "test")
        .select(
            F.col(c.loc_col).alias("PULocationID"),
            F.col(c.time_col).alias("pickup_bin_30m"),
            "sequence_flat",
        )
    )
    seq_lookup.write.mode("overwrite").partitionBy("PULocationID").parquet(
        c.hdfs("demo", "sequence_lookup")
    )
    print(f"Sequence lookup (CNN-LSTM input) exported to: {c.hdfs('demo', 'sequence_lookup')}")
    cleanup(spark, seq, seq_lookup)

# ─── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    c = Config()
    seed_all(c.random_state)
    spark = build_spark(c)
    spark.sparkContext.setLogLevel("WARN")

    try:
        # Read scaler from HDFS (written by premodel.py)
        scaler = SequenceScalerStats.from_hdfs(spark, c.hdfs("prepared", "scaler_stats"))

        # 1. XGBoost
        XGBoostTrainer(spark, c).run()

        # 2. CNN-LSTM
        CNNLSTMTrainer(spark, c, scaler).run()

        # 3. Ridge Ensemble + Metrics
        all_metrics = EnsembleTrainer(spark, c).run()

        # 4. Save metrics & metadata to HDFS
        save_metrics_to_hdfs(spark, all_metrics, c)
        save_metadata_to_hdfs(spark, c, scaler, all_metrics)

        # 5. Export feature lookup table for demo (test split snapshot)
        export_feature_lookup(spark, c)

        print("\n" + "=" * 80)
        print("MODEL TRAINING COMPLETE")
        print("=" * 80)
        print(f"  models          : {c.hdfs('models')}")
        print(f"    spark_xgb_model         (XGBoost)")
        print(f"    cnn_lstm.keras          (CNN-LSTM)")
        print(f"    spark_ridge_meta_model  (Ensemble)")
        print(f"    pipeline_metadata.json  (config + scaler + metrics)")
        print(f"  predictions     : {c.hdfs('predictions')}")
        print(f"  metrics         : {c.hdfs('metrics')}")
        print(f"  demo lookup     : {c.hdfs('demo')}")
        print(f"    feature_lookup/  (PULocationID + bin -> 18 tabular features)")
        print(f"    sequence_lookup/ (PULocationID + bin -> 48-step sequence)")
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
