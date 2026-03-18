#!/bin/bash

echo "Stopping all Lead Gen AI services..."

# 1. Kill Python Backend (FastAPI / Uvicorn)
echo "Stopping FastAPI Backend (port 8000)..."
pkill -f "uvicorn main:app" || true

# 2. Kill Celery Worker
echo "Stopping Celery Workers..."
pkill -f "celery -A app.tasks.celery_app worker" || true

# 3. Kill Python Static HTTP Server (Frontend)
echo "Stopping Frontend Server (port 3000)..."
pkill -f "python3 -m http.server 3000" || true

# 4. Stop Docker Infrastructure (Postgres & Redis)
echo "Stopping Docker containers..."
if [ "$(docker ps -q -f name=leadgen_postgres)" ]; then
    docker stop leadgen_postgres > /dev/null
fi

if [ "$(docker ps -q -f name=leadgen_redis)" ]; then
    docker stop leadgen_redis > /dev/null
fi

echo "=================================================="
echo "Cleanup complete! All services successfully stopped."
echo "=================================================="
