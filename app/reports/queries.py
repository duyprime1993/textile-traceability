"""
Reusable DB queries cho tất cả báo cáo
Reusable DB queries shared by all report modules
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    MassBalancePeriod, ProductionBatch, ProductionStage,
    StockTransaction, TCIn, TCLinkage, TCOut, QtyType,
)


def get_opening_balance(
    db          : Session,
    material_id : int,
    before_date : date,
    qty_type    : str = QtyType.CERTIFIED,
) -> Decimal:
    """
    Tổng cộng tất cả stock transactions TRƯỚC ngày chỉ định
    Sum all stock transactions BEFORE the given date (= opening balance)
    """
    result = (
        db.query(func.sum(StockTransaction.quantity))
        .filter(
            StockTransaction.material_id    == material_id,
            StockTransaction.quantity_type  == qty_type,
            StockTransaction.transaction_date < before_date,
        )
        .scalar()
    )
    return result or Decimal("0")


def get_closing_balance(
    db          : Session,
    material_id : int,
    as_of_date  : date,
    qty_type    : str = QtyType.CERTIFIED,
) -> Decimal:
    """
    Tổng cộng tất cả stock transactions ĐẾN ngày chỉ định (bao gồm ngày đó)
    Sum all stock transactions UP TO the given date inclusive (= closing balance)
    """
    result = (
        db.query(func.sum(StockTransaction.quantity))
        .filter(
            StockTransaction.material_id    == material_id,
            StockTransaction.quantity_type  == qty_type,
            StockTransaction.transaction_date <= as_of_date,
        )
        .scalar()
    )
    return result or Decimal("0")


def get_tc_in_for_period(
    db                     : Session,
    period_start           : date,
    period_end             : date,
    certification_standard : Optional[str] = None,
    material_id            : Optional[int] = None,
) -> List[TCIn]:
    """
    In TC nhận trong kỳ (theo received_date hoặc issue_date nếu không có received_date)
    In TCs received during period
    """
    q = (
        db.query(TCIn)
        .filter(
            TCIn.status != "cancelled",
            func.coalesce(TCIn.received_date, TCIn.issue_date) >= period_start,
            func.coalesce(TCIn.received_date, TCIn.issue_date) <= period_end,
        )
    )
    if certification_standard:
        q = q.filter(TCIn.certification_standard == certification_standard)
    if material_id:
        q = q.filter(TCIn.material_id == material_id)
    return q.order_by(TCIn.issue_date).all()


def get_tc_out_for_period(
    db                     : Session,
    period_start           : date,
    period_end             : date,
    certification_standard : Optional[str] = None,
) -> List[TCOut]:
    """
    Out TC phát hành trong kỳ
    Out TCs issued during period
    """
    q = (
        db.query(TCOut)
        .filter(
            TCOut.status      == "issued",
            TCOut.issue_date  >= period_start,
            TCOut.issue_date  <= period_end,
        )
    )
    if certification_standard:
        q = q.filter(TCOut.certification_standard == certification_standard)
    return q.order_by(TCOut.issue_date).all()


def get_stages_for_period(
    db           : Session,
    period_start : date,
    period_end   : date,
    material_id  : Optional[int] = None,
) -> List[ProductionStage]:
    """
    Công đoạn sản xuất trong kỳ
    Production stages during period
    """
    q = (
        db.query(ProductionStage)
        .join(ProductionStage.batch)
        .filter(
            ProductionStage.stage_date >= period_start,
            ProductionStage.stage_date <= period_end,
        )
    )
    if material_id:
        q = q.filter(ProductionBatch.tc_in.has(material_id=material_id))
    return q.order_by(ProductionStage.stage_date).all()


def get_stage_totals_for_period(
    db           : Session,
    period_start : date,
    period_end   : date,
    material_id  : Optional[int] = None,
) -> Dict[str, Tuple[Decimal, Decimal]]:
    """
    Tổng hợp input/output theo công đoạn trong kỳ
    Aggregate input/output by stage during period

    Returns: {"cutting": (total_input, total_output), "sewing": ..., "packing": ...}
    """
    q = (
        db.query(
            ProductionStage.stage,
            func.sum(ProductionStage.input_quantity).label("total_input"),
            func.sum(ProductionStage.output_quantity).label("total_output"),
        )
        .join(ProductionStage.batch)
        .filter(
            ProductionStage.stage_date >= period_start,
            ProductionStage.stage_date <= period_end,
        )
        .group_by(ProductionStage.stage)
    )

    if material_id:
        # Join qua tc_in để filter theo material
        q = q.filter(
            ProductionBatch.tc_in_id.in_(
                db.query(TCIn.id).filter(TCIn.material_id == material_id)
            )
        )

    result = {}
    for row in q.all():
        result[row.stage] = (
            row.total_input  or Decimal("0"),
            row.total_output or Decimal("0"),
        )
    return result


def get_batches_for_tc_in(
    db       : Session,
    tc_in_id : int,
) -> List[ProductionBatch]:
    """Tất cả lô sản xuất sử dụng In TC này / All batches using this In TC"""
    return (
        db.query(ProductionBatch)
        .filter(ProductionBatch.tc_in_id == tc_in_id)
        .order_by(ProductionBatch.start_date)
        .all()
    )


def get_linkages_for_tc_in(db: Session, tc_in_id: int) -> List[TCLinkage]:
    """Tất cả linkages (Out TCs) của In TC này"""
    return (
        db.query(TCLinkage)
        .filter(TCLinkage.tc_in_id == tc_in_id)
        .all()
    )


def get_stock_transactions_for_material(
    db           : Session,
    material_id  : int,
    date_from    : Optional[date] = None,
    date_to      : Optional[date] = None,
    tc_in_id     : Optional[int]  = None,
) -> List[StockTransaction]:
    """Tất cả giao dịch kho cho một vật liệu / All stock transactions for a material"""
    q = (
        db.query(StockTransaction)
        .filter(StockTransaction.material_id == material_id)
    )
    if date_from:
        q = q.filter(StockTransaction.transaction_date >= date_from)
    if date_to:
        q = q.filter(StockTransaction.transaction_date <= date_to)
    if tc_in_id:
        q = q.filter(StockTransaction.tc_in_id == tc_in_id)
    return q.order_by(StockTransaction.transaction_date, StockTransaction.created_at).all()
