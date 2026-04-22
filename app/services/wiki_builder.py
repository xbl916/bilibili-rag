"""
Bilibili RAG Wiki 系统

基于 Karpathy LLM Wiki 方案的知识库构建器
"""
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from loguru import logger
import httpx

from app.config import settings


@dataclass
class VideoSource:
    """视频源数据"""
    bvid: str
    title: str
    asr_text: str
    vision_analysis: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None


@dataclass
class ConceptPage:
    """概念页面"""
    name: str
    definition: str
    core_points: List[str]
    timestamps: List[int]
    related_concepts: List[str]
    related_videos: List[str]
    importance: str = "medium"


@dataclass
class EntityPage:
    """实体页面"""
    name: str
    entity_type: str
    description: str
    website: Optional[str]
    video_mentions: List[dict]
    related_concepts: List[str]


class WikiBuilder:
    """
    基于 Karpathy 方案的 Wiki 构建器
    
    功能：
    1. 读取原始素材
    2. 提取关键概念和实体
    3. 生成/更新 Wiki 页面
    4. 维护索引和日志
    """
    
    CONCEPT_TEMPLATES = {
        "default": """# {name}

## 定义
{definition}

## 核心要点
{core_points}

## 相关内容
{related_content}

## 参考视频
{video_references}

## 交叉引用
{cross_references}

## 更新历史
{update_history}
""",
        "simple": """# {name}

{definition}

**参考视频**: {video_references}

**相关概念**: {cross_references}
"""
    }
    
    ENTITY_TEMPLATES = {
        "default": """# {name}

## 基本信息
| 属性 | 值 |
|------|-----|
| 类型 | {entity_type} |
| 官网 | {website} |
| 介绍 | {description} |

## 在知识库中的出现
{video_mentions_table}

## 相关概念
{related_concepts}
"""
    }
    
    VIDEO_TEMPLATES = {
        "default": """# {title}

## 基本信息
| 属性 | 值 |
|------|-----|
| BV 号 | {bvid} |
| UP 主 | {up_owner} |
| 收录时间 | {ingest_time} |

## 内容摘要
{content_summary}

## 核心概念
{core_concepts}

## 关键视觉内容
{visual_content}

## 相关实体
{related_entities}
"""
    }
    
    def __init__(self, wiki_dir: str = None, llm_base_url: str = None, llm_model: str = None, vision_service: Optional[Any] = None):
        """
        初始化 WikiBuilder
        
        Args:
            wiki_dir: Wiki 存储目录
            llm_base_url: LLM 服务地址（默认使用配置的 LLM_BASE_URL）
            llm_model: LLM 模型名称（默认使用配置的 LLM_MODEL）
            vision_service: 视觉分析服务实例
        """
        self.wiki_dir = wiki_dir or settings.wiki_dir
        self.llm_base_url = llm_base_url or settings.llm_base_url
        self.llm_model = llm_model or settings.llm_model_name
        self.vision_service = vision_service
        self.llm_api_key = settings.llm_api_key or settings.openai_api_key
        
        # 确保目录存在
        self._ensure_directories()
        
        # 初始化 HTTP 客户端（携带 API Key 头）
        headers = {}
        if self.llm_api_key:
            headers["Authorization"] = f"Bearer {self.llm_api_key}"
        self.http_client = httpx.AsyncClient(timeout=300.0, headers=headers)
        
        logger.info(f"WikiBuilder 初始化完成，wiki_dir={self.wiki_dir}")
    
    def _ensure_directories(self):
        """确保 Wiki 目录结构存在"""
        dirs = [
            self.wiki_dir,
            os.path.join(self.wiki_dir, "concepts"),
            os.path.join(self.wiki_dir, "entities"),
            os.path.join(self.wiki_dir, "videos"),
            os.path.join(self.wiki_dir, "raw"),
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)
    
    async def close(self):
        """关闭 HTTP 客户端"""
        await self.http_client.aclose()
    
    async def process_video(self, source: VideoSource) -> dict:
        """
        处理单个视频源，生成/更新 Wiki 页面
        
        Args:
            source: 视频源数据
            
        Returns:
            处理结果统计
        """
        results = {
            "bvid": source.bvid,
            "pages_created": [],
            "pages_updated": [],
            "concepts_extracted": [],
            "entities_extracted": [],
            "errors": []
        }
        
        try:
            # 1. 保存原始素材
            raw_dir = os.path.join(self.wiki_dir, "raw", source.bvid)
            os.makedirs(raw_dir, exist_ok=True)
            
            with open(os.path.join(raw_dir, "asr.txt"), 'w', encoding='utf-8') as f:
                f.write(source.asr_text)
            
            with open(os.path.join(raw_dir, "vision.json"), 'w', encoding='utf-8') as f:
                json.dump(source.vision_analysis or {}, f, ensure_ascii=False, indent=2)
            
            with open(os.path.join(raw_dir, "meta.json"), 'w', encoding='utf-8') as f:
                json.dump(source.meta, f, ensure_ascii=False, indent=2)
            
            # 2. 提取关键概念
            concepts = await self._extract_concepts(source)
            results["concepts_extracted"] = [c.name for c in concepts]
            
            # 3. 提取实体
            entities = await self._extract_entities(source)
            results["entities_extracted"] = [e.name for e in entities]
            
            # 4. 生成/更新概念页面
            for concept in concepts:
                page_path = os.path.join(self.wiki_dir, "concepts", f"{concept.name}.md")
                if os.path.exists(page_path):
                    await self._update_concept_page(page_path, concept, source)
                    results["pages_updated"].append(page_path)
                else:
                    await self._create_concept_page(page_path, concept)
                    results["pages_created"].append(page_path)
            
            # 5. 生成/更新实体页面
            for entity in entities:
                page_path = os.path.join(self.wiki_dir, "entities", f"{entity.name}.md")
                if os.path.exists(page_path):
                    await self._update_entity_page(page_path, entity, source)
                    results["pages_updated"].append(page_path)
                else:
                    await self._create_entity_page(page_path, entity)
                    results["pages_created"].append(page_path)
            
            # 6. 生成视频摘要页面
            video_page = self._create_video_summary(source)
            video_path = os.path.join(self.wiki_dir, "videos", f"{source.bvid}.md")
            await self._write_page(video_path, video_page)
            results["pages_created"].append(video_path)
            
            # 7. 更新索引
            await self._update_index(results)
            
            # 8. 记录日志
            await self._log_operation("ingest", source.bvid, results)
            
            logger.info(f"视频处理完成：{source.bvid}, 创建 {len(results['pages_created'])} 页，更新 {len(results['pages_updated'])} 页")
            
        except Exception as e:
            logger.error(f"处理视频失败 [{source.bvid}]: {e}")
            results["errors"].append(str(e))
        
        return results
    
    async def _extract_concepts(self, source: VideoSource) -> List[ConceptPage]:
        """
        从视频内容中提取关键概念
        
        使用 Qwen3.5 分析 ASR + 视觉内容，提取概念
        """
        # 构建提示词
        prompt = self._build_concept_extraction_prompt(source)
        
        try:
            response = await self._call_llm(prompt, force_json=True)
            concepts_data = self._parse_json_response(response)
            
            if concepts_data is None:
                raise json.JSONDecodeError("无法解析 JSON", "", 0)
            
            concepts = []
            for c in concepts_data:
                concepts.append(ConceptPage(
                    name=c.get("name", "未知概念"),
                    definition=c.get("definition", ""),
                    core_points=c.get("core_points", []),
                    timestamps=c.get("timestamps", []),
                    related_concepts=c.get("related_concepts", []),
                    related_videos=[source.bvid],
                    importance=c.get("importance", "medium")
                ))
            
            logger.info(f"从视频 {source.bvid} 提取了 {len(concepts)} 个概念")
            return concepts
            
        except Exception as e:
            logger.error(f"概念提取失败：{e}")
            # 返回默认概念
            return [ConceptPage(
                name="视频内容",
                definition=f"视频《{source.title}》的内容摘要",
                core_points=[source.asr_text[:500]],
                timestamps=[],
                related_concepts=[],
                related_videos=[source.bvid]
            )]
    
    async def _extract_entities(self, source: VideoSource) -> List[EntityPage]:
        """从视频内容中提取实体（工具、框架、人物等）"""
        prompt = f"""你是一位知识管理专家。请从以下视频内容中提取提到的实体（工具、框架、技术、人物、组织等）。

【重要】只输出纯 JSON 数组，不要输出任何其他文字、解释或 markdown 代码块标记。

【视频标题】
{source.title}

【ASR 转写文本（前8000字）】
{source.asr_text[:8000]}

【视觉分析】
{json.dumps(source.vision_analysis, ensure_ascii=False) if source.vision_analysis else "无"}

请提取 3-10 个核心实体，每个实体包含：
1. name: 实体名称
2. entity_type: 实体类型（工具/框架/技术/人物/组织/其他）
3. description: 详细描述（50-150字，解释这个实体是什么、在视频中如何被提及）
4. website: 官网 URL（如果有，没有则填 null）
5. context_mentions: 视频中提到该实体的上下文摘录（1-2句）

输出格式（JSON 数组，不要包含```json标记）：
[
  {{
    "name": "实体名",
    "entity_type": "工具",
    "description": "详细描述",
    "website": "https://example.com",
    "context_mentions": ["上下文摘录"]
  }}
]
"""
        
        try:
            response = await self._call_llm(prompt, force_json=True)
            entities_data = self._parse_json_response(response)
            
            if entities_data is None:
                logger.warning("实体提取：无法解析 JSON 响应")
                return []
            
            entities = []
            for e in entities_data:
                entities.append(EntityPage(
                    name=e.get("name", "未知实体"),
                    entity_type=e.get("entity_type", "其他"),
                    description=e.get("description", ""),
                    website=e.get("website"),
                    video_mentions=[
                        {
                            "bvid": source.bvid,
                            "timestamp": m.get("timestamp", 0),
                            "context": m.get("context", "")
                        }
                        for m in e.get("mentions", [])
                    ],
                    related_concepts=[]
                ))
            
            logger.info(f"从视频 {source.bvid} 提取了 {len(entities)} 个实体")
            return entities
            
        except Exception as e:
            logger.warning(f"实体提取失败：{e}")
            return []
    
    async def _create_concept_page(self, path: str, concept: ConceptPage):
        """创建概念页面"""
        content = self.CONCEPT_TEMPLATES["default"].format(
            name=concept.name,
            definition=concept.definition,
            core_points="\n".join([f"- {p}" for p in concept.core_points]) if concept.core_points else "暂无",
            related_content="暂无",
            video_references=f"- [{concept.related_videos[0]}](../../videos/{concept.related_videos[0]}.md) @ 首次提及",
            cross_references="\n".join([f"- [{c}](../concepts/{c}.md)" for c in concept.related_concepts]) if concept.related_concepts else "暂无",
            update_history=f"- {datetime.now().strftime('%Y-%m-%d')}: 创建页面"
        )
        await self._write_page(path, content)
        logger.info(f"创建概念页面：{path}")
    
    async def _update_concept_page(self, path: str, concept: ConceptPage, source: VideoSource):
        """更新概念页面（合并新旧内容）"""
        # 读取现有内容
        with open(path, 'r', encoding='utf-8') as f:
            existing = f.read()
        
        # 使用 LLM 合并新旧内容
        merge_prompt = f"""
现有概念页面内容：
{existing}

新的视频内容提到这个概念：
- 视频标题：{source.title}
- BV 号：{source.bvid}
- 时间戳：{concept.timestamps}
- 定义：{concept.definition}
- 核心要点：{', '.join(concept.core_points)}

请合并这些信息，更新概念页面。要求：
1. 保持内容连贯，不要简单拼接
2. 如果新内容与现有内容矛盾，以最新内容为准并标注
3. 添加新的参考视频链接到"参考视频"部分
4. 更新"更新历史"部分
5. 如果概念定义有更新，更新"定义"部分
"""
        
        merged = await self._call_llm(merge_prompt)
        await self._write_page(path, merged)
        logger.info(f"更新概念页面：{path}")
        
        # 同时更新视频页面中的交叉引用
        await self._update_video_references(concept.name, source)
    
    async def _create_entity_page(self, path: str, entity: EntityPage):
        """创建实体页面"""
        video_mentions = "\n".join([
            f"- [{m['bvid']}](../../videos/{m['bvid']}.md) @ {m['timestamp']}s: {m['context']}"
            for m in entity.video_mentions
        ]) if entity.video_mentions else "暂无"
        
        related_concepts = "\n".join([f"- [{c}](../concepts/{c}.md)" for c in entity.related_concepts]) if entity.related_concepts else "暂无"
        
        content = self.ENTITY_TEMPLATES["default"].format(
            name=entity.name,
            entity_type=entity.entity_type,
            website=entity.website or "暂无",
            description=entity.description,
            video_mentions_table=video_mentions,
            related_concepts=related_concepts
        )
        await self._write_page(path, content)
        logger.info(f"创建实体页面：{path}")
    
    async def _update_entity_page(self, path: str, entity: EntityPage, source: VideoSource):
        """更新实体页面"""
        with open(path, 'r', encoding='utf-8') as f:
            existing = f.read()
        
        merge_prompt = f"""
现有实体页面内容：
{existing}

新的视频提及了这个实体：
- 视频标题：{source.title}
- BV 号：{source.bvid}
- 时间戳：{entity.video_mentions[0]['timestamp'] if entity.video_mentions else 0}
- 上下文：{entity.video_mentions[0]['context'] if entity.video_mentions else '暂无'}

请更新实体页面，添加新的视频提及到"在知识库中的出现"部分，并更新"更新历史"。
"""
        
        merged = await self._call_llm(merge_prompt)
        await self._write_page(path, merged)
        logger.info(f"更新实体页面：{path}")
    
    async def _create_video_summary(self, source: VideoSource) -> str:
        """创建视频摘要页面 - 使用 LLM 生成结构化摘要"""
        try:
            # 使用 LLM 生成视频摘要
            summary_prompt = f"""请为以下视频生成结构化的摘要内容。

【视频标题】
{source.title}

【ASR 转写（前3000字）】
{source.asr_text[:3000]}

请生成以下内容（JSON 格式，不要包含```json标记）：
{{
    "content_summary": "精炼的内容摘要（500字以内），要有条理地组织，不要直接粘贴原始转写",
    "key_topics": ["主题1", "主题2", "主题3"],
    "core_concepts": [
        {{"name": "概念名", "timestamp": "提及位置"}}
    ],
    "visual_content": "关键视觉内容描述（如果有）",
    "related_entities": ["实体1", "实体2"]
}}
"""
            llm_response = await self._call_llm(summary_prompt, force_json=True)
            summary_data = self._parse_json_response(llm_response)
            
            if summary_data:
                # 构建核心概念列表
                core_concepts = []
                if summary_data.get("core_concepts"):
                    for cc in summary_data["core_concepts"][:5]:
                        ts = cc.get("timestamp", "N/A")
                        core_concepts.append(f"- [{cc['name']}](../../concepts/{cc['name']}.md) @ {ts}")
                
                # 关键视觉内容
                visual_content = summary_data.get("visual_content", "暂无") or "暂无"
                
                # 相关实体
                related_entities = []
                if summary_data.get("related_entities"):
                    for re_item in summary_data["related_entities"][:5]:
                        related_entities.append(f"- [{re_item}](../../entities/{re_item}.md)")
                
                content = self.VIDEO_TEMPLATES["default"].format(
                    title=source.title,
                    bvid=source.bvid,
                    up_owner=source.meta.get("up_owner", "未知 UP 主") if source.meta else "未知 UP 主",
                    ingest_time=datetime.now().strftime('%Y-%m-%d %H:%M'),
                    content_summary=summary_data.get("content_summary", source.asr_text[:2000]),
                    core_concepts="\n".join(core_concepts) if core_concepts else "暂无",
                    visual_content=visual_content,
                    related_entities="\n".join(related_entities) if related_entities else "暂无"
                )
                return content
        except Exception as e:
            logger.warning(f"LLM 摘要生成失败，使用原始 ASR 文本：{e}")
        
        # 降级：使用原始 ASR 文本
        core_concepts = []
        if source.vision_analysis and "concepts" in source.vision_analysis:
            for c in source.vision_analysis["concepts"][:5]:
                core_concepts.append(f"- [{c['name']}](../../concepts/{c['name']}.md) @ {c.get('timestamp', 'N/A')}s")
        
        visual_content = "暂无"
        if source.vision_analysis and "visual_highlights" in source.vision_analysis:
            visual_content = "\n".join([
                f"- {h}" for h in source.vision_analysis["visual_highlights"][:5]
            ])
        
        related_entities = []
        if source.vision_analysis and "entities" in source.vision_analysis:
            for e in source.vision_analysis["entities"][:3]:
                related_entities.append(f"- [{e['name']}](../../entities/{e['name']}.md)")
        
        content = self.VIDEO_TEMPLATES["default"].format(
            title=source.title,
            bvid=source.bvid,
            up_owner=source.meta.get("up_owner", "未知 UP 主") if source.meta else "未知 UP 主",
            ingest_time=datetime.now().strftime('%Y-%m-%d %H:%M'),
            content_summary=source.asr_text[:3000],
            core_concepts="\n".join(core_concepts) if core_concepts else "暂无",
            visual_content=visual_content,
            related_entities="\n".join(related_entities) if related_entities else "暂无"
        )
        
        return content
    
    async def _update_index(self, results: dict):
        """更新全局索引"""
        index_path = os.path.join(self.wiki_dir, "index.md")
        
        # 读取现有索引
        if os.path.exists(index_path):
            with open(index_path, 'r', encoding='utf-8') as f:
                index = f.read()
        else:
            index = self._create_initial_index()
        
        # 更新各部分
        index = self._update_index_section(index, "concepts", results.get("concepts_extracted", []))
        index = self._update_index_section(index, "entities", results.get("entities_extracted", []))
        index = self._update_index_section(index, "videos", [results.get("bvid", "unknown")])
        
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(index)
        
        logger.info(f"更新索引：{index_path}")
    
    async def rebuild_index(self):
        """重建完整的索引（扫描所有页面并提取摘要）"""
        index_path = os.path.join(self.wiki_dir, "index.md")
        index = self._create_initial_index()
        
        # 重建概念索引
        concepts_dir = os.path.join(self.wiki_dir, "concepts")
        if os.path.exists(concepts_dir):
            concepts = []
            for filename in sorted(os.listdir(concepts_dir)):
                if filename.endswith(".md"):
                    filepath = os.path.join(concepts_dir, filename)
                    content = self._load_file_content(filepath)
                    if content:
                        title = self._extract_title(content)
                        summary = self._extract_summary(content)
                        concepts.append((title, filename, summary))
            index = self._update_index_with_summaries(index, "concepts", concepts)
        
        # 重建实体索引
        entities_dir = os.path.join(self.wiki_dir, "entities")
        if os.path.exists(entities_dir):
            entities = []
            for filename in sorted(os.listdir(entities_dir)):
                if filename.endswith(".md"):
                    filepath = os.path.join(entities_dir, filename)
                    content = self._load_file_content(filepath)
                    if content:
                        title = self._extract_title(content)
                        summary = self._extract_summary(content)
                        entities.append((title, filename, summary))
            index = self._update_index_with_summaries(index, "entities", entities)
        
        # 重建视频索引
        videos_dir = os.path.join(self.wiki_dir, "videos")
        if os.path.exists(videos_dir):
            videos = []
            for filename in sorted(os.listdir(videos_dir)):
                if filename.endswith(".md"):
                    filepath = os.path.join(videos_dir, filename)
                    content = self._load_file_content(filepath)
                    if content:
                        title = self._extract_title(content)
                        summary = self._extract_summary(content)
                        bvid = filename.replace(".md", "")
                        videos.append((title, filename, summary, bvid))
            index = self._update_index_with_video_summaries(index, "videos", videos)
        
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(index)
        
        logger.info(f"重建索引完成")
    
    def _load_file_content(self, path: str) -> Optional[str]:
        """加载文件内容"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.warning(f"读取文件失败 [{path}]: {e}")
            return None
    
    def _extract_summary(self, content: str, max_chars: int = 200) -> str:
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
    
    def _update_index_with_summaries(self, index: str, section: str, items: List[tuple]) -> str:
        """使用带摘要的格式更新索引部分"""
        import re
        
        # 找到对应部分
        pattern = rf"(## {section}\n>.*?\n)(.*?)(\n## |\n---|\Z)"
        
        new_content = f"\n"
        for item in items:
            title, filename, summary = item
            page_name = filename.replace(".md", "")
            new_content += f"- **[{title}]({section}/{filename})** - {summary}\n"
        
        new_content += "\n"
        
        replacement = rf"\1{new_content}"
        return re.sub(pattern, replacement, index, flags=re.DOTALL)
    
    def _update_index_with_video_summaries(self, index: str, section: str, items: List[tuple]) -> str:
        """使用带摘要的格式更新视频索引部分"""
        import re
        
        pattern = rf"(## {section}\n>.*?\n)(.*?)(\n## |\n---|\Z)"
        
        new_content = f"\n"
        for item in items:
            title, filename, summary, bvid = item
            new_content += f"- **[{title}](videos/{filename})** - {summary}\n"
        
        new_content += "\n"
        
        replacement = rf"\1{new_content}"
        return re.sub(pattern, replacement, index, flags=re.DOTALL)
    
    def _create_initial_index(self) -> str:
        """创建初始索引"""
        return """# Bilibili RAG Wiki

> 基于 Karpathy LLM Wiki 方案构建的个人知识库

## 导航

- [操作日志](log.md)

## 概念

> 概念页面存储视频中的核心知识点，包含定义、要点和相关视频。

（概念页面将自动添加到这里）

## 实体

> 实体页面存储视频中提到的人、工具、框架、技术等。

（实体页面将自动添加到这里）

## 视频

> 视频页面包含内容摘要、核心概念和关键视觉内容。

（视频页面将自动添加到这里）

---

*本 Wiki 由 Bilibili RAG 系统自动生成和维护*
"""
    
    def _update_index_section(self, index: str, section: str, items: List[str]) -> str:
        """更新索引的某个部分"""
        pattern = rf"(## {section}\n)(.*?)(\n## |\n---|\Z)"
        replacement = rf"\1\n"
        
        for item in items:
            if item:
                replacement += f"- [{item}](/{section}/{item}.md)\n"
        
        replacement += "\n"
        
        import re
        return re.sub(pattern, replacement, index, flags=re.DOTALL)
    
    async def _log_operation(self, operation: str, bvid: str, results: dict):
        """记录操作日志"""
        log_path = os.path.join(self.wiki_dir, "log.md")
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        log_entry = f"## [{timestamp}] {operation} | {bvid}\n\n"
        log_entry += f"- Pages created: {len(results.get('pages_created', []))}\n"
        log_entry += f"- Pages updated: {len(results.get('pages_updated', []))}\n"
        log_entry += f"- Concepts extracted: {len(results.get('concepts_extracted', []))}\n"
        log_entry += f"- Entities extracted: {len(results.get('entities_extracted', []))}\n"
        
        if results.get('errors'):
            log_entry += f"- Errors: {', '.join(results['errors'])}\n"
        
        log_entry += "\n"
        
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        logger.info(f"记录日志：{operation} | {bvid}")
    
    async def _call_llm(self, prompt: str, force_json: bool = False) -> str:
        """调用本地 LLM 服务"""
        try:
            logger.debug(f"调用 LLM: {self.llm_base_url}/chat/completions, model={self.llm_model}")
            
            messages = []
            if force_json:
                messages.append({
                    "role": "system",
                    "content": "你必须只输出纯 JSON 格式的内容。不要输出任何其他文字、解释或 markdown 代码块标记（如 ```json 或 ```）。只输出 JSON 数组或对象。"
                })
            messages.append({
                "role": "user",
                "content": prompt
            })
            
            response = await self.http_client.post(
                f"{self.llm_base_url}/chat/completions",
                json={
                    "model": self.llm_model,
                    "messages": messages,
                    "temperature": 0.3
                }
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            logger.debug(f"LLM 响应内容长度: {len(content)}, 前100字符: {content[:100]}")
            return content
        except httpx.HTTPStatusError as e:
            logger.error(f"LLM 调用失败 (HTTP {e.response.status_code}): {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"LLM 调用失败：{e}")
            raise
    
    def _parse_json_response(self, response: str):
        """尝试从 LLM 响应中解析 JSON"""
        import re
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # 尝试移除 markdown 代码块标记
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else lines[1] if len(lines) > 1 else ""
        
        # 尝试从文本中提取 JSON 数组
        match = re.search(r'\[.*\]', cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        
        # 尝试从文本中提取 JSON 对象
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        
        logger.warning(f"无法从响应中解析 JSON: {response[:200]}")
        return None
    
    async def _write_page(self, path: str, content: str):
        """写入页面文件"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def _build_concept_extraction_prompt(self, source: VideoSource) -> str:
        """构建概念提取提示词"""
        vision_text = ""
        if source.vision_analysis and source.vision_analysis.get("concepts"):
            vision_text = f"""

【视觉分析】
{json.dumps(source.vision_analysis, ensure_ascii=False, indent=2)}
"""
        
        return f"""你是一位知识管理专家。请从以下视频内容中提取关键概念和知识点，构建结构化的知识库。

【重要】只输出纯 JSON 数组，不要输出任何其他文字、解释或 markdown 代码块标记。

【视频标题】
{source.title}

【视频简介】
{source.meta.get("description", "无") if source.meta else "无"}

【ASR 转写文本（前8000字）】
{source.asr_text[:8000]}{vision_text}

请提取 3-10 个核心概念，每个概念包含：
1. name: 概念名称（简洁准确）
2. definition: 详细定义（100-200字，解释这个概念是什么、为什么重要）
3. core_points: 核心要点（3-5个要点，用简洁的语言概括关键信息）
4. context_mentions: 视频中提到该概念的关键上下文（2-3句原文摘录）
5. related_concepts: 相关概念名称列表（从视频内容中推断，0-3个）
6. importance: 重要性（high/medium/low）

输出格式（JSON 数组，不要包含```json标记）：
[
  {{
    "name": "概念名",
    "definition": "详细定义",
    "core_points": ["要点 1", "要点 2", "要点 3"],
    "context_mentions": ["关键上下文摘录1", "关键上下文摘录2"],
    "related_concepts": ["相关概念1", "相关概念2"],
    "importance": "high"
  }}
]

要求：
- 定义要准确、完整，不要过于简短
- 核心要点要具体，不要泛泛而谈
- 尽可能识别概念之间的关系
- 如果视频涉及多个领域，每个领域至少提取一个核心概念
"""
    
    async def _update_video_references(self, concept_name: str, source: VideoSource):
        """更新其他视频页面中对当前概念的引用"""
        # 查找引用了该概念的视频页面
        videos_dir = os.path.join(self.wiki_dir, "videos")
        for filename in os.listdir(videos_dir):
            if filename.endswith(".md"):
                video_path = os.path.join(videos_dir, filename)
                with open(video_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 检查是否已引用该概念
                if f"../../concepts/{concept_name}.md" not in content:
                    # 添加引用
                    import re
                    pattern = r"(## 核心概念\n)(.*?)(\n## |\Z)"
                    replacement = rf"\1- [{concept_name}](../../concepts/{concept_name}.md) @ 提及\n\2"
                    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
                    
                    if new_content != content:
                        with open(video_path, 'w', encoding='utf-8') as f:
                            f.write(new_content)
                        logger.info(f"更新视频页面引用：{filename}")