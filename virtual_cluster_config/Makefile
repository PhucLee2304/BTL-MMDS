.PHONY: prep-assets-local build build-fast up down start stop restart logs logs-master logs-worker1 logs-worker2 ps exec-master exec-worker1 exec-worker2 clean health hdfs-init test-spark

COMPOSE = docker compose

# Download and cache Hadoop/Spark archives and GraphFrames jar (no Docker required)
prep-assets-local:
	bash .docker-cache/prefetch_docker_assets.sh

# Build images (use local cache if available, fallback to online download)
build:
	$(COMPOSE) build

# Fast and stable flow for repeated rebuilds
build-fast: prep-assets-local build

# Start cluster (master + worker1 + worker2)
up:
	$(COMPOSE) up -d

# Stop and remove containers
down:
	$(COMPOSE) down

# Stop containers (keep volumes)
stop:
	$(COMPOSE) stop

# Start stopped containers
start:
	$(COMPOSE) start

# Restart cluster
restart:
	$(COMPOSE) restart

# View logs
logs:
	$(COMPOSE) logs -f

# View logs by service
logs-master:
	$(COMPOSE) logs -f master

logs-worker1:
	$(COMPOSE) logs -f worker1

logs-worker2:
	$(COMPOSE) logs -f worker2

# Show running containers
ps:
	$(COMPOSE) ps

# Execute bash in containers
exec-master:
	docker exec -it master bash

exec-worker1:
	docker exec -it worker1 bash

exec-worker2:
	docker exec -it worker2 bash

# Clean everything (WARNING: removes volumes)
clean:
	$(COMPOSE) down -v
	docker system prune -f

# Check cluster health
health:
	@echo "=== HDFS Status ==="
	docker exec master hdfs dfsadmin -report
	@echo "\n=== Spark Workers ==="
	docker exec master curl -s http://master:8080/json/ | grep -o '"aliveworkers":[0-9]*'

# Create required directories in HDFS
hdfs-init:
	docker exec master hdfs dfs -mkdir -p /user/taxi/raw_data
	docker exec master hdfs dfs -mkdir -p /user/taxi/zone_lookup
	docker exec master hdfs dfs -mkdir -p /user/taxi/results
	docker exec master hdfs dfs -mkdir -p /spark-logs
	docker exec master hdfs dfs -chmod -R 777 /spark-logs

# Test Spark
test-spark:
	docker exec master spark-submit \
		--class org.apache.spark.examples.SparkPi \
		--master spark://master:7077 \
		/opt/spark/examples/jars/spark-examples_*.jar 100
