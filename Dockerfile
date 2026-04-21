# ========== 第一阶段: 构建前端 ==========
FROM node:20-alpine AS frontend-builder

WORKDIR /build

# 复制 package.json 和 package-lock.json (如果存在)
COPY frontend/package.json frontend/package-lock.json* ./

# 安装依赖并构建前端
RUN npm ci || npm install
COPY frontend/ ./

# 构建前端 (output: 'export' 会生成 out/ 目录)
RUN npm run build

# 构建产物在 out/ 目录
# 下一步会复制到最终镜像

# ========== 第二阶段: 构建后端 + 最终镜像 ==========
FROM python:3.11-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    curl \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制 Python 依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端应用代码
COPY app/ ./app/

# 从第一阶段复制前端构建产物
COPY --from=frontend-builder /build/out /app/frontend-out

# 复制 Nginx 配置和启动脚本
COPY nginx.conf /etc/nginx/nginx.conf
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# 创建必要目录
RUN mkdir -p data logs data/wiki schema

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV APP_HOST=0.0.0.0
ENV APP_PORT=8000

# 暴露端口 (Nginx 统一入口)
EXPOSE 80

# 健康检查 (通过 Nginx 代理到后端)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:80/health || exit 1

# 启动脚本 (启动后端 + Nginx)
CMD ["/bin/bash", "/app/start.sh"]
