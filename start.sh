#!/bin/bash

# Stop on first error
set -e

echo "Checking and starting infrastructure (Postgres & Redis)..."

# Start Postgres if not running
if [ ! "$(docker ps -q -f name=leadgen_postgres)" ]; then
    if [ "$(docker ps -aq -f status=exited -f name=leadgen_postgres)" ]; then
        docker rm leadgen_postgres > /dev/null
    fi
    echo "Starting PostgreSQL container..."
    docker run -d --name leadgen_postgres -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=admin123 -e POSTGRES_DB=mydb -p 5432:5432 postgres:15-alpine
else
    echo "PostgreSQL is already running."
fi

# Start Redis if not running
if [ ! "$(docker ps -q -f name=leadgen_redis)" ]; then
    if [ "$(docker ps -aq -f status=exited -f name=leadgen_redis)" ]; then
        docker rm leadgen_redis > /dev/null
    fi
    echo "Starting Redis container..."
    docker run -d --name leadgen_redis -p 6379:6379 redis:7-alpine redis-server --requirepass redis123
else
    echo "Redis is already running."
fi

echo "Moving to backend directory to start services..."
cd backend

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Waiting for database to initialize before migrations..."
sleep 5

echo "Running database migrations..."
alembic upgrade head

echo "Starting FastAPI Backend Server on port 8000..."
uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "Starting Celery Worker..."
# Running natively so Chrome will pop up on your screen naturally
celery -A app.tasks.celery_app worker --loglevel=info &
CELERY_PID=$!

echo "Starting Native Frontend Server on port 3000..."
cd ../frontend
python3 -m http.server 3000 &
FRONTEND_PID=$!

echo "=================================================="
echo "All services are now running natively!"
echo "Frontend: http://localhost:3000"
echo "Backend API: http://localhost:8000"
echo "Logs are streaming below. Press Ctrl+C to stop all."
echo "=================================================="

# Function to handle graceful shutdown
cleanup() {
    echo ""
    echo "Caught shutdown signal! Stopping local services..."
    kill $BACKEND_PID $CELERY_PID $FRONTEND_PID 2>/dev/null || true
    echo "Stopping infrastructure containers..."
    docker stop leadgen_postgres leadgen_redis > /dev/null || true
    echo "Cleanup complete. Exiting."
    exit 0
}

# Trap Ctrl+C and termination signals
trap cleanup SIGINT SIGTERM

# Wait for background processes so the script doesn't exit immediately
wait $BACKEND_PID $CELERY_PID $FRONTEND_PID
