"""
Base CRUD helpers + AuditLog helper
Helpers dùng chung cho tất cả services
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional, Type, TypeVar

from sqlalchemy.orm import Session

from app.models import AuditLog, Base

T = TypeVar("T", bound=Base)


# ─────────────────────────────────────────────────────────────────────────────
# Audit helper / Ghi nhật ký
# ─────────────────────────────────────────────────────────────────────────────

def _serialize(obj: Any) -> Any:
    """Chuyển đổi kiểu dữ liệu đặc biệt sang JSON-serializable"""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


def model_to_dict(instance: Any) -> dict:
    """Chuyển SQLAlchemy model instance thành dict (bỏ qua lazy-loaded relations)"""
    result = {}
    for col in instance.__table__.columns:
        val = getattr(instance, col.name, None)
        result[col.name] = _serialize(val)
    return result


def write_audit_log(
    db         : Session,
    table_name : str,
    record_id  : int,
    action     : str,          # INSERT / UPDATE / DELETE
    old_values : Optional[dict] = None,
    new_values : Optional[dict] = None,
    user_id    : Optional[int]  = None,
) -> AuditLog:
    """
    Ghi nhật ký kiểm toán / Write audit log entry
    Phải gọi trước khi commit / Must be called before commit
    """
    changed = None
    if old_values and new_values:
        changed_fields = [k for k in new_values if old_values.get(k) != new_values.get(k)]
        changed = json.dumps(changed_fields)

    log = AuditLog(
        table_name     = table_name,
        record_id      = record_id,
        action         = action,
        old_values     = old_values,
        new_values     = new_values,
        changed_fields = changed,
        user_id        = user_id,
    )
    db.add(log)
    return log


# ─────────────────────────────────────────────────────────────────────────────
# Generic get helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_or_404(db: Session, model: Type[T], record_id: int) -> T:
    """
    Lấy record theo ID, raise ValueError nếu không tìm thấy
    Get record by ID, raise ValueError if not found
    """
    obj = db.get(model, record_id)
    if obj is None:
        raise ValueError(f"{model.__tablename__} id={record_id} không tìm thấy / not found")
    return obj
