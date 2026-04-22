"""
重建 Wiki 索引脚本

用法:
    python test/rebuild_wiki_index.py

说明:
    扫描所有 wiki 页面并重新生成 index.md，为每个页面添加摘要
"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.wiki_builder import WikiBuilder


async def main():
    """重建索引"""
    wiki_dir = os.environ.get("WIKI_DIR", "data/wiki")
    print(f"开始重建索引，目录: {wiki_dir}")
    
    builder = WikiBuilder(wiki_dir=wiki_dir)
    
    try:
        await builder.rebuild_index()
        print("索引重建完成！")
    except Exception as e:
        print(f"重建失败: {e}")
        raise
    finally:
        await builder.close()


if __name__ == "__main__":
    asyncio.run(main())