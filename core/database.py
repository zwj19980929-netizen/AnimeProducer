from sqlmodel import SQLModel, create_engine, Session
from config import settings

# SQLite requires check_same_thread=False for multi-threaded apps (like FastAPI)
connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=connect_args
)

def init_db():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
