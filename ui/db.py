"""DB session management cho Streamlit / DB session management for Streamlit"""

from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, init_db, engine
from app.models import Base


@st.cache_resource(show_spinner=False)
def _ensure_db() -> bool:
    """Khởi tạo DB một lần / Initialize DB once per app lifecycle"""
    Base.metadata.create_all(bind=engine)
    return True


def get_db() -> Session:
    """
    Trả về DB session mới cho mỗi request Streamlit
    Returns a new DB session for each Streamlit request

    Pattern: gọi db = get_db() ở đầu mỗi page, dùng db.close() trong finally
    Pattern: call db = get_db() at top of each page, call db.close() in finally
    """
    _ensure_db()
    return SessionLocal()


def run_with_db(fn, *args, **kwargs):
    """
    Chạy function với session + commit/rollback/close tự động
    Run function with auto commit/rollback/close
    """
    db = get_db()
    try:
        result = fn(db, *args, **kwargs)
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
