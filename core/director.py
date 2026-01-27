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
        self.session = session  # <--- [修复] 接收并存储注入的 session
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
        # 直接使用 self.session，不再使用 with Session(engine)
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
        # 注意：这里我们临时将 session 传递给 asset_manager 的方法（如果需要）
        # 或者确保 asset_manager 能处理。鉴于 asset_manager 当前是全局单例，
        # 我们这里调用 create_or_update_character 时需要稍微改动一下调用方式，
        # 最好是直接在这里处理数据库，或者让 asset_manager 支持传入 session。

        # 为了兼容性，我们修改下方的调用，手动处理 DB 部分，
        # 或者假设 asset_manager 已经被我们修复支持 session 注入。

        character_drafts = asset_manager.extract_characters(project.script_content)

        if not character_drafts:
            logger.warning(f"No characters extracted for project {project_id}")

        for draft in character_drafts:
            # 调用 asset_manager 创建角色，传入当前的 session
            # 注意：我们需要修改 asset_manager.create_or_update_character 以支持 session 参数
            character = asset_manager.create_or_update_character(project_id, draft, session=self.session)

            # 检查参考图
            if not os.path.exists(character.reference_image_path):
                logger.info(f"Generating reference image for {character.name}")
                candidates = asset_manager.generate_reference_images(
                    character=character,
                    style_spec=project.style_preset or "anime style",
                    n=4,
                    project_id=project_id
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

        # 清除旧分镜
        existing_shots = self.session.exec(
            select(Shot).where(Shot.project_id == project_id)
        ).all()

        if existing_shots:
            logger.info(f"Clearing {len(existing_shots)} existing shots for rebuild.")
            for shot in existing_shots:
                self.session.delete(shot)
            # 这里可以不立即 commit，最后一起 commit

        # 调用 LLM
        raw_shots = script_parser.parse_novel_to_storyboard(project.script_content)

        shots = []
        for idx, raw_shot in enumerate(raw_shots):
            shot = Shot(
                shot_id=idx + 1,
                project_id=project_id,
                sequence_order=idx,
                duration=raw_shot.duration,
                scene_description=raw_shot.scene_description,
                visual_prompt=raw_shot.visual_prompt,
                camera_movement=raw_shot.camera_movement,
                characters_in_shot=raw_shot.characters_in_shot,
                dialogue=raw_shot.dialogue,
                action_type=raw_shot.action_type
            )
            self.session.add(shot)
            shots.append(shot)

        project.status = ProjectStatus.STORYBOARD_READY
        project.updated_at = datetime.utcnow()
        self.session.add(project)
        self.session.commit()

        # 刷新 shot ID
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