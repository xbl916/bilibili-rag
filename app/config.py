"""
Bilibili Wiki 知识库系统

核心配置模块
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
import os

# 获取项目根目录（.env 文件所在目录）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Settings(BaseSettings):
    """应用配置"""
    
    model_config = SettingsConfigDict(
        env_file=os.path.join(BASE_DIR, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # ==================== 应用配置 ====================
    app_host: str = Field(default="0.0.0.0", validation_alias="APP_HOST")
    app_port: int = Field(default=8000, validation_alias="APP_PORT")
    debug: bool = Field(default=True, validation_alias="DEBUG")
    
    # ==================== 数据库配置 ====================
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/bilibili_rag.db",
        validation_alias="DATABASE_URL"
    )
    
    # ==================== 大模型服务配置 (LLM/VLM/视觉分析共用) ====================
    # 模型服务地址（兼容 OpenAI 格式）
    llm_base_url: str = Field(
        default="http://localhost:3000/v1",
        validation_alias="LLM_BASE_URL"
    )
    # 模型 API Key
    llm_api_key: str = Field(
        default="",
        validation_alias="LLM_API_KEY"
    )
    # LLM 模型名称（用于文本生成和概念/实体提取）
    llm_model_name: str = Field(
        default="",
        validation_alias="LLM_MODEL"
    )
    # VLM 模型名称（用于视觉分析和视频理解）
    vlm_model: str = Field(
        default="qwen2.5-vl-72b-instruct",
        validation_alias="VLM_MODEL"
    )
    
    # ==================== 视觉分析配置 ====================
    vision_enabled: bool = Field(default=False, validation_alias="VISION_ENABLED")
    vision_timeout: int = Field(
        default=300,
        validation_alias="VISION_TIMEOUT"
    )
    vision_model: str = Field(
        default="Qwen3.5-VL",
        validation_alias="VISION_MODEL"
    )
    
    # ==================== 本地 ASR 配置 ====================
    asr_base_url: str = Field(
        default="http://localhost:1234/v1",
        validation_alias="ASR_BASE_URL"
    )
    asr_api_key: str = Field(
        default="",
        validation_alias="ASR_API_KEY"
    )
    asr_model: str = Field(
        default="whisper",
        validation_alias="ASR_MODEL"
    )
    asr_timeout: int = Field(
        default=600,
        validation_alias="ASR_TIMEOUT"
    )
    
    # ==================== 视频抽帧配置 ====================
    frame_interval: int = Field(
        default=10,
        validation_alias="FRAME_INTERVAL"
    )
    frame_strategy: str = Field(
        default="keyframe",
        validation_alias="FRAME_STRATEGY"
    )
    max_video_duration: int = Field(
        default=600,
        validation_alias="MAX_VIDEO_DURATION"
    )
    max_frames_per_video: int = Field(
        default=20,
        validation_alias="MAX_FRAMES_PER_VIDEO"
    )
    
    # ==================== Wiki 构建配置 ====================
    wiki_enabled: bool = Field(default=True, validation_alias="WIKI_ENABLED")
    wiki_dir: str = Field(default="./data/wiki", validation_alias="WIKI_DIR")
    wiki_schema: str = Field(default="schema/BILIBILI_WIKI.md", validation_alias="WIKI_SCHEMA")
    
    # ==================== 向后兼容别名 ====================
    # 以下字段用于向后兼容，直接从对应的环境变量读取
    openai_api_key: str = Field(default="", validation_alias="LLM_API_KEY")
    openai_base_url: str = Field(default="", validation_alias="LLM_BASE_URL")
    local_asr_api_key: str = Field(default="", validation_alias="ASR_API_KEY")
    local_asr_base_url: str = Field(default="", validation_alias="ASR_BASE_URL")
    local_asr_model: str = Field(default="", validation_alias="ASR_MODEL")


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
