"""
数据库迁移：为 Shot 表添加 scene_id 字段

用于支持空间连贯性功能：同一 scene_id 的镜头会自动使用上一镜头的最后一帧作为参考，
保持同一场景内的光影、位置连贯性。
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


def column_exists_sqlite(conn, table: str, column: str) -> bool:
    """检查列是否存在（SQLite）"""
    result = conn.execute(text(f"PRAGMA table_info({table})"))
    columns = [row[1] for row in result.fetchall()]
    return column in columns


def column_exists_postgres(conn, table: str, column: str) -> bool:
    """检查列是否存在（PostgreSQL）"""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :table AND column_name = :column
        )
    """), {"table": table, "column": column})
    return result.scalar()


def column_exists(conn, table: str, column: str) -> bool:
    """检查列是否存在（自动检测数据库类型）"""
    try:
        # 尝试 SQLite 方式
        return column_exists_sqlite(conn, table, column)
    except Exception:
        # 回退到 PostgreSQL 方式
        return column_exists_postgres(conn, table, column)


def migrate():
    """执行迁移"""
    logger.info("开始迁移：为 Shot 表添加 scene_id 字段")

    with Session(engine) as session:
        conn = session.connection()

        # 检查并添加 scene_id 字段
        if column_exists(conn, "shots", "scene_id"):
            logger.info("scene_id 字段已存在，跳过")
        else:
            logger.info("添加 scene_id 字段...")
            conn.execute(text("ALTER TABLE shots ADD COLUMN scene_id VARCHAR(255) DEFAULT NULL"))
            logger.info("scene_id 字段添加成功")

            # 创建索引以优化查询
            try:
                conn.execute(text("CREATE INDEX ix_shots_scene_id ON shots (scene_id)"))
                logger.info("scene_id 索引创建成功")
            except Exception as e:
                logger.warning(f"创建索引失败（可能已存在）: {e}")

        session.commit()

    logger.info("迁移完成！")


if __name__ == "__main__":
    migrate()
