#!/bin/bash
set -e

cd "$(dirname "$0")"

# Start backend
echo "Starting backend..."
cd backend
source ../venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Start frontend
echo "Starting frontend..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "==================================="
echo "  Image Catalog is running!"
echo "  Frontend: http://10.0.1.98:5173"
echo "  Backend:  http://10.0.1.98:8000"
echo "  API docs: http://10.0.1.98:8000/docs"
echo "==================================="
echo ""

# Wait for either to exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
