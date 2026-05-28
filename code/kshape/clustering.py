import gc
import warnings
import numpy as np
from tslearn.clustering import KShape
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T

warnings.filterwarnings("ignore")

# ─── Đường dẫn I/O ────────────────────────────────────────────────────────────
# Input : weekly profile (zone × slot_in_week, normalized_demand)
#         từ output của preclustering.py
PRECLUSTERING_PATH  = "/user/kshape/preclustering"
# Input : full panel từ preprocess.py để gán nhãn cluster vào toàn bộ splits
FULL_PANEL_PATH     = "/user/kshape/preprocess"
# Output: full panel đã được gắn thêm cột cluster_id
OUTPUT_PATH         = "/user/kshape/clustering"

# ─── Tham số K-Shape ──────────────────────────────────────────────────────────
N_CLUSTERS   = 8   # số cụm — có thể tinh chỉnh dựa trên silhouette/elbow
RANDOM_STATE = 42
N_INIT       = 3   # số lần khởi tạo ngẫu nhiên (lấy kết quả inertia tốt nhất)
BINS_PER_WEEK = 336  # 7 ngày × 48 bins/ngày (30min/bin)

# ─── SparkSession ─────────────────────────────────────────────────────────────
spark = (
    SparkSession.builder
    .appName("KShapeClustering")
    .config("spark.sql.session.timeZone", "America/New_York")
    .config("spark.sql.files.ignoreCorruptFiles", "true")
    .config("spark.sql.parquet.mergeSchema", "false")
    .config("spark.sql.adaptive.enabled", "true")
    .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
    .config("spark.sql.adaptive.skewJoin.enabled", "true")
    # Tắt vectorized reader – đồng bộ với toàn pipeline
    .config("spark.sql.parquet.enableVectorizedReader", "false")
    # Tăng giới hạn collect về driver cho ma trận 257 × 336 (~0.7 MB)
    .config("spark.driver.maxResultSize", "1g")
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

# ─── Bước 1: Đọc weekly profile từ preclustering ─────────────────────────────
# Schema: PULocationID (long), slot_in_week (int), avg_demand (double),
#         zone_mean (double), zone_std (double), normalized_demand (double)
print("[STEP 1] Reading preclustering weekly profiles...")
profile_df = spark.read.parquet(PRECLUSTERING_PATH)
profile_df.printSchema()

n_locations = profile_df.select("PULocationID").distinct().count()
n_slots     = profile_df.select("slot_in_week").distinct().count()
print(f"  n_locations : {n_locations}")
print(f"  n_slots     : {n_slots}  (expected {BINS_PER_WEEK})")

if n_locations == 0:
    raise ValueError("Không có zone nào trong preclustering output!")
if n_slots != BINS_PER_WEEK:
    print(f"[WARN] n_slots={n_slots} != BINS_PER_WEEK={BINS_PER_WEEK}. Kiểm tra lại preclustering!")
if n_locations < N_CLUSTERS:
    raise ValueError(f"Số zone ({n_locations}) nhỏ hơn N_CLUSTERS={N_CLUSTERS}!")

# ─── Bước 2: Pivot về ma trận [n_zones, 336] trên driver ─────────────────────
# Ma trận rất nhỏ: 257 × 336 × 8 bytes ≈ 0.7 MB → an toàn để collect về driver.
# Thu thập theo thứ tự (PULocationID, slot_in_week) để đảm bảo thứ tự cột ổn định.
print("[STEP 2] Building clustering matrix on driver...")
rows = (
    profile_df
    .select("PULocationID", "slot_in_week", "normalized_demand")
    .orderBy("PULocationID", "slot_in_week")
    .collect()
)

# Nhóm theo zone
from collections import defaultdict
zone_data = defaultdict(lambda: np.zeros(BINS_PER_WEEK, dtype=np.float64))
for r in rows:
    zone_data[int(r["PULocationID"])][int(r["slot_in_week"])] = float(r["normalized_demand"] or 0.0)

loc_ids = sorted(zone_data.keys())
X_raw   = np.stack([zone_data[loc] for loc in loc_ids])  # shape: [n_zones, 336]

# K-Shape của tslearn yêu cầu shape [n_samples, seq_len, 1]
X_kshape = X_raw[:, :, np.newaxis]

matrix_cells = X_raw.shape[0] * X_raw.shape[1]
work_gb = (X_raw.shape[1] ** 2 * 8) / (1024 ** 3)
print(f"  Matrix shape    : {X_raw.shape}")
print(f"  Matrix cells    : {matrix_cells:,}")
print(f"  KShape work est : {work_gb:.4f} GB")

# ─── Bước 3: Chạy K-Shape ────────────────────────────────────────────────────
print(f"[STEP 3] Running K-Shape (k={N_CLUSTERS}, n_init={N_INIT}, seed={RANDOM_STATE})...")
model = KShape(
    n_clusters=N_CLUSTERS,
    random_state=RANDOM_STATE,
    n_init=N_INIT,
    verbose=False,
)
labels  = model.fit_predict(X_kshape).astype(int)   # shape: [n_zones]
centers = np.asarray(model.cluster_centers_).squeeze(-1)  # shape: [k, 336]

# In phân phối cluster
unique_ids, counts = np.unique(labels, return_counts=True)
print("  Cluster distribution:")
for cid, cnt in zip(unique_ids, counts):
    pct = cnt / len(labels) * 100
    print(f"    cluster {cid:2d} : {cnt:3d} zones ({pct:.1f}%)")

# ─── Bước 4: Lưu centroid ra HDFS dạng parquet ───────────────────────────────
# Mỗi hàng: cluster_id, slot_in_week, centroid_value
print("[STEP 4] Saving cluster centroids to HDFS...")
centroid_rows = [
    (int(cid), int(slot), float(centers[cid, slot]))
    for cid in range(N_CLUSTERS)
    for slot in range(BINS_PER_WEEK)
]
centroid_schema = T.StructType([
    T.StructField("cluster_id",      T.IntegerType(), False),
    T.StructField("slot_in_week",    T.IntegerType(), False),
    T.StructField("centroid_value",  T.DoubleType(),  False),
])
centroid_df = spark.createDataFrame(centroid_rows, centroid_schema)
centroid_df.write.mode("overwrite").parquet(OUTPUT_PATH + "/centroids")
print(f"  Centroids exported: {OUTPUT_PATH}/centroids")

# ─── Bước 5: Gán nhãn cluster vào full panel ─────────────────────────────────
# assignments: (PULocationID, cluster_id) cho tất cả zones
print("[STEP 5] Joining cluster labels to full panel...")
assignment_rows = [(int(loc), int(lbl)) for loc, lbl in zip(loc_ids, labels)]
assignment_schema = T.StructType([
    T.StructField("PULocationID", T.LongType(),    False),
    T.StructField("cluster_id",   T.IntegerType(), False),
])
assignments_df = spark.createDataFrame(assignment_rows, assignment_schema)

# Đọc full panel (toàn bộ splits: train / validation / test)
full_panel = spark.read.parquet(FULL_PANEL_PATH)

# Broadcast assignments vì bảng rất nhỏ (257 rows)
result = (
    full_panel
    .join(F.broadcast(assignments_df), on="PULocationID", how="left")
    .withColumn("cluster_id", F.col("cluster_id").cast("int"))
)

# Ghi ra HDFS, phân vùng theo dataset_split để tối ưu đọc downstream
result.write.mode("overwrite").partitionBy("dataset_split").parquet(OUTPUT_PATH + "/panel")
print(f"  Panel with cluster labels exported: {OUTPUT_PATH}/panel")

# ─── Bước 6: In metadata tổng kết ────────────────────────────────────────────
print("=" * 80)
print("K-SHAPE CLUSTERING DONE")
print("=" * 80)
print(f"  preclustering_path   : {PRECLUSTERING_PATH}")
print(f"  full_panel_path      : {FULL_PANEL_PATH}")
print(f"  output_centroids     : {OUTPUT_PATH}/centroids")
print(f"  output_panel         : {OUTPUT_PATH}/panel")
print(f"  n_clusters           : {N_CLUSTERS}")
print(f"  n_init               : {N_INIT}")
print(f"  random_state         : {RANDOM_STATE}")
print(f"  n_locations          : {len(loc_ids)}")
print(f"  bins_per_week        : {BINS_PER_WEEK}")
print(f"  matrix_shape         : {list(X_raw.shape)}")
print(f"  matrix_cells         : {matrix_cells:,}")
print(f"  estimated_work_gb    : {work_gb:.4f}")

# ─── Dọn dẹp tài nguyên ───────────────────────────────────────────────────────
try:
    del rows, zone_data, X_raw, X_kshape, centers, labels
    del profile_df, assignments_df, full_panel, result, centroid_df
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
