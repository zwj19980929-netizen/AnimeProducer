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
from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid

from sqlmodel import Session, select

from core.models import (
    Project, ProjectStatus,
    Job, JobStatus,
    Shot, ShotRender, ShotRenderStatus,
    Character
)
from core.database import engine
from core.script_parser import script_parser
from integrations.gen_client import gen_client
from integrations.llm_client import llm_client
from config import settings

logger = logging.getLogger(__name__)


class AssetNotReadyError(Exception):
    """角色资产未就绪时抛出"""
    pass


class ProjectNotFoundError(Exception):
    """项目不存在时抛出"""
    pass


class JobNotFoundError(Exception):
    """任务不存在时抛出"""
    pass


class InvalidProjectStateError(Exception):
    """项目状态不符合操作条件时抛出"""
    pass


class Director:
    """导演编排器 - 统筹影视生产全流程"""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers

    def create_project(self, name: str, description: Optional[str] = None) -> Project:
        """
        创建新项目
        
        Args:
            name: 项目名称
            description: 项目描述
            
        Returns:
            创建的 Project 对象
        """
        project = Project(name=name, description=description)
        
        with Session(engine) as session:
            session.add(project)
            session.commit()
            session.refresh(project)
            logger.info(f"Created project: {project.project_id} - {project.name}")
            return project

    def ingest_novel(
        self, 
        project_id: str, 
        text: str, 
        chapter_meta: Optional[Dict] = None
    ) -> Project:
        """
        导入小说文本到项目
        
        Args:
            project_id: 项目ID
            text: 小说文本
            chapter_meta: 章节元数据
            
        Returns:
            更新后的 Project 对象
            
        Raises:
            ProjectNotFoundError: 项目不存在
        """
        with Session(engine) as session:
            project = session.get(Project, project_id)
            if not project:
                raise ProjectNotFoundError(f"Project not found: {project_id}")
            
            project.novel_text = text
            project.chapter_meta = chapter_meta
            project.status = ProjectStatus.INGESTED
            project.updated_at = datetime.utcnow()
            
            session.add(project)
            session.commit()
            session.refresh(project)
            
            logger.info(f"Ingested novel for project: {project_id}, text length: {len(text)}")
            return project

    def build_assets(self, project_id: str) -> Project:
        """
        构建项目资产：角色提取 + 参考图生成
        
        Args:
            project_id: 项目ID
            
        Returns:
            更新后的 Project 对象
            
        Raises:
            ProjectNotFoundError: 项目不存在
            InvalidProjectStateError: 项目未导入小说
        """
        with Session(engine) as session:
            project = session.get(Project, project_id)
            if not project:
                raise ProjectNotFoundError(f"Project not found: {project_id}")
            
            if not project.novel_text:
                raise InvalidProjectStateError(
                    f"Project {project_id} has no novel text. Call ingest_novel first."
                )
            
            characters = self._extract_characters(project.novel_text, project_id, session)
            
            for character in characters:
                if not character.reference_image_path:
                    ref_path = self._generate_reference_image(character)
                    character.reference_image_path = ref_path
                    session.add(character)
            
            project.status = ProjectStatus.ASSETS_READY
            project.updated_at = datetime.utcnow()
            session.add(project)
            session.commit()
            session.refresh(project)
            
            logger.info(f"Built assets for project: {project_id}, {len(characters)} characters")
            return project

    def _extract_characters(
        self, 
        novel_text: str, 
        project_id: str, 
        session: Session
    ) -> List[Character]:
        """从小说文本中提取角色"""
        from pydantic import BaseModel, Field as PydanticField
        from typing import List as TypingList
        
        class ExtractedCharacter(BaseModel):
            name: str
            prompt_base: str = PydanticField(description="Character appearance description for image generation")
        
        class CharacterList(BaseModel):
            characters: TypingList[ExtractedCharacter]
        
        prompt = f"""
        Extract all named characters from the following novel text.
        For each character, provide:
        1. name: The character's name
        2. prompt_base: A detailed visual description suitable for AI image generation (appearance, clothing, features)
        
        Novel Text:
        {novel_text[:5000]}
        """
        
        try:
            result = llm_client.generate_structured_output(prompt, CharacterList)
            if not result:
                logger.warning(f"Failed to extract characters for project {project_id}")
                return []
            
            characters = []
            for extracted in result.characters:
                character_id = f"{project_id}_{extracted.name.replace(' ', '_').lower()}"
                
                existing = session.get(Character, character_id)
                if existing:
                    characters.append(existing)
                    continue
                
                character = Character(
                    character_id=character_id,
                    project_id=project_id,
                    name=extracted.name,
                    prompt_base=extracted.prompt_base
                )
                session.add(character)
                characters.append(character)
            
            session.commit()
            return characters
            
        except Exception as e:
            logger.error(f"Character extraction failed: {e}")
            return []

    def _generate_reference_image(self, character: Character) -> str:
        """为角色生成参考图"""
        import os
        
        prompt = f"Character portrait, {character.prompt_base}, high quality, detailed, anime style"
        
        try:
            image_data = gen_client.generate_image(prompt)
            if not image_data:
                logger.warning(f"Failed to generate reference image for {character.name}")
                return ""
            
            os.makedirs(settings.CHARACTERS_DIR, exist_ok=True)
            safe_name = character.character_id.replace('/', '_').replace('\\', '_')
            image_path = os.path.join(settings.CHARACTERS_DIR, f"{safe_name}.png")
            
            with open(image_path, 'wb') as f:
                f.write(image_data)
            
            logger.info(f"Generated reference image for {character.name}: {image_path}")
            return image_path
            
        except Exception as e:
            logger.error(f"Reference image generation failed for {character.name}: {e}")
            return ""

    def generate_storyboard(self, project_id: str) -> List[Shot]:
        """
        为项目生成分镜表
        
        Args:
            project_id: 项目ID
            
        Returns:
            生成的 Shot 列表
            
        Raises:
            ProjectNotFoundError: 项目不存在
            InvalidProjectStateError: 项目状态不符合要求
        """
        with Session(engine) as session:
            project = session.get(Project, project_id)
            if not project:
                raise ProjectNotFoundError(f"Project not found: {project_id}")
            
            if not project.novel_text:
                raise InvalidProjectStateError(
                    f"Project {project_id} has no novel text."
                )
            
            existing_shots = session.exec(
                select(Shot).where(Shot.project_id == project_id)
            ).all()
            
            if existing_shots:
                logger.info(f"Storyboard already exists for project {project_id}, returning cached")
                return list(existing_shots)
            
            raw_shots = script_parser.parse_novel_to_storyboard(project.novel_text)
            
            shots = []
            for idx, raw_shot in enumerate(raw_shots):
                shot = Shot(
                    shot_id=str(uuid.uuid4()),
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
                session.add(shot)
                shots.append(shot)
            
            project.status = ProjectStatus.STORYBOARD_READY
            project.updated_at = datetime.utcnow()
            session.add(project)
            session.commit()
            
            for shot in shots:
                session.refresh(shot)
            
            logger.info(f"Generated storyboard for project {project_id}: {len(shots)} shots")
            return shots

    def start_render_job(self, project_id: str) -> Job:
        """
        启动渲染任务
        
        硬规则：
        - 无资产不开拍：Shot 若包含角色，必须能取到 reference_image_path
        - 镜头并行：每个 shot 是独立渲染单元
        - 可恢复：已有产物的 shot 允许跳过重算
        
        Args:
            project_id: 项目ID
            
        Returns:
            创建的 Job 对象
            
        Raises:
            ProjectNotFoundError: 项目不存在
            InvalidProjectStateError: 项目未生成分镜
            AssetNotReadyError: 角色资产未就绪
        """
        with Session(engine) as session:
            project = session.get(Project, project_id)
            if not project:
                raise ProjectNotFoundError(f"Project not found: {project_id}")
            
            shots = session.exec(
                select(Shot).where(Shot.project_id == project_id)
            ).all()
            
            if not shots:
                raise InvalidProjectStateError(
                    f"Project {project_id} has no storyboard. Call generate_storyboard first."
                )
            
            self._validate_assets_for_shots(list(shots), project_id, session)
            
            job = Job(
                project_id=project_id,
                status=JobStatus.PENDING,
                total_shots=len(shots)
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            
            shot_renders = []
            for shot in shots:
                existing_render = session.exec(
                    select(ShotRender).where(
                        ShotRender.shot_id == shot.shot_id,
                        ShotRender.status == ShotRenderStatus.COMPLETED
                    )
                ).first()
                
                if existing_render and existing_render.output_path:
                    render = ShotRender(
                        job_id=job.job_id,
                        shot_id=shot.shot_id,
                        status=ShotRenderStatus.SKIPPED,
                        output_path=existing_render.output_path
                    )
                    job.completed_shots += 1
                else:
                    render = ShotRender(
                        job_id=job.job_id,
                        shot_id=shot.shot_id,
                        status=ShotRenderStatus.PENDING
                    )
                
                session.add(render)
                shot_renders.append(render)
            
            session.add(job)
            session.commit()
            session.refresh(job)
            
            self._execute_render_job(job.job_id, shot_renders)
            
            session.refresh(job)
            logger.info(f"Started render job {job.job_id} for project {project_id}")
            return job

    def _validate_assets_for_shots(
        self, 
        shots: List[Shot], 
        project_id: str, 
        session: Session
    ) -> None:
        """验证所有镜头中的角色是否有参考图"""
        all_character_names = set()
        for shot in shots:
            for char_name in shot.characters_in_shot:
                all_character_names.add(char_name)
        
        if not all_character_names:
            return
        
        characters = session.exec(
            select(Character).where(Character.project_id == project_id)
        ).all()
        
        char_map = {c.name.lower(): c for c in characters}
        
        missing_assets = []
        for char_name in all_character_names:
            char = char_map.get(char_name.lower())
            if not char:
                missing_assets.append(f"Character '{char_name}' not found")
            elif not char.reference_image_path:
                missing_assets.append(f"Character '{char_name}' has no reference image")
        
        if missing_assets:
            raise AssetNotReadyError(
                f"Assets not ready for rendering: {'; '.join(missing_assets)}"
            )

    def _execute_render_job(self, job_id: str, shot_renders: List[ShotRender]) -> None:
        """执行渲染任务（并行处理镜头）"""
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if not job:
                return
            
            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            session.add(job)
            session.commit()
        
        pending_renders = [r for r in shot_renders if r.status == ShotRenderStatus.PENDING]
        
        if not pending_renders:
            with Session(engine) as session:
                job = session.get(Job, job_id)
                if job:
                    job.status = JobStatus.COMPLETED
                    job.completed_at = datetime.utcnow()
                    session.add(job)
                    session.commit()
            return
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_render = {
                executor.submit(self._render_single_shot, r.render_id): r.render_id
                for r in pending_renders
            }
            
            for future in as_completed(future_to_render):
                render_id = future_to_render[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Render {render_id} failed: {e}")
        
        self._finalize_job(job_id)

    def _render_single_shot(self, render_id: str) -> str:
        """渲染单个镜头"""
        import os
        
        with Session(engine) as session:
            render = session.get(ShotRender, render_id)
            if not render:
                raise ValueError(f"Render not found: {render_id}")
            
            shot = session.get(Shot, render.shot_id)
            if not shot:
                raise ValueError(f"Shot not found: {render.shot_id}")
            
            render.status = ShotRenderStatus.RENDERING
            render.started_at = datetime.utcnow()
            session.add(render)
            session.commit()
            
            try:
                ref_images = []
                if shot.characters_in_shot:
                    characters = session.exec(
                        select(Character).where(Character.project_id == shot.project_id)
                    ).all()
                    char_map = {c.name.lower(): c for c in characters}
                    for char_name in shot.characters_in_shot:
                        char = char_map.get(char_name.lower())
                        if char and char.reference_image_path:
                            ref_images.append(char.reference_image_path)
                
                ref_path = ref_images[0] if ref_images else None
                image_data = gen_client.generate_image(shot.visual_prompt, ref_path)
                
                if not image_data:
                    raise RuntimeError("Image generation returned no data")
                
                os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
                output_path = os.path.join(
                    settings.OUTPUT_DIR, 
                    f"shot_{shot.shot_id}.png"
                )
                
                with open(output_path, 'wb') as f:
                    f.write(image_data)
                
                render.status = ShotRenderStatus.COMPLETED
                render.output_path = output_path
                render.completed_at = datetime.utcnow()
                session.add(render)
                session.commit()
                
                logger.info(f"Rendered shot {shot.shot_id} -> {output_path}")
                return output_path
                
            except Exception as e:
                render.status = ShotRenderStatus.FAILED
                render.error_message = str(e)
                render.completed_at = datetime.utcnow()
                session.add(render)
                session.commit()
                logger.error(f"Failed to render shot {shot.shot_id}: {e}")
                raise

    def _finalize_job(self, job_id: str) -> None:
        """完成任务统计"""
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if not job:
                return
            
            renders = session.exec(
                select(ShotRender).where(ShotRender.job_id == job_id)
            ).all()
            
            completed = sum(
                1 for r in renders 
                if r.status in (ShotRenderStatus.COMPLETED, ShotRenderStatus.SKIPPED)
            )
            failed = sum(1 for r in renders if r.status == ShotRenderStatus.FAILED)
            
            job.completed_shots = completed
            job.failed_shots = failed
            job.completed_at = datetime.utcnow()
            
            if failed > 0:
                job.status = JobStatus.FAILED
                job.error_message = f"{failed} shots failed to render"
            else:
                job.status = JobStatus.COMPLETED
            
            with Session(engine) as proj_session:
                project = proj_session.get(Project, job.project_id)
                if project:
                    if job.status == JobStatus.COMPLETED:
                        project.status = ProjectStatus.COMPLETED
                    else:
                        project.status = ProjectStatus.FAILED
                    project.updated_at = datetime.utcnow()
                    proj_session.add(project)
                    proj_session.commit()
            
            session.add(job)
            session.commit()
            
            logger.info(
                f"Job {job_id} finalized: {completed} completed, {failed} failed"
            )

    def get_job(self, job_id: str) -> Job:
        """
        获取任务信息
        
        Args:
            job_id: 任务ID
            
        Returns:
            Job 对象
            
        Raises:
            JobNotFoundError: 任务不存在
        """
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if not job:
                raise JobNotFoundError(f"Job not found: {job_id}")
            return job

    def get_project(self, project_id: str) -> Project:
        """
        获取项目信息
        
        Args:
            project_id: 项目ID
            
        Returns:
            Project 对象
            
        Raises:
            ProjectNotFoundError: 项目不存在
        """
        with Session(engine) as session:
            project = session.get(Project, project_id)
            if not project:
                raise ProjectNotFoundError(f"Project not found: {project_id}")
            return project

    def get_job_renders(self, job_id: str) -> List[ShotRender]:
        """获取任务的所有渲染记录"""
        with Session(engine) as session:
            renders = session.exec(
                select(ShotRender).where(ShotRender.job_id == job_id)
            ).all()
            return list(renders)


director = Director()
