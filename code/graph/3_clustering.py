"""
BƯỚC 3: GRAPH CLUSTERING - COMMUNITY DETECTION
Sử dụng Label Propagation Algorithm để phát hiện communities

Input: Edge list và PageRank scores từ HDFS
Output: Community assignments cho mỗi zone
"""

import sys
import os

# Thêm parent directory vào Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, count, sum as _sum, avg, desc

# Import từ config
from config.spark_config import (
    create_spark_session,
    HDFS_GRAPH_DATA,
    HDFS_RESULTS
)

# Import utils
try:
    from utils import timer, print_section, print_dataframe_stats
except ImportError:
    from src.utils import timer, print_section, print_dataframe_stats


@timer
def load_graph_data(spark):
    """
    Load edge list và PageRank scores từ HDFS
    
    Returns:
        tuple: (edges DataFrame, pagerank DataFrame)
    """
    print_section("LOAD GRAPH DATA TỪ HDFS")
    
    # Load edge list
    edge_path = f"{HDFS_GRAPH_DATA}edge_list"
    print(f"📂 Đọc edge list từ: {edge_path}")
    edges = spark.read.parquet(edge_path)
    print("✅ Đã load edge list")
    print_dataframe_stats(edges, "Edge List")
    
    # Load PageRank scores
    pr_path = f"{HDFS_RESULTS}pagerank_scores"
    print(f"\n📂 Đọc PageRank scores từ: {pr_path}")
    pagerank = spark.read.parquet(pr_path)
    print("✅ Đã load PageRank scores")
    print_dataframe_stats(pagerank, "PageRank Scores")
    
    return edges, pagerank


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
    print_section("TẠO GRAPHFRAME CHO CLUSTERING")
    
    try:
        from graphframes import GraphFrame
    except ImportError:
        print("❌ GraphFrames chưa được cài đặt!")
        raise
    
    # Tạo vertices (unique zones)
    print("🔨 Tạo vertices...")
    src_vertices = edges.select(col("src").alias("id")).distinct()
    dst_vertices = edges.select(col("dst").alias("id")).distinct()
    vertices = src_vertices.union(dst_vertices).distinct()
    
    num_vertices = vertices.count()
    print(f"   - Số vertices: {num_vertices:,}")
    
    # Prepare edges
    gf_edges = edges.select(
        col("src"),
        col("dst"),
        col("trip_count").alias("weight")
    )
    
    num_edges = gf_edges.count()
    print(f"   - Số edges: {num_edges:,}")
    
    # Create GraphFrame
    print("\n🔨 Tạo GraphFrame...")
    graph = GraphFrame(vertices, gf_edges)
    
    print("✅ GraphFrame đã được tạo!")
    
    return graph


@timer
def run_label_propagation(graph, max_iterations=10):
    """
    Chạy Label Propagation Algorithm để phát hiện communities
    
    Args:
        graph: GraphFrame
        max_iterations: Số iterations tối đa
        
    Returns:
        DataFrame với community assignments
    """
    print_section("CHẠY LABEL PROPAGATION ALGORITHM")
    
    print(f"⚙️  Cấu hình:")
    print(f"   - Max iterations: {max_iterations}")
    
    print("\n🚀 Bắt đầu Label Propagation...")
    print("   (Quá trình này có thể mất 20-40 phút)")
    
    try:
        # Run Label Propagation
        result = graph.labelPropagation(maxIter=max_iterations)
        
        # Get community assignments
        communities = result.select(
            col("id").alias("zone_id"),
            col("label").alias("community_id")
        )
        
        # Cache result
        communities.cache()
        
        print("\n✅ Label Propagation hoàn thành!")
        
        return communities
        
    except Exception as e:
        print(f"\n❌ Lỗi khi chạy Label Propagation: {str(e)}")
        raise


@timer
def analyze_communities(communities, pagerank_df):
    """
    Phân tích communities được phát hiện
    
    Args:
        communities: DataFrame với community assignments
        pagerank_df: DataFrame với PageRank scores
    """
    print_section("PHÂN TÍCH COMMUNITIES")
    
    # Join với PageRank scores
    comm_with_pr = communities.join(
        pagerank_df,
        communities.zone_id == pagerank_df.zone_id,
        "inner"
    ).select(
        communities.zone_id,
        communities.community_id,
        pagerank_df.pagerank
    )
    
    # Community statistics
    print("📊 Thống kê communities:")
    
    comm_stats = comm_with_pr.groupBy("community_id").agg(
        count("zone_id").alias("num_zones"),
        _sum("pagerank").alias("total_pagerank"),
        avg("pagerank").alias("avg_pagerank")
    ).orderBy(desc("num_zones"))
    
    total_communities = comm_stats.count()
    print(f"   - Tổng số communities: {total_communities:,}")
    
    # Cache stats
    comm_stats.cache()
    
    # Show top communities by size
    print("\n🔝 TOP 20 COMMUNITIES (theo số zones):")
    print("-" * 70)
    comm_stats.show(20, truncate=False)
    
    # Distribution analysis
    print("\n📈 Phân phối community size:")
    comm_stats.describe("num_zones").show()
    
    # Largest and smallest communities
    largest = comm_stats.first()
    smallest = comm_stats.orderBy("num_zones").first()
    
    print(f"\n📌 Community lớn nhất:")
    print(f"   - ID: {largest['community_id']}")
    print(f"   - Số zones: {largest['num_zones']}")
    print(f"   - Total PageRank: {largest['total_pagerank']:.4f}")
    
    print(f"\n📌 Community nhỏ nhất:")
    print(f"   - ID: {smallest['community_id']}")
    print(f"   - Số zones: {smallest['num_zones']}")
    print(f"   - Total PageRank: {smallest['total_pagerank']:.4f}")
    
    # PageRank concentration in top communities
    total_pr = comm_stats.agg(_sum("total_pagerank")).collect()[0][0]
    
    top5_pr = comm_stats.limit(5).agg(_sum("total_pagerank")).collect()[0][0]
    top5_pct = (top5_pr / total_pr) * 100
    
    top10_pr = comm_stats.limit(10).agg(_sum("total_pagerank")).collect()[0][0]
    top10_pct = (top10_pr / total_pr) * 100
    
    print(f"\n📊 PageRank concentration:")
    print(f"   - Top 5 communities: {top5_pct:.2f}% total PageRank")
    print(f"   - Top 10 communities: {top10_pct:.2f}% total PageRank")
    
    return comm_stats


@timer
def analyze_community_connectivity(communities, edges):
    """
    Phân tích connectivity trong và giữa các communities
    
    Args:
        communities: DataFrame với community assignments
        edges: Edge DataFrame
    """
    print_section("PHÂN TÍCH CONNECTIVITY")
    
    # Join edges với community info
    edges_with_comm = edges.alias("e") \
        .join(communities.alias("c1"), col("e.src") == col("c1.zone_id")) \
        .join(communities.alias("c2"), col("e.dst") == col("c2.zone_id")) \
        .select(
            col("e.src"),
            col("e.dst"),
            col("e.trip_count"),
            col("c1.community_id").alias("src_community"),
            col("c2.community_id").alias("dst_community")
        )
    
    # Intra-community vs inter-community edges
    total_trips_result = edges_with_comm.agg(_sum("trip_count")).collect()[0][0]
    
    # Handle None case (no data)
    if total_trips_result is None:
        print("⚠️  Không có dữ liệu trips để phân tích connectivity")
        return
    
    total_trips = total_trips_result
    
    intra_comm = edges_with_comm.filter(
        col("src_community") == col("dst_community")
    )
    intra_trips_result = intra_comm.agg(_sum("trip_count")).collect()[0][0]
    intra_trips = intra_trips_result if intra_trips_result is not None else 0
    intra_pct = (intra_trips / total_trips) * 100 if total_trips > 0 else 0
    
    inter_comm = edges_with_comm.filter(
        col("src_community") != col("dst_community")
    )
    inter_trips_result = inter_comm.agg(_sum("trip_count")).collect()[0][0]
    inter_trips = inter_trips_result if inter_trips_result is not None else 0
    inter_pct = (inter_trips / total_trips) * 100 if total_trips > 0 else 0
    
    print(f"🔗 Edge connectivity:")
    print(f"   - Intra-community trips: {intra_trips:,} ({intra_pct:.2f}%)")
    print(f"   - Inter-community trips: {inter_trips:,} ({inter_pct:.2f}%)")
    
    if intra_pct > 50:
        print("\n💡 Communities có tính chất strong intra-connectivity")
        print("   → Zones trong cùng community có traffic nội bộ cao")
    elif inter_pct > 50:
        print("\n💡 Communities có tính chất weak intra-connectivity")
        print("   → Traffic giữa các communities cao hơn traffic nội bộ")
    else:
        print("\n💡 Communities có connectivity cân bằng")


@timer
def save_results(communities, comm_stats, output_path):
    """
    Lưu kết quả clustering vào HDFS
    
    Args:
        communities: DataFrame với community assignments
        comm_stats: DataFrame với community statistics
        output_path: HDFS output path
    """
    print_section("LƯU KẾT QUẢ CLUSTERING")
    
    # Save community assignments (Parquet)
    assign_path = f"{output_path}/community_assignments"
    print(f"💾 Lưu assignments vào: {assign_path}")
    
    communities.write \
        .mode("overwrite") \
        .parquet(assign_path)
    
    print("✅ Đã lưu community assignments (Parquet)")
    
    # Save community statistics (Parquet)
    stats_path = f"{output_path}/community_statistics"
    print(f"\n💾 Lưu statistics vào: {stats_path}")
    
    comm_stats.write \
        .mode("overwrite") \
        .parquet(stats_path)
    
    print("✅ Đã lưu community statistics (Parquet)")
    
    # Also save CSV for inspection
    csv_path = f"{output_path}/community_assignments_csv"
    print(f"\n💾 Lưu CSV vào: {csv_path}")
    
    communities.coalesce(1).write \
        .mode("overwrite") \
        .option("header", "true") \
        .csv(csv_path)
    
    print("✅ Đã lưu CSV format")


def main():
    """Main execution"""
    
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║                                                                ║
    ║      NYC TAXI GRAPH MINING - BƯỚC 3: GRAPH CLUSTERING         ║
    ║                                                                ║
    ║  Mục tiêu: Phát hiện communities trong đồ thị giao thông     ║
    ║  Thuật toán: Label Propagation                                ║
    ║                                                                ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    
    # Create Spark session
    spark = create_spark_session("NYC_Taxi_Clustering")
    
    try:
        # Step 1: Load data
        edges, pagerank_df = load_graph_data(spark)
        
        # Step 2: Create GraphFrame
        graph = create_graphframe(spark, edges)
        
        # Step 3: Run Label Propagation
        communities = run_label_propagation(graph, max_iterations=10)
        
        # Step 4: Analyze communities
        comm_stats = analyze_communities(communities, pagerank_df)
        
        # Step 5: Analyze connectivity
        analyze_community_connectivity(communities, edges)
        
        # Step 6: Save results
        output_path = f"{HDFS_RESULTS}clustering"
        save_results(communities, comm_stats, output_path)
        
        print("\n" + "="*70)
        print("🎉 HOÀN THÀNH BƯỚC 3: GRAPH CLUSTERING")
        print("="*70)
        print(f"\n📂 Kết quả đã được lưu tại: {output_path}")
        print("\n📌 Next steps:")
        print("   1. Chạy 4_visualization.py để visualize kết quả")
        print("   2. Chạy 5_benchmark.py để đo scalability")
        
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
