"""
Bilibili RAG 知识库系统

视觉分析服务 - 基于 Qwen3.5-VL 的视频分析
"""
import asyncio
import base64
import math
import os
import shutil
import subprocess
import time
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlparse

import httpx
from loguru import logger

from app.config import settings


class VisionService:
    """视觉分析服务 - 支持整体分析和关键帧分析"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 300,
    ):
        self.base_url = base_url or getattr(settings, "vision_base_url", 
                    getattr(settings, "local_vlm_base_url", "http://localhost:3000/v1"))
        self.api_key = api_key or getattr(settings, "vision_api_key", 
                    getattr(settings, "local_vlm_api_key", ""))
        self.model = model or getattr(settings, "vision_model", 
                    getattr(settings, "local_vlm_model", "qwen3.5-vl"))
        self.timeout = timeout or getattr(settings, "vision_timeout", 300)
        self.temp_dir = os.path.join("data", "vision_tmp")
        os.makedirs(self.temp_dir, exist_ok=True)

    async def analyze_video_global(
        self,
        video_url: str,
        title: str = "",
        prompt: str = None,
        duration_limit: int = 600,
    ) -> Optional[Dict[str, Any]]:
        """
        整体视频分析
        
        Args:
            video_url: 视频 URL
            title: 视频标题
            prompt: 自定义提示词
            duration_limit: 最大分析时长（秒）
            
        Returns:
            分析结果字典
        """
        if not settings.vision_enabled:
            logger.info("视觉分析功能未启用，跳过")
            return None

        temp_files = []
        try:
            # 1. 下载视频片段（截断到最大时长）
            video_path = await self._download_video_segment(video_url, duration_limit, temp_files)
            if not video_path or not os.path.exists(video_path):
                logger.warning("视频下载失败，跳过视觉分析")
                return None

            # 2. 构造提示词
            if prompt is None:
                prompt = f"""请对以下视频进行全面分析：

视频标题：{title}

请提供：
1. **内容摘要**：简要描述视频内容
2. **核心概念**：提取 3-10 个关键概念，每个概念包含：
   - 概念名称
   - 定义/解释
   - 在视频中的大致时间点
3. **关键实体**：提取 3-10 个实体（工具、框架、技术、人物等），每个包含：
   - 实体名称
   - 类型（工具/框架/技术/人物/其他）
   - 简短描述
4. **视觉亮点**：描述 3-5 个重要的画面内容（代码截图、图表、演示等）

请严格按照以下 JSON 格式返回，不要包含其他内容：
{{
    "summary": "内容摘要",
    "concepts": [
        {{
            "name": "概念名",
            "definition": "定义",
            "timestamp": 30,
            "importance": "high"
        }}
    ],
    "entities": [
        {{
            "name": "实体名",
            "entity_type": "工具",
            "description": "描述"
        }}
    ],
    "visual_highlights": [
        "视觉亮点描述"
    ]
}}"""

            # 3. 调用 VL API
            result = await self._call_vl_api_with_video(video_path, prompt)

            logger.info(f"视频整体分析完成，标题={title}")
            return result

        except Exception as e:
            logger.warning(f"视频整体分析失败：{e}")
            return None
        finally:
            self._cleanup_temp_files(temp_files)
            # 清理临时视频文件
            for f in temp_files:
                try:
                    if os.path.exists(f):
                        os.remove(f)
                except:
                    pass

    async def analyze_video_keyframes(
        self,
        video_url: str,
        timestamps: List[float],
        asr_contexts: List[str] = None,
        title: str = "",
        frame_count_limit: int = 20,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        关键帧分析
        
        Args:
            video_url: 视频 URL
            timestamps: 需要分析的时间点列表（秒）
            asr_contexts: 对应时间点的 ASR 文本
            title: 视频标题
            frame_count_limit: 最大关键帧数
            
        Returns:
            每个关键帧的分析结果列表
        """
        if not settings.vision_enabled:
            logger.info("视觉分析功能未启用，跳过")
            return None

        temp_files = []
        try:
            # 1. 下载完整视频（关键帧分析需要完整视频来提取帧）
            video_path = await self._download_video(video_url, temp_files)
            if not video_path or not os.path.exists(video_path):
                logger.warning("视频下载失败，跳过关键帧分析")
                return None

            # 2. 限制关键帧数量
            if len(timestamps) > frame_count_limit:
                # 均匀采样
                step = len(timestamps) / frame_count_limit
                timestamps = [timestamps[int(i * step)] for i in range(frame_count_limit)]
                if asr_contexts:
                    asr_contexts = [asr_contexts[int(i * step)] for i in range(frame_count_limit)]

            # 3. 提取关键帧
            frame_paths = await self._extract_frames_at_times(video_path, timestamps, temp_files)
            if not frame_paths:
                logger.warning("关键帧提取失败")
                return None

            # 4. 对每个关键帧进行分析
            results = []
            for i, frame_path in enumerate(frame_paths):
                ts = timestamps[i] if i < len(timestamps) else 0
                asr_text = asr_contexts[i] if asr_contexts and i < len(asr_contexts) else ""

                prompt = self._build_keyframe_prompt(title, ts, asr_text)
                result = await self._call_vl_api_with_image(frame_path, prompt)

                results.append({
                    "timestamp": ts,
                    "asr_context": asr_text,
                    "analysis": result,
                    "frame_path": frame_path,  # 保留用于调试
                })

            logger.info(f"关键帧分析完成，共 {len(results)} 帧")
            return results

        except Exception as e:
            logger.warning(f"关键帧分析失败：{e}")
            return None
        finally:
            self._cleanup_temp_files(temp_files)

    async def _download_video(
        self,
        url: str,
        temp_files: List[str],
        timeout: int = 120,
    ) -> Optional[str]:
        """下载完整视频到临时文件"""
        try:
            bvid = f"video_{int(time.time())}"
            video_path = os.path.join(self.temp_dir, f"{bvid}.mp4")
            temp_files.append(video_path)

            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        logger.warning(f"视频下载失败：status={response.status_code}")
                        return None

                    with open(video_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)

            file_size = os.path.getsize(video_path) if os.path.exists(video_path) else 0
            if file_size < 1024:
                logger.warning(f"视频文件过小：{file_size} 字节")
                return None

            logger.info(f"视频下载完成：{video_path} ({file_size / 1024 / 1024:.1f} MB)")
            return video_path

        except Exception as e:
            logger.warning(f"下载视频失败：{e}")
            return None

    async def _download_video_segment(
        self,
        url: str,
        duration: int,
        temp_files: List[str],
        timeout: int = 120,
    ) -> Optional[str]:
        """
        下载视频片段（使用前 duration 秒）
        
        使用 ffmpeg 截取视频前 N 秒
        """
        try:
            # 1. 先下载完整视频
            full_video_path = await self._download_video(url, temp_files, timeout)
            if not full_video_path:
                return None

            # 2. 获取视频总时长
            total_duration = self._get_video_duration(full_video_path)
            if total_duration is None:
                return full_video_path

            # 3. 如果视频超过限制，截取前 duration 秒
            if total_duration > duration:
                segment_path = os.path.join(self.temp_dir, f"segment_{int(time.time())}.mp4")
                temp_files.append(segment_path)

                success = self._trim_video(full_video_path, segment_path, duration)
                if success:
                    # 清理原始视频
                    try:
                        os.remove(full_video_path)
                        if full_video_path in temp_files:
                            temp_files.remove(full_video_path)
                    except:
                        pass
                    logger.info(f"视频截断完成：{segment_path} ({duration}s)")
                    return segment_path
                else:
                    return full_video_path

            return full_video_path

        except Exception as e:
            logger.warning(f"下载视频片段失败：{e}")
            return None

    async def _extract_frames_at_times(
        self,
        video_path: str,
        timestamps: List[float],
        temp_files: List[str],
    ) -> List[str]:
        """
        从视频中提取指定时间点的帧
        
        Returns:
            提取的帧文件路径列表
        """
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            logger.warning("未检测到 ffmpeg，无法提取关键帧")
            return []

        frame_paths = []
        for ts in timestamps:
            # 确保时间戳在视频范围内
            duration = self._get_video_duration(video_path)
            if duration and ts > duration:
                ts = max(duration - 0.5, 0)

            frame_path = os.path.join(self.temp_dir, f"frame_{int(ts * 1000)}ms.jpg")
            temp_files.append(frame_path)

            try:
                cmd = [
                    ffmpeg,
                    "-y",
                    "-i", video_path,
                    "-ss", str(ts),
                    "-frames:v", "1",
                    "-q:v", "2",  # 高质量
                    frame_path,
                ]
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0 and os.path.exists(frame_path) and os.path.getsize(frame_path) > 100:
                    frame_paths.append(frame_path)
                else:
                    logger.warning(f"提取帧失败：ts={ts}s")

            except Exception as e:
                logger.warning(f"提取帧异常：ts={ts}s, error={e}")

        logger.info(f"关键帧提取完成：{len(frame_paths)}/{len(timestamps)}")
        return frame_paths

    def _get_video_duration(self, video_path: str) -> Optional[float]:
        """获取视频时长（秒）"""
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return None

        try:
            cmd = [
                ffprobe,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception:
            pass
        return None

    def _trim_video(self, input_path: str, output_path: str, duration: int) -> bool:
        """截取视频前 N 秒"""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return False

        try:
            cmd = [
                ffmpeg,
                "-y",
                "-i", input_path,
                "-t", str(duration),
                "-c", "copy",
                output_path,
            ]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
            )
            return result.returncode == 0 and os.path.exists(output_path)
        except Exception as e:
            logger.warning(f"截取视频失败：{e}")
            return False

    def _build_keyframe_prompt(
        self,
        title: str,
        timestamp: float,
        asr_context: str = "",
    ) -> str:
        """构建关键帧分析提示词"""
        prompt = f"""请分析视频在 {timestamp:.1f} 秒时的画面内容。

视频标题：{title}"""

        if asr_context:
            prompt += f"""

此时段的 ASR 转写文本：
{asr_context[:500]}"""

        prompt += """

请提供：
1. **画面描述**：详细描述此时画面中显示的内容
2. **文字内容**：如果画面中有文字（代码、PPT、图表等），请完整提取
3. **关键信息**：这个画面传达的核心信息

请严格按照以下 JSON 格式返回：
{
    "description": "画面描述",
    "text_content": "提取的文字内容（如果有）",
    "key_insight": "关键信息"
}"""
        return prompt

    async def _call_vl_api_with_video(
        self,
        video_path: str,
        prompt: str,
    ) -> Optional[Dict[str, Any]]:
        """
        调用 VL API 分析视频（本地文件）
        
        将本地视频文件转为 base64 发送
        """
        try:
            # 读取视频文件并转为 base64
            video_b64 = self._file_to_base64(video_path)
            if not video_b64:
                return None

            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "video",
                                "video": video_b64,
                            },
                        ],
                    }
                ],
                "temperature": 0.3,
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()

            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return self._parse_llm_response(content)

        except Exception as e:
            logger.warning(f"VL API 调用失败（视频）：{e}")
            return None

    async def _call_vl_api_with_image(
        self,
        image_path: str,
        prompt: str,
    ) -> Optional[Dict[str, Any]]:
        """
        调用 VL API 分析图片（本地文件）
        
        将本地图片文件转为 base64 发送
        """
        try:
            # 读取图片文件并转为 base64
            image_b64 = self._file_to_base64(image_path)
            if not image_b64:
                return None

            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_b64,
                                },
                            },
                        ],
                    }
                ],
                "temperature": 0.3,
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()

            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return self._parse_llm_response(content)

        except Exception as e:
            logger.warning(f"VL API 调用失败（图片）：{e}")
            return None

    def _file_to_base64(self, file_path: str) -> Optional[str]:
        """将文件转为 base64 data URL"""
        try:
            # 确定 MIME 类型
            ext = os.path.splitext(file_path)[1].lower()
            mime_types = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
                ".mp4": "video/mp4",
                ".webm": "video/webm",
            }
            mime_type = mime_types.get(ext, "application/octet-stream")

            with open(file_path, "rb") as f:
                file_data = f.read()

            b64_data = base64.b64encode(file_data).decode("utf-8")
            return f"data:{mime_type};base64,{b64_data}"

        except Exception as e:
            logger.warning(f"文件转 base64 失败：{e}")
            return None

    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
        """解析 LLM 响应，提取 JSON 数据"""
        import json
        import re

        # 尝试直接解析
        try:
            return json.loads(content)
        except:
            pass

        # 尝试从 markdown 代码块中提取 JSON
        match = re.search(r'```(?:json)?\s*\n(.*?)\n```', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                pass

        # 尝试提取第一个 JSON 对象
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass

        # 返回原始文本
        return {"raw": content}

    def _cleanup_temp_files(self, file_paths: List[str]):
        """清理临时文件"""
        for path in file_paths:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

    async def close(self):
        """关闭服务"""
        pass