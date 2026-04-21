"""
Bilibili Wiki 检索服务

基于 Karpathy Wiki 方案的文件系统检索
"""
import os
import re
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from loguru import logger
from app.config import settings


@dataclass
class WikiDocument:
    """Wiki 文档"""
    bvid: str
    title: str
    content: str
    doc_type: str  # "video", "concept", "entity"
    path: str
    relevance_score: float = 0.0


class WikiRetriever:
    """
    Wiki 检索器
    
    从 Wiki 目录文件中检索相关内容
    """
    
    def __init__(self, wiki_dir: str = None):
        self.wiki_dir = wiki_dir or settings.wiki_dir
        self._cache: Dict[str, str] = {}  # 路径 -> 内容缓存
        
        logger.info(f"WikiRetriever 初始化完成，wiki_dir={self.wiki_dir}")
    
    def _load_file(self, path: str) -> Optional[str]:
        """加载文件内容（带缓存）"""
        if path in self._cache:
            return self._cache[path]
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                self._cache[path] = content
                return content
        except Exception as e:
            logger.warning(f"读取文件失败 [{path}]: {e}")
            return None
    
    def search_by_bvid(self, bvid: str) -> List[WikiDocument]:
        """通过 BV 号搜索相关文档"""
        docs = []
        videos_dir = os.path.join(self.wiki_dir, "videos")
        
        if not os.path.exists(videos_dir):
            return docs
        
        for filename in os.listdir(videos_dir):
            if filename.startswith(bvid) and filename.endswith(".md"):
                filepath = os.path.join(videos_dir, filename)
                content = self._load_file(filepath)
                if content:
                    title = self._extract_title(content)
                    docs.append(WikiDocument(
                        bvid=bvid,
                        title=title,
                        content=content,
                        doc_type="video",
                        path=filepath,
                        relevance_score=1.0
                    ))
        
        return docs
    
    def search_by_keywords(self, query: str, bvids: Optional[List[str]] = None, k: int = 5) -> List[WikiDocument]:
        """通过关键词搜索 Wiki 文档"""
        query_terms = self._extract_query_terms(query)
        if not query_terms:
            return []
        
        docs = []
        scored_docs = {}  # path -> (doc, score)
        
        # 搜索视频页面
        if bvids:
            bvid_set = set(bvids)
            for bvid in bvids:
                videos_dir = os.path.join(self.wiki_dir, "videos")
                if os.path.exists(videos_dir):
                    for filename in os.listdir(videos_dir):
                        if filename.startswith(bvid) and filename.endswith(".md"):
                            filepath = os.path.join(videos_dir, filename)
                            content = self._load_file(filepath)
                            if content:
                                title = self._extract_title(content)
                                score = self._calculate_relevance(content, title, query_terms)
                                doc = WikiDocument(
                                    bvid=bvid,
                                    title=title,
                                    content=content,
                                    doc_type="video",
                                    path=filepath,
                                    relevance_score=score
                                )
                                scored_docs[filepath] = (doc, score)
        else:
            # 搜索所有视频页面
            videos_dir = os.path.join(self.wiki_dir, "videos")
            if os.path.exists(videos_dir):
                for filename in os.listdir(videos_dir):
                    if filename.endswith(".md"):
                        filepath = os.path.join(videos_dir, filename)
                        content = self._load_file(filepath)
                        if content:
                            title = self._extract_title(content)
                            bvid = filename.replace(".md", "")
                            score = self._calculate_relevance(content, title, query_terms)
                            doc = WikiDocument(
                                bvid=bvid,
                                title=title,
                                content=content,
                                doc_type="video",
                                path=filepath,
                                relevance_score=score
                            )
                            scored_docs[filepath] = (doc, score)
        
        # 搜索概念页面
        concepts_dir = os.path.join(self.wiki_dir, "concepts")
        if os.path.exists(concepts_dir):
            for filename in os.listdir(concepts_dir):
                if filename.endswith(".md"):
                    filepath = os.path.join(concepts_dir, filename)
                    content = self._load_file(filepath)
                    if content:
                        title = self._extract_title(content)
                        score = self._calculate_relevance(content, title, query_terms)
                        if score > 0.3:  # 概念页面需要更高的相关性阈值
                            doc = WikiDocument(
                                bvid="",
                                title=title,
                                content=content,
                                doc_type="concept",
                                path=filepath,
                                relevance_score=score
                            )
                            scored_docs[filepath] = (doc, score)
        
        # 按相关性排序
        sorted_docs = sorted(scored_docs.items(), key=lambda x: x[1][1], reverse=True)
        
        for _, (doc, score) in sorted_docs[:k]:
            docs.append(doc)
        
        return docs
    
    def search_all(self, query: str, k: int = 10) -> List[WikiDocument]:
        """全面搜索（不限 bvid 限制）"""
        return self.search_by_keywords(query, k=k)
    
    def get_video_content(self, bvid: str) -> Optional[str]:
        """获取指定 BV 号的完整内容"""
        videos_dir = os.path.join(self.wiki_dir, "videos")
        filepath = os.path.join(videos_dir, f"{bvid}.md")
        return self._load_file(filepath)
    
    def get_all_bvids(self) -> List[str]:
        """获取所有已入库的 BV 号"""
        bvids = []
        videos_dir = os.path.join(self.wiki_dir, "videos")
        
        if not os.path.exists(videos_dir):
            return bvids
        
        for filename in os.listdir(videos_dir):
            if filename.endswith(".md"):
                bvids.append(filename.replace(".md", ""))
        
        return bvids
    
    def get_collection_stats(self) -> Dict[str, int]:
        """获取 Wiki 集合统计信息"""
        stats = {"total_videos": 0, "total_concepts": 0, "total_entities": 0}
        
        for subdir, key in [("videos", "total_videos"), ("concepts", "total_concepts"), ("entities", "total_entities")]:
            dirpath = os.path.join(self.wiki_dir, subdir)
            if os.path.exists(dirpath):
                stats[key] = len([f for f in os.listdir(dirpath) if f.endswith(".md")])
        
        return stats
    
    def _extract_title(self, content: str) -> str:
        """从 Markdown 内容中提取标题"""
        match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return "未知标题"
    
    def _extract_query_terms(self, query: str) -> List[str]:
        """提取查询词"""
        # 提取中文词汇
        chinese_terms = re.findall(r'[\u4e00-\u9fff]{2,}', query)
        # 提取英文/数字词汇
        english_terms = re.findall(r'[A-Za-z0-9]{2,}', query)
        return chinese_terms + english_terms
    
    def _calculate_relevance(self, content: str, title: str, query_terms: List[str]) -> float:
        """计算文档与查询的相关性分数"""
        if not query_terms:
            return 0.0
        
        text = content + " " + title
        matched = 0
        total_terms = len(query_terms)
        
        for term in query_terms:
            if term in text:
                matched += 1
            elif term in title:  # 标题匹配权重更高
                matched += 0.8
        
        return matched / total_terms if total_terms > 0 else 0.0
    
    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()