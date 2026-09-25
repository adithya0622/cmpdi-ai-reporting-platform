#!/bin/bash
set -e
pg_ctlcluster 16 main start 2>/dev/null || true
pg_isready -p 5432
su - postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='cmpdi'\"" | grep -q 1 || su - postgres -c "psql -c \"CREATE USER cmpdi WITH PASSWORD 'cmpdi';\""
su - postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='cmpdi'\"" | grep -q 1 || su - postgres -c "psql -c \"CREATE DATABASE cmpdi OWNER cmpdi;\""
su - postgres -c "psql -d cmpdi -c 'CREATE EXTENSION IF NOT EXISTS vector;'"
su - postgres -c "psql -d cmpdi -tAc \"SELECT extname FROM pg_extension WHERE extname='vector';\""
echo "setup done"
