import logging
from datetime import datetime
from typing import List, Optional, Dict
import os

from sqlmodel import Session, select

from core.models import (
    Project, ProjectStatus,
    Job, JobStatus, JobType,
    Shot, ShotRender, ShotRenderStatus,
    Character, Chapter, Episode, EpisodeStatus
)
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
        self.session = session
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

        character_drafts = asset_manager.extract_characters(project.script_content)

        if not character_drafts:
            logger.warning(f"No characters extracted for project {project_id}")

        for draft in character_drafts:
            character = asset_manager.create_or_update_character(project_id, draft, session=self.session)

            if not os.path.exists(character.reference_image_path):
                logger.info(f"Generating reference image for {character.name}")
                candidates = asset_manager.generate_reference_images(
                    character=character,
                    style_spec=project.style_preset or "anime style",
                    n=4,
                    project_id=project_id
                )
                if candidates:
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

        existing_shots = self.session.exec(
            select(Shot).where(Shot.project_id == project_id)
        ).all()

        if existing_shots:
            logger.info(f"Clearing {len(existing_shots)} existing shots for rebuild.")
            for shot in existing_shots:
                self.session.delete(shot)
            self.session.commit()

        raw_shots = script_parser.parse_novel_to_storyboard(project.script_content)

        if not raw_shots:
            logger.warning(f"No shots generated for project {project_id}")
            raise InvalidProjectStateError(
                f"Failed to generate storyboard for project {project_id}. LLM returned no shots."
            )

        shots = []
        for idx, raw_shot in enumerate(raw_shots):
            shot = Shot(
                project_id=project_id,
                sequence_order=idx,
                duration=raw_shot.duration,
                scene_description=raw_shot.scene_description,
                visual_prompt=raw_shot.visual_prompt,
                camera_movement=raw_shot.camera_movement,
                characters_in_shot=raw_shot.characters_in_shot or [],
                dialogue=raw_shot.dialogue,
                action_type=raw_shot.action_type
            )
            self.session.add(shot)
            shots.append(shot)

        project.status = ProjectStatus.STORYBOARD_READY
        project.updated_at = datetime.utcnow()
        self.session.add(project)
        self.session.commit()

        for shot in shots:
            self.session.refresh(shot)

        logger.info(f"Generated storyboard for project {project_id}: {len(shots)} shots")
        return shots

    def start_render_job(self, project_id: str) -> Job:
        project = self.session.get(Project, project_id)
        if not project:
            raise ProjectNotFoundError(f"Project not found: {project_id}")

        active_job = self.session.exec(
            select(Job).where(
                Job.project_id == project_id,
                Job.job_type == JobType.FULL_PIPELINE,
                Job.status.in_([JobStatus.PENDING, JobStatus.STARTED])
            ).order_by(Job.created_at.desc())
        ).first()
        if active_job:
            raise InvalidProjectStateError(
                f"Project {project_id} already has an active render job: {active_job.id}"
            )

        shots = self.session.exec(
            select(Shot).where(Shot.project_id == project_id).order_by(Shot.sequence_order)
        ).all()

        if not shots:
            raise InvalidProjectStateError(
                f"Project {project_id} has no storyboard. Call generate_storyboard first."
            )

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

        from tasks.jobs import render_project_job
        task_result = render_project_job.delay(project_id, job.id)
        job.celery_task_id = task_result.id
        self.session.add(job)
        self.session.commit()

        logger.info(f"Started render job {job.id} for project {project_id}")
        return job

    # ========================================================================
    # Episode-based methods (按集操作)
    # ========================================================================

    def generate_episode_storyboard(self, project_id: str, episode_number: int) -> List[Shot]:
        """
        为单集生成分镜。

        Args:
            project_id: 项目 ID
            episode_number: 集数

        Returns:
            List[Shot]: 生成的分镜列表
        """
        project = self.session.get(Project, project_id)
        if not project:
            raise ProjectNotFoundError(f"Project not found: {project_id}")

        # 获取集信息
        episode = self.session.exec(
            select(Episode).where(
                Episode.project_id == project_id,
                Episode.episode_number == episode_number
            )
        ).first()

        if not episode:
            raise InvalidProjectStateError(
                f"Episode {episode_number} not found for project {project_id}"
            )

        # 获取该集包含的章节
        chapters = self.session.exec(
            select(Chapter).where(
                Chapter.project_id == project_id,
                Chapter.chapter_number >= episode.start_chapter,
                Chapter.chapter_number <= episode.end_chapter
            ).order_by(Chapter.chapter_number)
        ).all()

        if not chapters:
            raise InvalidProjectStateError(
                f"No chapters found for episode {episode_number} "
                f"(chapters {episode.start_chapter}-{episode.end_chapter})"
            )

        # 合并章节内容
        combined_content = "\n\n".join([
            f"【第{ch.chapter_number}章 {ch.title or ''}】\n{ch.content}"
            for ch in chapters
        ])

        # 清除该集现有的分镜
        existing_shots = self.session.exec(
            select(Shot).where(Shot.episode_id == episode.id)
        ).all()

        if existing_shots:
            logger.info(f"Clearing {len(existing_shots)} existing shots for episode {episode_number}")
            for shot in existing_shots:
                self.session.delete(shot)
            self.session.commit()

        # 生成分镜
        raw_shots = script_parser.parse_novel_to_storyboard(combined_content)

        if not raw_shots:
            logger.warning(f"No shots generated for episode {episode_number}")
            raise InvalidProjectStateError(
                f"Failed to generate storyboard for episode {episode_number}. LLM returned no shots."
            )

        shots = []
        for idx, raw_shot in enumerate(raw_shots):
            shot = Shot(
                project_id=project_id,
                episode_id=episode.id,
                sequence_order=idx,
                duration=raw_shot.duration,
                scene_description=raw_shot.scene_description,
                visual_prompt=raw_shot.visual_prompt,
                camera_movement=raw_shot.camera_movement,
                characters_in_shot=raw_shot.characters_in_shot or [],
                dialogue=raw_shot.dialogue,
                action_type=raw_shot.action_type
            )
            self.session.add(shot)
            shots.append(shot)

        # 更新集状态
        episode.status = EpisodeStatus.STORYBOARD_READY
        episode.updated_at = datetime.utcnow()
        self.session.add(episode)
        self.session.commit()

        for shot in shots:
            self.session.refresh(shot)

        logger.info(f"Generated storyboard for episode {episode_number}: {len(shots)} shots")
        return shots

    def start_episode_render_job(self, project_id: str, episode_number: int) -> Job:
        """
        启动单集渲染任务。

        Args:
            project_id: 项目 ID
            episode_number: 集数

        Returns:
            Job: 创建的任务
        """
        project = self.session.get(Project, project_id)
        if not project:
            raise ProjectNotFoundError(f"Project not found: {project_id}")

        # 获取集信息
        episode = self.session.exec(
            select(Episode).where(
                Episode.project_id == project_id,
                Episode.episode_number == episode_number
            )
        ).first()

        if not episode:
            raise InvalidProjectStateError(
                f"Episode {episode_number} not found for project {project_id}"
            )

        # 获取该集的分镜
        shots = self.session.exec(
            select(Shot).where(Shot.episode_id == episode.id).order_by(Shot.sequence_order)
        ).all()

        if not shots:
            raise InvalidProjectStateError(
                f"Episode {episode_number} has no storyboard. Call generate_episode_storyboard first."
            )

        active_job = self.session.exec(
            select(Job).where(
                Job.project_id == project_id,
                Job.job_type == JobType.FULL_PIPELINE,
                Job.status.in_([JobStatus.PENDING, JobStatus.STARTED]),
                Job.result.contains({"episode_id": episode.id})
            ).order_by(Job.created_at.desc())
        ).first()
        if active_job:
            raise InvalidProjectStateError(
                f"Episode {episode_number} already has an active render job: {active_job.id}"
            )

        # 创建任务
        job = Job(
            project_id=project_id,
            job_type=JobType.FULL_PIPELINE,
            status=JobStatus.PENDING,
            progress=0.0,
            result={"episode_number": episode_number, "episode_id": episode.id}
        )
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)

        # 为每个分镜创建渲染记录
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

        # 更新集状态
        episode.status = EpisodeStatus.RENDERING
        episode.updated_at = datetime.utcnow()
        self.session.add(episode)
        self.session.commit()

        # 触发 Celery 任务
        from tasks.jobs import render_episode_job
        task_result = render_episode_job.delay(project_id, episode.id, job.id)
        job.celery_task_id = task_result.id
        self.session.add(job)
        self.session.commit()

        logger.info(f"Started render job {job.id} for episode {episode_number}")
        return job

    def build_assets_from_chapters(self, project_id: str) -> Project:
        """
        从章节内容构建资产（角色提取）。
        与 build_assets 类似，但从 chapters 表读取内容而非 script_content。

        Args:
            project_id: 项目 ID

        Returns:
            Project: 更新后的项目
        """
        project = self.session.get(Project, project_id)
        if not project:
            raise ProjectNotFoundError(f"Project not found: {project_id}")

        # 获取所有章节
        chapters = self.session.exec(
            select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number)
        ).all()

        if not chapters:
            raise InvalidProjectStateError(
                f"Project {project_id} has no chapters. Upload chapters first."
            )

        # 合并章节内容（取前几章用于角色提取，避免内容过长）
        sample_chapters = chapters[:10]  # 取前10章
        combined_content = "\n\n".join([ch.content for ch in sample_chapters])

        logger.info(f"Extracting characters from {len(sample_chapters)} chapters for project {project_id}...")

        character_drafts = asset_manager.extract_characters(combined_content)

        if not character_drafts:
            logger.warning(f"No characters extracted for project {project_id}")

        for draft in character_drafts:
            character = asset_manager.create_or_update_character(project_id, draft, session=self.session)

            if not os.path.exists(character.reference_image_path):
                logger.info(f"Generating reference image for {character.name}")
                candidates = asset_manager.generate_reference_images(
                    character=character,
                    style_spec=project.style_preset or "anime style",
                    n=4,
                    project_id=project_id
                )
                if candidates:
                    asset_manager.select_best_reference(candidates, character, session=self.session)

        project.status = ProjectStatus.ASSETS_READY
        project.updated_at = datetime.utcnow()
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)

        logger.info(f"Built assets for project: {project_id}, {len(character_drafts)} characters processed")
        return project
