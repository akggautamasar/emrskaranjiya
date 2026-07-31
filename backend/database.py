import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# On Render's free tier, local disk (sqlite) is wiped on every redeploy.
# Set a DATABASE_URL env var (e.g. a free Postgres from Neon/Render/Railway)
# for data that must survive redeploys. Falls back to local SQLite for
# quick local testing.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./payroll.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
