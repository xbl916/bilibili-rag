"""
诊断视频内容获取问题 - 完整版

检查视频的字幕、音频、ASR 等情况
"""
import asyncio
import httpx
import sys
import json
from loguru import logger


async def diagnose_content_fetch(bvid: str, session_id: str = None, api_base: str = "http://localhost:8000"):
    """
    通过 API 服务诊断视频内容获取问题
    """
    logger.info(f"=== 开始诊断视频 {bvid} 的内容获取问题 ===")
    
    bilibili_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. 获取视频基本信息
        logger.info("\n[步骤 1] 获取视频基本信息...")
        try:
            resp = await client.get(
                "https://api.bilibili.com/x/web-interface/view",
                params={"bvid": bvid},
                headers=bilibili_headers
            )
            data = resp.json()
            
            if data.get("code") == 0:
                video_data = data["data"]
                aid = video_data.get("aid")
                cid = video_data.get("cid")
                title = video_data.get("title")
                desc = video_data.get("desc", "")
                
                logger.info(f"  ✓ 视频信息获取成功")
                logger.info(f"  - aid: {aid}")
                logger.info(f"  - cid: {cid}")
                logger.info(f"  - title: {title}")
                logger.info(f"  - 简介: {desc[:100] if desc else '(无)'}...")
                
                # 检查字幕列表（来自视频信息接口）
                subtitle_list = video_data.get("subtitle", {}).get("list", [])
                logger.info(f"\n  [视频信息接口] 字幕数量: {len(subtitle_list)}")
                for i, sub in enumerate(subtitle_list):
                    lan = sub.get("lan", "")
                    lan_doc = sub.get("lan_doc", "")
                    ai_status = sub.get("ai_status", "")
                    url = sub.get("subtitle_url") or sub.get("url", "")
                    logger.info(f"    字幕[{i}]: lan={lan}, lan_doc={lan_doc}, ai_status={ai_status}")
                    logger.info(f"      url 前100字符: {url[:100] if url else 'None'}...")
                
                # 2. 获取播放器信息
                logger.info(f"\n[步骤 2] 获取播放器信息（包含字幕）...")
                player_resp = await client.get(
                    "https://api.bilibili.com/x/player/v2",
                    params={"bvid": bvid, "cid": cid},
                    headers=bilibili_headers
                )
                player_data = player_resp.json()
                
                if player_data.get("code") == 0:
                    player_info = player_data["data"]
                    player_cid = player_info.get("cid")
                    
                    logger.info(f"  ✓ 播放器信息获取成功")
                    logger.info(f"  - 播放器返回的 cid: {player_cid}")
                    
                    if player_cid and cid != player_cid:
                        logger.error(f"  ⚠️ CID 不匹配！请求的 cid={cid}，播放器返回的 cid={player_cid}")
                    else:
                        logger.info(f"  ✓ CID 匹配正确")
                    
                    # 检查播放器字幕
                    subtitle_info = player_info.get("subtitle", {}) or {}
                    subtitles = subtitle_info.get("subtitles") or subtitle_info.get("list") or []
                    
                    logger.info(f"\n  [播放器接口] 字幕数量: {len(subtitles)}")
                    for i, sub in enumerate(subtitles):
                        lan = sub.get("lan", "")
                        lan_doc = sub.get("lan_doc", "")
                        ai_status = sub.get("ai_status", "")
                        subtitle_url = sub.get("subtitle_url") or sub.get("url", "")
                        
                        logger.info(f"    字幕[{i}]:")
                        logger.info(f"      - lan: {lan}")
                        logger.info(f"      - lan_doc: {lan_doc}")
                        logger.info(f"      - ai_status: {ai_status}")
                        logger.info(f"      - url 前150字符: {subtitle_url[:150] if subtitle_url else 'None'}...")
                        
                        # 尝试下载字幕
                        if subtitle_url:
                            if subtitle_url.startswith("//"):
                                subtitle_url = "https:" + subtitle_url
                            try:
                                sub_resp = await client.get(subtitle_url)
                                sub_data = sub_resp.json()
                                sub_body = sub_data.get("body", [])
                                logger.info(f"      - 字幕内容段数: {len(sub_body)}")
                                if sub_body:
                                    first_content = sub_body[0].get("content", "")
                                    logger.info(f"      - 第一段内容: {first_content[:100]}...")
                            except Exception as e:
                                logger.warning(f"      - 下载字幕失败: {e}")
                    
                    # 检查音频信息
                    logger.info(f"\n  [播放器接口] 检查音频流...")
                    dash = player_info.get("dash", {})
                    audio_list = dash.get("audio", [])
                    logger.info(f"  - 音频流数量: {len(audio_list)}")
                    for i, audio in enumerate(audio_list[:3]):  # 只显示前3个
                        bw = audio.get("bandwidth") or audio.get("bandWidth", 0)
                        url = audio.get("baseUrl") or audio.get("base_url", "")
                        logger.info(f"    音频[{i}]: bandwidth={bw}, url 前100字符: {url[:100] if url else 'None'}...")
                    
                else:
                    logger.warning(f"  播放器信息获取失败: {player_data.get('message')}")
                    
            else:
                logger.error(f"  视频信息获取失败: {data.get('message')}")
                
        except Exception as e:
            import traceback
            logger.error(f"请求异常: {e}\n{traceback.format_exc()}")
        
        # 3. 如果通过 API 服务获取
        if session_id:
            logger.info(f"\n[步骤 3] 通过 API 服务获取内容...")
            try:
                resp = await client.get(
                    f"{api_base}/bilibili/video-content",
                    params={"bvid": bvid, "session_id": session_id},
                    headers={"Cookie": f"session_id={session_id}"}
                )
                content_data = resp.json()
                logger.info(f"  API 返回: {json.dumps(content_data, ensure_ascii=False, indent=2)[:500]}...")
            except Exception as e:
                logger.warning(f"  通过 API 获取失败: {e}")
        
        logger.info("\n=== 诊断完成 ===")
        logger.info("请检查以上输出:")
        logger.info("1. 如果字幕数量为 0，说明该视频没有字幕")
        logger.info("2. 如果字幕存在，检查字幕内容是否属于当前视频")
        logger.info("3. 如果字幕不存在，系统会回退到 ASR 或简介")


if __name__ == "__main__":
    bvid = sys.argv[1] if len(sys.argv) > 1 else "BV12scozxE73"
    session_id = sys.argv[2] if len(sys.argv) > 2 else None
    asyncio.run(diagnose_content_fetch(bvid, session_id))
