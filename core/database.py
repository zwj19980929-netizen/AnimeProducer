import logging

from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import event, text
from config import settings

logger = logging.getLogger(__name__)


def _is_sqlite_url(database_url: str) -> bool:
    return "sqlite" in database_url


def _build_connect_args(database_url: str) -> dict:
    if _is_sqlite_url(database_url):
        return {
            "check_same_thread": False,
            "timeout": 30,
        }

    if database_url.startswith("postgresql"):
        return {
            "connect_timeout": 5,
        }

    return {}


def _can_connect(database_url: str) -> bool:
    probe_engine = create_engine(
        database_url,
        echo=False,
        connect_args=_build_connect_args(database_url),
        pool_pre_ping=False,
    )
    try:
        with probe_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Configured database is unavailable: %s", exc)
        return False
    finally:
        probe_engine.dispose()


def _resolve_database_url() -> str:
    configured_url = settings.DATABASE_URL
    fallback_url = settings.DEV_DATABASE_FALLBACK_URL

    if not settings.DEBUG or not settings.ALLOW_DATABASE_FALLBACK_IN_DEBUG:
        return configured_url

    if _is_sqlite_url(configured_url) or configured_url == fallback_url:
        return configured_url

    if _can_connect(configured_url):
        return configured_url

    logger.warning("Falling back to local development database.")
    return fallback_url


DATABASE_URL = _resolve_database_url()

engine = create_engine(
    DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=_build_connect_args(DATABASE_URL),
    pool_pre_ping=True,
)

if _is_sqlite_url(DATABASE_URL):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        """设置 SQLite 的 WAL 模式和超时参数。"""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


def init_db():
    """初始化数据库表结构。"""
    SQLModel.metadata.create_all(engine)
    from api.auth import ensure_default_admin_user

    ensure_default_admin_user()


def get_session():
    """获取数据库会话生成器。"""
    with Session(engine) as session:
        yield session
