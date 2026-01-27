"""
Director - 影视工业制片调度系统

职责：
- 项目创建与管理
- 小说导入与解析
- 资产构建（角色提取 + 参考图生成）
- 分镜生成
- 渲染任务调度
"""
import logging
from datetime import datetime
from typing import List, Optional, Dict
import os

from sqlmodel import Session, select

from core.models import (
    Project, ProjectStatus,
    Job, JobStatus,
    Shot, ShotRender, ShotRenderStatus,
    Character
)
# 移除 core.database 的 engine 导入，因为我们不再自己创建连接
from core.script_parser import script_parser
from core.asset_manager import asset_manager
from integrations.llm_client import llm_client
from config import settings

logger = logging.getLogger(__name__)


class AssetNotReadyError(Exception):
    pass

class ProjectNotFoundError(Exception):
    pass

class InvalidProjectStateError(Exception):
    pass


class Director:
    """导演编排器 - 统筹影视生产全流程"""

    def __init__(self, session: Session, max_workers: int = 4):
        """
        初始化导演
        :param session: 注入的数据库会话
        :param max_workers: 最大并发数
        """
        self.session = session  # 接收并存储注入的 session
        self.max_workers = max_workers

    def create_project(self, name: str, description: Optional[str] = None) -> Project:
        project = Project(name=name, description=description)
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        logger.info(f"Created project: {project.id} - {project.name}")
        return project

    def ingest_novel(
        self,
        project_id: str,
        text: str,
        chapter_meta: Optional[Dict] = None
    ) -> Project:
        # 直接使用 self.session
        project = self.session.get(Project, project_id)
        if not project:
            raise ProjectNotFoundError(f"Project not found: {project_id}")

        project.script_content = text
        project.status = ProjectStatus.ASSETS_READY
        project.updated_at = datetime.utcnow()

        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)

        logger.info(f"Ingested novel for project: {project_id}, text length: {len(text)}")
        
        self.auto_detect_genre_and_style(project_id)
        
        return project

    def auto_detect_genre_and_style(self, project_id: str) -> Project:
        """
        在项目启动时自动判定题材和生成画风约束
        
        1. 获取项目内容（小说开篇或第一章）
        2. 调用 LLM 分析题材（东方玄幻/赛博朋克/日系校园等）
        3. 根据题材生成全局画风提示词
        4. 保存到 Project.genre 和 Project.style_preset
        """
        from pydantic import BaseModel
        
        project = self.session.get(Project, project_id)
        if not project:
            raise ProjectNotFoundError(f"Project not found: {project_id}")
        
        if not project.script_content:
            logger.warning(f"Project {project_id} has no script content, skipping genre detection")
            return project
        
        class GenreStyleResponse(BaseModel):
            genre: str
            genre_name: str
            style_preset: str
        
        prompt = f"""分析以下小说内容，判定其题材类型和推荐的画风风格。

题材选项：
- 东方玄幻 (chinese_fantasy)
- 西方奇幻 (western_fantasy)
- 现代都市 (modern_urban)
- 赛博朋克 (cyberpunk)
- 日系校园 (japanese_school)
- 历史古风 (historical)
- 科幻未来 (sci_fi)

小说内容：
---
{project.script_content[:8000]}
---

返回 JSON:
{{
    "genre": "题材代码（如 chinese_fantasy）",
    "genre_name": "题材中文名（如 东方玄幻）",
    "style_preset": "详细的画风提示词约束，用于图像生成，需要是英文，包含艺术风格、色调、渲染风格等"
}}"""

        try:
            result = llm_client.generate_structured_output(prompt, GenreStyleResponse, temperature=0.3)
            if result:
                project.style_preset = result.style_preset
                if project.project_metadata is None:
                    project.project_metadata = {}
                project.project_metadata["genre"] = result.genre
                project.project_metadata["genre_name"] = result.genre_name
                project.updated_at = datetime.utcnow()
                
                self.session.add(project)
                self.session.commit()
                self.session.refresh(project)
                
                logger.info(f"Auto-detected genre for project {project_id}: {result.genre_name}, style_preset: {result.style_preset[:50]}...")
            else:
                logger.warning(f"Failed to detect genre for project {project_id}, using default style")
        except Exception as e:
            logger.error(f"Error detecting genre for project {project_id}: {e}")
        
        return project

    def build_assets(self, project_id: str) -> Project:
        project = self.session.get(Project, project_id)
        if not project:
            raise ProjectNotFoundError(f"Project not found: {project_id}")

        if not project.script_content:
            raise InvalidProjectStateError(
                f"Project {project_id} has no script content. Upload novel first."
            )

        logger.info(f"Extracting characters for project {project_id}...")

        # 使用 asset_manager 提取角色
        character_drafts = asset_manager.extract_characters(project.script_content)

        if not character_drafts:
            logger.warning(f"No characters extracted for project {project_id}")

        for draft in character_drafts:
            # 调用 asset_manager 创建角色，传入当前的 session
            character = asset_manager.create_or_update_character(project_id, draft, session=self.session)

            # 检查参考图
            if not os.path.exists(character.reference_image_path):
                logger.info(f"Generating reference image for {character.name}")
                candidates = asset_manager.generate_reference_images(
                    character=character,
                    style_spec=project.style_preset or "anime style",
                    n=4,
                    project_id=project_id,
                    style_preset=project.style_preset
                )
                if candidates:
                    # 传入 session 以保存选择
                    asset_manager.select_best_reference(candidates, character, session=self.session)

        project.status = ProjectStatus.ASSETS_READY
        project.updated_at = datetime.utcnow()
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)

        logger.info(f"Built assets for project: {project_id}, {len(character_drafts)} characters processed")
        return project

    def generate_storyboard(self, project_id: str) -> List[Shot]:
        project = self.session.get(Project, project_id)
        if not project:
            raise ProjectNotFoundError(f"Project not found: {project_id}")

        if not project.script_content:
            raise InvalidProjectStateError(
                f"Project {project_id} has no script content."
            )

        # 1. 清除旧分镜
        # 注意：这里我们只删除，不需要担心 ID 冲突，因为新生成的 ID 会自增
        existing_shots = self.session.exec(
            select(Shot).where(Shot.project_id == project_id)
        ).all()

        if existing_shots:
            logger.info(f"Clearing {len(existing_shots)} existing shots for rebuild.")
            for shot in existing_shots:
                self.session.delete(shot)
            # 显式提交一次删除，确保旧数据被清理
            self.session.flush()

        # 2. 调用 LLM 生成数据
        raw_shots = script_parser.parse_novel_to_storyboard(project.script_content)

        shots = []
        for idx, raw_shot in enumerate(raw_shots):
            shot = Shot(
                project_id=project_id,
                sequence_order=idx,  # 使用 sequence_order 来记录它是第几个镜头(0, 1, 2...)
                duration=raw_shot.duration,
                scene_description=raw_shot.scene_description,
                visual_prompt=raw_shot.visual_prompt,
                camera_movement=raw_shot.camera_movement,
                characters_in_shot=raw_shot.characters_in_shot,
                dialogue=raw_shot.dialogue,
                action_type=raw_shot.action_type
                # 注意：此处未设置 shot_id，由数据库自动生成全局唯一 ID
            )
            self.session.add(shot)
            shots.append(shot)

        project.status = ProjectStatus.STORYBOARD_READY
        project.updated_at = datetime.utcnow()
        self.session.add(project)

        # 3. 提交事务
        self.session.commit()

        # 4. 刷新对象以获取数据库生成的 ID
        for shot in shots:
            self.session.refresh(shot)

        logger.info(f"Generated storyboard for project {project_id}: {len(shots)} shots")
        return shots

    def start_render_job(self, project_id: str) -> Job:
        project = self.session.get(Project, project_id)
        if not project:
            raise ProjectNotFoundError(f"Project not found: {project_id}")

        shots = self.session.exec(
            select(Shot).where(Shot.project_id == project_id).order_by(Shot.sequence_order)
        ).all()

        if not shots:
            raise InvalidProjectStateError(
                f"Project {project_id} has no storyboard. Call generate_storyboard first."
            )

        # 创建 Job
        from core.models import JobType
        job = Job(
            project_id=project_id,
            job_type=JobType.FULL_PIPELINE,
            status=JobStatus.PENDING,
            progress=0.0
        )
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)

        # 创建 Render 记录
        for shot in shots:
            existing_render = self.session.exec(
                select(ShotRender).where(
                    ShotRender.shot_id == shot.shot_id,
                    ShotRender.project_id == project_id
                )
            ).first()

            if existing_render:
                existing_render.job_id = job.id
                existing_render.status = ShotRenderStatus.PENDING
                existing_render.error_message = None
                self.session.add(existing_render)
            else:
                render = ShotRender(
                    job_id=job.id,
                    project_id=project_id,
                    shot_id=shot.shot_id,
                    status=ShotRenderStatus.PENDING
                )
                self.session.add(render)

        project.status = ProjectStatus.RENDERING
        self.session.add(project)
        self.session.commit()

        # 异步调用 Celery
        from tasks.jobs import render_project_job
        render_project_job.delay(project_id)

        logger.info(f"Started render job {job.id} for project {project_id}")
        return job