#!/bin/bash
set -e

# 启动后端服务 (后台运行)
cd /app
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# 等待后端服务启动
sleep 2

# 启动 Nginx (前台运行，作为主进程)
# 先停止可能运行的 nginx，然后启动
nginx -s stop 2>/dev/null || true
sleep 1
nginx -g "daemon off;"