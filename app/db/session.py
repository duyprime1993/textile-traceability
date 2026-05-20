"""
Database session management / Quản lý kết nối database
Hỗ trợ SQLite (demo) và PostgreSQL (production)
"""

from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

# ─────────────────────────────────────────────────────────────────────────────
# Config / Cấu hình
# ─────────────────────────────────────────────────────────────────────────────

# Mặc định dùng SQLite cho demo; đổi thành PostgreSQL URL cho production
# Default to SQLite for demo; change to PostgreSQL URL for production
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./textile_traceability.db"
)

# SQLite cần bật WAL mode và foreign key enforcement
# SQLite needs WAL mode and foreign key enforcement enabled
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# ─────────────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────────────

engine = create_engine(
    DATABASE_URL,
    # SQLite: check_same_thread=False bắt buộc cho Streamlit / FastAPI
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    # Ghi log SQL queries khi debug (tắt trong production)
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
)


@event.listens_for(Engine, "connect")
def _on_connect(dbapi_conn, connection_record):
    """Bật foreign key constraints cho SQLite / Enable FK constraints for SQLite"""
    if IS_SQLITE:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")  # Cải thiện concurrency
        cursor.close()


# ─────────────────────────────────────────────────────────────────────────────
# Session factory
# ─────────────────────────────────────────────────────────────────────────────

SessionLocal = sessionmaker(
    bind        = engine,
    autocommit  = False,
    autoflush   = False,
    expire_on_commit = False,   # Giữ object sau commit (hữu ích cho API responses)
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency – trả về DB session và đóng sau khi dùng xong
    FastAPI dependency – yields a DB session and closes it when done

    Usage:
        @app.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Tạo tất cả bảng trong database
    Create all database tables

    Gọi 1 lần khi khởi động / Call once on startup
    """
    Base.metadata.create_all(bind=engine)
    print(f"✓ Database initialized: {DATABASE_URL}")


def drop_db() -> None:
    """
    Xóa tất cả bảng – CHỈ DÙNG TRONG TESTING
    Drop all tables – FOR TESTING ONLY
    """
    Base.metadata.drop_all(bind=engine)
