import os
import json
import numpy as np
import tempfile
import subprocess
from pyspark.sql import SparkSession
import pyspark.sql.functions as F
from pyspark.ml.regression import LinearRegressionModel
from xgboost.spark import SparkXGBRegressorModel
import tensorflow as tf

def main():
    print("=" * 60)
    print("INFERENCE DEMO - ENSEMBLE MODEL")
    print("=" * 60)

    # 1. Khởi tạo Spark (Chạy local để test nhanh)
    spark = (
        SparkSession.builder.appName("TestingEnsemble")
        .config("spark.jars", "/home/tiennd3886/lib/spark-tfrecord_2.12-0.7.0.jar")
        .config("spark.master", "local[*]")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    
    hdfs_base = "/user/kshape/model"
    
    # 2. Lấy metadata (chứa config và scaler của CNN-LSTM)
    print("[1] Loading pipeline metadata & scaler...")
    subprocess.run(f"hdfs dfs -get -f {hdfs_base}/models/pipeline_metadata.json /tmp/pipeline_metadata.json", shell=True, stderr=subprocess.DEVNULL)
    with open("/tmp/pipeline_metadata.json", "r") as f:
        meta = json.load(f)
    
    scaler = meta["scaler_stats"]
    mean, std = scaler["seq_mean"], scaler["seq_std"]
    y_min, y_den = scaler["y_min"], scaler["y_denom"]
    window = meta["config"]["seq_window"]
    
    # 3. Load các mô hình
    print("[2] Loading XGBoost Model from HDFS...")
    xgb_model = SparkXGBRegressorModel.load(f"{hdfs_base}/models/spark_xgb_model")
    
    print("[3] Loading Ridge Ensemble Model from HDFS...")
    ridge_model = LinearRegressionModel.load(f"{hdfs_base}/models/spark_ridge_meta_model")
    
    print("[4] Loading CNN-LSTM Model from HDFS...")
    local_keras = "/tmp/cnn_lstm_testing.keras"
    subprocess.run(f"hdfs dfs -get -f {hdfs_base}/models/cnn_lstm.keras {local_keras}", shell=True, stderr=subprocess.DEVNULL)
    cnn_model = tf.keras.models.load_model(local_keras)
    
    # 4. Sinh ngẫu nhiên dữ liệu đầu vào (Thay vì lấy từ HDFS)
    print("[5] Generating random sample input arrays...")
    
    # Số lượng features
    num_tabular_features = len(meta["config"]["tabular_features"]) # 18 features
    num_sequence_features = len(meta["config"]["sequence_features"]) # 4 features
    
    # A. Sinh mảng ngẫu nhiên cho Tabular (XGBoost)
    # Ví dụ: Mảng 1 chiều chứa 18 giá trị số thực ngẫu nhiên từ 0 đến 10
    random_tabular_array = np.random.uniform(0, 10, size=num_tabular_features).tolist()
    
    # B. Sinh mảng ngẫu nhiên cho Sequence (CNN-LSTM)
    # Ví dụ: Mảng 1 chiều chứa 48 * 4 = 192 giá trị (mô phỏng 48 khung giờ trong quá khứ)
    seq_flat = np.random.uniform(0, 10, size=window * num_sequence_features).tolist()
    
    print(f"\n{'=' * 60}")
    print(f" DỮ LIỆU ĐẦU VÀO NGẪU NHIÊN (RANDOM SAMPLE)")
    print(f"{'=' * 60}")
    
    print("\n[A] CHI TIẾT 18 TÍNH NĂNG TABULAR (Cho XGBoost):")
    tabular_feature_names = meta["config"]["tabular_features"]
    for i, (name, val) in enumerate(zip(tabular_feature_names, random_tabular_array)):
        print(f"  {i:2d}. {name:<30} = {val:.4f}")
        
    print(f"\n[B] CHI TIẾT 192 TÍNH NĂNG SEQUENCE (Cho CNN-LSTM):")
    sequence_feature_names = meta["config"]["sequence_features"]
    print(f"  Gồm {window} bước thời gian (time steps) trong quá khứ.")
    print(f"  Tại mỗi bước có {num_sequence_features} tính năng: {sequence_feature_names}")
    
    # In ra 2 bước đầu và 1 bước cuối cho đỡ dài (192 dòng)
    seq_np_2d = np.array(seq_flat).reshape(window, num_sequence_features)
    for step in range(window):
        if step < 2 or step == window - 1:
            print(f"  * Bước thời gian {step + 1}/{window}:")
            for j, name in enumerate(sequence_feature_names):
                print(f"      - {name:<20} = {seq_np_2d[step, j]:.4f}")
        elif step == 2:
            print(f"  * ... (Các bước từ 3 đến {window-1} tương tự) ...")
            
    print(f"{'=' * 60}\n")
    
    # ---------------------------------------------------------
    # A. DỰ ĐOÁN BẰNG XGBOOST (Dạng Tabular: features_vector)
    # ---------------------------------------------------------
    from pyspark.ml.linalg import Vectors
    
    # Chuyển mảng Python list thành PySpark Dense Vector
    # Tạo DataFrame 1 dòng để feed vào Spark MLlib XGBoost
    sample_df = spark.createDataFrame(
        [(Vectors.dense(random_tabular_array),)], 
        ["features_vector"]
    )
    
    xgb_df = xgb_model.transform(sample_df)
    xgb_pred = xgb_df.select("xgb_pred").first()[0]
    print(f"▶ [XGBoost]    Prediction : {xgb_pred:.4f}")
    
    # ---------------------------------------------------------
    # B. DỰ ĐOÁN BẰNG CNN-LSTM (Dạng Sequence: sequence_flat)
    # ---------------------------------------------------------
    # Chuyển list thành numpy array và Reshape thành (1, 48, n_features)
    seq_np = np.array(seq_flat)
    seq_matrix = seq_np.reshape(1, window, num_sequence_features)
    
    # Chuẩn hóa (Z-Score standardization) dựa trên Scaler đã lưu
    seq_matrix = (seq_matrix - mean) / std
    
    # Gọi Keras predict
    cnn_raw_pred = cnn_model.predict(seq_matrix, verbose=0).squeeze(-1)[0]
    cnn_pred = max(cnn_raw_pred * y_den + y_min, 0.0)
    print(f"▶ [CNN-LSTM]   Prediction : {cnn_pred:.4f}")
    
    # ---------------------------------------------------------
    # C. DỰ ĐOÁN BẰNG ENSEMBLE RIDGE
    # ---------------------------------------------------------
    # Ridge kết hợp có dạng: y = w1*xgb + w2*cnn + bias
    w_xgb = ridge_model.coefficients[0]
    w_cnn = ridge_model.coefficients[1]
    bias = ridge_model.intercept
    
    ensemble_pred = max(w_xgb * xgb_pred + w_cnn * cnn_pred + bias, 0.0)
    
    print(f"▶ [ENSEMBLE]   Prediction : {ensemble_pred:.4f}")
    print(f"\n[Chi tiết Ensemble] y = {w_xgb:.4f} * xgb + {w_cnn:.4f} * cnn_lstm + {bias:.4f}")
    print("=" * 60)
    
    spark.stop()

if __name__ == "__main__":
    main()
