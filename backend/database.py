from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "fraud_history.db"

# check_same_thread=False is required for SQLite when used from FastAPI
# (FastAPI runs sync endpoints in a threadpool)
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db():
    """Create tables if they don't exist. Called once at app startup."""
    from backend import models  # noqa: F401 — import so Base knows about models
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency that yields a session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()