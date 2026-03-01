# code/test/test_malloc.py
import pandas as pd
import os
import sys

def trigger_malloc_error_with_data():
    print("--- Starting Realistic Memory Allocation Test ---")

    current_dir = os.path.dirname(os.path.abspath(__file__))

    data_folder = os.path.join(current_dir, "../../data/raw/") 

    print(f"Đường dẫn dữ liệu đang dùng là: {os.path.abspath(data_folder)}")
    
    all_chunks = []
        
    try:
        iteration = 0
        while True:
            iteration += 1
            for i in range(1, 7): 
                file_name = f"yellow_tripdata_2025-{i:02d}.parquet"
                file_path = os.path.join(data_folder, file_name)
                
                if os.path.exists(file_path):
                    # Nạp file vào RAM
                    df = pd.read_parquet(file_path)
                    all_chunks.append(df)
                    
                    # Quá trình concat tạo ra bản sao mới, chiếm cực nhiều RAM
                    full_df = pd.concat(all_chunks, ignore_index=True)
                    
                    # Tính toán dung lượng DataFrame trong RAM (xấp xỉ)
                    mem_usage = sys.getsizeof(full_df) / (1024**3) # GB
                    print(f"Lần lặp {iteration}, nạp {file_name}: {len(full_df):,} dòng (~{mem_usage:.2f} GB)")
                else:
                    print(f"Không tìm thấy file: {file_name}")
                
    except MemoryError:
        print("\n[SUCCESS] MemoryError caught!")
        print("Hệ thống không thể cấp phát thêm bộ nhớ cho pd.concat.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    trigger_malloc_error_with_data()