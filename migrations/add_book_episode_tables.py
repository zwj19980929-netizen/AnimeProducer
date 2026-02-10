"""数据库迁移脚本 - 添加 Book/Episode 表，增强 Chapter/Shot 表。

运行方式:
    python -m migrations.add_book_episode_tables

注意:
    - 此脚本用于升级现有数据库
    - 新部署会自动创建所有表（通过 SQLModel.metadata.create_all）
    - 运行前请备份数据库
"""

import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from sqlmodel import Session

from config import settings
from core.database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def table_exists(inspector, table_name: str) -> bool:
    """检查表是否存在。"""
    return table_name in inspector.get_table_names()


def column_exists(inspector, table_name: str, column_name: str) -> bool:
    """检查列是否存在。"""
    if not table_exists(inspector, table_name):
        return False
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def run_migration():
    """执行数据库迁移。"""
    logger.info("Starting database migration...")
    logger.info(f"Database URL: {settings.DATABASE_URL}")

    inspector = inspect(engine)
    is_sqlite = "sqlite" in settings.DATABASE_URL

    with Session(engine) as session:
        # ============================================================
        # 0. 更新 PostgreSQL 枚举类型（添加缺失的值）
        # ============================================================
        if not is_sqlite:
            logger.info("Checking PostgreSQL enum types...")
            # 添加 chapterstatus 枚举的 READY 值
            try:
                session.exec(text("ALTER TYPE chapterstatus ADD VALUE IF NOT EXISTS 'READY'"))
                logger.info("Added 'READY' to chapterstatus enum")
            except Exception as e:
                logger.info(f"chapterstatus enum already has READY or error: {e}")

            # 提交枚举更改（枚举更改需要单独提交）
            session.commit()

        # ============================================================
        # 1. 创建 books 表
        # ============================================================
        if not table_exists(inspector, "books"):
            logger.info("Creating 'books' table...")
            if is_sqlite:
                session.exec(text("""
                    CREATE TABLE books (
                        id VARCHAR PRIMARY KEY,
                        project_id VARCHAR UNIQUE NOT NULL,
                        original_title VARCHAR,
                        author VARCHAR,
                        genre VARCHAR,
                        total_chapters INTEGER DEFAULT 0,
                        uploaded_chapters INTEGER DEFAULT 0,
                        total_words INTEGER DEFAULT 0,
                        upload_status VARCHAR DEFAULT 'EMPTY',
                        ai_summary TEXT,
                        main_plot_points JSON DEFAULT '[]',
                        suggested_episodes INTEGER,
                        created_at DATETIME,
                        updated_at DATETIME,
                        FOREIGN KEY (project_id) REFERENCES projects(id)
                    )
                """))
            else:
                # PostgreSQL / MySQL
                session.exec(text("""
                    CREATE TABLE books (
                        id VARCHAR(36) PRIMARY KEY,
                        project_id VARCHAR(36) UNIQUE NOT NULL REFERENCES projects(id),
                        original_title VARCHAR(500),
                        author VARCHAR(200),
                        genre VARCHAR(100),
                        total_chapters INTEGER DEFAULT 0,
                        uploaded_chapters INTEGER DEFAULT 0,
                        total_words INTEGER DEFAULT 0,
                        upload_status VARCHAR(20) DEFAULT 'EMPTY',
                        ai_summary TEXT,
                        main_plot_points JSONB DEFAULT '[]',
                        suggested_episodes INTEGER,
                        created_at TIMESTAMP,
                        updated_at TIMESTAMP
                    )
                """))
            logger.info("Created 'books' table")
        else:
            logger.info("'books' table already exists, skipping")

        # ============================================================
        # 2. 创建 episodes 表
        # ============================================================
        if not table_exists(inspector, "episodes"):
            logger.info("Creating 'episodes' table...")
            if is_sqlite:
                session.exec(text("""
                    CREATE TABLE episodes (
                        id VARCHAR PRIMARY KEY,
                        project_id VARCHAR NOT NULL,
                        episode_number INTEGER NOT NULL,
                        title VARCHAR,
                        synopsis TEXT,
                        start_chapter INTEGER NOT NULL,
                        end_chapter INTEGER NOT NULL,
                        target_duration_minutes REAL DEFAULT 24.0,
                        actual_duration_minutes REAL,
                        status VARCHAR DEFAULT 'PLANNED',
                        output_video_path VARCHAR,
                        output_video_url VARCHAR,
                        episode_metadata JSON DEFAULT '{}',
                        created_at DATETIME,
                        updated_at DATETIME,
                        FOREIGN KEY (project_id) REFERENCES projects(id)
                    )
                """))
                session.exec(text("CREATE INDEX ix_episodes_project_id ON episodes(project_id)"))
                session.exec(text("CREATE INDEX ix_episodes_episode_number ON episodes(episode_number)"))
            else:
                session.exec(text("""
                    CREATE TABLE episodes (
                        id VARCHAR(36) PRIMARY KEY,
                        project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
                        episode_number INTEGER NOT NULL,
                        title VARCHAR(500),
                        synopsis TEXT,
                        start_chapter INTEGER NOT NULL,
                        end_chapter INTEGER NOT NULL,
                        target_duration_minutes REAL DEFAULT 24.0,
                        actual_duration_minutes REAL,
                        status VARCHAR(30) DEFAULT 'PLANNED',
                        output_video_path VARCHAR(1000),
                        output_video_url VARCHAR(1000),
                        episode_metadata JSONB DEFAULT '{}',
                        created_at TIMESTAMP,
                        updated_at TIMESTAMP
                    )
                """))
                session.exec(text("CREATE INDEX ix_episodes_project_id ON episodes(project_id)"))
                session.exec(text("CREATE INDEX ix_episodes_episode_number ON episodes(episode_number)"))
            logger.info("Created 'episodes' table")
        else:
            logger.info("'episodes' table already exists, skipping")

        # ============================================================
        # 3. 修改 chapters 表 - 添加新字段
        # ============================================================
        logger.info("Checking 'chapters' table for new columns...")

        new_chapter_columns = [
            ("word_count", "INTEGER DEFAULT 0"),
            ("key_events", "JSON DEFAULT '[]'" if is_sqlite else "JSONB DEFAULT '[]'"),
            ("emotional_arc", "VARCHAR"),
            ("importance_score", "REAL DEFAULT 0.5"),
            ("suggested_episode", "INTEGER"),
            ("characters_appeared", "JSON DEFAULT '[]'" if is_sqlite else "JSONB DEFAULT '[]'"),
        ]

        for col_name, col_type in new_chapter_columns:
            if not column_exists(inspector, "chapters", col_name):
                logger.info(f"Adding column 'chapters.{col_name}'...")
                session.exec(text(f"ALTER TABLE chapters ADD COLUMN {col_name} {col_type}"))
                logger.info(f"Added column 'chapters.{col_name}'")
            else:
                logger.info(f"Column 'chapters.{col_name}' already exists, skipping")

        # ============================================================
        # 4. 修改 shots 表 - 添加 episode_id 字段
        # ============================================================
        logger.info("Checking 'shots' table for episode_id column...")

        if not column_exists(inspector, "shots", "episode_id"):
            logger.info("Adding column 'shots.episode_id'...")
            session.exec(text("ALTER TABLE shots ADD COLUMN episode_id VARCHAR"))
            # SQLite 不支持 ADD CONSTRAINT，所以只添加列
            if not is_sqlite:
                session.exec(text(
                    "ALTER TABLE shots ADD CONSTRAINT fk_shots_episode_id "
                    "FOREIGN KEY (episode_id) REFERENCES episodes(id)"
                ))
            session.exec(text("CREATE INDEX ix_shots_episode_id ON shots(episode_id)"))
            logger.info("Added column 'shots.episode_id'")
        else:
            logger.info("Column 'shots.episode_id' already exists, skipping")

        # ============================================================
        # 5. 更新现有章节的 word_count
        # ============================================================
        logger.info("Updating word_count for existing chapters...")
        if is_sqlite:
            session.exec(text("""
                UPDATE chapters
                SET word_count = LENGTH(content)
                WHERE word_count = 0 OR word_count IS NULL
            """))
        else:
            session.exec(text("""
                UPDATE chapters
                SET word_count = CHAR_LENGTH(content)
                WHERE word_count = 0 OR word_count IS NULL
            """))
        logger.info("Updated word_count for existing chapters")

        # ============================================================
        # 6. 修改 characters 表 - 添加 reference_image_url 字段
        # ============================================================
        logger.info("Checking 'characters' table for reference_image_url column...")

        if not column_exists(inspector, "characters", "reference_image_url"):
            logger.info("Adding column 'characters.reference_image_url'...")
            session.exec(text("ALTER TABLE characters ADD COLUMN reference_image_url VARCHAR"))
            logger.info("Added column 'characters.reference_image_url'")
        else:
            logger.info("Column 'characters.reference_image_url' already exists, skipping")

        # ============================================================
        # 7. 修改 shots 表 - 添加情感相关字段
        # ============================================================
        logger.info("Checking 'shots' table for emotion columns...")

        shot_emotion_columns = [
            ("emotion", "VARCHAR(50)"),
            ("emotion_intensity", "REAL DEFAULT 0.5"),
            ("emotion_context", "TEXT"),
        ]

        for col_name, col_type in shot_emotion_columns:
            if not column_exists(inspector, "shots", col_name):
                logger.info(f"Adding column 'shots.{col_name}'...")
                session.exec(text(f"ALTER TABLE shots ADD COLUMN {col_name} {col_type}"))
                logger.info(f"Added column 'shots.{col_name}'")
            else:
                logger.info(f"Column 'shots.{col_name}' already exists, skipping")

        session.commit()
        logger.info("Migration completed successfully!")


if __name__ == "__main__":
    run_migration()
