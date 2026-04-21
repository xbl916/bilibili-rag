"""
诊断 B 站 API 问题
测试视频: BV12scozxE73
"""
import asyncio
import httpx
import json
from urllib.parse import urlencode
import hashlib
from functools import reduce

# 混淆表
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52
]


def get_mixin_key(img_key: str, sub_key: str) -> str:
    """生成混淆后的 key"""
    return reduce(lambda s, i: s + img_key[i], MIXIN_KEY_ENC_TAB, '')[:32]


async def diagnose():
    bvid = "BV12scozxE73"
    
    # 从 SQLite 数据库读取 Cookie
    import os
    import sqlite3
    
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "bilibili_rag.db")
    cookies = {}
    
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # 查询有效的会话
            cursor.execute("""
                SELECT sessdata, bili_jct, dedeuserid 
                FROM user_sessions 
                WHERE is_valid = 1 
                ORDER BY last_active_at DESC 
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            if row:
                cookies = {
                    "SESSDATA": row[0] or "",
                    "bili_jct": row[1] or "",
                    "DedeUserID": row[2] or ""
                }
                print(f"✅ 从数据库读取到 Cookie")
            else:
                print("❌ 数据库中没有有效会话")
            
            conn.close()
        except Exception as e:
            print(f"❌ 读取数据库失败: {e}")
    else:
        print(f"❌ 数据库文件不存在: {db_path}")
    
    print(f"Cookie: SESSDATA={cookies.get('SESSDATA', 'MISSING')[:50]}...")
    print(f"bili_jct={cookies.get('bili_jct', 'MISSING')[:20] if cookies.get('bili_jct') else 'MISSING'}...")
    print(f"DedeUserID={cookies.get('DedeUserID', 'MISSING')}")
    print()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
        "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())
    }
    
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        # 1. 获取视频信息
        print("=" * 60)
        print("1. 获取视频信息 (/x/web-interface/view)")
        print("=" * 60)
        try:
            resp = await client.get(
                "https://api.bilibili.com/x/web-interface/view",
                params={"bvid": bvid},
                cookies=cookies
            )
            data = resp.json()
            print(f"状态码: {resp.status_code}")
            print(f"响应: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")
            if data.get("code") == 0:
                video_data = data["data"]
                print(f"\n视频信息:")
                print(f"  aid: {video_data.get('aid')}")
                print(f"  cid: {video_data.get('cid')}")
                print(f"  bvid: {video_data.get('bvid')}")
                print(f"  title: {video_data.get('title')[:50]}")
                print(f"  desc: {video_data.get('desc', '')[:100]}")
            else:
                print(f"错误: {data.get('message')}")
                return
        except Exception as e:
            print(f"失败: {e}")
            return
        
        aid = data["data"].get("aid")
        cid = data["data"].get("cid")
        
        # 2. 获取 WBI keys
        print("\n" + "=" * 60)
        print("2. 获取 WBI keys")
        print("=" * 60)
        try:
            nav_resp = await client.get(
                "https://api.bilibili.com/x/web-interface/nav",
                cookies=cookies
            )
            nav_data = nav_resp.json()
            if nav_data.get("code") == 0:
                wbi_img = nav_data["data"]["wbi_img"]
                img_key = wbi_img["img_url"].rsplit("/", 1)[1].split(".")[0]
                sub_key = wbi_img["sub_url"].rsplit("/", 1)[1].split(".")[0]
                mixin_key = get_mixin_key(img_key, sub_key)
                print(f"img_key: {img_key}")
                print(f"sub_key: {sub_key}")
                print(f"mixin_key: {mixin_key}")
            else:
                print(f"获取 WBI keys 失败: {nav_data.get('message')}")
        except Exception as e:
            print(f"失败: {e}")
            mixin_key = "dummy"  # 设置 dummy 值避免 UnboundLocalError
        
        # 3. 测试 playurl API（多种参数组合）
        print("\n" + "=" * 60)
        print("3. 测试 playurl API")
        print("=" * 60)
        
        test_cases = [
            ("用户提供的参数", {"bvid": bvid, "cid": cid, "qn": 32, "fnval": 16}),
            ("加上 aid", {"aid": aid, "bvid": bvid, "cid": cid, "qn": 32, "fnval": 16}),
            ("完整参数", {"aid": aid, "bvid": bvid, "cid": cid, "qn": 32, "fnval": 16, "fnver": 0, "fourk": 1}),
            ("qn=80", {"bvid": bvid, "cid": cid, "qn": 80, "fnval": 16}),
        ]
        
        for name, params in test_cases:
            print(f"\n--- {name} ---")
            print(f"参数: {params}")
            
            # 普通接口
            try:
                resp = await client.get(
                    "https://api.bilibili.com/x/player/playurl",
                    params=params,
                    cookies=cookies
                )
                print(f"普通接口: status={resp.status_code}, text_len={len(resp.text)}")
                if resp.status_code == 200 and resp.text:
                    play_data = resp.json()
                    print(f"响应: {json.dumps(play_data, ensure_ascii=False, indent=2)[:300]}")
                    if play_data.get("code") == 0:
                        payload = play_data.get("data", {})
                        dash = payload.get("dash", {})
                        audio_list = dash.get("audio", [])
                        print(f"audio 数量: {len(audio_list)}")
                        if audio_list:
                            for i, item in enumerate(audio_list[:3]):
                                bw = item.get("bandwidth") or item.get("bandWidth")
                                url = item.get("baseUrl") or item.get("base_url")
                                print(f"  audio[{i}]: bandwidth={bw}, url={url[:80] if url else None}...")
                    elif play_data.get("code") == -404:
                        print(f"错误: {play_data.get('message')}")
            except Exception as e:
                print(f"普通接口失败: {e}")
            
            # WBI 签名接口
            if mixin_key:
                try:
                    # 签名
                    filtered_params = {k: "".join(c for c in str(v) if c not in "!'()*") for k, v in params.items()}
                    filtered_params["wts"] = int(asyncio.get_event_loop().time() % (2**31))
                    filtered_params = dict(sorted(filtered_params.items()))
                    query = urlencode(filtered_params)
                    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
                    filtered_params["w_rid"] = w_rid
                    
                    resp = await client.get(
                        "https://api.bilibili.com/x/player/wbi/v2",
                        params=filtered_params,
                        cookies=cookies
                    )
                    print(f"WBI 接口: status={resp.status_code}, text_len={len(resp.text)}")
                    if resp.status_code == 200 and resp.text:
                        wbi_data = resp.json()
                        print(f"响应: {json.dumps(wbi_data, ensure_ascii=False, indent=2)[:300]}")
                except Exception as e:
                    print(f"WBI 接口失败: {e}")
        
        # 4. 测试播放器信息 API
        print("\n" + "=" * 60)
        print("4. 测试播放器信息 API (/x/player/v2)")
        print("=" * 60)
        
        player_params = {"bvid": bvid, "cid": cid}
        if aid:
            player_params["aid"] = aid
        
        try:
            resp = await client.get(
                "https://api.bilibili.com/x/player/v2",
                params=player_params,
                cookies=cookies
            )
            print(f"状态码: {resp.status_code}")
            print(f"响应长度: {len(resp.text)}")
            if resp.status_code == 200 and resp.text:
                player_data = resp.json()
                print(f"响应: {json.dumps(player_data, ensure_ascii=False, indent=2)[:1000]}")
                
                if player_data.get("code") == 0:
                    playdata = player_data.get("data", {})
                    subtitle_info = playdata.get("subtitle", {}) or {}
                    subtitles = subtitle_info.get("subtitles") or subtitle_info.get("list") or []
                    print(f"\n字幕数量: {len(subtitles)}")
                    for sub in subtitles:
                        lan = sub.get("lan", "")
                        lan_doc = sub.get("lan_doc", "")
                        subtitle_url = sub.get("subtitle_url") or sub.get("url", "")
                        print(f"  lan={lan}, lan_doc={lan_doc}")
                        print(f"  url={subtitle_url[:150] if subtitle_url else None}...")
        except Exception as e:
            print(f"失败: {e}")


if __name__ == "__main__":
    asyncio.run(diagnose())