.PHONY: build up down start stop restart logs clean ps exec-master exec-worker1

# Build images
build:
	docker-compose build

# Start cluster (2 nodes: master + worker1)
up:
	docker-compose up -d

# Start full cluster (3 nodes: master + worker1 + worker2)
up-full:
	docker-compose --profile full-cluster up -d

# Stop and remove containers
down:
	docker-compose down

# Stop containers (keep data)
stop:
	docker-compose stop

# Start stopped containers
start:
	docker-compose start

# Restart cluster
restart:
	docker-compose restart

# View logs
logs:
	docker-compose logs -f

# View logs of specific service
logs-master:
	docker-compose logs -f master

logs-worker1:
	docker-compose logs -f worker1

# Show running containers
ps:
	docker-compose ps

# Execute bash in master
exec-master:
	docker exec -it taxi-mining-master bash

# Execute bash in worker1
exec-worker1:
	docker exec -it taxi-mining-worker1 bash

# Clean everything (WARNING: removes volumes)
clean:
	docker-compose down -v
	docker system prune -f

# Check cluster health
health:
	@echo "=== HDFS Status ==="
	docker exec taxi-mining-master hdfs dfsadmin -report
	@echo "\n=== Spark Workers ==="
	docker exec taxi-mining-master curl -s http://master:8080/json/ | grep -o '"aliveworkers":[0-9]*'

# Create required directories in HDFS
hdfs-init:
	docker exec taxi-mining-master hdfs dfs -mkdir -p /user/taxi/raw_data
	docker exec taxi-mining-master hdfs dfs -mkdir -p /user/taxi/zone_lookup
	docker exec taxi-mining-master hdfs dfs -mkdir -p /user/taxi/results
	docker exec taxi-mining-master hdfs dfs -mkdir -p /spark-logs
	docker exec taxi-mining-master hdfs dfs -chmod -R 777 /spark-logs

# Test Spark
test-spark:
	docker exec taxi-mining-master spark-submit \
		--class org.apache.spark.examples.SparkPi \
		--master spark://master:7077 \
		/opt/spark/examples/jars/spark-examples_*.jar 100
