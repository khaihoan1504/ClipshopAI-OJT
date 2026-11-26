"""Kết nối MySQL hoặc PostgreSQL (Supabase) bằng SQLAlchemy."""
import os

from sqlalchemy import create_engine
from sqlalchemy.dialects.mysql import BIGINT as MYSQL_BIGINT
from sqlalchemy.dialects.mysql import INTEGER as MYSQL_INTEGER
from sqlalchemy.dialects.mysql import JSON as MYSQL_JSON
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings


@compiles(MYSQL_BIGINT, "postgresql")
def _compile_bigint_pg(type_, compiler, **kw):
    return "BIGINT"


@compiles(MYSQL_INTEGER, "postgresql")
def _compile_int_pg(type_, compiler, **kw):
    return "INTEGER"


@compiles(MYSQL_JSON, "postgresql")
def _compile_json_pg(type_, compiler, **kw):
    return "JSONB"

# Trên Vercel Serverless / Supabase Pooler, dùng NullPool để đóng kết nối ngay sau mỗi request,
# tránh giữ kết nối nhàn rỗi làm tràn giới hạn Session Pooler (max 15 clients).
_use_null_pool = bool(
    os.getenv("VERCEL") or settings.database_url.startswith("postgresql")
)
_engine_kwargs = (
    {"poolclass": NullPool}
    if _use_null_pool
    else {"pool_pre_ping": True}
)
engine = create_engine(settings.database_url, **_engine_kwargs)

# SessionLocal(): mỗi lần gọi tạo ra 1 phiên làm việc với DB
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Mọi model (bảng) đều kế thừa từ Base."""


def get_db():
    """Dependency cho FastAPI: mở session cho mỗi request và luôn đóng lại sau đó.

    Dùng trong router:  db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
