"""数据库迁移脚本 - 添加角色图片库表和相关字段。

运行方式:
    python -m migrations.add_character_image_gallery

功能:
    1. 创建 character_images 表（角色图片库）
    2. 为 characters 表添加 appearance_prompt, bio, anchor_image 相关字段

注意:
    - 此脚本用于升级现有数据库
    - 新部署会自动创建所有表（通过 SQLModel.metadata.create_all）
    - 运行前请备份数据库
"""

import logging
import sys
import uuid
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
    logger.info("Starting character image gallery migration...")
    logger.info(f"Database URL: {settings.DATABASE_URL}")

    is_sqlite = "sqlite" in settings.DATABASE_URL

    # ============================================================
    # 1. 创建 character_images 表
    # ============================================================
    inspector = inspect(engine)

    with Session(engine) as session:
        if not table_exists(inspector, "character_images"):
            logger.info("Creating 'character_images' table...")
            if is_sqlite:
                session.exec(text("""
                    CREATE TABLE character_images (
                        id VARCHAR PRIMARY KEY,
                        character_id VARCHAR NOT NULL,
                        image_type VARCHAR DEFAULT 'CANDIDATE',
                        image_path VARCHAR NOT NULL,
                        image_url VARCHAR,
                        thumbnail_path VARCHAR,
                        thumbnail_url VARCHAR,
                        prompt TEXT DEFAULT '',
                        pose VARCHAR,
                        expression VARCHAR,
                        angle VARCHAR,
                        style_preset VARCHAR,
                        is_selected_for_training BOOLEAN DEFAULT 0,
                        is_anchor BOOLEAN DEFAULT 0,
                        quality_score REAL,
                        generation_metadata JSON DEFAULT '{}',
                        created_at DATETIME,
                        FOREIGN KEY (character_id) REFERENCES characters(character_id)
                    )
                """))
                session.exec(text("CREATE INDEX ix_character_images_character_id ON character_images(character_id)"))
            else:
                # PostgreSQL
                session.exec(text("""
                    CREATE TABLE character_images (
                        id VARCHAR(36) PRIMARY KEY,
                        character_id VARCHAR(100) NOT NULL REFERENCES characters(character_id),
                        image_type VARCHAR(20) DEFAULT 'CANDIDATE',
                        image_path VARCHAR(1000) NOT NULL,
                        image_url VARCHAR(1000),
                        thumbnail_path VARCHAR(1000),
                        thumbnail_url VARCHAR(1000),
                        prompt TEXT DEFAULT '',
                        pose VARCHAR(100),
                        expression VARCHAR(100),
                        angle VARCHAR(100),
                        style_preset VARCHAR(100),
                        is_selected_for_training BOOLEAN DEFAULT FALSE,
                        is_anchor BOOLEAN DEFAULT FALSE,
                        quality_score REAL,
                        generation_metadata JSONB DEFAULT '{}',
                        created_at TIMESTAMP
                    )
                """))
                session.exec(text("CREATE INDEX ix_character_images_character_id ON character_images(character_id)"))
            session.commit()
            logger.info("Created 'character_images' table")
        else:
            logger.info("'character_images' table already exists, skipping")

    # ============================================================
    # 2. 修改 characters 表 - 添加新字段
    # ============================================================
    # 重新获取 inspector 以刷新缓存
    inspector = inspect(engine)

    logger.info("Checking 'characters' table for new columns...")

    new_character_columns = [
        ("appearance_prompt", "TEXT DEFAULT ''"),
        ("bio", "TEXT DEFAULT ''"),
        ("anchor_image_id", "VARCHAR"),
        ("anchor_image_path", "VARCHAR"),
        ("anchor_image_url", "VARCHAR"),
    ]

    with Session(engine) as session:
        for col_name, col_type in new_character_columns:
            if not column_exists(inspector, "characters", col_name):
                logger.info(f"Adding column 'characters.{col_name}'...")
                session.exec(text(f"ALTER TABLE characters ADD COLUMN {col_name} {col_type}"))
                logger.info(f"Added column 'characters.{col_name}'")
            else:
                logger.info(f"Column 'characters.{col_name}' already exists, skipping")
        session.commit()

    # ============================================================
    # 3. 迁移现有数据：将 prompt_base 复制到 appearance_prompt
    # ============================================================
    logger.info("Migrating existing data: copying prompt_base to appearance_prompt...")
    with Session(engine) as session:
        session.exec(text("""
            UPDATE characters
            SET appearance_prompt = prompt_base
            WHERE (appearance_prompt IS NULL OR appearance_prompt = '')
              AND prompt_base IS NOT NULL
              AND prompt_base != ''
        """))
        session.commit()
    logger.info("Data migration completed")

    # ============================================================
    # 4. 迁移现有参考图到图片库（可选，跳过有问题的数据）
    # ============================================================
    logger.info("Migrating existing reference images to gallery...")

    with Session(engine) as session:
        # 查询有参考图但没有锚定图的角色
        result = session.exec(text("""
            SELECT character_id, reference_image_path, reference_image_url
            FROM characters
            WHERE (reference_image_path IS NOT NULL AND reference_image_path != '')
              AND (anchor_image_id IS NULL OR anchor_image_id = '')
        """))

        rows = result.fetchall()

    # 每个角色单独处理，避免一个失败影响其他
    for row in rows:
        char_id, ref_path, ref_url = row
        if ref_path:
            try:
                with Session(engine) as session:
                    image_id = str(uuid.uuid4())
                    conn = session.connection()

                    # 插入到图片库
                    if is_sqlite:
                        conn.execute(text("""
                            INSERT INTO character_images (id, character_id, image_type, image_path, image_url, is_anchor, created_at)
                            VALUES (:id, :char_id, 'ANCHOR', :path, :url, 1, datetime('now'))
                        """), {"id": image_id, "char_id": char_id, "path": ref_path, "url": ref_url})
                    else:
                        conn.execute(text("""
                            INSERT INTO character_images (id, character_id, image_type, image_path, image_url, is_anchor, created_at)
                            VALUES (:id, :char_id, 'ANCHOR', :path, :url, TRUE, NOW())
                        """), {"id": image_id, "char_id": char_id, "path": ref_path, "url": ref_url})

                    # 更新角色的锚定图字段
                    conn.execute(text("""
                        UPDATE characters
                        SET anchor_image_id = :image_id,
                            anchor_image_path = :path,
                            anchor_image_url = :url
                        WHERE character_id = :char_id
                    """), {"image_id": image_id, "path": ref_path, "url": ref_url, "char_id": char_id})

                    session.commit()
                    logger.info(f"Migrated reference image for character: {char_id}")
            except Exception as e:
                logger.warning(f"Failed to migrate character {char_id}: {e}")

    logger.info("Migration completed successfully!")


if __name__ == "__main__":
    run_migration()
