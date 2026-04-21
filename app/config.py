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
    
    # ==================== OpenAI API 配置（用于 LLM 和 Embeddings） ====================
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
    
    # ==================== 本地 LLM 配置 ====================
    local_llm_base_url: str = Field(
        default="http://localhost:8000/v1",
        env="LOCAL_LLM_BASE_URL"
    )
    local_llm_api_key: str = Field(
        default="",
        env="LOCAL_LLM_API_KEY"
    )
    local_llm_model: str = Field(
        default="qwen3.5-35b-a3b",
        env="LOCAL_LLM_MODEL"
    )
    
    # ==================== 本地 ASR 配置 ====================
    local_asr_base_url: str = Field(
        default="http://localhost:1234/v1",
        env="LOCAL_ASR_BASE_URL"
    )
    local_asr_api_key: str = Field(
        default="",
        env="LOCAL_ASR_API_KEY"
    )
    local_asr_model: str = Field(
        default="whisper",
        env="LOCAL_ASR_MODEL"
    )
    asr_timeout: int = Field(
        default=600,
        env="ASR_TIMEOUT"
    )
    
    # ==================== 本地 VLM 配置 ====================
    local_vlm_base_url: str = Field(
        default="http://localhost:3000/v1",
        env="LOCAL_VLM_BASE_URL"
    )
    local_vlm_api_key: str = Field(
        default="",
        env="LOCAL_VLM_API_KEY"
    )
    local_vlm_model: str = Field(
        default="qwen2.5-vl-72b-instruct",
        env="LOCAL_VLM_MODEL"
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
    
    # ==================== Wiki 构建配置 ====================
    wiki_enabled: bool = Field(default=True, env="WIKI_ENABLED")
    wiki_dir: str = Field(default="./data/wiki", env="WIKI_DIR")
    wiki_schema: str = Field(default="schema/BILIBILI_WIKI.md", env="WIKI_SCHEMA")
    
    # ==================== 视觉分析配置 ====================
    vision_enabled: bool = Field(default=False, env="VISION_ENABLED")
    vision_base_url: str = Field(
        default="http://localhost:3000/v1",
        env="VISION_BASE_URL"
    )
    vision_api_key: str = Field(
        default="",
        env="VISION_API_KEY"
    )
    vision_model: str = Field(
        default="qwen3.5-vl",
        env="VISION_MODEL"
    )
    vision_timeout: int = Field(
        default=300,
        env="VISION_TIMEOUT"
    )
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