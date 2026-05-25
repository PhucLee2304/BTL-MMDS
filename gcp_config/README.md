# Cluster GCP cho bài tập lớn MMDS

Tài liệu này mô tả cụm 3 máy trên Google Cloud Platform dùng để xử lý dữ liệu lớn và huấn luyện mô hình dự đoán nhu cầu taxi NYC (2020-2025). Cụm đã được cấu hình Hadoop HDFS, YARN và Spark chạy trên YARN để xử lý phân tán và lưu trữ phân tán.

Tham khảo thêm:
- Tổng quan dự án: /README.md
- Cụm ảo để thử nghiệm nhỏ: /virtual_cluster_config/README_DOCKER.md
- Cụm vật lý trong LAN: /real_cluster_config/README.md

## 1. Cấu hình cụm

- Số node: 3 (1 master + 2 worker)
- Loại máy: GCP E2 Standard, 4 vCPU, 16 GB RAM/máy
- Hệ điều hành: Linux

### Dịch vụ đang chạy

- HDFS: NameNode, SecondaryNameNode, DataNode
- YARN: ResourceManager, NodeManager
- Spark-on-YARN

### Ví dụ IP và host

- hadoop-master (10.128.0.2)
- hadoop-worker-1 (10.128.0.3)
- hadoop-worker-2 (10.128.0.4)

Lưu ý: IP có thể thay đổi theo VPC. Cập nhật lại nếu cần.

## 2. Cấu trúc thư mục

```
gcp_config/
	cluster.env              # biến môi trường và topology
	hadoop/                  # core-site.xml, hdfs-site.xml, yarn-site.xml, workers
	spark/                   # spark-defaults.conf, spark-env.sh
	scripts/
		deploy_configs.sh      # đẩy config lên master và workers
		format_and_start.sh    # format NameNode (lần đầu) + start HDFS/YARN
		stop_cluster.sh        # stop HDFS/YARN
```

## 3. Khởi động và dừng cụm

### 3.1. Chuẩn bị (chỉ cần làm khi thay đổi config)

Đăng nhập vào master, đứng tại thư mục gốc dự án:

```bash
cd ~/BTL-MMDS/gcp_config
./scripts/deploy_configs.sh
```

Script sẽ copy file cấu hình sang từng worker, tạo thư mục lưu trữ HDFS và log trên tất cả node.

### 3.2. Khởi động cụm

```bash
cd ~/BTL-MMDS/gcp_config
./scripts/format_and_start.sh
```

Lần đầu tiên sẽ format NameNode nếu thư mục /data/hdfs/nn/current chưa tồn tại.

### 3.3. Dừng cụm

```bash
cd ~/BTL-MMDS/gcp_config
./scripts/stop_cluster.sh
```

## 4. Kiểm tra nhanh

Trên master:

```bash
jps
hdfs dfsadmin -report
yarn node -list
```

Chạy thử một job Spark trên YARN:

```bash
spark-submit \
	--class org.apache.spark.examples.SparkPi \
	--master yarn \
	--deploy-mode cluster \
	$SPARK_HOME/examples/jars/spark-examples_*.jar \
	10
```

## 5. Truy cập giao diện web

Nếu cần, mở port trên GCP firewall (hoặc dùng SSH tunnel):

- HDFS NameNode UI: http://<master-ip>:9870
- YARN ResourceManager UI: http://<master-ip>:8088

## 6. Thiết lập VS Code Remote SSH cho thành viên

### 6.1. Cài extension Remote - SSH

Trên VS Code: Extensions -> tìm "Remote - SSH" (Microsoft) và cài đặt.

### 6.2. Tạo và chia sẻ SSH key

Mỗi thành viên tạo key trên máy của mình:

```bash
ssh-keygen -t ed25519 -C "<email>"
```

Gửi nội dung public key (file ~/.ssh/id_ed25519.pub) cho người quản lý cụm.

Trên từng node (master và workers), thêm key vào ~/.ssh/authorized_keys:

```bash
mkdir -p ~/.ssh
cat >> ~/.ssh/authorized_keys
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

### 6.3. Cấu hình ~/.ssh/config

Trên máy cá nhân, tạo hoặc cập nhật file ~/.ssh/config:

```bash
Host hadoop-master
	HostName <master-public-ip>
	User tiennd3886
	IdentityFile ~/.ssh/id_ed25519

Host hadoop-worker-1
	HostName <worker-1-public-ip>
	User tiennd3886
	IdentityFile ~/.ssh/id_ed25519

Host hadoop-worker-2
	HostName <worker-2-public-ip>
	User tiennd3886
	IdentityFile ~/.ssh/id_ed25519
```

Sau đó, mở VS Code -> Command Palette -> "Remote-SSH: Connect to Host" -> chọn hadoop-master.

## 7. Lưu ý vận hành
- cd đúng thư mục dự án:
```bash
cd ~/BTL-MMDS
```
- kích hoạt python venv:
```bash
tiennd3886@hadoop-master:~/BTL-MMDS$ source env/bin/activate
```
- Nếu update file config trong gcp_config/hadoop hoặc gcp_config/spark, hãy chạy lại deploy_configs.sh rồi mới restart cụm.
- Với dữ liệu lớn, nên đẩy lên HDFS và chạy notebook/spark-submit trên cụm thay vì xử lý cục bộ.
- Các biến chuẩn nằm trong gcp_config/cluster.env, thay đổi tại đây trước khi deploy.
- Khi đã ssh vào được master, có thể ssh sang các worker đề cài thêm thư viện python nếu cần, đã thiết lập ssh không mật khẩu:
```bash
ssh hadoop-worker-1
exit
ssh hadoop-worker-2
exit
```

Quick check:
```bash
jps

hdfs dfsadmin -report

hdfs dfs -df -h

yarn node -list

http://35.253.31.186:9870/explorer.html#/
```

Xóa vĩnh viễn rác trên HDFS (Quan trọng):
Mặc định, khi bạn xóa một file trên HDFS, hệ thống chỉ di chuyển nó vào thùng rác (Trash) và dung lượng ổ cứng không hề giảm đi. Để giải phóng không gian lập tức, bạn bắt buộc phải dùng cờ -skipTrash. Các file tạm của Spark sinh ra khi submit code thường nằm trong /user/*/.sparkStaging/. Nếu cụm đang rảnh (không ai chạy code), có thể xóa toàn bộ file trong này:
```bash
hdfs dfs -rm -r -skipTrash /đường/dẫn/thư/mục/cần/xóa
```

Quy tắc làm việc nhóm để chống sập cụm
Để cụm 4 node chạy ổn định trong suốt quá trình làm bài, nhóm bạn nên thiết lập các quy tắc sau vào trực tiếp mã nguồn code (Python/Scala) của từng người:

Phân quyền không gian làm việc: Tạo 4 thư mục đích riêng biệt trên HDFS cho từng người để không ai ghi đè hoặc vô tình xóa mất model của người khác:

```Bash
hdfs dfs -mkdir -p /user/thanhvien1 /user/thanhvien2
```
Quản lý Model Checkpoint: Khi cấu hình lưu lại trọng số trong các epoch huấn luyện, mã nguồn sẽ liên tục sinh ra file mới trên HDFS. Bạn nên viết code để cơ chế lưu Checkpoint tự động ghi đè lên file cũ, hoặc chỉ giữ lại 1 - 2 Checkpoint mới nhất thay vì lưu tất cả.

Tự động dọn dẹp Output: Spark sẽ báo lỗi và dừng chạy nếu thư mục lưu kết quả (Output) đã tồn tại. Thay vì mỗi lần chạy lại phải nghĩ ra một cái tên thư mục mới làm rác HDFS, hãy thêm một hàm kiểm tra và tự động xóa thư mục Output cũ ở ngay đầu file script train của mỗi người.


cài python lib trên các worker, may be onetime
```bash
for node in hadoop-worker-1 hadoop-worker-2; do
    echo "=== Đang cấu hình Python Environment trên $node ==="
    
    # 1. Cài đặt python3-venv trên Worker
    ssh -t $node "sudo apt update && sudo apt install python3-venv python3-full -y"
    
    # 2. Tạo thư mục dự án (nếu chưa có) và khởi tạo môi trường ảo env
    ssh $node "mkdir -p ~/BTL-MMDS && python3 -m venv ~/BTL-MMDS/env"
    
    # 3. Copy file requirements.txt từ Master sang Worker
    scp ~/BTL-MMDS/requirements.txt $node:~/BTL-MMDS/
    
    # 4. Kích hoạt môi trường ảo trên Worker và tiến hành cài đặt thư viện
    ssh $node "~/BTL-MMDS/env/bin/pip install --upgrade pip"
    ssh $node "~/BTL-MMDS/env/bin/pip install -r ~/BTL-MMDS/requirements.txt"
done
```