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
        """通过关键词搜索 Wiki 文档 - 先扫描 index.md 快速定位，再读取详细内容"""
        query_terms = self._extract_query_terms(query)
        logger.info(f"Wiki 检索: query='{query}', query_terms={query_terms}, bvids={bvids}, k={k}")
        if not query_terms:
            logger.warning(f"Wiki 检索: 未提取到查询词")
            return []
        
        docs = []
        scored_docs = {}  # path -> (doc, score)
        
        # 第一步：扫描 index.md 快速定位相关页面
        index_candidates = self._scan_index_for_candidates(query_terms)
        logger.info(f"Index 扫描候选: {len(index_candidates)} 个页面")
        
        # 第二步：只读取高相关性页面的详细内容
        for doc_type, filename, index_score in index_candidates:
            if doc_type == "video" and bvids:
                # 如果指定了 bvids，只处理匹配的
                bvid = filename.replace(".md", "")
                if bvid not in bvids:
                    continue
            
            filepath = os.path.join(self.wiki_dir, doc_type, filename)
            content = self._load_file(filepath)
            if content:
                title = self._extract_title(content)
                # 综合 index 评分和详细内容评分
                content_score = self._calculate_relevance(content, title, query_terms)
                # 综合分数 = index分数*0.3 + 内容分数*0.7
                combined_score = index_score * 0.3 + content_score * 0.7
                
                if combined_score > 0.1:  # 降低阈值，让更多文档参与排序
                    doc = WikiDocument(
                        bvid=bvid if doc_type == "video" else "",
                        title=title,
                        content=content,
                        doc_type=doc_type,
                        path=filepath,
                        relevance_score=combined_score
                    )
                    scored_docs[filepath] = (doc, combined_score)
        
        # 如果没有通过 index 找到任何文档，回退到全量搜索
        if not scored_docs:
            logger.info("Index 未找到候选，回退到全量搜索")
            scored_docs = self._full_search(query_terms, bvids)
        
        # 按相关性排序
        sorted_docs = sorted(scored_docs.items(), key=lambda x: x[1][1], reverse=True)
        logger.info(f"Wiki 检索: 找到 {len(scored_docs)} 个相关文档，返回前 {k} 个")
        for path, (doc, score) in sorted_docs:
            logger.info(f"  - [{doc.doc_type}] {doc.title} (score={score:.2f}, path={path})")
        
        for _, (doc, score) in sorted_docs[:k]:
            docs.append(doc)
        
        logger.info(f"Wiki 检索: 最终返回 {len(docs)} 个文档")
        return docs
    
    def _scan_index_for_candidates(self, query_terms: List[str]) -> List[tuple]:
        """扫描 index.md，快速定位可能相关的页面"""
        index_path = os.path.join(self.wiki_dir, "index.md")
        candidates = []
        
        if not os.path.exists(index_path):
            return candidates
        
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception:
            return candidates
        
        current_section = None
        section_pattern = re.compile(r'^##\s+(concepts|entities|videos)\s*$')
        
        for line in lines:
            line = line.strip()
            
            # 检测章节
            section_match = section_pattern.match(line)
            if section_match:
                current_section = section_match.group(1)
                continue
            
            # 跳过非内容章节
            if current_section is None:
                continue
            
            # 解析列表项：- **[标题](路径)** - 摘要
            item_match = re.search(r'- \*\*\[([^\]]+)\]\(([^)]+)\)\*\*', line)
            if item_match:
                title = item_match.group(1)
                path = item_match.group(2)
                
                # 检查标题是否匹配查询词
                title_score = 0
                for term in query_terms:
                    if term in title:
                        title_score += 1.0  # 标题匹配权重高
                
                # 检查摘要是否匹配查询词
                # 获取该行剩余部分（摘要）
                summary_match = re.search(r'\*\*\)\s*-\s*(.+)$', line)
                summary_score = 0
                if summary_match:
                    summary = summary_match.group(1)
                    for term in query_terms:
                        if term in summary:
                            summary_score += 0.5
                
                combined = title_score + summary_score
                if combined > 0:
                    # 确定文档类型
                    doc_type = "videos" if current_section == "videos" else current_section
                    candidates.append((doc_type, path, combined))
        
        # 按分数排序，返回前 k*3 个（预留更多候选）
        candidates.sort(key=lambda x: x[2], reverse=True)
        return candidates[:k * 3] if k else candidates[:15]
    
    def _full_search(self, query_terms: List[str], bvids: Optional[List[str]] = None) -> dict:
        """全量搜索（回退方案）"""
        scored_docs = {}
        
        # 搜索视频页面
        if bvids:
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
                        if score > 0.2:
                            doc = WikiDocument(
                                bvid="",
                                title=title,
                                content=content,
                                doc_type="concept",
                                path=filepath,
                                relevance_score=score
                            )
                            scored_docs[filepath] = (doc, score)
        
        # 搜索实体页面
        entities_dir = os.path.join(self.wiki_dir, "entities")
        if os.path.exists(entities_dir):
            for filename in os.listdir(entities_dir):
                if filename.endswith(".md"):
                    filepath = os.path.join(entities_dir, filename)
                    content = self._load_file(filepath)
                    if content:
                        title = self._extract_title(content)
                        score = self._calculate_relevance(content, title, query_terms)
                        if score > 0.1:
                            doc = WikiDocument(
                                bvid="",
                                title=title,
                                content=content,
                                doc_type="entity",
                                path=filepath,
                                relevance_score=score
                            )
                            scored_docs[filepath] = (doc, score)
        
        return scored_docs
    
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
        """计算文档与查询的相关性分数 - 改进版，标题加权"""
        if not query_terms:
            return 0.0
        
        matched = 0
        total_terms = len(query_terms)
        title_matches = 0
        
        for term in query_terms:
            if term in title:
                title_matches += 1
                matched += 1.5  # 标题匹配权重 1.5x
            elif term in content:
                matched += 0.5  # 内容匹配权重 0.5x
                # 检查出现频率
                term_count = content.lower().count(term.lower())
                if term_count > 3:
                    matched += 0.3  # 高频出现额外加分
        
        # 标题中有任何匹配就给予基础分
        if title_matches > 0:
            matched += 1.0
        
        return min(matched / total_terms, 3.0) if total_terms > 0 else 0.0
    
    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()