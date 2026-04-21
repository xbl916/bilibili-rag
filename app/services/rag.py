"""
Bilibili RAG 知识库系统

RAG 服务模块 - 已迁移到 Wiki 检索方案
本文件保留以兼容旧代码，实际检索由 wiki_retriever.py 提供
"""
from typing import List, Optional, Dict, Any
from loguru import logger
from app.services.wiki_retriever import WikiRetriever, WikiDocument

# 全局 Wiki 检索器实例（单例）
_wiki_retriever_instance = None


def get_rag_service(collection_name: str = "bilibili_videos") -> WikiRetriever:
    """
    获取 Wiki 检索器实例（单例模式）
    
    注意：此函数返回 WikiRetriever 而非旧的 RAGService
    collection_name 参数保留以兼容旧代码
    
    Returns:
        WikiRetriever 实例
    """
    global _wiki_retriever_instance
    if _wiki_retriever_instance is None:
        _wiki_retriever_instance = WikiRetriever()
    return _wiki_retriever_instance


class RAGService:
    """
    兼容类：包装 WikiRetriever 以兼容旧代码
    
    注意：此类已废弃，建议使用 WikiRetriever 直接
    """
    
    def __init__(self, collection_name: str = "bilibili_videos"):
        self._retriever = WikiRetriever()
        self.collection_name = collection_name
        logger.warning("RAGService 已废弃，请使用 WikiRetriever")
    
    def search(self, query: str, k: int = 5, bvids: Optional[List[str]] = None) -> List[WikiDocument]:
        """搜索 Wiki 文档"""
        return self._retriever.search_by_keywords(query, bvids=bvids, k=k)
    
    def get_collection_stats(self) -> Dict[str, int]:
        """获取集合统计信息"""
        return self._retriever.get_collection_stats()