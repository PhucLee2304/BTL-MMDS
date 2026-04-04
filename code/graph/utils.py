"""
Utility functions cho NYC Taxi Graph Mining Project
"""

import time
import functools
from datetime import datetime


def timer(func):
    """
    Decorator để đo thời gian thực thi của function
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        print(f"\n⏱️  Bắt đầu: {func.__name__}")
        print(f"   Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        result = func(*args, **kwargs)
        
        end_time = time.time()
        elapsed = end_time - start_time
        print(f"\n✅ Hoàn thành: {func.__name__}")
        print(f"   Thời gian thực thi: {elapsed:.2f} seconds ({elapsed/60:.2f} minutes)")
        
        return result
    return wrapper


def print_section(title):
    """
    In tiêu đề section với formatting đẹp
    """
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70 + "\n")


def print_dataframe_stats(df, name="DataFrame"):
    """
    In thống kê cơ bản của DataFrame
    """
    try:
        count = df.count()
        print(f"\n📊 Thống kê {name}:")
        print(f"   - Số dòng: {count:,}")
        print(f"   - Số cột: {len(df.columns)}")
        print(f"   - Columns: {', '.join(df.columns)}")
    except Exception as e:
        print(f"⚠️  Không thể lấy stats: {str(e)}")


def save_dataframe_as_csv(df, output_path, sample_size=None):
    """
    Lưu DataFrame ra CSV
    
    Args:
        df: Spark DataFrame
        output_path: Đường dẫn output
        sample_size: Số dòng để sample (None = all)
    """
    try:
        if sample_size:
            df = df.limit(sample_size)
        
        df.coalesce(1).write \
            .mode("overwrite") \
            .option("header", "true") \
            .csv(output_path)
        
        print(f"✅ Đã lưu CSV: {output_path}")
    except Exception as e:
        print(f"❌ Lỗi khi lưu CSV: {str(e)}")


def format_number(num):
    """
    Format số với dấu phẩy
    """
    return f"{num:,}"


def print_progress(current, total, prefix="Progress"):
    """
    In progress bar đơn giản
    """
    percent = (current / total) * 100
    bar_length = 50
    filled = int(bar_length * current / total)
    bar = "█" * filled + "-" * (bar_length - filled)
    print(f"\r{prefix}: |{bar}| {percent:.1f}% ({current}/{total})", end="", flush=True)
