"""
BƯỚC 1: XÂY DỰNG EDGE LIST TỪ NYC TAXI DATA
Sử dụng Spark MapReduce để tạo đồ thị giao thông

Input: NYC TLC Yellow Taxi Parquet files (~30GB)
Output: Edge list với trọng số (số chuyến taxi giữa các zone)

Đây là bước MASSIVE - scan toàn bộ dữ liệu phân tán
"""

import sys
import os

# Thêm parent directory vào Python path để import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, count, sum as _sum, avg

# Import từ config directory
from config.spark_config import (
    create_spark_session, 
    HDFS_RAW_DATA, 
    HDFS_GRAPH_DATA,
    PICKUP_LOCATION,
    DROPOFF_LOCATION,
    FARE_AMOUNT,
    TIP_AMOUNT,
    TRIP_DISTANCE
)

# Import từ src directory
try:
    from utils import timer, print_section, print_dataframe_stats, save_dataframe_as_csv
except ImportError:
    # Nếu import trực tiếp không được, thử import từ src
    from src.utils import timer, print_section, print_dataframe_stats, save_dataframe_as_csv


@timer
def load_taxi_data(spark, sample_months=None):
    """
    Load dữ liệu taxi từ HDFS
    
    Args:
        spark: SparkSession
        sample_months: List các tháng để load (None = all)
        
    Returns:
        Spark DataFrame
    """
    print_section("LOAD DỮ LIỆU TỪ HDFS")
    
    try:
        # Load tất cả parquet files
        print(f"📂 Đọc dữ liệu từ: {HDFS_RAW_DATA}")
        df = spark.read.parquet(HDFS_RAW_DATA)
        
        print(f"✅ Đã load dữ liệu thành công!")
        print_dataframe_stats(df, "Raw Taxi Data")
        
        # Hiển thị schema
        print("\n📋 Schema:")
        df.printSchema()
        
        # Hiển thị sample
        print("\n📄 Sample data:")
        df.show(5)
        
        return df
        
    except Exception as e:
        print(f"❌ Lỗi khi load dữ liệu: {str(e)}")
        print("\n💡 Gợi ý:")
        print("   - Kiểm tra HDFS đã chạy: hdfs dfs -ls /")
        print("   - Kiểm tra path: hdfs dfs -ls /user/taxi/raw_data/")
        print("   - Đảm bảo đã upload dữ liệu vào HDFS")
        raise


@timer
def clean_and_filter_data(df):
    """
    Làm sạch và lọc dữ liệu
    
    Args:
        df: Raw DataFrame
        
    Returns:
        Cleaned DataFrame
    """
    print_section("LÀM SẠCH DỮ LIỆU")
    
    print("🧹 Áp dụng các filter:")
    print("   - Loại bỏ NULL location IDs")
    print("   - Loại bỏ location IDs không hợp lệ (< 1 hoặc > 263)")
    print("   - Loại bỏ self-loops (PU == DO)")
    print("   - Loại bỏ fare âm")
    
    # Original count
    original_count = df.count()
    print(f"\n📊 Số dòng ban đầu: {original_count:,}")
    
    # Cleaning pipeline
    cleaned_df = df.filter(
        (col(PICKUP_LOCATION).isNotNull()) &
        (col(DROPOFF_LOCATION).isNotNull()) &
        (col(PICKUP_LOCATION) >= 1) &
        (col(PICKUP_LOCATION) <= 263) &
        (col(DROPOFF_LOCATION) >= 1) &
        (col(DROPOFF_LOCATION) <= 263) &
        (col(PICKUP_LOCATION) != col(DROPOFF_LOCATION)) &
        (col(FARE_AMOUNT) >= 0)
    )
    
    # Cache vì sẽ dùng nhiều lần
    cleaned_df.cache()
    
    cleaned_count = cleaned_df.count()
    removed = original_count - cleaned_count
    removed_pct = (removed / original_count) * 100
    
    print(f"✅ Số dòng sau khi làm sạch: {cleaned_count:,}")
    print(f"🗑️  Đã loại bỏ: {removed:,} dòng ({removed_pct:.2f}%)")
    
    return cleaned_df


@timer
def build_edge_list(df):
    """
    Xây dựng edge list từ trip data
    MapReduce aggregation
    
    Args:
        df: Cleaned trip DataFrame
        
    Returns:
        Edge DataFrame với columns: src, dst, trip_count, total_fare, avg_fare, total_tip
    """
    print_section("XÂY DỰNG EDGE LIST (MapReduce)")
    
    print("🔨 Thực hiện aggregation:")
    print("   - Group by (PULocationID, DOLocationID)")
    print("   - Count số chuyến")
    print("   - Sum và avg các metrics")
    
    # MapReduce aggregation
    edge_list = df.groupBy(
        col(PICKUP_LOCATION).alias("src"),
        col(DROPOFF_LOCATION).alias("dst")
    ).agg(
        count("*").alias("trip_count"),
        _sum(FARE_AMOUNT).alias("total_fare"),
        avg(FARE_AMOUNT).alias("avg_fare"),
        _sum(TIP_AMOUNT).alias("total_tip"),
        avg(TRIP_DISTANCE).alias("avg_distance")
    )
    
    # Sort by trip count descending
    edge_list = edge_list.orderBy(col("trip_count").desc())
    
    # Cache result
    edge_list.cache()
    
    print_dataframe_stats(edge_list, "Edge List")
    
    # Show top edges
    print("\n🔝 Top 10 cạnh bận rộn nhất:")
    edge_list.show(10, truncate=False)
    
    # Statistics
    total_edges = edge_list.count()
    total_trips = edge_list.agg(_sum("trip_count")).collect()[0][0]
    avg_trips_per_edge = total_trips / total_edges
    
    print(f"\n📈 Thống kê đồ thị:")
    print(f"   - Tổng số edges: {total_edges:,}")
    print(f"   - Tổng số trips: {total_trips:,}")
    print(f"   - Trung bình trips/edge: {avg_trips_per_edge:.2f}")
    
    return edge_list


@timer
def analyze_graph_structure(edge_list):
    """
    Phân tích cấu trúc đồ thị cơ bản
    
    Args:
        edge_list: Edge DataFrame
    """
    print_section("PHÂN TÍCH CẤU TRÚC ĐỒ THỊ")
    
    # Unique nodes (zones)
    print("🔍 Đếm số nodes...")
    src_nodes = edge_list.select("src").distinct()
    dst_nodes = edge_list.select("dst").distinct()
    all_nodes = src_nodes.union(dst_nodes).distinct()
    num_nodes = all_nodes.count()
    
    print(f"   - Số nodes (zones): {num_nodes}")
    
    # Out-degree distribution
    print("\n📊 Out-degree distribution (số zone mà mỗi zone đi đến):")
    out_degree = edge_list.groupBy("src") \
        .agg(count("dst").alias("out_degree")) \
        .orderBy(col("out_degree").desc())
    
    out_degree.describe("out_degree").show()
    
    print("\n🔝 Top 10 zones có out-degree cao nhất:")
    out_degree.show(10)
    
    # In-degree distribution
    print("\n📊 In-degree distribution (số zone đi đến mỗi zone):")
    in_degree = edge_list.groupBy("dst") \
        .agg(count("src").alias("in_degree")) \
        .orderBy(col("in_degree").desc())
    
    in_degree.describe("in_degree").show()
    
    print("\n🔝 Top 10 zones có in-degree cao nhất:")
    in_degree.show(10)
    
    # Edge weight distribution
    print("\n📊 Edge weight (trip count) distribution:")
    edge_list.describe("trip_count").show()
    
    # Heavy edges
    print("\n⚖️  Phân tích heavy edges:")
    total_trips = edge_list.agg(_sum("trip_count")).collect()[0][0]
    
    heavy_edges = edge_list.filter(col("trip_count") >= 1000)
    heavy_trips = heavy_edges.agg(_sum("trip_count")).collect()[0][0]
    heavy_pct = (heavy_trips / total_trips) * 100
    
    print(f"   - Edges với ≥1000 trips: {heavy_edges.count():,}")
    print(f"   - % trips trong heavy edges: {heavy_pct:.2f}%")


@timer
def save_edge_list(edge_list, output_path):
    """
    Lưu edge list vào HDFS
    
    Args:
        edge_list: Edge DataFrame
        output_path: HDFS output path
    """
    print_section("LƯU EDGE LIST")
    
    print(f"💾 Lưu vào HDFS: {output_path}")
    
    # Save as Parquet (efficient for Spark)
    edge_list.write \
        .mode("overwrite") \
        .parquet(output_path)
    
    print(f"✅ Đã lưu edge list (Parquet format)")
    
    # Also save as CSV for inspection
    csv_path = output_path.replace("/graph/", "/graph_csv/")
    print(f"\n💾 Lưu CSV cho inspection: {csv_path}")
    
    edge_list.coalesce(1).write \
        .mode("overwrite") \
        .option("header", "true") \
        .csv(csv_path)
    
    print(f"✅ Đã lưu edge list (CSV format)")


def main():
    """Main execution"""
    
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║                                                                ║
    ║        NYC TAXI GRAPH MINING - BƯỚC 1: BUILD EDGE LIST        ║
    ║                                                                ║
    ║  Mục tiêu: Xây dựng đồ thị giao thông từ 30GB trip data      ║
    ║  Phương pháp: Spark MapReduce phân tán                        ║
    ║                                                                ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    
    # Create Spark session
    spark = create_spark_session("NYC_Taxi_Build_Graph")
    
    try:
        # Step 1: Load data
        raw_df = load_taxi_data(spark)
        
        # Step 2: Clean data
        cleaned_df = clean_and_filter_data(raw_df)
        
        # Step 3: Build edge list
        edge_list = build_edge_list(cleaned_df)
        
        # Step 4: Analyze graph
        analyze_graph_structure(edge_list)
        
        # Step 5: Save results
        output_path = f"{HDFS_GRAPH_DATA}edge_list"
        save_edge_list(edge_list, output_path)
        
        print("\n" + "="*70)
        print("🎉 HOÀN THÀNH BƯỚC 1: BUILD EDGE LIST")
        print("="*70)
        print(f"\n📂 Edge list đã được lưu tại: {output_path}")
        print("\n📌 Next steps:")
        print("   1. Chạy 2_pagerank.py để tính PageRank scores")
        print("   2. Chạy 3_clustering.py để phát hiện communities")
        print("   3. Chạy 4_visualization.py để visualize kết quả")
        
    except Exception as e:
        print(f"\n❌ LỖI: {str(e)}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Stop Spark
        spark.stop()
        print("\n🛑 Đã dừng Spark session")


if __name__ == "__main__":
    main()
