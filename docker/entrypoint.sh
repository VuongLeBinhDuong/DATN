#!/bin/bash
# docker/entrypoint.sh
set -e

# Chạy kịch bản kiểm tra dịch vụ nền và tự động cấu hình/import dữ liệu
python scripts/wait_for_services.py

# Xác định số lượng workers (WEB_CONCURRENCY) từ biến môi trường hoặc mặc định là 4
WORKERS=${WEB_CONCURRENCY:-4}

echo "[*] Starting Uvicorn production server with ${WORKERS} workers..."
exec python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers "$WORKERS"
