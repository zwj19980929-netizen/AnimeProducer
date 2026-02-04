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
        render_project_job.delay(project_id)

        logger.info(f"Started render job {job.id} for project {project_id}")
        return job