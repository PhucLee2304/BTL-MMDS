import gc
from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

INPUT_PATH  = "/user/kshape/preprocess"
OUTPUT_PATH = "/user/kshape/preclustering"

spark = (
    SparkSession.builder
    .appName("Preclustering")
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
spark.sparkContext.setLogLevel("ERROR")

df = spark.read.parquet(INPUT_PATH)
df.printSchema()
print(f"Total input rows (all splits): {df.count():,}")

df = (
    df.filter(F.col("dataset_split") == "train")
      .filter(F.col("pickup_bin_30m").isNotNull() & F.col("PULocationID").isNotNull())
      .fillna(0, subset=["pickup_demand"])
)

train_count = df.count()
print(f"Train rows (after null filter): {train_count:,}")

BINS_PER_DAY  = 48   # 24h / 30min
BINS_PER_WEEK = 336  # 7 days × 48 bins

# Index 30mins in a week: 0-335
df = df.withColumn(
    "slot_in_week",
    (F.col("day_of_week") * BINS_PER_DAY + F.col("hour") * 2 + (F.col("minute") / 30).cast("int")).cast("int")
)

weekly_profile = (
    df.groupBy("PULocationID", "slot_in_week")
      .agg(F.avg("pickup_demand").cast("double").alias("avg_demand"))
      .orderBy("PULocationID", "slot_in_week")
)

w_zone = Window.partitionBy("PULocationID")
weekly_profile = (
    weekly_profile
    .withColumn("zone_mean", F.avg("avg_demand").over(w_zone))
    .withColumn("zone_std",  F.stddev_pop("avg_demand").over(w_zone))
    .withColumn(
        "normalized_demand",
        F.when(F.col("zone_std") == 0, F.lit(0.0))
         .otherwise((F.col("avg_demand") - F.col("zone_mean")) / F.col("zone_std"))
    )
)

preclustering = weekly_profile.select(
    "PULocationID",
    "slot_in_week",
    "avg_demand",
    "zone_mean",
    "zone_std",
    "normalized_demand",
)

preclustering_count = preclustering.count()
print(f"Preclustering rows (zone × slot): {preclustering_count:,}")

slot_check = (
    preclustering
    .groupBy("PULocationID")
    .agg(F.count("*").alias("n_slots"))
    .filter(F.col("n_slots") != BINS_PER_WEEK)
)
incomplete_zones = slot_check.count()
if incomplete_zones > 0:
    print(f"[WARN] {incomplete_zones} zone(s) có số slot != {BINS_PER_WEEK}. Kiểm tra lại dữ liệu nguồn!")
    slot_check.orderBy("n_slots").show(20, truncate=False)
else:
    print(f"[OK] Tất cả các zone đều có đủ {BINS_PER_WEEK} slot/tuần.")

preclustering.write.mode("overwrite").parquet(OUTPUT_PATH)
print(f"Exported preclustering data to: {OUTPUT_PATH}")

meta_raw = preclustering.agg(
    F.count("*").alias("total_rows"),
    F.countDistinct("PULocationID").alias("n_locations"),
    F.countDistinct("slot_in_week").alias("n_slots"),
    F.min("avg_demand").alias("min_avg_demand"),
    F.max("avg_demand").alias("max_avg_demand"),
    F.avg("avg_demand").alias("global_mean_demand"),
    F.min("normalized_demand").alias("min_norm"),
    F.max("normalized_demand").alias("max_norm"),
).first().asDict()

print("[PRECLUSTERING META]")
print(f"  total_rows       : {meta_raw['total_rows']:,}")
print(f"  n_locations      : {meta_raw['n_locations']}")
print(f"  n_slots          : {meta_raw['n_slots']}")
print(f"  bins_per_week    : {BINS_PER_WEEK}")
print(f"  bins_per_day     : {BINS_PER_DAY}")
print(f"  min_avg_demand   : {meta_raw['min_avg_demand']:.4f}")
print(f"  max_avg_demand   : {meta_raw['max_avg_demand']:.4f}")
print(f"  global_mean      : {meta_raw['global_mean_demand']:.4f}")
print(f"  min_norm         : {meta_raw['min_norm']:.4f}")
print(f"  max_norm         : {meta_raw['max_norm']:.4f}")
print(f"  incomplete_zones : {incomplete_zones}")
print(f"  input_path       : {INPUT_PATH}")
print(f"  output_path      : {OUTPUT_PATH}")

try:
    del df, weekly_profile, preclustering
except Exception:
    pass

try:
    spark.catalog.clearCache()
except Exception:
    pass

try:
    gc.collect()
except Exception:
    pass

try:
    spark.stop()
    print("[INFO] Spark stopped and resources released.")
except Exception as e:
    print(f"[WARN] spark.stop failed: {e}")
