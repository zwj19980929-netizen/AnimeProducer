"""
数据库迁移：为 Character 表添加 updated_at 字段
"""

import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from sqlmodel import Session

from core.database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def column_exists(conn, table: str, column: str) -> bool:
    """检查列是否存在（PostgreSQL）"""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :table AND column_name = :column
        )
    """), {"table": table, "column": column})
    return result.scalar()


def migrate():
    """执行迁移"""
    logger.info("开始迁移：添加 Character.updated_at 字段")

    with Session(engine) as session:
        conn = session.connection()

        # 检查并添加 updated_at 字段
        if column_exists(conn, "characters", "updated_at"):
            logger.info("updated_at 字段已存在，跳过")
        else:
            logger.info("添加 updated_at 字段...")
            conn.execute(text("""
                ALTER TABLE characters
                ADD COLUMN updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
            """))
            logger.info("updated_at 字段添加成功")

        session.commit()

    logger.info("迁移完成！")


if __name__ == "__main__":
    migrate()
