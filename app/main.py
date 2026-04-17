"""
Bilibili Wiki 知识库系统

基于 Karpathy LLM Wiki 方案的主应用入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import sys

from app.config import settings, ensure_directories
from app.database import init_db
from app.routers import auth, favorites, knowledge, chat


# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="DEBUG" if settings.debug else "INFO"
)
logger.add(
    "logs/app.log",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("🚀 Bilibili Wiki 知识库系统启动中...")
    ensure_directories()
    await init_db()
    logger.info("✅ 数据库初始化完成")
    
    yield
    
    # 关闭时
    logger.info("👋 应用关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="Bilibili Wiki 知识库系统",
    description="""
## 项目简介

基于 Karpathy LLM Wiki 方案，将你的 B 站收藏夹变成可对话的持久化知识库！

### 功能特性

- 🔐 **B 站扫码登录** - 安全便捷
- 📁 **收藏夹管理** - 查看和选择收藏夹
- 🤖 **AI 内容提取** - 自动获取视频摘要/字幕
- 📚 **Wiki 构建** - 增量构建结构化知识库
- 💬 **智能问答** - 基于 Wiki 回答问题

### 技术栈

- FastAPI + Qwen3.5 (本地 vLLM)
- 基于 Karpathy LLM Wiki 方案
- B 站 API (非官方)
    """,
    version="0.1.0",
    lifespan=lifespan
)


# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 注册路由
app.include_router(auth.router)
app.include_router(favorites.router)
app.include_router(knowledge.router)
app.include_router(chat.router)


@app.get("/")
async def root():
    """API 根路径"""
    return {
        "message": "🎬 Bilibili Wiki 知识库系统",
        "version": "0.1.0",
        "docs": "/docs",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug
    )