"""
诊断脚本：检查视频入库流程是否正常

用法：
  cd /workspace/bilibili-rag && source .venv/bin/activate && python test/diagnose_ingest.py

说明：
  1. 检查 SQLite 数据库中 VideoCache 表的状态
  2. 检查 Wiki 目录中的文件
  3. 检查数据库中的收藏夹状态
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text


async def main():
    print("=" * 60)
    print("视频入库流程诊断工具")
    print("=" * 60)
    
    # 1. 检查数据库
    print("\n[1/4] 检查数据库...")
    await check_database()
    
    # 2. 检查 Wiki 目录
    print("\n[2/4] 检查 Wiki 目录...")
    check_wiki_directory()
    
    # 3. 检查配置
    print("\n[3/4] 检查配置...")
    check_config()
    
    # 4. 总结
    print("\n[4/4] 诊断总结...")
    print_diagnostic_summary()
    
    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)


async def check_database():
    """检查数据库状态"""
    from app.config import settings
    from sqlalchemy.ext.asyncio import create_async_engine
    
    db_url = settings.database_url
    print(f"  数据库 URL: {db_url}")
    
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        # 检查 VideoCache 表
        result = await conn.execute(text('SELECT id, bvid, title, content_source, is_processed, length(content) as content_len FROM video_cache'))
        rows = result.fetchall()
        
        print(f"\n  [VideoCache 表]")
        print(f"    总记录数: {len(rows)}")
        
        processed = [r for r in rows if r.is_processed]
        unprocessed = [r for r in rows if not r.is_processed]
        
        print(f"    已处理: {len(processed)}")
        print(f"    未处理: {len(unprocessed)}")
        
        if processed:
            print(f"\n    已处理视频列表:")
            for r in processed:
                has_content = r.content_len and r.content_len > 10
                src = r.content_source or '未知'
                print(f"      - {r.bvid}: {r.title[:40]}... (内容: {'有' if has_content else '无'}, 来源: {src})")
        
        if unprocessed:
            print(f"\n    未处理视频列表 (需要入库):")
            for r in unprocessed:
                print(f"      - {r.bvid}: {r.title[:40]}...")
        
        # 检查 FavoriteFolder 表
        result = await conn.execute(text('SELECT id, media_id, title, media_count, last_sync_at FROM favorite_folders'))
        folders = result.fetchall()
        
        print(f"\n  [FavoriteFolder 表]")
        print(f"    收藏夹数量: {len(folders)}")
        
        for folder in folders:
            last_sync = folder.last_sync_at
            if isinstance(last_sync, str):
                pass  # 已经是字符串格式
            elif last_sync:
                last_sync = last_sync.strftime('%Y-%m-%d %H:%M:%S')
            else:
                last_sync = '从未'
            print(f"      - ID={folder.id}, media_id={folder.media_id}, 标题: {folder.title}")
            print(f"        视频数: {folder.media_count}, 最后同步: {last_sync}")
            
            # 检查该收藏夹下的视频
            result = await conn.execute(text(f"SELECT bvid FROM favorite_videos WHERE folder_id = {folder.id}"))
            bvids = [row[0] for row in result.fetchall()]
            print(f"        视频 BV 号: {bvids}")
        
        # 检查 UserSession 表
        result = await conn.execute(text('SELECT id, session_id, bili_mid, bili_uname, is_valid FROM user_sessions'))
        sessions = result.fetchall()
        
        print(f"\n  [UserSession 表]")
        print(f"    会话数量: {len(sessions)}")
        
        for session in sessions:
            print(f"      - SessionID: {session.session_id[:20]}...")
            print(f"        MID: {session.bili_mid}, 用户名: {session.bili_uname}")
            print(f"        有效: {session.is_valid}")
    
    await engine.dispose()


def check_wiki_directory():
    """检查 Wiki 目录"""
    from app.config import settings
    wiki_dir = settings.wiki_dir
    
    print(f"  Wiki 目录: {wiki_dir}")
    
    if not os.path.exists(wiki_dir):
        print(f"    ⚠️ Wiki 目录不存在")
        return
    
    # 统计各类型文件
    videos_dir = os.path.join(wiki_dir, "videos")
    concepts_dir = os.path.join(wiki_dir, "concepts")
    entities_dir = os.path.join(wiki_dir, "entities")
    raw_dir = os.path.join(wiki_dir, "raw")
    
    video_files = []
    if os.path.exists(videos_dir):
        video_files = [f for f in os.listdir(videos_dir) if f.endswith(".md")]
    
    concept_files = []
    if os.path.exists(concepts_dir):
        concept_files = [f for f in os.listdir(concepts_dir) if f.endswith(".md")]
    
    entity_files = []
    if os.path.exists(entities_dir):
        entity_files = [f for f in os.listdir(entities_dir) if f.endswith(".md")]
    
    print(f"\n  [Wiki 文件统计]")
    print(f"    视频页面: {len(video_files)} 个")
    print(f"    概念页面: {len(concept_files)} 个")
    print(f"    实体页面: {len(entity_files)} 个")
    
    if video_files:
        print(f"\n    视频页面列表:")
        for f in video_files:
            filepath = os.path.join(videos_dir, f)
            size = os.path.getsize(filepath)
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            print(f"      - {f} ({size} 字节, 最后修改: {mtime})")
            
            # 检查内容是否有效
            with open(filepath, 'r', encoding='utf-8') as fp:
                content = fp.read()
                if len(content) < 50:
                    print(f"        ⚠️ 内容过短，可能生成失败")
    
    # 检查 raw 目录
    raw_bvids = []
    if os.path.exists(raw_dir):
        for item in os.listdir(raw_dir):
            item_path = os.path.join(raw_dir, item)
            if os.path.isdir(item_path):
                raw_bvids.append(item)
    
    if raw_bvids:
        print(f"\n  [Raw 数据]")
        print(f"    已缓存视频数: {len(raw_bvids)}")
        for bvid in raw_bvids:
            print(f"      - {bvid}")


def check_config():
    """检查配置"""
    from app.config import settings
    
    print(f"\n  [系统配置]")
    print(f"    LLM API Key 配置: {'是' if settings.openai_api_key else '否'}")
    print(f"    LLM Base URL: {settings.openai_base_url}")
    print(f"    LLM Model: {settings.llm_model_name}")
    print(f"    Wiki 目录: {settings.wiki_dir}")
    
    # 检查 Vision 功能
    print(f"    Vision 功能: {'启用' if settings.vision_enabled else '禁用'}")
    
    # 检查 ASR 配置
    from app.services.asr import ASRService
    asr_service = ASRService()
    print(f"    ASR 模式: {'本地' if asr_service.use_local else 'DashScope'}")
    print(f"    ASR Base URL: {asr_service.base_url}")


def print_diagnostic_summary():
    """打印诊断总结"""
    print(f"""
  ============================================================
  常见问题排查指南:
  
  1. 如果看到"未处理视频"，说明这些视频还没有被处理入库。
     解决方法：在前端点击"更新"按钮，等待后台任务完成。
  
  2. 如果 Wiki 目录中的视频页面内容过短或为空，
     可能是 LLM 服务调用失败或 ASR 转写失败。
     解决方法：检查后端日志，确认 LLM 和 ASR 服务正常。
  
  3. 如果 VideoCache 中有数据但 Wiki 目录中没有对应文件，
     可能是 WikiBuilder.process_video() 执行失败。
     解决方法：检查后端日志中的错误信息。
  
  4. 如果所有视频都显示"已处理"但新视频内容无法提问，
     可能是新视频没有被正确添加到 Wiki 目录中。
     解决方法：
       a. 检查后端日志，确认新视频被处理
       b. 检查 Wiki/videos/ 目录下是否有新视频的 .md 文件
       c. 如果有文件但内容为空，尝试清空 Wiki 后重新入库
  
  5. 前端显示"更新(1)"表示已选中1个收藏夹，这是正常行为。
     点击后应启动后台构建任务，轮询 /knowledge/build/status/<task_id>
     可查看进度。
  ============================================================
""")


if __name__ == "__main__":
    asyncio.run(main())
