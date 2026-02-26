"""Book management API routes."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlmodel import select

from api.auth import get_current_active_user
from api.deps import DBSession, get_project_or_404
from api.schemas import (
    BookResponse,
    BookUpdate,
    ChapterListResponse,
    ChapterResponse,
    ErrorResponse,
)
from core.models import Book, BookUploadStatus, Chapter, ChapterStatus, Project

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_active_user)])


def _get_or_create_book(session: DBSession, project_id: str) -> Book:
    """获取或创建书籍记录。"""
    book = session.exec(
        select(Book).where(Book.project_id == project_id)
    ).first()

    if not book:
        book = Book(project_id=project_id)
        session.add(book)
        session.commit()
        session.refresh(book)

    return book


@router.get(
    "",
    response_model=BookResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_book(
    project_id: str,
    session: DBSession,
) -> Book:
    """获取书籍信息。"""
    logger.debug(f"Getting book for project: {project_id}")

    get_project_or_404(session, project_id)
    book = _get_or_create_book(session, project_id)

    return book


@router.patch(
    "",
    response_model=BookResponse,
    responses={404: {"model": ErrorResponse}},
)
def update_book(
    project_id: str,
    book_in: BookUpdate,
    session: DBSession,
) -> Book:
    """更新书籍元数据。"""
    logger.info(f"Updating book for project: {project_id}")

    get_project_or_404(session, project_id)
    book = _get_or_create_book(session, project_id)

    update_data = book_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(book, field, value)

    book.updated_at = datetime.utcnow()

    session.add(book)
    session.commit()
    session.refresh(book)

    logger.info(f"Updated book for project: {project_id}")
    return book


@router.post(
    "/upload",
    response_model=ChapterListResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def upload_book(
    project_id: str,
    session: DBSession,
    file: UploadFile = File(...),
    replace_existing: bool = Query(default=False, description="是否替换现有章节"),
) -> ChapterListResponse:
    """
    上传整本书文件，自动解析为章节。

    支持格式: txt

    Args:
        project_id: 项目 ID
        file: 上传的文件
        replace_existing: 是否替换现有章节
    """
    logger.info(f"Uploading book for project: {project_id}, file: {file.filename}")

    get_project_or_404(session, project_id)

    # 检查文件类型
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    filename_lower = file.filename.lower()
    if not filename_lower.endswith('.txt'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .txt files are supported currently",
        )

    # 读取文件内容
    try:
        content = await file.read()
        # 尝试多种编码
        text_content = None
        for encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'big5']:
            try:
                text_content = content.decode(encoding)
                logger.info(f"Successfully decoded with {encoding}")
                break
            except UnicodeDecodeError:
                continue

        if text_content is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to decode file. Please ensure it's a valid text file.",
            )
    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read file",
        )

    # 解析书籍
    from core.book_parser import book_parser
    try:
        parse_result = book_parser.parse_txt(text_content)
    except Exception as e:
        logger.error(f"Failed to parse book: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to parse book",
        )

    if not parse_result.chapters:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No chapters detected in the file",
        )

    # 如果需要替换，先删除现有章节
    if replace_existing:
        existing_chapters = session.exec(
            select(Chapter).where(Chapter.project_id == project_id)
        ).all()
        for ch in existing_chapters:
            session.delete(ch)
        session.commit()
        logger.info(f"Deleted {len(existing_chapters)} existing chapters")
    else:
        # 检查是否有冲突
        existing_numbers = session.exec(
            select(Chapter.chapter_number).where(Chapter.project_id == project_id)
        ).all()
        new_numbers = [ch.chapter_number for ch in parse_result.chapters]
        conflicts = set(existing_numbers) & set(new_numbers)
        if conflicts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Chapter numbers already exist: {sorted(conflicts)}. Use replace_existing=true to overwrite.",
            )

    # 创建章节记录
    created_chapters = []
    for parsed_ch in parse_result.chapters:
        chapter = Chapter(
            project_id=project_id,
            chapter_number=parsed_ch.chapter_number,
            title=parsed_ch.title,
            content=parsed_ch.content,
            word_count=parsed_ch.word_count,
            status=ChapterStatus.PENDING,
        )
        session.add(chapter)
        created_chapters.append(chapter)

    session.commit()

    # 更新书籍元数据
    book = _get_or_create_book(session, project_id)
    book.total_chapters = parse_result.total_chapters
    book.uploaded_chapters = parse_result.total_chapters
    book.total_words = parse_result.total_words
    book.upload_status = BookUploadStatus.COMPLETE

    if parse_result.detected_title:
        book.original_title = parse_result.detected_title
    if parse_result.detected_author:
        book.author = parse_result.detected_author

    book.updated_at = datetime.utcnow()
    session.add(book)
    session.commit()

    # 刷新章节
    for chapter in created_chapters:
        session.refresh(chapter)

    logger.info(f"Created {len(created_chapters)} chapters from uploaded book")
    return ChapterListResponse(
        items=[ChapterResponse.model_validate(ch) for ch in created_chapters],
        total=len(created_chapters),
        page=1,
        page_size=len(created_chapters),
    )


@router.post(
    "/analyze",
    response_model=BookResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def analyze_book(
    project_id: str,
    session: DBSession,
) -> Book:
    """
    使用 AI 分析整本书，生成摘要和主要情节点。
    """
    logger.info(f"Analyzing book for project: {project_id}")

    get_project_or_404(session, project_id)
    book = _get_or_create_book(session, project_id)

    # 获取所有章节
    chapters = session.exec(
        select(Chapter)
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.chapter_number)
    ).all()

    if not chapters:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No chapters found. Please upload chapters first.",
        )

    # 构建章节摘要
    chapter_summaries = []
    for ch in chapters:
        if ch.key_events:
            summary = f"第{ch.chapter_number}章 {ch.title or ''}: {'; '.join(ch.key_events[:2])}"
        else:
            # 取前200字作为摘要
            summary = f"第{ch.chapter_number}章 {ch.title or ''}: {ch.content[:200]}..."
        chapter_summaries.append(summary)

    # 使用 LLM 生成全书摘要
    from integrations.llm_client import llm_client
    from pydantic import BaseModel, Field
    from typing import List

    class BookAnalysis(BaseModel):
        summary: str = Field(description="全书摘要，200-300字")
        main_plot_points: List[str] = Field(description="主要情节点，5-10个")
        suggested_episodes: int = Field(description="建议的动漫集数")

    prompt = f"""分析以下小说的章节摘要，生成全书分析。

章节摘要:
{chr(10).join(chapter_summaries[:50])}  # 限制数量避免超出 token

请提供:
1. 全书摘要（200-300字，概括主要剧情）
2. 主要情节点（5-10个关键转折点）
3. 建议的动漫集数（每集约24分钟，考虑剧情完整性）
"""

    try:
        analysis = llm_client.generate_structured_output(prompt, BookAnalysis)
        if analysis:
            book.ai_summary = analysis.summary
            book.main_plot_points = analysis.main_plot_points
            book.suggested_episodes = analysis.suggested_episodes
    except Exception as e:
        logger.error(f"Failed to analyze book: {e}")
        # 不抛出异常，只是记录错误

    book.updated_at = datetime.utcnow()
    session.add(book)
    session.commit()
    session.refresh(book)

    logger.info(f"Analyzed book for project: {project_id}")
    return book
