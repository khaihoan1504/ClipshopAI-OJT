"""Script chuyển toàn bộ dữ liệu từ MySQL Local sang Supabase PostgreSQL.

Cách chạy:
    $env:PYTHONPATH='backend'
    $env:SUPABASE_DATABASE_URL='postgresql://postgres:MAT_KHAU@db.xxxx.supabase.co:5432/postgres'
    python backend/migrate_mysql_to_supabase.py
"""
import os
import sys
from pathlib import Path

BACKEND_DIR = str(Path(__file__).resolve().parent)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import create_engine, text
from app import models  # noqa: F401
from app.core.config import settings
from app.db.session import Base


def normalize_pg_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


def main():
    supa_url = os.environ.get("SUPABASE_DATABASE_URL") or settings.DATABASE_URL
    if not supa_url or "mysql" in supa_url:
        print("LOI: Hay dat bien moi truong SUPABASE_DATABASE_URL (link PostgreSQL cua Supabase)!")
        sys.exit(1)

    supa_url = normalize_pg_url(supa_url)
    mysql_url = (
        f"mysql+pymysql://{settings.DB_USER}:{settings.DB_PASSWORD}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}?charset=utf8mb4"
    )

    print("1. Ket noi MySQL local...")
    mysql_engine = create_engine(mysql_url)
    print("2. Ket noi Supabase PostgreSQL...")
    pg_engine = create_engine(supa_url)

    print("3. Tao toan bo bang tren Supabase...")
    Base.metadata.create_all(bind=pg_engine)

    with mysql_engine.connect() as src, pg_engine.begin() as dst:
        for table in Base.metadata.sorted_tables:
            rows = src.execute(table.select()).mappings().all()
            if not rows:
                print(f" - {table.name}: 0 dong (bo qua)")
                continue

            # Xoa du lieu cu trong bang neu chay lai nhieu lan
            dst.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))
            dst.execute(table.insert(), [dict(r) for r in rows])

            # Dong bo lai sequence cho cot id (neu co)
            if "id" in table.c:
                dst.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('\"{table.name}\"', 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM \"{table.name}\"), 1), true)"
                    )
                )
            print(f" - {table.name}: da chuyen {len(rows)} dong")

    print("HOAN TAT! Da day toan bo du lieu len Supabase thanh cong.")


if __name__ == "__main__":
    main()
