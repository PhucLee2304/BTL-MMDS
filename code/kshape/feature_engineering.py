import gc
import warnings
from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

warnings.filterwarnings("ignore")

PANEL_PATH  = "/user/kshape/clustering/panel"
OUTPUT_PATH = "/user/kshape/feature_engineering"

BINS_PER_DAY      = 48    
MISSING_CLUSTER   = -1    

spark = (
    SparkSession.builder
    .appName("FeatureEngineering")
    .config("spark.sql.session.timeZone", "America/New_York")
    .config("spark.sql.files.ignoreCorruptFiles", "true")
    .config("spark.sql.parquet.mergeSchema", "false")
    .config("spark.sql.adaptive.enabled", "true")
    .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
    .config("spark.sql.adaptive.skewJoin.enabled", "true")
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

print("[STEP 1] Reading clustered panel...")
panel = spark.read.parquet(PANEL_PATH)
panel.printSchema()
print(f"  Total rows : {panel.count():,}")

panel = (
    panel
    .filter(F.col("pickup_bin_30m").isNotNull() & F.col("PULocationID").isNotNull())
    .withColumn("pickup_demand", F.coalesce(F.col("pickup_demand"), F.lit(0)).cast("double"))
    .withColumn("cluster_id",    F.coalesce(F.col("cluster_id"),    F.lit(MISSING_CLUSTER)).cast("int"))
    .withColumn("ready",         F.coalesce(F.col("ready"),         F.lit(0)).cast("int"))
)

if "year" not in panel.columns:
    panel = panel.withColumn("year",         F.year("pickup_bin_30m").cast("int"))
if "month" not in panel.columns:
    panel = panel.withColumn("month",        F.month("pickup_bin_30m").cast("int"))
if "day_of_month" not in panel.columns:
    panel = panel.withColumn("day_of_month", F.dayofmonth("pickup_bin_30m").cast("int"))
if "week_of_year" not in panel.columns:
    panel = panel.withColumn("week_of_year", F.weekofyear("pickup_bin_30m").cast("int"))
if "is_weekday" not in panel.columns:
    panel = panel.withColumn("is_weekday", (F.col("day_of_week") < 5).cast("int"))
if "is_weekend" not in panel.columns:
    panel = panel.withColumn("is_weekend", (F.col("day_of_week") >= 5).cast("int"))

if "slot_in_week" not in panel.columns:
    panel = panel.withColumn(
        "slot_in_week",
        (F.col("day_of_week") * BINS_PER_DAY + F.col("hour") * 2 + (F.col("minute") / 30).cast("int")).cast("int")
    )

panel = panel.persist()
print(f"  Panel persisted with {len(panel.columns)} columns")

print("[STEP 2] Computing cluster-level temporal features...")

w_cluster     = Window.partitionBy("cluster_id").orderBy("pickup_bin_30m")
w_cluster_24h = w_cluster.rowsBetween(-BINS_PER_DAY, -1)

# Pickup demand average in each cluster and bin
cluster_ts = (
    panel
    .filter(F.col("cluster_id") != MISSING_CLUSTER)
    .groupBy("cluster_id", "pickup_bin_30m")
    .agg(F.avg("pickup_demand").alias("cluster_avg_demand_t"))
)

# Pickup demand lag 1-5 in each cluster and bin
for i in range(1, 6):
    cluster_ts = cluster_ts.withColumn(
        f"cluster_demand_t_{i}",
        F.lag("cluster_avg_demand_t", i).over(w_cluster)
    )

cluster_ts = (
    cluster_ts
    .withColumn("cluster_rolling_mean_24h", F.avg("cluster_avg_demand_t").over(w_cluster_24h))
    .withColumn("cluster_rolling_max_24h",  F.max("cluster_avg_demand_t").over(w_cluster_24h))
    .withColumn("cluster_rolling_min_24h",  F.min("cluster_avg_demand_t").over(w_cluster_24h))
    .withColumn("cluster_rolling_std_24h",  F.stddev("cluster_avg_demand_t").over(w_cluster_24h))
    .withColumn("cluster_rolling_obs_24h",  F.count("cluster_avg_demand_t").over(w_cluster_24h))
)

panel = panel.join(
    F.broadcast(cluster_ts),
    on=["cluster_id", "pickup_bin_30m"],
    how="left"
)

cluster_fill = {
    **{f"cluster_demand_t_{i}": 0.0 for i in range(1, 6)},
    "cluster_avg_demand_t":    0.0,
    "cluster_rolling_mean_24h": 0.0,
    "cluster_rolling_max_24h":  0.0,
    "cluster_rolling_min_24h":  0.0,
    "cluster_rolling_std_24h":  0.0,
    "cluster_rolling_obs_24h":  0,
}
panel = panel.fillna(cluster_fill)

# Calculate the difference between zone's demand and cluster's demand
panel = (
    panel
    # 30 minutes demand difference between zone's demand and cluster's demand
    .withColumn(
        "cluster_diff_t1",
        (F.coalesce(F.col("demand_t_1"), F.lit(0.0)) - F.col("cluster_demand_t_1")).cast("double")
    )
    # Last 24 hours average demand difference between zone's demand and cluster's demand
    .withColumn(
        "cluster_mean_diff_24h",
        (F.coalesce(F.col("rolling_mean_24h"), F.lit(0.0)) - F.col("cluster_rolling_mean_24h")).cast("double")
    )
    # Whether the cluster_id and cluster_demand_t_1 are valid
    .withColumn(
        "has_valid_cluster_feature",
        ((F.col("cluster_id") != MISSING_CLUSTER) & F.col("cluster_demand_t_1").isNotNull()).cast("int")
    )
)

print("[STEP 3] Computing intra/inter cluster similarity...")
train_df = panel.filter(
    (F.col("dataset_split") == "train") &
    (F.col("cluster_id") != MISSING_CLUSTER)
)

w_loc = Window.partitionBy("PULocationID")
loc_z = (
    train_df
    .withColumn("loc_mean", F.avg("pickup_demand").over(w_loc))
    .withColumn("loc_std",  F.stddev("pickup_demand").over(w_loc))
    .withColumn(
        "loc_z",
        (F.col("pickup_demand") - F.col("loc_mean")) /
        F.when(F.col("loc_std") >= 1e-12, F.col("loc_std")).otherwise(F.lit(1.0))
    )
    .select("PULocationID", "cluster_id", "pickup_bin_30m", "loc_z")
)

cluster_rep = loc_z.groupBy("cluster_id", "pickup_bin_30m").agg(
    F.avg("loc_z").alias("avg_loc_z")
)
w_cid = Window.partitionBy("cluster_id")
rep_z = (
    cluster_rep
    .withColumn("rep_mean", F.avg("avg_loc_z").over(w_cid))
    .withColumn("rep_std",  F.stddev("avg_loc_z").over(w_cid))
    .withColumn(
        "rep_z",
        (F.col("avg_loc_z") - F.col("rep_mean")) /
        F.when(F.col("rep_std") >= 1e-12, F.col("rep_std")).otherwise(F.lit(1.0))
    )
    .select(F.col("cluster_id").alias("target_cluster_id"), "pickup_bin_30m", "rep_z")
)

# Compute the similarity between zone's demand and cluster's demand: Pearson correlation [-1, 1]
sim_df = (
    loc_z.join(rep_z, on="pickup_bin_30m")
    .withColumn("sim_product", F.col("loc_z") * F.col("rep_z"))
    .groupBy("PULocationID", "cluster_id", "target_cluster_id")
    .agg(F.avg("sim_product").alias("similarity"))
)

# Intra-cluster similarity: similarity between zone's demand and cluster's demand in the same cluster
intra_sim = (
    sim_df.filter(F.col("cluster_id") == F.col("target_cluster_id"))
    .select("PULocationID", F.col("similarity").alias("intra_cluster_similarity"))
)
# Inter-cluster similarity: similarity between zone's demand and cluster's demand in different clusters
inter_sim = (
    sim_df.filter(F.col("cluster_id") != F.col("target_cluster_id"))
    .groupBy("PULocationID")
    .agg(F.max("similarity").alias("inter_cluster_similarity"))
)

sims = intra_sim.join(inter_sim, on="PULocationID", how="outer")
panel = (
    panel.join(F.broadcast(sims), on="PULocationID", how="left")
    .fillna({"intra_cluster_similarity": 0.0, "inter_cluster_similarity": 0.0})
)

print("[STEP 4] Selecting output columns and writing to HDFS...")

OUTPUT_COLS_ORDERED = [
    "pickup_bin_30m", "dataset_split", "PULocationID",
    "pickup_demand",
    "hour", "minute", "day_of_week", "day_of_month",
    "week_of_year", "month", "year",
    "is_weekday", "is_weekend",
    "slot_in_week",
    "demand_t_1",
    "rolling_mean_24h",
    "ewma_output",
    "cluster_id",
    "cluster_avg_demand_t",
    "cluster_demand_t_1", "cluster_demand_t_2", "cluster_demand_t_3",
    "cluster_demand_t_4", "cluster_demand_t_5",
    "cluster_rolling_mean_24h", "cluster_rolling_max_24h",
    "cluster_rolling_min_24h",  "cluster_rolling_std_24h",
    "cluster_rolling_obs_24h",
    "cluster_diff_t1", "cluster_mean_diff_24h",
    "intra_cluster_similarity", "inter_cluster_similarity",
    "has_valid_cluster_feature", "ready",
]

existing_cols = [c for c in OUTPUT_COLS_ORDERED if c in panel.columns]
out = panel.select(*existing_cols)

print(f"  Output columns ({len(existing_cols)}): {existing_cols}")

out.write.mode("overwrite").partitionBy("dataset_split").parquet(OUTPUT_PATH)

print("=" * 80)
print("FEATURE ENGINEERING DONE")
print("=" * 80)
print(f"  input        : {PANEL_PATH}")
print(f"  output       : {OUTPUT_PATH}")
print(f"  n_columns    : {len(existing_cols)}")
print(f"  columns      : {existing_cols}")

try:
    panel.unpersist()
except Exception:
    pass

try:
    del panel, out, cluster_ts, loc_z, cluster_rep, rep_z, sim_df, intra_sim, inter_sim, sims, train_df
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
