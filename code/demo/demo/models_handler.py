import os
import json
import numpy as np
import pandas as pd
import datetime
import joblib

import tensorflow as tf
import xgboost as xgb

try:
    from pyspark.sql import SparkSession
    from pyspark.ml.feature import VectorAssembler
    from pyspark.ml.regression import GBTRegressionModel
except ImportError:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")

class ModelHandler:
    def __init__(self):
        self.models = {}
        self._load_all_models()
        
    def _load_all_models(self):
        print("Đang khởi tạo toàn bộ mô hình AI (Chế độ Không Spark)...")
        
        # 1. Load KShape Models (Native XGBoost & Hardcoded Ridge Weights)
        print("-> Loading KShape Models...")
        kshape_dir = os.path.join(MODELS_DIR, "kshape")
        try:
            b_kshape = xgb.Booster()
            b_kshape.load_model(os.path.join(kshape_dir, "spark_xgb_model", "model", "part-00000"))
            self.models['kshape_xgb'] = b_kshape
            
            # Ridge weights extracted from spark_ridge_meta_model/data parquet
            self.models['kshape_ridge'] = {
                'w_xgb': 2.16285228,
                'w_cnn': 0.63443531,
                'bias': -10.69202087206511
            }
            
            self.models['kshape_cnn'] = tf.keras.models.load_model(os.path.join(kshape_dir, "cnn_lstm.keras"))
            with open(os.path.join(kshape_dir, "pipeline_metadata.json"), "r") as f:
                self.models['kshape_meta'] = json.load(f)
        except Exception as e:
            print(f"Lỗi khi load KShape: {e}")

        # 2. Load Holt-Winters (XGBoost Native)
        print("-> Loading Holt-Winters (Native XGBoost)...")
        holt_dir = os.path.join(MODELS_DIR, "holt")
        try:
            booster = xgb.Booster()
            booster.load_model(os.path.join(holt_dir, "native_booster.json"))
            self.models['holt_xgb'] = booster
        except Exception as e:
            print(f"Lỗi khi load Holt-Winters: {e}")
            
        # 3. Load Spatiotemporal
        print("-> Loading Spatiotemporal Bundle...")
        spatio_dir = os.path.join(MODELS_DIR, "spatiotemporal")
        try:
            bundle = joblib.load(os.path.join(spatio_dir, "best_model_bundle.joblib"))
            self.models['spatio_bundle'] = bundle
        except Exception as e:
            print(f"Lỗi khi load Spatiotemporal: {e}")
            
        # 4. Load GBT (PySpark)
        print("-> Loading GBT Model (Spark)...")
        gbt_dir = os.path.join(MODELS_DIR, "gbt")
        try:
            # Fix Java 17+ security manager issue
            os.environ["PYSPARK_SUBMIT_ARGS"] = '--driver-java-options "-Djava.security.manager=allow" pyspark-shell'
            os.environ["HADOOP_USER_NAME"] = "windows"
            
            # Cấu hình Hadoop Home local cho Windows để nạp hadoop.dll (phiên bản 3.2.0 tương thích)
            hadoop_path = os.path.join(BASE_DIR, "..", "..", "hadoop")
            os.environ["HADOOP_HOME"] = os.path.abspath(hadoop_path)
            os.environ["PATH"] = os.path.join(os.environ["HADOOP_HOME"], "bin") + os.pathsep + os.environ.get("PATH", "")
            
            import sys
            os.environ["PYSPARK_PYTHON"] = sys.executable
            os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
            
            spark = SparkSession.builder \
                .appName("TaxiDemandZoneInferenceGBT") \
                .master("local[*]") \
                .config("spark.driver.extraJavaOptions", "-Djava.security.manager=allow") \
                .config("spark.executor.extraJavaOptions", "-Djava.security.manager=allow") \
                .getOrCreate()
            spark.sparkContext.setLogLevel("ERROR")
            self.models['spark'] = spark
            self.models['gbt_model'] = GBTRegressionModel.load(gbt_dir)
            
            # Load ratios
            ratios_file = os.path.join(gbt_dir, "zone_cluster_ratios.json")
            if not os.path.exists(ratios_file):
                raise FileNotFoundError(f"Không tìm thấy file tỷ trọng: {ratios_file}")
            
            with open(ratios_file, "r") as f:
                ratios_data = json.load(f)
                
            zone_lookup = {}
            for cluster_id_str, zones_dict in ratios_data["ratios"].items():
                for zone_id_str, prop in zones_dict.items():
                    zone_lookup[zone_id_str] = (int(cluster_id_str), float(prop))
            self.models['gbt_zone_lookup'] = zone_lookup
            
        except Exception as e:
            print(f"Lỗi khi load GBT: {e}")
            
        print("Hoàn tất tải mô hình!")

    def predict(self, model_choice, location_id, date_str, hour_str, minute_str):
        # Parse datetime
        dt = datetime.datetime.strptime(f"{date_str} {hour_str}:{minute_str}", "%Y-%m-%d %H:%M")
        
        # Danh sách locationID được hỗ trợ (Từ Spatiotemporal Cluster Map)
        valid_46_zones = [13, 43, 48, 50, 68, 75, 79, 87, 90, 100, 107, 113, 114, 132, 137, 138, 140, 141, 142, 143, 144, 148, 151, 158, 161, 162, 163, 164, 166, 170, 186, 211, 229, 230, 231, 233, 234, 236, 237, 238, 239, 246, 249, 262, 263, 264]
        
        # Kiểm tra logic location bị loại bỏ
        if model_choice == "Holt-Winters (XGBoost)":
            # Giả định Holt-Winters cũng bị filter chỉ còn 46 zones (hoặc tương tự)
            if location_id not in valid_46_zones:
                return "Không có thông tin cho LocationID này ở mô hình Holt-Winters."
        elif model_choice == "Spatiotemporal Bundle":
            if location_id not in valid_46_zones:
                return "Không có thông tin cho LocationID này ở mô hình Spatiotemporal."
        elif model_choice == "GBT Model":
            if str(location_id) not in self.models.get('gbt_zone_lookup', {}):
                return "Không có thông tin cho LocationID này ở mô hình GBT."
        
        # Base Features Extract
        hour = float(dt.hour)
        minute = float(dt.minute)
        dow = float(dt.weekday())
        month = float(dt.month)
        is_weekend = 1.0 if dow >= 5 else 0.0
        
        # Mảng base chung
        base_features = [
            hour, dow, month, is_weekend, 0.0, 0.0, 0.0,
            np.random.uniform(5, 50), np.random.uniform(5, 50), np.random.uniform(5, 50),
            np.random.uniform(10, 60), np.random.uniform(10, 60), np.random.uniform(1, 10),
            float(location_id % 10) # cluster_id mock
        ]

        try:
            if model_choice == "KShape Ensemble":
                return self._predict_kshape(base_features, minute)
            elif model_choice == "Holt-Winters (XGBoost)":
                return self._predict_holt(base_features)
            elif model_choice == "Spatiotemporal Bundle":
                return self._predict_spatiotemporal(location_id)
            elif model_choice == "GBT Model":
                return self._predict_gbt(location_id, hour, dow, is_weekend, month)
            else:
                raise ValueError("Model không hợp lệ.")
        except Exception as e:
            return f"Error: {str(e)}"

    def _predict_kshape(self, base_features, minute):
        # KShape XGBoost cần 18 features
        # Thứ tự chuẩn: hour, minute, dow, is_weekday, is_weekend, slot_in_week, ...
        # Lấy từ base_features và chèn minute vào
        hour = base_features[0]
        dow = base_features[1]
        is_weekend = base_features[3]
        is_weekday = 1.0 if is_weekend == 0.0 else 0.0
        slot_in_week = dow * 48 + (hour * 2) + (1 if minute >= 30 else 0)
        
        # Reconstruct tabular_features array to length 18
        tabular_features = np.array([
            hour, minute, dow, is_weekday, is_weekend, slot_in_week,
            np.random.uniform(1, 10), np.random.uniform(10, 50), np.random.uniform(10, 50),
            base_features[13], # cluster_id
            np.random.uniform(10, 50), np.random.uniform(10, 50), np.random.uniform(10, 50),
            np.random.uniform(1, 10), np.random.uniform(0, 5), np.random.uniform(0, 5),
            np.random.uniform(0, 1), np.random.uniform(0, 1)
        ]).reshape(1, -1)
        
        # 1. Native XGBoost Prediction
        dmatrix = xgb.DMatrix(tabular_features)
        xgb_pred = self.models['kshape_xgb'].predict(dmatrix)[0]
        
        # 2. CNN-LSTM Prediction
        meta = self.models['kshape_meta']
        window = meta["config"]["seq_window"]
        num_seq_features = len(meta["config"]["sequence_features"])
        seq_matrix = np.random.uniform(0, 10, size=(1, window, num_seq_features))
        
        scaler = meta["scaler_stats"]
        mean, std = scaler["seq_mean"], scaler["seq_std"]
        y_min, y_den = scaler["y_min"], scaler["y_denom"]
        
        seq_scaled = (seq_matrix - mean) / std
        cnn_raw = self.models['kshape_cnn'](seq_scaled, training=False).numpy().squeeze(-1)[0]
        cnn_pred = max(cnn_raw * y_den + y_min, 0.0)
        
        # 3. Ridge Ensemble (Manual compute)
        ridge = self.models['kshape_ridge']
        w_xgb = ridge['w_xgb']
        w_cnn = ridge['w_cnn']
        bias = ridge['bias']
        
        final_pred = max(w_xgb * xgb_pred + w_cnn * cnn_pred + bias, 0.0)
        return float(final_pred)

    def _predict_holt(self, base_features):
        # Holt-Winters cần 15 features: base_features + hw_forecast
        hw_forecast = np.random.uniform(20, 80)
        hw_features = np.array(base_features + [hw_forecast]).reshape(1, -1)
        
        booster = self.models['holt_xgb']
        dmatrix = xgb.DMatrix(hw_features)
        pred = booster.predict(dmatrix)[0]
        return float(max(pred, 0.0))

    def _predict_spatiotemporal(self, location_id):
        bundle = self.models['spatio_bundle']
        cluster_map = bundle['cluster_map']
        
        # Tìm cluster_id của location_id
        if location_id not in cluster_map.index:
            # Nếu không tìm thấy, mock random một cụm có trong index
            c_id = cluster_map.iloc[0]
            print(f"Location {location_id} không có trong map. Dùng cụm giả định: {c_id}")
        else:
            c_id = cluster_map.loc[location_id]
            
        c = int(c_id)
        cluster_model_dict = bundle['cluster_models'][f"cluster_{c}"]
        disagg_model_dict = bundle['disagg_models'][c]
        
        cluster_lag = bundle['cluster_lag']
        disagg_lag = bundle['disagg_lag']
        zones = disagg_model_dict['zones']
        n_zones = len(zones)
        
        # MOCK dữ liệu đầu vào cho Cụm (Cluster)
        X_cluster = np.random.uniform(10, 100, size=(1, cluster_lag))
        
        # MOCK dữ liệu đầu vào cho Phân rã (Disaggregation)
        # Bao gồm: cluster history + history của TẤT CẢ các zone trong cụm
        # Kích thước = disagg_lag * (1 + n_zones)
        X_disagg = np.random.uniform(1, 50, size=(1, disagg_lag * (1 + n_zones)))
        
        # Thực hiện gọi hàm dự báo disaggregation (đã bao gồm cluster predictions nếu là LSTM+RF)
        # Chú ý: Ở đây ta chỉ chạy Disagg model để phân rã ra từng zone.
        x_scaler = disagg_model_dict['x_scaler']
        y_scaler = disagg_model_dict['y_scaler']
        best_name = disagg_model_dict['best_name']
        model = disagg_model_dict['model']
        
        X_eval_sc = x_scaler.transform(X_disagg)
        
        if best_name == "LSTM+RF":
            import torch
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            lstm = model["lstm"].to(device)
            lstm.eval()
            with torch.no_grad():
                X_t = torch.from_numpy(X_eval_sc.reshape(-1, disagg_lag, 1 + n_zones)).float().to(device)
                _, feat_eval = lstm(X_t)
            feat_eval = feat_eval.cpu().numpy()
            pred_sc = model["rf"].predict(np.concatenate([X_eval_sc, feat_eval], axis=1))
        else:
            pred_sc = model.predict(X_eval_sc)
            
        if pred_sc.ndim == 1:
            pred_sc = pred_sc.reshape(-1, 1)
        
        y_pred = y_scaler.inverse_transform(pred_sc)
        y_pred = np.round(np.clip(y_pred, 0, None))[0] # Mảng chứa KQ của n_zones
        
        # Lấy kết quả cho đúng location_id
        if location_id in zones:
            idx = list(zones).index(location_id)
            final_pred = y_pred[idx]
        else:
            # Fallback nếu zone không thuộc cụm 
            final_pred = y_pred[0]
            
        return float(final_pred)

    def _predict_gbt(self, location_id, hour, dow, is_weekend, month):
        zone_lookup = self.models.get('gbt_zone_lookup', {})
        if str(location_id) not in zone_lookup:
            raise ValueError(f"Zone {location_id} không tồn tại trong dữ liệu GBT!")
            
        target_cluster, proportion = zone_lookup[str(location_id)]
        
        # TỐI ƯU HOÁ: Batch prediction cho tất cả các cluster trong 1 lần chạy Spark
        time_key = f"{hour}_{dow}_{month}"
        
        if not hasattr(self, '_gbt_cache'):
            self._gbt_cache = {}
            self._gbt_current_time = None
            
        # Nếu thời gian thay đổi, chạy Spark predict 1 lần duy nhất cho toàn bộ cụm
        if self._gbt_current_time != time_key:
            self._gbt_cache.clear()
            self._gbt_current_time = time_key
            
            unique_clusters = set([c for c, p in zone_lookup.values()])
            
            columns = [
                'cluster_id', 'hour', 'day_of_week', 'is_weekend', 'month', 
                'lag_1', 'lag_2', 'lag_3', 'lag_48', 'lag_336'
            ]
            
            sample_data = []
            for cid in unique_clusters:
                sample_data.append((
                    cid,
                    int(hour),
                    int(dow) + 1,
                    int(is_weekend),
                    int(month),
                    float(np.random.randint(10, 500)),
                    float(np.random.randint(10, 500)),
                    float(np.random.randint(10, 500)),
                    float(np.random.randint(10, 500)),
                    float(np.random.randint(10, 500))
                ))
                
            spark = self.models.get('spark')
            gbt_model = self.models.get('gbt_model')
            
            if not spark or not gbt_model:
                raise ValueError("GBT Model chưa được load thành công!")
                
            df_sample = spark.createDataFrame(sample_data, columns)
            from pyspark.ml.feature import VectorAssembler
            assembler = VectorAssembler(inputCols=columns, outputCol="features")
            df_features = assembler.transform(df_sample)
            
            predictions = gbt_model.transform(df_features)
            
            # Lấy tất cả kết quả về RAM trong 1 Action duy nhất (cực nhanh)
            rows = predictions.select("cluster_id", "prediction").collect()
            for row in rows:
                self._gbt_cache[row["cluster_id"]] = row["prediction"]
                
        # Lấy demand của cluster từ cache O(1)
        predicted_cluster_demand = self._gbt_cache.get(target_cluster, 0.0)
        predicted_zone_demand = predicted_cluster_demand * proportion
        return float(predicted_zone_demand)
