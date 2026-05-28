from dataclasses import dataclass
from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, TimestampType, DoubleType, LongType, IntegerType
import gc, os, shutil

@dataclass
class Config:
    input_train: str = "/user/data/train"
    input_val: str = "/user/data/val"
    input_test: str = "/user/data/test"
    output_path_base: str = "/user/kshape/preprocess"
    bin_minutes: int = 30
    min_duration_minute: float = 1.0
    max_duration_minute: float = 180.0
    min_trip_distance: float = 0.1
    max_trip_distance: float = 50.0
    max_passengers: int = 8
    min_location_id: int = 1
    max_location_id: int = 263
    active_ratio_threshold: float = 0.05
    ewma_alpha: float = 0.3
    ewma_lookback: int = 12

    @property
    def bins_per_day(self):
        return 24 * 60 // self.bin_minutes

    @property
    def bins_per_week(self):
        return self.bins_per_day * 7

    @property
    def required_history_bins(self):
        # We only need enough history for the 24h rolling mean or the EWMA lookback
        return max(5, self.bins_per_day, self.ewma_lookback)


class Preprocess:
    def __init__(self, c=Config()):
        self.c = c
        self.spark = (
            SparkSession.builder.appName("Preprocess")
            .config("spark.sql.session.timeZone", "America/New_York")
            .config("spark.sql.files.ignoreCorruptFiles", "true")
            .config("spark.sql.parquet.mergeSchema", "false")
            .config("spark.sql.adaptive.enabled", "true")
            .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
            # Tắt vectorized reader để tránh lỗi thầm lặng khi kiểu cột trong parquet
            # (ví dụ IntegerType) không khớp chính xác với schema được ép buộc (LongType).
            # Nếu bật vectorized reader, Spark có thể trả về toàn NULL cho cả cột
            # và làm hỏng cả push-down filter mà không báo lỗi rõ ràng.
            .config("spark.sql.parquet.enableVectorizedReader", "false")
            .config("spark.master", "yarn")
            .config("spark.submit.deployMode", "client")
            .config("spark.executor.instances", "3")
            .config("spark.executor.cores", "3")
            .config("spark.executor.memory", "8g")
            .config("spark.executor.memoryOverhead", "1g")
            .config("spark.driver.memory", "3g")
            .config("spark.driver.memoryOverhead", "1g")
            .config("spark.sql.shuffle.partitions", "18")
            .getOrCreate()
        )
        self.spark.sparkContext.setLogLevel("ERROR")

        # Schema chỉ còn dùng để tạo DataFrame rỗng khi read thất bại.
        # Không dùng để ép kiểu lúc đọc parquet nữa — việc cast được thực hiện
        # tường minh trong select() để tránh lỗi thầm lặng của vectorized reader.
        self.schema = StructType([
            StructField("tpep_pickup_datetime", TimestampType(), True),
            StructField("tpep_dropoff_datetime", TimestampType(), True),
            StructField("PULocationID", LongType(), True),
            StructField("DOLocationID", LongType(), True),
            StructField("passenger_count", DoubleType(), True),
            StructField("trip_distance", DoubleType(), True),
            StructField("fare_amount", DoubleType(), True),
            StructField("total_amount", DoubleType(), True),
        ])

    def read_and_clean_split(self, path: str, split_name: str):
        c = self.c
        try:
            # Không dùng .schema() khi đọc để Spark tự suy ra kiểu gốc trong parquet.
            # Việc ép kiểu về đúng type được thực hiện tường minh ở select() bên dưới.
            df = self.spark.read.option("mergeSchema", "false").parquet(path)
        except Exception as e:
            print(f"Warning: Could not read parquet from {path}. Error: {e}")
            df = self.spark.createDataFrame([], self.schema)
            
        cleaned = (
            df.withColumn("_source_file", F.input_file_name())
            .select(
                F.col("tpep_pickup_datetime").cast("timestamp").alias("pickup_dt"),
                F.col("tpep_dropoff_datetime").cast("timestamp").alias("dropoff_dt"),
                F.col("PULocationID").cast("long"),
                F.col("DOLocationID").cast("long"),
                F.col("passenger_count").cast("int"),
                F.col("trip_distance").cast("double"),
                F.col("fare_amount").cast("double"),
                F.col("total_amount").cast("double"),
                F.col("_source_file"),
            )
            .withColumn("trip_duration_minute", (F.unix_timestamp("dropoff_dt") - F.unix_timestamp("pickup_dt")) / 60.0)
            .filter(F.col("PULocationID").between(c.min_location_id, c.max_location_id))
            .filter(F.col("trip_duration_minute").between(c.min_duration_minute, c.max_duration_minute))
            .filter(F.col("trip_distance").isNotNull() & F.col("trip_distance").between(c.min_trip_distance, c.max_trip_distance))
            .filter(F.col("passenger_count").isNull() | F.col("passenger_count").between(1, c.max_passengers))
            .filter(F.col("fare_amount").isNull() | (F.col("fare_amount") >= 0))
            .filter(F.col("total_amount").isNull() | (F.col("total_amount") >= 0))
            .withColumn("raw_dataset_split", F.lit(split_name))
        )
        return cleaned

    def clean(self):
        train_df = self.read_and_clean_split(self.c.input_train, "train")
        val_df   = self.read_and_clean_split(self.c.input_val,   "validation")
        test_df  = self.read_and_clean_split(self.c.input_test,  "test")

        # ─── CHẶN FUTURE LEAK: cắt cứng khoảng thời gian hợp lệ của từng tập ───
        # Train : 01/2020 → hết tháng 02/2024  (< 2024-03-01)
        # Val   : 03/2024 → hết tháng 09/2024  (>= 2024-03-01 và < 2024-10-01)
        # Test  : 10/2024 → hết tháng 12/2025  (>= 2024-10-01 và < 2026-01-01)
        train_df = train_df.filter(
            (F.col("pickup_dt") >= F.lit("2020-01-01").cast("timestamp")) &
            (F.col("pickup_dt") <  F.lit("2024-03-01").cast("timestamp"))
        )
        val_df = val_df.filter(
            (F.col("pickup_dt") >= F.lit("2024-03-01").cast("timestamp")) &
            (F.col("pickup_dt") <  F.lit("2024-10-01").cast("timestamp"))
        )
        test_df = test_df.filter(
            (F.col("pickup_dt") >= F.lit("2024-10-01").cast("timestamp")) &
            (F.col("pickup_dt") <  F.lit("2026-01-01").cast("timestamp"))
        )

        # ─── DIAGNOSTIC: in count + min/max ts của từng tập sau khi filter ───
        for name, sdf in [("train", train_df), ("validation", val_df), ("test", test_df)]:
            stats = sdf.agg(
                F.count("*").alias("cnt"),
                F.min("pickup_dt").alias("min_ts"),
                F.max("pickup_dt").alias("max_ts"),
            ).collect()[0]
            print(
                f"[CLEAN] {name:>12}: count={stats['cnt']:>12,} "
                f"| min={stats['min_ts']} "
                f"| max={stats['max_ts']}"
            )
            if stats["cnt"] == 0:
                print(f"[WARN]  {name:>12} is EMPTY after date filter! "
                      f"Check HDFS path or raw timestamp range.")

        df = train_df.unionByName(val_df).unionByName(test_df)
        print("Data unioned and filtered anomalous dates successfully.")
        return df


    def build_panel(self, df):
        c = self.c
        demand = (
            df.withColumn(
                "pickup_bin_30m",
                F.to_timestamp(
                    F.from_unixtime(
                        F.floor(F.unix_timestamp("pickup_dt") / (c.bin_minutes * 60)) * (c.bin_minutes * 60)
                    )
                )
            )
            .groupBy("pickup_bin_30m", "PULocationID")
            .agg(F.count("*").cast("int").alias("pickup_demand"))
        )

        print("Calculating dataset time bounds...")
        bounds_df = df.groupBy("raw_dataset_split").agg(
            F.min("pickup_dt").alias("min_ts"), 
            F.max("pickup_dt").alias("max_ts"),
            F.count("*").alias("count")
        ).collect()
        
        for r in bounds_df:
            print(f"Split '{r['raw_dataset_split']}': {r['count']} rows, min: {r['min_ts']}, max: {r['max_ts']}")
            
        if not bounds_df:
            raise ValueError("All data splits are completely empty! Please check your input paths and data.")

        min_ts_val = min(r["min_ts"] for r in bounds_df if r["min_ts"] is not None)
        max_ts_val = max(r["max_ts"] for r in bounds_df if r["max_ts"] is not None)
        
        if min_ts_val is None or max_ts_val is None:
            raise ValueError("Time boundaries are null. Dataset might be empty after filters.")

        min_ts = min_ts_val.strftime("%Y-%m-%d %H:%M:%S")
        max_ts = max_ts_val.strftime("%Y-%m-%d %H:%M:%S")

        train_end_val = next((r["max_ts"] for r in bounds_df if r["raw_dataset_split"] == "train"), min_ts_val)
        val_end_val = next((r["max_ts"] for r in bounds_df if r["raw_dataset_split"] == "validation"), train_end_val)
        
        train_end_str = train_end_val.strftime("%Y-%m-%d %H:%M:%S")
        val_end_str = val_end_val.strftime("%Y-%m-%d %H:%M:%S")

        train_expr = F.expr(f"timestamp'{train_end_str}'")
        val_expr = F.expr(f"timestamp'{val_end_str}'")

        # Tính số ngày phân biệt có dữ liệu trong tập train
        # Dùng Day Coverage thay vì Bin Coverage để tránh mẫu số quá lớn (~70k bins)
        train_days_total = max(1, int((train_end_val - min_ts_val).total_seconds() / 86400))

        active = (
            demand.filter(F.col("pickup_bin_30m") <= train_expr)
            .groupBy("PULocationID")
            .agg(
                F.countDistinct(F.to_date("pickup_bin_30m")).alias("active_days"),
                F.sum("pickup_demand").alias("total_demand")
            )
            .withColumn("day_coverage", F.col("active_days") / F.lit(train_days_total))
            .filter(F.col("day_coverage") >= c.active_ratio_threshold)
            .select("PULocationID")
        )

        active_count = active.count()
        print(f"Train days total: {train_days_total}")
        print(f"Active zones (day_coverage >= {c.active_ratio_threshold}): {active_count}")
        if active_count == 0:
            raise ValueError(
                f"No active zones found! "
                f"train_days_total={train_days_total}, threshold={c.active_ratio_threshold}. "
                f"Lowering active_ratio_threshold in Config may help."
            )

        bins = self.spark.sql(f"""
            SELECT explode(
                sequence(
                    to_timestamp('{min_ts}'),
                    to_timestamp('{max_ts}'),
                    interval {c.bin_minutes} minutes
                )
            ) AS pickup_bin_30m
        """)

        panel = (
            bins.crossJoin(active)
            .join(demand, ["pickup_bin_30m", "PULocationID"], "left")
            .fillna({"pickup_demand": 0})
        )

        return panel, train_expr, val_expr, min_ts

    def engineer(self, df, train_expr, val_expr, min_ts):
        c = self.c
        
        df = df.withColumn(
            "time_idx",
            ((F.unix_timestamp("pickup_bin_30m") - F.unix_timestamp(F.lit(min_ts).cast("timestamp"))) / (c.bin_minutes * 60)).cast("int")
        )

        df = df.repartition("PULocationID").sortWithinPartitions("time_idx")

        w = Window.partitionBy("PULocationID").orderBy("time_idx")
        w24 = w.rowsBetween(-c.bins_per_day, -1)

        df = (
            df.withColumn("hour", F.hour("pickup_bin_30m").cast("int"))
            .withColumn("minute", F.minute("pickup_bin_30m").cast("int"))
            .withColumn("day_of_week", ((F.dayofweek("pickup_bin_30m") + 5) % 7).cast("int"))
        )

        df = df.withColumn("demand_t_1", F.lag("pickup_demand", 1).over(w))

        df = (
            df.withColumn("rolling_mean_24h", F.avg("pickup_demand").over(w24))
        )

        ewma = F.lit(0.0)
        for i in range(1, c.ewma_lookback + 1):
            ewma += (
                F.coalesce(F.lag("pickup_demand", i).over(w), F.lit(0.0)).cast("double")
                * F.lit(c.ewma_alpha * ((1 - c.ewma_alpha) ** (i - 1)))
            )

        df = df.withColumn("ewma_output", ewma.cast("double")).fillna({
            "demand_t_1": 0.0,
            "rolling_mean_24h": 0.0,
            "ewma_output": 0.0,
        })

        df = (
            df.withColumn(
                "dataset_split",
                F.when(F.col("pickup_bin_30m") <= train_expr, "train")
                .when(F.col("pickup_bin_30m") <= val_expr, "validation")
                .otherwise("test")
            )
            .withColumn("ready", (F.col("time_idx") >= c.required_history_bins).cast("int"))
        )

        cols = [
            "pickup_bin_30m", "dataset_split", "PULocationID", "pickup_demand",
            "hour", "minute", "day_of_week", 
            "demand_t_1", "rolling_mean_24h", "ewma_output",
            "ready"
        ]

        panel = df.select(*cols).filter(F.col("ready") == 1)
        
        return panel

    def run(self):
        try:
            clean = self.clean()
            panel, train_expr, val_expr, min_ts = self.build_panel(clean)
            panel = self.engineer(panel, train_expr, val_expr, min_ts)

            # Output straight to HDFS/Cloud
            panel.write.mode("overwrite").partitionBy("dataset_split").parquet(self.c.output_path_base)

            print(f"Exported: {self.c.output_path_base}")
            print("[SUCCESS] Preprocessing completed (Cloud output only).")

        finally:
            try:
                # Dọn dẹp DataFrame (báo Spark giải phóng vùng nhớ đang bị chiếm dụng)
                del clean, panel
            except Exception:
                pass
            
            try:
                # Clear bộ đệm Cache của Spark (những bảng được cache lại)
                self.spark.catalog.clearCache()
            except Exception:
                pass
                
            try:
                # Gọi thủ công Garbage Collector của Python để giải phóng RAM
                gc.collect()
            except Exception:
                pass
                
            try:
                # Ép tắt phiên Spark, thao tác này sẽ kill mọi tiến trình / job đang chạy ngầm trên YARN Cluster
                self.spark.stop()
                print("[INFO] Spark stopped and resources released.")
            except Exception as e:
                print(f"[WARN] spark.stop failed: {e}")

cfg = Config()
job = Preprocess(cfg)
job.run()

# Dọn dẹp lần cuối các biến cục bộ ngoài class
del job
gc.collect()
