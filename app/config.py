"""
Bilibili Wiki 知识库系统

核心配置模块
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    """应用配置"""
    
    # ==================== OpenAI API 配置（兼容旧字段） ====================
    # 注意：LLM/VLM/视觉分析现在共用 LLM_BASE_URL 和 LLM_API_KEY
    # 以下字段仅为向后兼容，新配置请使用下面的统一字段
    openai_api_key: str = Field(
        default="",
        env="OPENAI_API_KEY"
    )
    openai_base_url: str = Field(
        default="http://localhost:8000/v1",
        env="OPENAI_BASE_URL"
    )
    llm_model: str = Field(
        default="qwen3.5-35b-a3b",
        env="LLM_MODEL"
    )
    
    # ==================== 应用配置 ====================
    app_host: str = Field(default="0.0.0.0", env="APP_HOST")
    app_port: int = Field(default=8000, env="APP_PORT")
    debug: bool = Field(default=True, env="DEBUG")
    
    # ==================== 数据库配置 ====================
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/bilibili_rag.db",
        env="DATABASE_URL"
    )
    
    # ==================== 大模型服务配置 (LLM/VLM/视觉分析共用) ====================
    # 模型服务地址（兼容 OpenAI 格式）
    llm_base_url: str = Field(
        default="http://localhost:3000/v1",
        env="LLM_BASE_URL"
    )
    # 模型 API Key
    llm_api_key: str = Field(
        default="",
        env="LLM_API_KEY"
    )
    # LLM 模型名称（用于文本生成和概念/实体提取）
    llm_model_name: str = Field(
        default="qwen3.5-35b-a3b",
        env="LLM_MODEL"
    )
    # VLM 模型名称（用于视觉分析和视频理解）
    vlm_model: str = Field(
        default="qwen2.5-vl-72b-instruct",
        env="VLM_MODEL"
    )
    
    # ==================== 视觉分析配置 ====================
    vision_enabled: bool = Field(default=False, env="VISION_ENABLED")
    vision_timeout: int = Field(
        default=300,
        env="VISION_TIMEOUT"
    )
    vision_model: str = Field(
        default="Qwen3.5-VL",
        env="VISION_MODEL"
    )
    
    # ==================== 本地 ASR 配置 ====================
    asr_base_url: str = Field(
        default="http://localhost:1234/v1",
        env="ASR_BASE_URL"
    )
    asr_api_key: str = Field(
        default="",
        env="ASR_API_KEY"
    )
    asr_model: str = Field(
        default="whisper",
        env="ASR_MODEL"
    )
    asr_timeout: int = Field(
        default=600,
        env="ASR_TIMEOUT"
    )
    
    # ==================== 视频抽帧配置 ====================
    frame_interval: int = Field(
        default=10,
        env="FRAME_INTERVAL"
    )
    frame_strategy: str = Field(
        default="keyframe",
        env="FRAME_STRATEGY"
    )
    max_video_duration: int = Field(
        default=600,
        env="MAX_VIDEO_DURATION"
    )
    max_frames_per_video: int = Field(
        default=20,
        env="MAX_FRAMES_PER_VIDEO"
    )
    
    # ==================== Wiki 构建配置 ====================
    wiki_enabled: bool = Field(default=True, env="WIKI_ENABLED")
    wiki_dir: str = Field(default="./data/wiki", env="WIKI_DIR")
    wiki_schema: str = Field(default="schema/BILIBILI_WIKI.md", env="WIKI_SCHEMA")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# 全局配置实例
settings = Settings()


def ensure_directories():
    """确保必要的目录存在"""
    dirs = [
        "data",
        "logs"
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)