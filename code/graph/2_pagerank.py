"""
BƯỚC 2: TÍNH PAGERANK CHO CÁC TAXI ZONES
Sử dụng GraphFrames PageRank algorithm

Input: Edge list từ HDFS (output của bước 1)
Output: PageRank scores cho mỗi zone
"""

import sys
import os

# Thêm parent directory vào Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, desc, count, sum as _sum, avg

# Import từ config
from config.spark_config import (
    create_spark_session,
    HDFS_GRAPH_DATA,
    HDFS_RESULTS,
    PAGERANK_ITERATIONS,
    DAMPING_FACTOR
)

# Import utils
try:
    from utils import timer, print_section, print_dataframe_stats
except ImportError:
    from src.utils import timer, print_section, print_dataframe_stats


@timer
def load_edge_list(spark):
    """
    Load edge list từ HDFS
    
    Returns:
        Spark DataFrame với columns: src, dst, trip_count
    """
    print_section("LOAD EDGE LIST TỪ HDFS")
    
    edge_path = f"{HDFS_GRAPH_DATA}edge_list"
    print(f"📂 Đọc dữ liệu từ: {edge_path}")
    
    try:
        edges = spark.read.parquet(edge_path)
        print("✅ Đã load edge list thành công!")
        print_dataframe_stats(edges, "Edge List")
        
        # Show sample
        print("\n📄 Sample edges:")
        edges.show(10)
        
        return edges
        
    except Exception as e:
        print(f"❌ Lỗi khi load edge list: {str(e)}")
        print("\n💡 Gợi ý:")
        print("   - Đảm bảo đã chạy 1_build_graph.py trước")
        print(f"   - Kiểm tra path tồn tại: hdfs dfs -ls {edge_path}")
        raise


@timer
def create_graphframe(spark, edges):
    """
    Tạo GraphFrame từ edge list
    
    Args:
        spark: SparkSession
        edges: Edge DataFrame
        
    Returns:
        GraphFrame object
    """
    print_section("TẠO GRAPHFRAME")
    
    try:
        from graphframes import GraphFrame
    except ImportError:
        print("❌ GraphFrames chưa được cài đặt!")
        print("💡 Chạy: pip install graphframes")
        print("   Hoặc dùng --packages trong spark-submit")
        raise
    
    print("🔨 Tạo vertices từ edges...")
    
    # Tạo vertices (unique zones)
    src_vertices = edges.select(col("src").alias("id")).distinct()
    dst_vertices = edges.select(col("dst").alias("id")).distinct()
    vertices = src_vertices.union(dst_vertices).distinct()
    
    num_vertices = vertices.count()
    print(f"   - Số vertices (zones): {num_vertices:,}")
    
    # Chuẩn bị edges cho GraphFrame
    gf_edges = edges.select(
        col("src"),
        col("dst"),
        col("trip_count").alias("weight")
    )
    
    num_edges = gf_edges.count()
    print(f"   - Số edges: {num_edges:,}")
    
    # Tạo GraphFrame
    print("\n🔨 Tạo GraphFrame...")
    graph = GraphFrame(vertices, gf_edges)
    
    print("✅ GraphFrame đã được tạo thành công!")
    
    return graph


@timer
def run_pagerank(graph, iterations=20, reset_prob=0.15):
    """
    Chạy PageRank algorithm
    
    Args:
        graph: GraphFrame
        iterations: Số iterations (mặc định 20)
        reset_prob: Reset probability (1 - damping factor)
        
    Returns:
        DataFrame với PageRank scores
    """
    print_section("CHẠY PAGERANK ALGORITHM")
    
    print(f"⚙️  Cấu hình:")
    print(f"   - Số iterations: {iterations}")
    print(f"   - Damping factor: {1 - reset_prob:.2f}")
    print(f"   - Reset probability: {reset_prob:.2f}")
    
    print("\n🚀 Bắt đầu tính PageRank...")
    print("   (Quá trình này có thể mất 20-60 phút)")
    
    try:
        # Chạy PageRank
        results = graph.pageRank(
            resetProbability=reset_prob,
            maxIter=iterations
        )
        
        # Lấy vertices với PageRank scores
        pagerank_df = results.vertices.select(
            col("id").alias("zone_id"),
            col("pagerank")
        )
        
        # Cache kết quả
        pagerank_df.cache()
        
        # Statistics
        total_zones = pagerank_df.count()
        total_pr = pagerank_df.agg(_sum("pagerank")).collect()[0][0]
        avg_pr = total_pr / total_zones if total_zones > 0 else 0
        
        print("\n✅ PageRank hoàn thành!")
        print(f"\n📊 Thống kê:")
        print(f"   - Tổng số zones: {total_zones:,}")
        print(f"   - Tổng PageRank: {total_pr:.4f}")
        print(f"   - Trung bình PageRank: {avg_pr:.6f}")
        
        return pagerank_df
        
    except Exception as e:
        print(f"\n❌ Lỗi khi chạy PageRank: {str(e)}")
        raise


@timer
def analyze_pagerank_results(pagerank_df):
    """
    Phân tích kết quả PageRank
    
    Args:
        pagerank_df: DataFrame với PageRank scores
    """
    print_section("PHÂN TÍCH KẾT QUẢ PAGERANK")
    
    # Sort by PageRank descending
    ranked = pagerank_df.orderBy(desc("pagerank"))
    
    # Top 20 zones
    print("🏆 TOP 20 ZONES QUAN TRỌNG NHẤT:")
    print("-" * 50)
    top20 = ranked.limit(20)
    top20.show(20, truncate=False)
    
    # Distribution analysis
    print("\n📊 Phân phối PageRank:")
    pagerank_df.describe("pagerank").show()
    
    # Concentration analysis
    total_pr = pagerank_df.agg(_sum("pagerank")).collect()[0][0]
    
    top10_pr = ranked.limit(10).agg(_sum("pagerank")).collect()[0][0]
    top10_pct = (top10_pr / total_pr) * 100
    
    top20_pr = ranked.limit(20).agg(_sum("pagerank")).collect()[0][0]
    top20_pct = (top20_pr / total_pr) * 100
    
    top50_pr = ranked.limit(50).agg(_sum("pagerank")).collect()[0][0]
    top50_pct = (top50_pr / total_pr) * 100
    
    print(f"\n📈 Phân tích concentration:")
    print(f"   - Top 10 zones: {top10_pct:.2f}% total PageRank")
    print(f"   - Top 20 zones: {top20_pct:.2f}% total PageRank")
    print(f"   - Top 50 zones: {top50_pct:.2f}% total PageRank")
    
    # Power-law check
    if top10_pct > 40:
        print("\n💡 Phân phối PageRank có đặc điểm POWER-LAW")
        print("   → Một số zones rất quan trọng, phần lớn zones ít quan trọng hơn")


@timer
def save_pagerank_results(pagerank_df, output_path):
    """
    Lưu kết quả PageRank vào HDFS
    
    Args:
        pagerank_df: DataFrame với PageRank scores
        output_path: HDFS output path
    """
    print_section("LƯU KẾT QUẢ PAGERANK")
    
    print(f"💾 Lưu Parquet vào: {output_path}")
    
    # Save as Parquet
    pagerank_df.write \
        .mode("overwrite") \
        .parquet(output_path)
    
    print("✅ Đã lưu Parquet format")
    
    # Also save CSV of top 100
    csv_path = output_path.replace("/results/", "/results_csv/")
    print(f"\n💾 Lưu CSV top 100 vào: {csv_path}")
    
    pagerank_df.orderBy(desc("pagerank")) \
        .limit(100) \
        .coalesce(1) \
        .write \
        .mode("overwrite") \
        .option("header", "true") \
        .csv(csv_path)
    
    print("✅ Đã lưu CSV format")


def main():
    """Main execution"""
    
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║                                                                ║
    ║        NYC TAXI GRAPH MINING - BƯỚC 2: PAGERANK               ║
    ║                                                                ║
    ║  Mục tiêu: Tính PageRank cho các taxi zones                  ║
    ║  Thuật toán: GraphFrames PageRank (iterative)                ║
    ║                                                                ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    
    # Create Spark session
    spark = create_spark_session("NYC_Taxi_PageRank")
    
    try:
        # Step 1: Load edge list
        edges = load_edge_list(spark)
        
        # Step 2: Create GraphFrame
        graph = create_graphframe(spark, edges)
        
        # Step 3: Run PageRank
        pagerank_df = run_pagerank(
            graph, 
            iterations=PAGERANK_ITERATIONS,
            reset_prob=1 - DAMPING_FACTOR
        )
        
        # Step 4: Analyze results
        analyze_pagerank_results(pagerank_df)
        
        # Step 5: Save results
        output_path = f"{HDFS_RESULTS}pagerank_scores"
        save_pagerank_results(pagerank_df, output_path)
        
        print("\n" + "="*70)
        print("🎉 HOÀN THÀNH BƯỚC 2: PAGERANK")
        print("="*70)
        print(f"\n📂 Kết quả đã được lưu tại: {output_path}")
        print("\n📌 Next steps:")
        print("   1. Chạy 3_clustering.py để phát hiện communities")
        print("   2. Chạy 4_visualization.py để visualize kết quả")
        
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
