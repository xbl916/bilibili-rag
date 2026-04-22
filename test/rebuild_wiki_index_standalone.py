"""
重建 Wiki 索引脚本（独立版本）

不依赖完整应用模块，直接扫描文件系统重建 index.md

用法:
    python test/rebuild_wiki_index_standalone.py
"""
import os
import re
import sys


def extract_title(content: str) -> str:
    """从 Markdown 内容中提取标题"""
    match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "未知标题"


def extract_summary(content: str, max_chars: int = 200) -> str:
    """从 Markdown 内容中提取摘要（前2-3段非空文本）"""
    lines = content.split('\n')
    summary_parts = []
    current_len = 0
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # 跳过标题行（# 开头）和表格行
        if stripped.startswith('#') or stripped.startswith('|'):
            continue
        # 跳过列表项（- 开头）的前几条，只取正文段落
        if stripped.startswith('-'):
            continue
        
        if current_len + len(stripped) > max_chars:
            summary_parts.append(stripped[:max_chars - current_len])
            break
        
        summary_parts.append(stripped)
        current_len += len(stripped) + 1
        
        if current_len >= max_chars:
            break
    
    return ' '.join(summary_parts) if summary_parts else "暂无摘要"


def rebuild_index(wiki_dir: str) -> None:
    """重建完整的索引"""
    index_path = os.path.join(wiki_dir, "index.md")
    
    # 初始索引模板
    initial_index = """# Bilibili RAG Wiki

> 基于 Karpathy LLM Wiki 方案构建的个人知识库

## 导航

- [操作日志](log.md)

## 概念

> 概念页面存储视频中的核心知识点，包含定义、要点和相关视频。

"""
    
    # 重建概念索引
    concepts_dir = os.path.join(wiki_dir, "concepts")
    concepts_content = ""
    if os.path.exists(concepts_dir):
        concepts = []
        for filename in sorted(os.listdir(concepts_dir)):
            if filename.endswith(".md"):
                filepath = os.path.join(concepts_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    title = extract_title(content)
                    summary = extract_summary(content)
                    concepts.append((title, filename, summary))
                except Exception as e:
                    print(f"  读取概念文件失败 [{filename}]: {e}")
        
        for title, filename, summary in concepts:
            page_name = filename.replace(".md", "")
            concepts_content += f"- **[{title}](concepts/{filename})** - {summary}\n"
    
    if concepts_content:
        initial_index += concepts_content + "\n"
    else:
        initial_index += "\n（暂无概念页面）\n\n"
    
    # 重建实体索引
    entities_dir = os.path.join(wiki_dir, "entities")
    entities_content = ""
    if os.path.exists(entities_dir):
        entities = []
        for filename in sorted(os.listdir(entities_dir)):
            if filename.endswith(".md"):
                filepath = os.path.join(entities_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    title = extract_title(content)
                    summary = extract_summary(content)
                    entities.append((title, filename, summary))
                except Exception as e:
                    print(f"  读取实体文件失败 [{filename}]: {e}")
        
        for title, filename, summary in entities:
            entities_content += f"- **[{title}](entities/{filename})** - {summary}\n"
    
    initial_index += """
## 实体

> 实体页面存储视频中提到的人、工具、框架、技术等。

"""
    
    if entities_content:
        initial_index += entities_content + "\n"
    else:
        initial_index += "\n（暂无实体页面）\n\n"
    
    # 重建视频索引
    videos_dir = os.path.join(wiki_dir, "videos")
    videos_content = ""
    if os.path.exists(videos_dir):
        videos = []
        for filename in sorted(os.listdir(videos_dir)):
            if filename.endswith(".md"):
                filepath = os.path.join(videos_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    title = extract_title(content)
                    summary = extract_summary(content)
                    bvid = filename.replace(".md", "")
                    videos.append((title, filename, summary, bvid))
                except Exception as e:
                    print(f"  读取视频文件失败 [{filename}]: {e}")
        
        for title, filename, summary, bvid in videos:
            videos_content += f"- **[{title}](videos/{filename})** - {summary}\n"
    
    initial_index += """
## 视频

> 视频页面包含内容摘要、核心概念和关键视觉内容。

"""
    
    if videos_content:
        initial_index += videos_content + "\n"
    else:
        initial_index += "\n（暂无视频页面）\n\n"
    
    initial_index += """
---

*本 Wiki 由 Bilibili RAG 系统自动生成和维护*
"""
    
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(initial_index)
    
    print(f"索引重建完成: {index_path}")
    print(f"  概念页面: {len([c for c in concepts_content.splitlines() if c.strip()])} 个")
    print(f"  实体页面: {len([e for e in entities_content.splitlines() if e.strip()])} 个")
    print(f"  视频页面: {len([v for v in videos_content.splitlines() if v.strip()])} 个")


def main():
    wiki_dir = os.environ.get("WIKI_DIR", "data/wiki")
    print(f"开始重建索引，目录: {wiki_dir}")
    
    if not os.path.exists(wiki_dir):
        print(f"错误: Wiki 目录不存在: {wiki_dir}")
        sys.exit(1)
    
    rebuild_index(wiki_dir)
    print("完成！")


if __name__ == "__main__":
    main()