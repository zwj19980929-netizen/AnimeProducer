from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import event
from config import settings

connect_args = {}
if "sqlite" in settings.DATABASE_URL:
    connect_args = {
        "check_same_thread": False,
        "timeout": 30,
    }

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=connect_args,
    pool_pre_ping=True,
)

if "sqlite" in settings.DATABASE_URL:
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


def get_session():
    """获取数据库会话生成器。"""
    with Session(engine) as session:
        yield session
