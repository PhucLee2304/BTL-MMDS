"""
BƯỚC 4: VISUALIZATION - TẠO CHARTS VÀ GRAPHS
Visualize kết quả PageRank và Clustering

Input: Kết quả từ HDFS (PageRank, Communities)
Output: Charts (PNG files) và summary reports (CSV)
"""

import sys
import os

# Thêm parent directory vào Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pyspark.sql import SparkSession

# Import từ config
from config.spark_config import (
    create_local_spark_session,
    HDFS_RESULTS,
    LOCAL_VISUALIZATIONS_DIR
)

# Import utils
try:
    from utils import timer, print_section
except ImportError:
    from src.utils import timer, print_section

# Set plot style
sns.set_theme(style="whitegrid")
plt.rcParams['figure.figsize'] = (12, 8)


@timer
def load_results(spark):
    """
    Load kết quả từ HDFS
    
    Returns:
        tuple: (pagerank_df, communities_df, comm_stats_df)
    """
    print_section("LOAD KẾT QUẢ TỪ HDFS")
    
    # Load PageRank
    pr_path = f"{HDFS_RESULTS}pagerank_scores"
    print(f"📂 Đọc PageRank từ: {pr_path}")
    pagerank = spark.read.parquet(pr_path)
    
    # Load Communities
    comm_path = f"{HDFS_RESULTS}clustering/community_assignments"
    print(f"📂 Đọc Communities từ: {comm_path}")
    communities = spark.read.parquet(comm_path)
    
    # Load Community Stats
    stats_path = f"{HDFS_RESULTS}clustering/community_statistics"
    print(f"📂 Đọc Community Stats từ: {stats_path}")
    comm_stats = spark.read.parquet(stats_path)
    
    print("✅ Đã load tất cả kết quả!")
    
    return pagerank, communities, comm_stats


@timer
def create_output_directory():
    """Tạo thư mục output cho visualizations"""
    import os
    
    # Convert relative path to absolute
    output_dir = os.path.abspath(LOCAL_VISUALIZATIONS_DIR)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"✅ Đã tạo thư mục: {output_dir}")
    else:
        print(f"📁 Thư mục đã tồn tại: {output_dir}")
    
    return output_dir


@timer
def plot_pagerank_distribution(pagerank_pdf, output_dir):
    """
    Vẽ phân phối PageRank
    
    Args:
        pagerank_pdf: Pandas DataFrame với PageRank scores
        output_dir: Output directory
    """
    print_section("VẼ PAGERANK DISTRIBUTION")
    
    # Create figure with subplots
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    # 1. Histogram
    axes[0, 0].hist(pagerank_pdf['pagerank'], bins=50, edgecolor='black', alpha=0.7)
    axes[0, 0].set_xlabel('PageRank Score')
    axes[0, 0].set_ylabel('Frequency')
    axes[0, 0].set_title('PageRank Distribution (Histogram)')
    axes[0, 0].grid(True, alpha=0.3)
    
    # 2. Cumulative distribution
    sorted_pr = pagerank_pdf['pagerank'].sort_values(ascending=False).reset_index(drop=True)
    cumsum = sorted_pr.cumsum() / sorted_pr.sum() * 100
    axes[0, 1].plot(cumsum.values)
    axes[0, 1].set_xlabel('Zone Rank')
    axes[0, 1].set_ylabel('Cumulative PageRank (%)')
    axes[0, 1].set_title('Cumulative PageRank Distribution')
    axes[0, 1].grid(True, alpha=0.3)
    axes[0, 1].axhline(y=50, color='r', linestyle='--', label='50%')
    axes[0, 1].axhline(y=80, color='orange', linestyle='--', label='80%')
    axes[0, 1].legend()
    
    # 3. Top 20 zones bar chart
    top20 = pagerank_pdf.nlargest(20, 'pagerank')
    axes[1, 0].barh(range(len(top20)), top20['pagerank'].values)
    axes[1, 0].set_yticks(range(len(top20)))
    axes[1, 0].set_yticklabels([f"Zone {int(z)}" for z in top20['zone_id'].values])
    axes[1, 0].invert_yaxis()
    axes[1, 0].set_xlabel('PageRank Score')
    axes[1, 0].set_title('Top 20 Zones by PageRank')
    axes[1, 0].grid(True, alpha=0.3, axis='x')
    
    # 4. Log-log plot (Power-law check)
    sorted_pr_desc = pagerank_pdf['pagerank'].sort_values(ascending=False).reset_index(drop=True)
    axes[1, 1].loglog(range(1, len(sorted_pr_desc)+1), sorted_pr_desc.values, 'b.')
    axes[1, 1].set_xlabel('Rank (log scale)')
    axes[1, 1].set_ylabel('PageRank (log scale)')
    axes[1, 1].set_title('Power-Law Distribution Check (Log-Log Plot)')
    axes[1, 1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save figure
    output_path = os.path.join(output_dir, 'pagerank_distribution.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ Đã lưu: {output_path}")
    
    plt.close()


@timer
def plot_community_analysis(comm_stats_pdf, output_dir):
    """
    Vẽ phân tích communities
    
    Args:
        comm_stats_pdf: Pandas DataFrame với community statistics
        output_dir: Output directory
    """
    print_section("VẼ COMMUNITY ANALYSIS")
    
    # Create figure
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    # 1. Community size distribution
    axes[0, 0].hist(comm_stats_pdf['num_zones'], bins=30, edgecolor='black', alpha=0.7, color='skyblue')
    axes[0, 0].set_xlabel('Number of Zones')
    axes[0, 0].set_ylabel('Number of Communities')
    axes[0, 0].set_title('Community Size Distribution')
    axes[0, 0].grid(True, alpha=0.3)
    
    # 2. Top 15 communities by size
    top15 = comm_stats_pdf.nlargest(15, 'num_zones')
    axes[0, 1].barh(range(len(top15)), top15['num_zones'].values, color='coral')
    axes[0, 1].set_yticks(range(len(top15)))
    axes[0, 1].set_yticklabels([f"Comm {int(c)}" for c in top15['community_id'].values])
    axes[0, 1].invert_yaxis()
    axes[0, 1].set_xlabel('Number of Zones')
    axes[0, 1].set_title('Top 15 Largest Communities')
    axes[0, 1].grid(True, alpha=0.3, axis='x')
    
    # 3. PageRank concentration by community
    top10_pr = comm_stats_pdf.nlargest(10, 'total_pagerank')
    axes[1, 0].barh(range(len(top10_pr)), top10_pr['total_pagerank'].values, color='lightgreen')
    axes[1, 0].set_yticks(range(len(top10_pr)))
    axes[1, 0].set_yticklabels([f"Comm {int(c)}" for c in top10_pr['community_id'].values])
    axes[1, 0].invert_yaxis()
    axes[1, 0].set_xlabel('Total PageRank')
    axes[1, 0].set_title('Top 10 Communities by Total PageRank')
    axes[1, 0].grid(True, alpha=0.3, axis='x')
    
    # 4. Scatter: Size vs PageRank
    axes[1, 1].scatter(comm_stats_pdf['num_zones'], comm_stats_pdf['total_pagerank'], 
                      alpha=0.6, s=100, color='purple')
    axes[1, 1].set_xlabel('Number of Zones')
    axes[1, 1].set_ylabel('Total PageRank')
    axes[1, 1].set_title('Community Size vs Total PageRank')
    axes[1, 1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save figure
    output_path = os.path.join(output_dir, 'community_analysis.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ Đã lưu: {output_path}")
    
    plt.close()


@timer
def generate_summary_reports(pagerank_pdf, comm_stats_pdf, output_dir):
    """
    Tạo summary reports (CSV)
    
    Args:
        pagerank_pdf: Pandas DataFrame với PageRank
        comm_stats_pdf: Pandas DataFrame với community stats
        output_dir: Output directory
    """
    print_section("TẠO SUMMARY REPORTS")
    
    # Summary statistics
    summary = {
        'Total Zones': len(pagerank_pdf),
        'Total Communities': len(comm_stats_pdf),
        'Avg PageRank': pagerank_pdf['pagerank'].mean(),
        'Max PageRank': pagerank_pdf['pagerank'].max(),
        'Min PageRank': pagerank_pdf['pagerank'].min(),
        'Avg Community Size': comm_stats_pdf['num_zones'].mean(),
        'Largest Community': comm_stats_pdf['num_zones'].max(),
        'Smallest Community': comm_stats_pdf['num_zones'].min()
    }
    
    summary_df = pd.DataFrame([summary]).T
    summary_df.columns = ['Value']
    
    # Save summary
    summary_path = os.path.join(output_dir, 'summary_statistics.csv')
    summary_df.to_csv(summary_path)
    print(f"✅ Đã lưu: {summary_path}")
    
    # Top 50 zones by PageRank
    top50 = pagerank_pdf.nlargest(50, 'pagerank')
    top50_path = os.path.join(output_dir, 'top50_zones_detailed.csv')
    top50.to_csv(top50_path, index=False)
    print(f"✅ Đã lưu: {top50_path}")
    
    # Print summary
    print("\n📊 Summary Statistics:")
    print(summary_df.to_string())


def main():
    """Main execution"""
    
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║                                                                ║
    ║        NYC TAXI GRAPH MINING - BƯỚC 4: VISUALIZATION          ║
    ║                                                                ║
    ║  Mục tiêu: Tạo charts và visualizations cho kết quả          ║
    ║                                                                ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    
    # Create Spark session (local mode)
    spark = create_local_spark_session("NYC_Taxi_Visualization")
    
    try:
        # Step 1: Create output directory
        output_dir = create_output_directory()
        
        # Step 2: Load results
        pagerank, communities, comm_stats = load_results(spark)
        
        # Step 3: Convert to Pandas
        print_section("CONVERT TO PANDAS")
        print("🔄 Converting Spark DataFrames to Pandas...")
        pagerank_pdf = pagerank.toPandas()
        comm_stats_pdf = comm_stats.toPandas()
        print("✅ Conversion hoàn thành!")
        
        # Step 4: Plot PageRank distribution
        plot_pagerank_distribution(pagerank_pdf, output_dir)
        
        # Step 5: Plot community analysis
        plot_community_analysis(comm_stats_pdf, output_dir)
        
        # Step 6: Generate summary reports
        generate_summary_reports(pagerank_pdf, comm_stats_pdf, output_dir)
        
        print("\n" + "="*70)
        print("🎉 HOÀN THÀNH BƯỚC 4: VISUALIZATION")
        print("="*70)
        print(f"\n📂 Tất cả visualizations đã được lưu tại: {output_dir}")
        print("\n📌 Files được tạo:")
        print("   - pagerank_distribution.png")
        print("   - community_analysis.png")
        print("   - summary_statistics.csv")
        print("   - top50_zones_detailed.csv")
        print("\n📌 Next step:")
        print("   - Chạy 5_benchmark.py để đo scalability")
        
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
