"""
快速修复脚本：修复 favorite_videos 表缺失的记录

这个脚本会：
1. 从 video_cache 表中获取所有已处理的视频
2. 从 favorite_folders 表中获取所有收藏夹
3. 将缺失的 favorite_videos 记录添加进去

用法：
  cd /workspace/bilibili-rag && source .venv/bin/activate && python test/fix_favorite_videos.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import settings


async def main():
    print("=" * 60)
    print("修复 favorite_videos 表")
    print("=" * 60)
    
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        # 1. 获取所有已处理的视频
        result = await conn.execute(text(
            "SELECT bvid FROM video_cache WHERE is_processed = 1"
        ))
        processed_videos = [row[0] for row in result.fetchall()]
        print(f"\n已处理的视频数: {len(processed_videos)}")
        
        # 2. 获取所有收藏夹
        result = await conn.execute(text(
            "SELECT id FROM favorite_folders"
        ))
        folder_ids = [row[0] for row in result.fetchall()]
        print(f"收藏夹数: {len(folder_ids)}")
        
        if not folder_ids:
            print("\n⚠️ 没有找到收藏夹，请先使用「同步」功能")
            await engine.dispose()
            return
        
        # 3. 获取现有的 favorite_videos 记录
        existing_records = []
        for fid in folder_ids:
            result = await conn.execute(text(
                "SELECT folder_id, bvid FROM favorite_videos WHERE folder_id = :fid"
            ), {"fid": fid})
            existing_records.extend(result.fetchall())
        existing_records = result.fetchall()
        print(f"现有的 favorite_videos 记录数: {len(existing_records)}")
        
        # 4. 找出缺失的记录并添加
        # 注意：我们不知道视频属于哪个收藏夹，所以将所有视频添加到第一个收藏夹
        # 实际情况下，建议重新运行「同步」功能来正确关联
        
        folder_id = folder_ids[0]
        missing = 0
        
        for bvid in processed_videos:
            exists = False
            for folder_id_db, bvid_db in existing_records:
                if folder_id_db == folder_id and bvid_db == bvid:
                    exists = True
                    break
            if not exists:
                # 插入缺失的记录
                await conn.execute(text(
                    f"INSERT INTO favorite_videos (folder_id, bvid) VALUES (:folder_id, :bvid)"
                ), {"folder_id": folder_id, "bvid": bvid})
                missing += 1
                print(f"  添加: {bvid} -> 收藏夹 {folder_id}")
        
        await conn.commit()
        print(f"\n修复完成！添加了 {missing} 条缺失记录")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
