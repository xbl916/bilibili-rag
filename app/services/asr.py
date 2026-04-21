"""
Bilibili Wiki 知识库系统

ASR 服务 - 支持 DashScope 和本地 OpenAI 格式 ASR
"""
import asyncio
import json
import os
import shutil
import subprocess
import time
from typing import Optional, Any
from urllib import request as urlrequest

import httpx
from loguru import logger

from app.config import settings


class ASRService:
    """音频转文字服务 - 支持 DashScope 和本地 OpenAI 格式 ASR"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        use_local: bool = False,
    ):
        self.use_local = use_local or getattr(settings, "asr_use_local", False)
        
        if self.use_local:
            # 本地 OpenAI 格式 ASR
            self.api_key = api_key or settings.local_asr_api_key
            self.base_url = base_url or settings.local_asr_base_url
            self.model = model or settings.local_asr_model
            self.timeout = timeout or getattr(settings, "asr_timeout", 600)
            logger.info("使用本地 OpenAI 格式 ASR 服务")
        else:
            # DashScope ASR
            self.api_key = api_key or settings.openai_api_key
            self.base_url = base_url or getattr(settings, "dashscope_base_url", None)
            self.model = model or getattr(settings, "asr_model", "paraformer-v2")
            self.timeout = timeout or getattr(settings, "asr_timeout", 600)
            logger.info("使用 DashScope ASR 服务")

    def _configure(self) -> None:
        if not self.api_key:
            raise ValueError("未配置 DASHSCOPE API Key")
        dashscope.api_key = self.api_key
        if self.base_url:
            dashscope.base_http_api_url = self.base_url

    def _get_output_value(self, output: Any, key: str, default=None):
        if isinstance(output, dict):
            return output.get(key, default)
        return getattr(output, key, default)

    def _transcode_audio_to_pcm(self, file_path: str) -> Optional[str]:
        """转码为 16k s16le PCM，适配 Recognition"""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            logger.info("未检测到 ffmpeg，无法转码为 PCM")
            return None
        base, _ext = os.path.splitext(file_path)
        pcm_path = base + ".pcm"
        cmd = [
            ffmpeg,
            "-y",
            "-i", file_path,
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "-ac", "1",
            "-ar", "16000",
            pcm_path,
        ]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode != 0:
                err = (result.stderr or "").strip()
                logger.warning(f"转码 PCM 失败: {err[:200]}")
                return None
            return pcm_path
        except Exception as e:
            logger.warning(f"转码 PCM 异常: {e}")
            return None

    def _transcode_audio_to_mp3(self, input_path: str, output_path: str) -> Optional[str]:
        """将音频转码为 MP3 格式"""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            logger.info("未检测到 ffmpeg，无法转码为 MP3")
            return None
        
        cmd = [
            ffmpeg,
            "-y",
            "-i", input_path,
            "-codec:a", "libmp3lame",
            "-q:a", "2",
            output_path,
        ]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode != 0:
                err = (result.stderr or "").strip()
                logger.warning(f"转码 MP3 失败: {err[:200]}")
                return None
        except Exception as e:
            logger.warning(f"转码 MP3 异常: {e}")
            return None
        
        if not os.path.exists(output_path) or os.path.getsize(output_path) < 1024:
            logger.warning("转码 MP3 输出过小")
            return None
        
        logger.info(f"转码 MP3 完成: {output_path}")
        return output_path

    def _transcode_mp3_to_wav(self, input_path: str) -> Optional[str]:
        """将 MP3 转码为 16k 单声道 WAV（用于本地 ASR）"""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            logger.info("未检测到 ffmpeg，无法转码为 WAV")
            return None
        
        base, _ext = os.path.splitext(input_path)
        wav_path = base + ".wav"
        
        cmd = [
            ffmpeg,
            "-y",
            "-i", input_path,
            "-ac", "1",
            "-ar", "16000",
            "-vn",
            wav_path,
        ]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode != 0:
                err = (result.stderr or "").strip()
                logger.warning(f"转码 WAV 失败: {err[:200]}")
                return None
        except Exception as e:
            logger.warning(f"转码 WAV 异常: {e}")
            return None
        
        if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 1024:
            logger.warning("转码 WAV 输出过小")
            return None
        
        logger.info(f"MP3 转 WAV 完成: {wav_path}")
        return wav_path

    def _transcode_audio_to_wav(self, file_path: str) -> Optional[str]:
        """转码为 16k 单声道 WAV"""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            logger.info("未检测到 ffmpeg，无法转码为 WAV")
            return None
        base, _ext = os.path.splitext(file_path)
        wav_path = base + ".wav"
        cmd = [
            ffmpeg,
            "-y",
            "-i", file_path,
            "-ac", "1",
            "-ar", "16000",
            "-vn",
            wav_path,
        ]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode != 0:
                err = (result.stderr or "").strip()
                logger.warning(f"转码 WAV 失败: {err[:200]}")
                return None
            return wav_path
        except Exception as e:
            logger.warning(f"转码 WAV 异常: {e}")
            return None

    def _prepare_recognition_input(self, file_path: str) -> Optional[str]:
        """按输入格式准备 Recognition 文件"""
        fmt = (self.input_format or "pcm").lower()
        if fmt == "wav":
            return self._transcode_audio_to_wav(file_path)
        return self._transcode_audio_to_pcm(file_path)

    def _recognize_local_file(self, file_path: str) -> Optional[str]:
        """使用 Recognition 直传本地音频"""
        self._configure()
        if not os.path.exists(file_path):
            logger.warning(f"ASR 本地文件不存在: {file_path}")
            return None

        input_path = self._prepare_recognition_input(file_path)
        if not input_path:
            return None

        logger.info(
            f"ASR Recognition 使用模型: {self.local_model or self.model}, format={self.input_format or 'pcm'}"
        )

        try:
            recognizer = Recognition(
                model=self.local_model or self.model,
                callback=None,
                format=(self.input_format or "pcm"),
                sample_rate=16000,
            )
            result = recognizer.call(input_path)
            logger.info(
                "ASR Recognition 结果: status_code={}, code={}, message={}, request_id={}",
                getattr(result, "status_code", None),
                getattr(result, "code", None),
                getattr(result, "message", None),
                getattr(result, "request_id", None),
            )
            sentences = result.get_sentence() or []
            if isinstance(sentences, dict):
                sentences = [sentences]
            texts = []
            for s in sentences:
                if isinstance(s, dict):
                    t = s.get("text") or ""
                    if t:
                        texts.append(t)
            text = "\n".join(texts).strip() if texts else None
            if text:
                preview = text[:120].replace("\n", " ").strip()
                logger.info(f"ASR Recognition 成功，长度={len(text)}，预览：{preview}")
            return text
        except Exception as e:
            logger.warning(f"ASR Recognition 异常: {e}")
            return None
        finally:
            for path in {file_path, input_path}:
                try:
                    if path and os.path.exists(path):
                        os.remove(path)
                except Exception:
                    logger.debug(f"ASR 临时文件清理失败: {path}")

    def _download_transcription(self, url: str) -> Optional[str]:
        try:
            raw = urlrequest.urlopen(url).read().decode("utf-8")
            data = json.loads(raw)
        except Exception as e:
            logger.warning(f"ASR 结果下载失败: {e}")
            return None

        texts = []
        transcripts = data.get("transcripts") or []
        for item in transcripts:
            text = item.get("text", "") or ""
            if text:
                texts.append(text)
                continue
            for s in item.get("sentences", []) or []:
                s_text = s.get("text", "") or ""
                if s_text:
                    texts.append(s_text)

        if not texts and isinstance(data.get("text"), str):
            texts.append(data["text"])

        return "\n".join(texts).strip() if texts else None

    def _build_api_url(self, *parts: str) -> str:
        base_url = self.base_url or getattr(dashscope, "base_http_api_url", None)
        if not base_url:
            base_url = "https://dashscope.aliyuncs.com/api/v1"
        return join_url(base_url, *parts)

    def _submit_transcription_task_restful(self, audio_url: str, model: str) -> Optional[str]:
        url = self._build_api_url("services", "audio", "asr", "transcription")
        headers = {
            **default_headers(self.api_key),
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        parameters = {}
        if "paraformer" in model:
            parameters["language_hints"] = ["zh", "en"]
        payload = {"model": model, "input": {"file_urls": [audio_url]}}
        if parameters:
            payload["parameters"] = parameters

        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
        except Exception as e:
            logger.warning(f"ASR RESTful 提交失败: {e}")
            return None

        if resp.status_code != HTTPStatus.OK:
            logger.warning(f"ASR RESTful 提交失败: status_code={resp.status_code}, body={resp.text[:300]}")
            return None

        data = resp.json()
        task_id = data.get("task_id")
        if not task_id:
            output = data.get("output") if isinstance(data, dict) else None
            if isinstance(output, dict):
                task_id = output.get("task_id")
        return task_id

    def _fetch_transcription_task_restful(self, task_id: str) -> Optional[dict]:
        url = self._build_api_url("tasks", task_id)
        headers = default_headers(self.api_key)
        try:
            resp = httpx.get(url, headers=headers, timeout=30.0)
        except Exception as e:
            logger.warning(f"ASR RESTful 查询失败: {e}")
            return None

        if resp.status_code != HTTPStatus.OK:
            logger.warning(f"ASR RESTful 查询失败: status_code={resp.status_code}, body={resp.text[:300]}")
            return None

        data = resp.json()
        if isinstance(data, dict) and isinstance(data.get("output"), dict):
            return data["output"]
        return data if isinstance(data, dict) else None

    def _transcribe_sync_restful(self, audio_url: str, model: str) -> Optional[str]:
        self._configure()
        task_id = self._submit_transcription_task_restful(audio_url, model)
        if not task_id:
            logger.warning("ASR RESTful 未返回 task_id")
            return None
        logger.info(f"ASR 任务已提交(RESTful): task_id={task_id}")

        start = time.time()
        output = None
        while True:
            if time.time() - start > self.timeout:
                logger.warning("ASR 任务超时(RESTful)")
                return None
            output = self._fetch_transcription_task_restful(task_id)
            if not output:
                time.sleep(1.5)
                continue
            status = self._get_output_value(output, "task_status")
            if status in ("SUCCEEDED", "FAILED"):
                break
            time.sleep(1.5)

        results = self._get_output_value(output, "results", []) or []
        status_message = self._get_output_value(output, "status_message")
        logger.info(
            "ASR 任务状态(RESTful): task_id={}, task_status={}, status_code={}, status_message={}, results={}",
            task_id,
            self._get_output_value(output, "task_status"),
            HTTPStatus.OK,
            status_message,
            len(results),
        )
        for item in results:
            sub_status = item.get("subtask_status")
            transcription_url = item.get("transcription_url")
            error_message = item.get("error_message") or item.get("message")
            if sub_status:
                logger.info(
                    "ASR 子任务状态(RESTful): task_id={}, subtask_status={}, has_url={}, error={}",
                    task_id,
                    sub_status,
                    bool(transcription_url),
                    error_message,
                )
            if sub_status == "SUCCEEDED" and transcription_url:
                return self._download_transcription(transcription_url)

        logger.warning("ASR 未返回有效转写结果(RESTful)")
        return None

    def _transcribe_sync(self, audio_url: str) -> Optional[str]:
        self._configure()
        if audio_url.startswith("oss://"):
            return self._transcribe_sync_restful(audio_url, self.model)

        kwargs = {}
        if "paraformer" in self.model:
            kwargs["language_hints"] = ["zh", "en"]

        try:
            resp = Transcription.async_call(
                model=self.model,
                file_urls=[audio_url],
                **kwargs,
            )
        except Exception as e:
            logger.warning(f"ASR 提交失败: {e}")
            return None

        output = getattr(resp, "output", None)
        task_id = self._get_output_value(output, "task_id")
        if not task_id:
            logger.warning("ASR 未返回 task_id")
            return None
        logger.info(f"ASR 任务已提交: task_id={task_id}")

        start = time.time()
        while True:
            status = self._get_output_value(output, "task_status")
            if status in ("SUCCEEDED", "FAILED"):
                break
            if time.time() - start > self.timeout:
                logger.warning("ASR 任务超时")
                return None
            time.sleep(1.5)
            resp = Transcription.fetch(task=task_id)
            output = getattr(resp, "output", None)

        status_code = getattr(resp, "status_code", None)
        if status_code != HTTPStatus.OK:
            logger.warning(f"ASR 请求失败: status_code={status_code}")
            return None

        results = self._get_output_value(output, "results", []) or []
        status_message = self._get_output_value(output, "status_message")
        logger.info(
            "ASR 任务状态: task_id={}, task_status={}, status_code={}, status_message={}, results={}",
            task_id,
            self._get_output_value(output, "task_status"),
            status_code,
            status_message,
            len(results),
        )
        for item in results:
            sub_status = item.get("subtask_status")
            transcription_url = item.get("transcription_url")
            error_message = item.get("error_message") or item.get("message")
            if sub_status:
                logger.info(
                    "ASR 子任务状态: task_id={}, subtask_status={}, has_url={}, error={}",
                    task_id,
                    sub_status,
                    bool(transcription_url),
                    error_message,
                )
            if sub_status == "SUCCEEDED" and transcription_url:
                return self._download_transcription(item["transcription_url"])

        logger.warning("ASR 未返回有效转写结果")
        return None

    def _upload_temp_file(self, file_path: str, model: Optional[str] = None) -> Optional[str]:
        """上传本地文件到 DashScope 临时 OSS，返回 oss:// URL"""
        self._configure()
        if not os.path.exists(file_path):
            logger.warning(f"ASR 本地文件不存在: {file_path}")
            return None
        try:
            upload_model = model or self.local_model or self.model
            oss_url = OssUtils.upload(
                model=upload_model,
                file_path=file_path,
                api_key=self.api_key,
            )
            logger.info(f"ASR 临时文件上传成功: {oss_url}")
            return oss_url
        except Exception as e:
            logger.warning(f"ASR 临时文件上传失败: {e}")
            return None

    async def _transcribe_url_with_download(self, audio_url: str, cookies: dict = None) -> Optional[str]:
        """先下载音频到本地，再使用本地 Whisper ASR 处理"""
        try:
            # 下载音频到临时文件
            temp_dir = os.path.join("data", "asr_tmp")
            os.makedirs(temp_dir, exist_ok=True)
            
            temp_file = os.path.join(temp_dir, f"audio_{int(time.time())}.m4s")
            downloaded = await self._download_audio(audio_url, temp_file, cookies=cookies)
            
            if not downloaded or not os.path.exists(temp_file) or os.path.getsize(temp_file) < 1024:
                logger.warning("音频下载失败或文件过小")
                return None
            
            # 使用本地 Whisper 转写
            result = await self._call_local_asr(temp_file)
            
            # 清理临时文件
            try:
                os.remove(temp_file)
            except:
                pass
            
            return result
        except Exception as e:
            import traceback
            logger.warning(f"ASR 转写失败：{e}\n{traceback.format_exc()}")
            return None

    async def transcribe_url(self, audio_url: str, cookies: dict = None) -> Optional[str]:
        """转写音频 URL"""
        # 对于需要 Cookie 的音频 URL（如 B 站），先下载到本地再处理
        if "bilivideo.com" in audio_url or "bilibili.com" in audio_url:
            logger.info("检测到 B 站音频 URL，先下载到本地再处理")
            return await self._transcribe_url_with_download(audio_url, cookies=cookies)
        
        if self.use_local:
            return await self._transcribe_url_local(audio_url, cookies=cookies)
        return await asyncio.to_thread(self._transcribe_sync, audio_url)

    async def transcribe_local_file(self, file_path: str) -> Optional[str]:
        """本地文件直传识别"""
        if self.use_local:
            return await self._transcribe_local_file_local(file_path)
        return await asyncio.to_thread(self._recognize_local_file, file_path)

    async def _transcribe_url_local(self, audio_url: str, cookies: dict = None) -> Optional[str]:
        """本地 OpenAI 格式 ASR - 转写音频 URL（下载后转码为 MP3，再转为 WAV）"""
        try:
            # 下载音频到临时文件
            temp_dir = os.path.join("data", "asr_tmp")
            os.makedirs(temp_dir, exist_ok=True)
            
            # 先下载为原始格式
            temp_raw = os.path.join(temp_dir, f"audio_{int(time.time())}.m4s")
            downloaded = await self._download_audio(audio_url, temp_raw, cookies=cookies)
            
            if not downloaded or not os.path.exists(temp_raw) or os.path.getsize(temp_raw) < 1024:
                logger.warning(f"音频文件过小或不存在：{temp_raw}")
                return None
            
            # 转码为 MP3
            temp_mp3 = os.path.join(temp_dir, f"audio_{int(time.time())}.mp3")
            mp3_success = self._transcode_audio_to_mp3(temp_raw, temp_mp3)
            
            # 清理原始文件
            try:
                os.remove(temp_raw)
            except:
                pass
            
            if mp3_success and os.path.exists(temp_mp3):
                use_path = temp_mp3
                logger.info(f"使用转码后的 MP3 文件: {use_path}")
            else:
                use_path = temp_raw
                logger.warning(f"MP3 转码失败，使用原始文件")
            
            # 调用本地 ASR（内部会自动将 MP3 转为 WAV）
            result = await self._call_local_asr(use_path)
            
            # 清理 MP3 文件
            if mp3_success and os.path.exists(temp_mp3):
                try:
                    os.remove(temp_mp3)
                except:
                    pass
            
            return result
        except Exception as e:
            logger.warning(f"本地 ASR 转写失败：{e}")
            return None

    async def _transcribe_local_file_local(self, file_path: str) -> Optional[str]:
        """本地 OpenAI 格式 ASR - 转写本地文件"""
        try:
            result = await self._call_local_asr(file_path)
            return result
        except Exception as e:
            logger.warning(f"本地 ASR 转写失败：{e}")
            return None

    async def _download_audio(self, url: str, file_path: str, cookies: dict = None) -> bool:
        """下载音频到本地文件"""
        try:
            # 构建完整的请求头（必须包含 User-Agent）
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com/",
                "Origin": "https://www.bilibili.com",
            }
            if cookies:
                # 手动将 Cookie 添加到请求头（httpx 的 cookies 参数不会自动添加到 Cookie 头）
                cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
                headers["Cookie"] = cookie_header
            
            logger.info(f"开始下载音频: {url[:100]}...")
            logger.info(f"Cookie: {list(cookies.keys()) if cookies else 'None'}")
            logger.info(f"Headers: {headers}")
            
            async with httpx.AsyncClient(timeout=60.0, headers=headers) as client:
                response = await client.get(url)
                logger.info(f"下载响应: status={response.status_code}, content_len={len(response.content)}")
                
                if response.status_code == 200:
                    with open(file_path, 'wb') as f:
                        f.write(response.content)
                    import os
                    file_size = os.path.getsize(file_path)
                    logger.info(f"音频下载成功，保存到 {file_path}，文件大小={file_size} 字节")
                    return True
                else:
                    logger.warning(f"下载响应异常: status={response.status_code}, text={response.text[:200] if response.text else 'empty'}")
            return False
        except Exception as e:
            import traceback
            logger.warning(f"下载音频失败：{e}\n{traceback.format_exc()}")
            return False

    async def _call_local_asr(self, file_path: str) -> Optional[str]:
        """调用本地 OpenAI 格式 ASR 服务（自动将 MP3 转为 WAV）"""
        try:
            # 如果输入是 MP3 文件，先转码为 WAV
            use_path = file_path
            mp3_temp_cleaned = False
            
            if file_path.endswith('.mp3'):
                logger.info(f"检测到 MP3 文件，自动转码为 WAV: {file_path}")
                wav_path = self._transcode_mp3_to_wav(file_path)
                if wav_path and os.path.exists(wav_path):
                    use_path = wav_path
                    mp3_temp_cleaned = True  # 标记需要清理 MP3 原始文件
                else:
                    logger.warning("MP3 转 WAV 失败，尝试直接使用原始文件")
            
            # 确保 base_url 包含协议
            base_url = self.base_url or settings.local_asr_base_url
            if not base_url or not base_url.startswith(("http://", "https://")):
                base_url = f"http://{base_url}" if base_url else "http://localhost:1234/v1"
            
            # 如果 base_url 已经包含 /v1，直接使用；否则追加 /v1
            if not base_url.endswith("/v1"):
                api_path = "/v1/audio/transcriptions"
            else:
                api_path = "/audio/transcriptions"
            
            url = f"{base_url}{api_path}"
            
            # 使用本地 Whisper 模型（优先使用 settings 配置）
            model = settings.local_asr_model or self.model
            
            logger.info(f"本地 ASR 请求 URL: {url}, 模型: {model}, 文件: {use_path}")
            
            with open(use_path, 'rb') as f:
                files = {'file': (os.path.basename(use_path), f)}
                data = {
                    'model': model,
                    'language': 'zh',
                }
                
                headers = {
                    'Authorization': f'Bearer {self.api_key}'
                }
                
                async with httpx.AsyncClient(timeout=300.0) as client:
                    response = await client.post(
                        url,
                        files=files,
                        data=data,
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        text = result.get('text', '')
                        logger.info(f"本地 ASR 成功，长度={len(text)}")
                        return text
                    else:
                        logger.warning(f"本地 ASR 失败：{response.status_code} - {response.text[:200]}")
                        return None
                        
        except Exception as e:
            logger.warning(f"调用本地 ASR 失败：{e}")
            return None
        finally:
            # 清理临时 WAV 文件（如果创建了的话）
            if use_path != file_path and os.path.exists(use_path):
                try:
                    os.remove(use_path)
                    logger.debug(f"清理临时 WAV 文件: {use_path}")
                except Exception:
                    pass

    def _transcribe_sync_with_model(self, audio_url: str, model: str) -> Optional[str]:
        """使用指定模型转写（用于本地文件上传）"""
        if audio_url.startswith("oss://"):
            return self._transcribe_sync_restful(audio_url, model)
        original_model = self.model
        try:
            self.model = model
            return self._transcribe_sync(audio_url)
        finally:
            self.model = original_model
