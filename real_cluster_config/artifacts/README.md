# Offline Artifacts

Place the following files in this folder before running build scripts:

- hadoop-3.3.6.tar.gz
- spark-3.5.0-bin-hadoop3.tgz
- graphframes-0.8.3-spark3.5-s_2.12.jar

These files are consumed by:
- docker/Dockerfile.master
- docker/Dockerfile.worker

If filenames differ, update both Dockerfiles accordingly.
