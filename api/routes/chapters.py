"""Chapter management API routes."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import func, select

from api.deps import DBSession
from api.schemas import (
    ChapterBatchAnalysisResponse,
    ChapterBatchCreate,
    ChapterCreate,
    ChapterListResponse,
    ChapterResponse,
    ChapterUpdate,
    ChapterAnalysisResult,
    ErrorResponse,
)
from core.models import Chapter, ChapterStatus, Project, Book, BookUploadStatus

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_project_or_404(session: DBSession, project_id: str) -> Project:
    """获取项目，不存在则抛出 404。"""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {project_id}",
        )
    return project


def _update_book_stats(session: DBSession, project_id: str) -> None:
    """更新书籍统计信息。"""
    # 获取或创建 Book 记录
    book = session.exec(
        select(Book).where(Book.project_id == project_id)
    ).first()

    if not book:
        book = Book(project_id=project_id)
        session.add(book)

    # 统计章节数和字数
    chapters = session.exec(
        select(Chapter).where(Chapter.project_id == project_id)
    ).all()

    book.uploaded_chapters = len(chapters)
    book.total_words = sum(ch.word_count for ch in chapters)

    # 更新上传状态
    if book.uploaded_chapters == 0:
        book.upload_status = BookUploadStatus.EMPTY
    elif book.total_chapters > 0 and book.uploaded_chapters >= book.total_chapters:
        book.upload_status = BookUploadStatus.COMPLETE
    else:
        book.upload_status = BookUploadStatus.PARTIAL

    book.updated_at = datetime.utcnow()
    session.add(book)


@router.post(
    "",
    response_model=ChapterResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def create_chapter(
    project_id: str,
    chapter_in: ChapterCreate,
    session: DBSession,
) -> Chapter:
    """上传单个章节。"""
    logger.info(f"Creating chapter {chapter_in.chapter_number} for project: {project_id}")

    _get_project_or_404(session, project_id)

    # 检查章节号是否已存在
    existing = session.exec(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_in.chapter_number
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chapter {chapter_in.chapter_number} already exists",
        )

    # 计算字数
    word_count = len(chapter_in.content)

    chapter = Chapter(
        project_id=project_id,
        chapter_number=chapter_in.chapter_number,
        title=chapter_in.title,
        content=chapter_in.content,
        word_count=word_count,
        status=ChapterStatus.PENDING,
    )

    session.add(chapter)
    session.commit()

    # 更新书籍统计
    _update_book_stats(session, project_id)
    session.commit()

    session.refresh(chapter)
    logger.info(f"Created chapter: {chapter.chapter_id}")
    return chapter


@router.post(
    "/batch",
    response_model=ChapterListResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def create_chapters_batch(
    project_id: str,
    batch_in: ChapterBatchCreate,
    session: DBSession,
) -> ChapterListResponse:
    """批量上传章节。"""
    logger.info(f"Batch creating {len(batch_in.chapters)} chapters for project: {project_id}")

    _get_project_or_404(session, project_id)

    # 检查章节号是否有重复
    chapter_numbers = [ch.chapter_number for ch in batch_in.chapters]
    if len(chapter_numbers) != len(set(chapter_numbers)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate chapter numbers in batch",
        )

    # 检查是否与现有章节冲突
    existing = session.exec(
        select(Chapter.chapter_number).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number.in_(chapter_numbers)
        )
    ).all()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chapters already exist: {existing}",
        )

    # 创建章节
    created_chapters = []
    for chapter_in in batch_in.chapters:
        word_count = len(chapter_in.content)
        chapter = Chapter(
            project_id=project_id,
            chapter_number=chapter_in.chapter_number,
            title=chapter_in.title,
            content=chapter_in.content,
            word_count=word_count,
            status=ChapterStatus.PENDING,
        )
        session.add(chapter)
        created_chapters.append(chapter)

    session.commit()

    # 更新书籍统计
    _update_book_stats(session, project_id)
    session.commit()

    # 刷新所有章节
    for chapter in created_chapters:
        session.refresh(chapter)

    logger.info(f"Batch created {len(created_chapters)} chapters")
    return ChapterListResponse(
        items=[ChapterResponse.model_validate(ch) for ch in created_chapters],
        total=len(created_chapters),
        page=1,
        page_size=len(created_chapters),
    )


@router.get(
    "",
    response_model=ChapterListResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_chapters(
    project_id: str,
    session: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status_filter: Optional[ChapterStatus] = Query(default=None, alias="status"),
) -> ChapterListResponse:
    """列出项目所有章节（分页）。"""
    logger.debug(f"Listing chapters for project: {project_id}")

    _get_project_or_404(session, project_id)

    query = select(Chapter).where(Chapter.project_id == project_id)
    count_query = select(func.count()).select_from(Chapter).where(Chapter.project_id == project_id)

    if status_filter:
        query = query.where(Chapter.status == status_filter)
        count_query = count_query.where(Chapter.status == status_filter)

    query = query.order_by(Chapter.chapter_number)
    query = query.offset((page - 1) * page_size).limit(page_size)

    chapters = session.exec(query).all()
    total = session.exec(count_query).one()

    return ChapterListResponse(
        items=[ChapterResponse.model_validate(ch) for ch in chapters],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{chapter_number}",
    response_model=ChapterResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_chapter(
    project_id: str,
    chapter_number: int,
    session: DBSession,
) -> ChapterResponse:
    """获取单个章节详情。"""
    logger.debug(f"Getting chapter {chapter_number} for project: {project_id}")

    _get_project_or_404(session, project_id)

    chapter = session.exec(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number
        )
    ).first()

    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter {chapter_number} not found",
        )

    # 确保字段有默认值
    return ChapterResponse(
        chapter_id=chapter.chapter_id,
        project_id=chapter.project_id,
        chapter_number=chapter.chapter_number,
        title=chapter.title,
        content=chapter.content,
        word_count=chapter.word_count if chapter.word_count else len(chapter.content),
        key_events=chapter.key_events or [],
        emotional_arc=chapter.emotional_arc,
        importance_score=chapter.importance_score if chapter.importance_score is not None else 0.5,
        suggested_episode=chapter.suggested_episode,
        characters_appeared=chapter.characters_appeared or [],
        status=chapter.status,
        created_at=chapter.created_at,
        updated_at=chapter.updated_at,
    )


@router.patch(
    "/{chapter_number}",
    response_model=ChapterResponse,
    responses={404: {"model": ErrorResponse}},
)
def update_chapter(
    project_id: str,
    chapter_number: int,
    chapter_in: ChapterUpdate,
    session: DBSession,
) -> Chapter:
    """更新章节内容。"""
    logger.info(f"Updating chapter {chapter_number} for project: {project_id}")

    _get_project_or_404(session, project_id)

    chapter = session.exec(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number
        )
    ).first()

    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter {chapter_number} not found",
        )

    update_data = chapter_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(chapter, field, value)

    # 如果更新了内容，重新计算字数
    if "content" in update_data:
        chapter.word_count = len(chapter.content)
        # 重置分析状态
        chapter.status = ChapterStatus.PENDING
        chapter.key_events = []
        chapter.emotional_arc = None
        chapter.importance_score = 0.5
        chapter.characters_appeared = []
        chapter.suggested_episode = None

    chapter.updated_at = datetime.utcnow()

    session.add(chapter)
    session.commit()

    # 更新书籍统计
    _update_book_stats(session, project_id)
    session.commit()

    session.refresh(chapter)
    logger.info(f"Updated chapter {chapter_number}")
    return chapter


@router.delete(
    "/{chapter_number}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
def delete_chapter(
    project_id: str,
    chapter_number: int,
    session: DBSession,
) -> None:
    """删除章节。"""
    logger.info(f"Deleting chapter {chapter_number} from project: {project_id}")

    _get_project_or_404(session, project_id)

    chapter = session.exec(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number
        )
    ).first()

    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter {chapter_number} not found",
        )

    session.delete(chapter)
    session.commit()

    # 更新书籍统计
    _update_book_stats(session, project_id)
    session.commit()

    logger.info(f"Deleted chapter {chapter_number}")


@router.post(
    "/{chapter_number}/analyze",
    response_model=ChapterAnalysisResult,
    responses={404: {"model": ErrorResponse}},
)
def analyze_chapter(
    project_id: str,
    chapter_number: int,
    session: DBSession,
) -> ChapterAnalysisResult:
    """分析单个章节。"""
    logger.info(f"Analyzing chapter {chapter_number} for project: {project_id}")

    _get_project_or_404(session, project_id)

    chapter = session.exec(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number
        )
    ).first()

    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter {chapter_number} not found",
        )

    # 获取前一章的摘要作为上下文
    previous_summary = None
    if chapter_number > 1:
        prev_chapter = session.exec(
            select(Chapter).where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == chapter_number - 1
            )
        ).first()
        if prev_chapter and prev_chapter.key_events:
            previous_summary = "; ".join(prev_chapter.key_events[:3])

    # 调用分析服务
    from core.chapter_analyzer import chapter_analyzer
    analysis = chapter_analyzer.analyze_chapter(
        chapter_content=chapter.content,
        chapter_number=chapter_number,
        chapter_title=chapter.title,
        previous_summary=previous_summary
    )

    # 更新章节记录
    chapter.key_events = analysis.key_events
    chapter.emotional_arc = analysis.emotional_arc
    chapter.importance_score = analysis.importance_score
    chapter.characters_appeared = analysis.characters_appeared
    chapter.status = ChapterStatus.READY
    chapter.updated_at = datetime.utcnow()

    session.add(chapter)
    session.commit()
    session.refresh(chapter)

    logger.info(f"Analyzed chapter {chapter_number}")
    return ChapterAnalysisResult(
        chapter_id=chapter.chapter_id,
        chapter_number=chapter.chapter_number,
        key_events=chapter.key_events,
        emotional_arc=chapter.emotional_arc or "neutral",
        importance_score=chapter.importance_score,
        characters_appeared=chapter.characters_appeared,
        suggested_episode=chapter.suggested_episode,
    )


@router.post(
    "/analyze-all",
    response_model=ChapterBatchAnalysisResponse,
    responses={404: {"model": ErrorResponse}},
)
def analyze_all_chapters(
    project_id: str,
    session: DBSession,
    force: bool = Query(default=False, description="强制重新分析已分析的章节"),
) -> ChapterBatchAnalysisResponse:
    """分析项目所有章节。"""
    logger.info(f"Analyzing all chapters for project: {project_id}")

    _get_project_or_404(session, project_id)

    # 获取所有章节
    query = select(Chapter).where(Chapter.project_id == project_id)
    if not force:
        query = query.where(Chapter.status != ChapterStatus.READY)
    query = query.order_by(Chapter.chapter_number)

    chapters = session.exec(query).all()

    if not chapters:
        return ChapterBatchAnalysisResponse(
            analyzed_count=0,
            results=[],
        )

    # 准备章节数据
    chapter_data = [
        {
            "chapter_number": ch.chapter_number,
            "title": ch.title,
            "content": ch.content,
        }
        for ch in chapters
    ]

    # 批量分析
    from core.chapter_analyzer import chapter_analyzer
    analyses = chapter_analyzer.analyze_chapters_batch(chapter_data)

    # 更新章节记录
    results = []
    for chapter, analysis in zip(chapters, analyses):
        chapter.key_events = analysis.key_events
        chapter.emotional_arc = analysis.emotional_arc
        chapter.importance_score = analysis.importance_score
        chapter.characters_appeared = analysis.characters_appeared
        chapter.status = ChapterStatus.READY
        chapter.updated_at = datetime.utcnow()
        session.add(chapter)

        results.append(ChapterAnalysisResult(
            chapter_id=chapter.chapter_id,
            chapter_number=chapter.chapter_number,
            key_events=chapter.key_events,
            emotional_arc=chapter.emotional_arc or "neutral",
            importance_score=chapter.importance_score,
            characters_appeared=chapter.characters_appeared,
            suggested_episode=chapter.suggested_episode,
        ))

    session.commit()

    logger.info(f"Analyzed {len(results)} chapters")
    return ChapterBatchAnalysisResponse(
        analyzed_count=len(results),
        results=results,
    )
