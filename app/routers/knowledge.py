"""
Bilibili Wiki 知识库系统

基于 Karpathy LLM Wiki 方案的知识库构建和管理
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from loguru import logger
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_db_context
from app.models import FavoriteFolder, FavoriteVideo, VideoCache, UserSession
from app.services.bilibili import BilibiliService
from app.services.content_fetcher import ContentFetcher
from app.services.asr import ASRService
from app.services.vision import VisionService
from app.services.wiki_builder import WikiBuilder, VideoSource
from app.routers.auth import get_session
from app.config import settings

router = APIRouter(prefix="/knowledge", tags=["知识库"])

# 构建任务状态
build_tasks = {}


class BuildRequest(BaseModel):
    """知识库构建请求"""
    folder_ids: List[int]  # 要处理的收藏夹 ID 列表
    exclude_bvids: Optional[List[str]] = None  # 排除的视频


class WikiStats(BaseModel):
    """Wiki 统计信息"""
    total_concepts: int
    total_entities: int
    total_videos: int
    last_update: Optional[str]


class BuildStatus(BaseModel):
    """构建状态"""
    task_id: str
    status: str  # pending / running / completed / failed
    progress: int  # 0-100
    current_step: str
    total_videos: int
    processed_videos: int
    message: str


class FolderStatus(BaseModel):
    """收藏夹入库状态"""
    media_id: int
    indexed_count: int
    media_count: Optional[int] = None
    last_sync_at: Optional[datetime] = None


class SyncRequest(BaseModel):
    """同步请求"""
    folder_ids: Optional[List[int]] = None


class SyncResult(BaseModel):
    """同步结果"""
    folder_id: int
    total: int
    added: int
    removed: int
    indexed: int
    message: str
    last_sync_at: Optional[datetime] = None


async def _get_or_create_folder(
    db: AsyncSession,
    session_id: str,
    media_id: int,
    title: Optional[str] = None,
    media_count: Optional[int] = None,
) -> FavoriteFolder:
    """获取或创建收藏夹记录"""
    result = await db.execute(
        select(FavoriteFolder).where(
            FavoriteFolder.session_id == session_id,
            FavoriteFolder.media_id == media_id,
        )
    )
    folder = result.scalar_one_or_none()

    if folder is None:
        folder = FavoriteFolder(
            session_id=session_id,
            media_id=media_id,
            title=title or "",
            media_count=media_count or 0,
            is_selected=True,
        )
        db.add(folder)
        await db.flush()
    else:
        if title:
            folder.title = title
        if media_count is not None:
            folder.media_count = media_count

    return folder


def _extract_video_info(media: dict) -> tuple[str, str, Optional[int]]:
    """抽取视频关键信息"""
    bvid = media.get("bvid") or media.get("bv_id")
    title = media.get("title", bvid)
    cid = None
    ugc = media.get("ugc") or {}
    if ugc.get("first_cid"):
        cid = ugc.get("first_cid")
    else:
        cid = media.get("cid") or media.get("id")
    return bvid, title, cid


async def _upsert_video_cache(db: AsyncSession, bvid: str, meta: dict) -> None:
    """写入或更新视频缓存信息"""
    result = await db.execute(select(VideoCache).where(VideoCache.bvid == bvid))
    cache = result.scalar_one_or_none()

    if cache is None:
        cache = VideoCache(
            bvid=bvid,
            title=meta.get("title") or bvid,
            description=meta.get("intro"),
            owner_name=meta.get("owner_name"),
            owner_mid=meta.get("owner_mid"),
            duration=meta.get("duration"),
            pic_url=meta.get("cover"),
            is_processed=False,
        )
        db.add(cache)
        return

    cache.title = meta.get("title") or cache.title
    if meta.get("intro") is not None:
        cache.description = meta.get("intro")
    if meta.get("owner_name") is not None:
        cache.owner_name = meta.get("owner_name")
    if meta.get("owner_mid") is not None:
        cache.owner_mid = meta.get("owner_mid")
    if meta.get("duration") is not None:
        cache.duration = meta.get("duration")
    if meta.get("cover") is not None:
        cache.pic_url = meta.get("cover")


async def _sync_folder(
    db: AsyncSession,
    bili: BilibiliService,
    content_fetcher: ContentFetcher,
    session_id: str,
    folder_id: int,
    exclude_bvids: Optional[set[str]] = None,
    progress_callback: Optional = None,
) -> dict:
    """同步单个收藏夹到 Wiki"""
    info = {}
    try:
        info_result = await bili.get_favorite_content(folder_id, pn=1, ps=1)
        info = info_result.get("info", {})
    except Exception as e:
        logger.warning(f"获取收藏夹信息失败 [{folder_id}]: {e}")

    videos = await bili.get_all_favorite_videos(folder_id)
    total_in_folder = info.get("media_count", len(videos))

    # 保护：接口异常返回空列表时，避免误删
    if not videos:
        if total_in_folder and total_in_folder > 0:
            logger.warning(f"[{folder_id}] 收藏夹返回空列表，跳过删除逻辑")
            existing_count = await db.scalar(
                select(func.count(FavoriteVideo.bvid))
                .where(FavoriteVideo.folder_id == folder_id)
            )
            return {
                "folder_id": folder_id,
                "total": total_in_folder,
                "added": 0,
                "removed": 0,
                "indexed": existing_count or 0,
                "message": "本次同步异常：空列表，已跳过",
                "last_sync_at": datetime.utcnow(),
            }

    video_map = {}
    skipped_invalid = 0
    for media in videos:
        bvid, title, cid = _extract_video_info(media)
        if not bvid:
            continue
        if exclude_bvids and bvid in exclude_bvids:
            continue
        
        # 过滤失效视频（被删除、下架等）
        attr = media.get("attr", 0)
        if attr == 9 or title in ["已失效视频", "已删除视频"]:
            skipped_invalid += 1
            logger.debug(f"跳过失效视频：{bvid} - {title}")
            continue
        
        owner = media.get("upper") or {}
        video_map[bvid] = {
            "title": title,
            "cid": cid,
            "intro": media.get("intro"),
            "cover": media.get("cover"),
            "duration": media.get("duration"),
            "owner_name": owner.get("name"),
            "owner_mid": owner.get("mid"),
        }
    
    if skipped_invalid > 0:
        logger.info(f"[{folder_id}] 过滤了 {skipped_invalid} 个失效视频")

    valid_count = len(video_map)
    current_bvids = set(video_map.keys())

    folder = await _get_or_create_folder(
        db,
        session_id=session_id,
        media_id=folder_id,
        title=info.get("title"),
        media_count=valid_count,
    )

    existing_rows = await db.execute(
        select(FavoriteVideo.bvid).where(FavoriteVideo.folder_id == folder.id)
    )
    existing_bvids = {row[0] for row in existing_rows.fetchall()}

    added = current_bvids - existing_bvids
    removed = existing_bvids - current_bvids

    # 写入标题/简介等信息
    for bvid, meta in video_map.items():
        await _upsert_video_cache(db, bvid, meta)

    # 写入 FavoriteVideo 记录
    for bvid in current_bvids:
        exists_row = await db.execute(
            select(FavoriteVideo.id).where(
                FavoriteVideo.folder_id == folder.id,
                FavoriteVideo.bvid == bvid,
            )
        )
        if exists_row.scalar_one_or_none() is None:
            db.add(FavoriteVideo(folder_id=folder.id, bvid=bvid, is_selected=True))

    # 删除无效记录
    if removed:
        await db.execute(
            select(FavoriteVideo).where(
                FavoriteVideo.folder_id == folder.id,
                FavoriteVideo.bvid.in_(removed),
            )
        )
        for bvid in removed:
            other_count = await db.scalar(
                select(func.count())
                .select_from(FavoriteVideo)
                .where(
                    FavoriteVideo.bvid == bvid,
                    FavoriteVideo.folder_id != folder.id,
                )
            )
            if other_count == 0:
                # 如果其他收藏夹也没有，可以删除
                pass

        await db.execute(
            select(FavoriteVideo).where(
                FavoriteVideo.folder_id == folder.id,
                FavoriteVideo.bvid.in_(removed),
            )
        )

    folder.last_sync_at = datetime.utcnow()

    await db.commit()

    indexed_count = await db.scalar(
        select(func.count(func.distinct(FavoriteVideo.bvid)))
        .select_from(FavoriteVideo)
        .where(FavoriteVideo.folder_id == folder.id)
    )

    return {
        "folder_id": folder_id,
        "total": valid_count,
        "added": len(added),
        "removed": len(removed),
        "indexed": indexed_count or 0,
        "message": "同步完成",
        "last_sync_at": folder.last_sync_at,
    }


@router.get("/stats")
async def get_knowledge_stats():
    """获取知识库统计信息（Wiki 模式）"""
    try:
        wiki_dir = settings.wiki_dir
        import os
        
        # 统计视频页面
        videos_dir = os.path.join(wiki_dir, "videos")
        total_videos = len([f for f in os.listdir(videos_dir) if f.endswith(".md")]) if os.path.exists(videos_dir) else 0
        
        return {
            "total_videos": total_videos,
            "mode": "wiki"
        }
    except Exception as e:
        logger.error(f"获取统计信息失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wiki/stats")
async def get_wiki_stats():
    """获取 Wiki 统计信息"""
    try:
        wiki_dir = settings.wiki_dir
        import os
        from datetime import datetime
        
        # 统计概念页面
        concepts_dir = os.path.join(wiki_dir, "concepts")
        total_concepts = len([f for f in os.listdir(concepts_dir) if f.endswith(".md")]) if os.path.exists(concepts_dir) else 0
        
        # 统计实体页面
        entities_dir = os.path.join(wiki_dir, "entities")
        total_entities = len([f for f in os.listdir(entities_dir) if f.endswith(".md")]) if os.path.exists(entities_dir) else 0
        
        # 统计视频页面
        videos_dir = os.path.join(wiki_dir, "videos")
        total_videos = len([f for f in os.listdir(videos_dir) if f.endswith(".md")]) if os.path.exists(videos_dir) else 0
        
        # 获取最后更新时间
        last_update = None
        log_path = os.path.join(wiki_dir, "log.md")
        if os.path.exists(log_path):
            import stat
            stat_info = os.stat(log_path)
            last_update = datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        
        return WikiStats(
            total_concepts=total_concepts,
            total_entities=total_entities,
            total_videos=total_videos,
            last_update=last_update
        )
    except Exception as e:
        logger.error(f"获取 Wiki 统计信息失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/folders/status", response_model=List[FolderStatus])
async def get_folder_status(
    session_id: str = Query(..., description="会话 ID"),
    db: AsyncSession = Depends(get_db),
):
    """获取收藏夹入库状态（跨 Session 查找同一用户的数据）"""
    
    # 1. 先查当前 Session 对应的用户 MID
    result = await db.execute(
        select(UserSession.bili_mid).where(UserSession.session_id == session_id)
    )
    mid = result.scalar()
    
    target_session_ids = [session_id]
    
    if mid:
        # 2. 如果有 MID，查找该用户所有的 Session ID
        result = await db.execute(
            select(UserSession.session_id).where(UserSession.bili_mid == mid)
        )
        target_session_ids = [row[0] for row in result.fetchall()]
    
    # 3. 查询所有关联 Session 的收藏夹状态
    rows = await db.execute(
        select(FavoriteFolder.id, FavoriteFolder.media_id, FavoriteFolder.last_sync_at)
        .where(FavoriteFolder.session_id.in_(target_session_ids))
        .order_by(FavoriteFolder.updated_at.desc())
    )
    
    # 手动按 media_id 去重，保留最新的
    folders_map = {}
    for row in rows.fetchall():
        fid, media_id, last_sync = row
        if media_id not in folders_map:
            folders_map[media_id] = (fid, last_sync)
            
    if not folders_map:
        return []

    folder_ids = [v[0] for v in folders_map.values()]
    
    # 4. 统计视频数量
    counts = await db.execute(
        select(FavoriteVideo.folder_id, func.count(func.distinct(FavoriteVideo.bvid)))
        .where(FavoriteVideo.folder_id.in_(folder_ids))
        .group_by(FavoriteVideo.folder_id)
    )
    count_map = {row[0]: row[1] for row in counts.fetchall()}

    result = []
    for media_id, (folder_id, last_sync_at) in folders_map.items():
        folder_row = await db.execute(
            select(FavoriteFolder.media_count).where(FavoriteFolder.id == folder_id)
        )
        media_count = folder_row.scalar()
        result.append(
            FolderStatus(
                media_id=media_id,
                indexed_count=count_map.get(folder_id, 0),
                media_count=media_count,
                last_sync_at=last_sync_at,
            )
        )
    return result


@router.post("/folders/sync", response_model=List[SyncResult])
async def sync_folders(
    request: SyncRequest,
    session_id: str = Query(..., description="会话 ID"),
    db: AsyncSession = Depends(get_db),
):
    """同步收藏夹到 Wiki"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    cookies = session.get("cookies", {})
    user_info = session.get("user_info", {})

    bili = BilibiliService(
        sessdata=cookies.get("SESSDATA"),
        bili_jct=cookies.get("bili_jct"),
        dedeuserid=cookies.get("DedeUserID"),
    )
    asr_service = ASRService()
    vision_service = VisionService() if settings.vision_enabled else None
    content_fetcher = ContentFetcher(bili, asr_service, vision_service)

    try:
        folder_ids = request.folder_ids or []
        if not folder_ids:
            mid = user_info.get("mid") or cookies.get("DedeUserID")
            if not mid:
                raise HTTPException(status_code=400, detail="无法获取用户信息")
            folders = await bili.get_user_favorites(mid=mid)
            folder_ids = [folder.get("id") for folder in folders if folder.get("id")]

        results: List[SyncResult] = []
        for folder_id in folder_ids:
            try:
                result = await _sync_folder(
                    db,
                    bili,
                    content_fetcher,
                    session_id,
                    folder_id,
                )
                results.append(SyncResult(**result))
            except Exception as e:
                logger.error(f"同步收藏夹失败 [{folder_id}]: {e}")
                results.append(
                    SyncResult(
                        folder_id=folder_id,
                        total=0,
                        added=0,
                        removed=0,
                        indexed=0,
                        message=f"同步失败：{e}",
                        last_sync_at=None,
                    )
                )

        return results
    finally:
        await bili.close()


@router.post("/build")
async def build_knowledge_base(
    request: BuildRequest,
    background_tasks: BackgroundTasks,
    session_id: str = Query(..., description="会话 ID"),
):
    """构建知识库（Wiki 模式）"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    import uuid
    task_id = str(uuid.uuid4())

    build_tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "current_step": "初始化中...",
        "total_videos": 0,
        "processed_videos": 0,
        "message": "",
    }

    background_tasks.add_task(
        _build_wiki_task,
        task_id,
        session_id,
        session,
        request.folder_ids,
        request.exclude_bvids or [],
    )

    return {"task_id": task_id, "message": "构建任务已启动", "mode": "wiki"}


async def _build_wiki_task(
    task_id: str,
    session_id: str,
    session: dict,
    folder_ids: List[int],
    exclude_bvids: List[str],
):
    """后台构建任务（Wiki 模式）"""
    cookies = session.get("cookies", {})

    try:
        build_tasks[task_id]["status"] = "running"
        build_tasks[task_id]["current_step"] = "初始化 Wiki 构建器..."

        bili = BilibiliService(
            sessdata=cookies.get("SESSDATA"),
            bili_jct=cookies.get("bili_jct"),
            dedeuserid=cookies.get("DedeUserID"),
        )
        asr_service = ASRService()
        vision_service = VisionService() if settings.vision_enabled else None
        content_fetcher = ContentFetcher(bili, asr_service, vision_service)
        wiki_builder = WikiBuilder()

        try:
            total_folders = len(folder_ids)
            if total_folders == 0:
                build_tasks[task_id]["status"] = "completed"
                build_tasks[task_id]["progress"] = 100
                build_tasks[task_id]["message"] = "没有需要处理的收藏夹"
                return

            processed = 0
            total_videos = 0
            total_concepts = 0
            total_entities = 0

            async with get_db_context() as db:
                for idx, folder_id in enumerate(folder_ids, start=1):
                    build_tasks[task_id]["current_step"] = f"处理收藏夹 {folder_id}"

                    # 获取收藏夹视频
                    videos = await bili.get_all_favorite_videos(folder_id)
                    total_videos += len(videos)

                    for media in videos:
                        bvid = media.get("bvid") or media.get("bv_id")
                        if not bvid or bvid in exclude_bvids:
                            continue
                        
                        # 检查是否已处理
                        result = await db.execute(
                            select(VideoCache).where(VideoCache.bvid == bvid)
                        )
                        cache = result.scalar_one_or_none()
                        
                        if cache and cache.is_processed:
                            continue
                        
                        title = media.get("title", bvid)
                        cid = media.get("cid") or media.get("id")
                        
                        build_tasks[task_id]["current_step"] = f"处理视频：{title}"

                        # 获取视频内容
                        content = await content_fetcher.fetch_content(bvid, cid, title)
                        
                        # 保存缓存
                        if cache:
                            cache.content = content.content
                            cache.content_source = content.source.value
                            cache.is_processed = True
                        else:
                            from app.models import VideoCache as VC
                            new_cache = VC(
                                bvid=bvid,
                                title=title,
                                content=content.content,
                                content_source=content.source.value,
                                is_processed=True,
                            )
                            db.add(new_cache)

                        # 构建视频源数据
                        video_source = VideoSource(
                            bvid=bvid,
                            title=title,
                            asr_text=content.content or "",
                            vision_analysis=content.vision_analysis,
                            meta={
                                "up_owner": media.get("upper", {}).get("name", "未知 UP 主"),
                                "duration": media.get("duration"),
                                "cover": media.get("cover"),
                            }
                        )

                        # 处理视频到 Wiki
                        result = await wiki_builder.process_video(video_source)
                        total_concepts += len(result.get("concepts_extracted", []))
                        total_entities += len(result.get("entities_extracted", []))
                        
                        processed += 1
                        build_tasks[task_id]["progress"] = int((processed / total_videos) * 100) if total_videos > 0 else 0

            build_tasks[task_id]["status"] = "completed"
            build_tasks[task_id]["progress"] = 100
            build_tasks[task_id]["current_step"] = "完成"
            build_tasks[task_id]["message"] = f"Wiki 构建完成：处理 {processed} 视频，提取 {total_concepts} 概念，{total_entities} 实体"

            logger.info(f"Wiki 构建完成：处理 {processed} 视频，提取 {total_concepts} 概念，{total_entities} 实体")
        finally:
            await wiki_builder.close()
            await bili.close()

    except Exception as e:
        logger.error(f"Wiki 构建任务失败：{e}")
        build_tasks[task_id]["status"] = "failed"
        build_tasks[task_id]["message"] = str(e)


@router.get("/build/status/{task_id}", response_model=BuildStatus)
async def get_build_status(task_id: str):
    """获取构建任务状态"""
    if task_id not in build_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = build_tasks[task_id]
    return BuildStatus(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"],
        current_step=task["current_step"],
        total_videos=task["total_videos"],
        processed_videos=task["processed_videos"],
        message=task["message"],
    )


@router.delete("/clear")
async def clear_knowledge_base():
    """清空 Wiki 知识库"""
    try:
        import shutil
        wiki_dir = settings.wiki_dir
        if os.path.exists(wiki_dir):
            shutil.rmtree(wiki_dir)
        os.makedirs(wiki_dir, exist_ok=True)
        return {"message": "Wiki 知识库已清空"}
    except Exception as e:
        logger.error(f"清空知识库失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))
