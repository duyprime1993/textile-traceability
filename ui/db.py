"""DB session management cho Streamlit / DB session management for Streamlit"""

from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, init_db, engine
from app.models import Base


def _seed_demo_data() -> None:
    """
    Seed dữ liệu demo khi DB trống / Seed demo data when DB is empty.
    Chỉ chạy 1 lần khi chưa có Supplier nào.
    Only runs once when no Suppliers exist yet.
    """
    from datetime import date
    from decimal import Decimal
    from app.models import Supplier
    from app.schemas.tc import (
        BuyerCreate, MaterialCreate, SupplierCreate,
        TCInCreate, TCOutCreate, TCOutIssueRequest, TCInAllocation,
    )
    from app.schemas.production import ProductionBatchCreate, ProductionStageCreate
    from app.crud.tc import BuyerService, MaterialService, SupplierService, TCInService, TCOutService
    from app.crud.production import ProductionBatchService, ProductionStageService

    db = SessionLocal()
    try:
        # Check if data already exists
        if db.query(Supplier).first() is not None:
            return

        # -- Master Data --
        sup_svc = SupplierService(db)
        buy_svc = BuyerService(db)
        mat_svc = MaterialService(db)

        supplier = sup_svc.create(SupplierCreate(
            code="SUP-001", name="Green Fiber Co., Ltd.", country="Taiwan",
            certification_body="Control Union", scope_cert_number="CU-GRS-2024-001",
            scope_cert_expiry=date(2025, 6, 30), certification_standards="GRS,RCS",
        ))
        buyer = buy_svc.create(BuyerCreate(
            code="BUY-001", name="EcoWear Europe B.V.", country="Netherlands",
        ))
        material = mat_svc.create(MaterialCreate(
            code="FAB-rPET-100", name="100% Recycled PET Woven Fabric",
            unit="kg", recycled_content=Decimal("100.00"), composition="100% rPET",
        ))
        db.commit()

        # -- In TCs --
        tc_in_svc = TCInService(db)
        tc_in_1 = tc_in_svc.create(TCInCreate(
            tc_number="TC-IN-2024-001", issue_date=date(2024, 1, 15),
            received_date=date(2024, 1, 20), supplier_id=supplier.id,
            material_id=material.id, certification_standard="GRS",
            certified_quantity=Decimal("5000.000"), invoice_number="INV-2024-001",
            certification_body="Control Union",
        ))
        tc_in_2 = tc_in_svc.create(TCInCreate(
            tc_number="TC-IN-2024-002", issue_date=date(2024, 4, 10),
            received_date=date(2024, 4, 15), supplier_id=supplier.id,
            material_id=material.id, certification_standard="GRS",
            certified_quantity=Decimal("5000.000"), invoice_number="INV-2024-002",
            certification_body="Control Union",
        ))
        db.commit()

        # -- Production Batches --
        batch_svc = ProductionBatchService(db)
        stage_svc = ProductionStageService(db)

        batch1 = batch_svc.create(ProductionBatchCreate(
            batch_number="BATCH-2024-001", product_name="Men Polo Shirt - Style EW-MP-001",
            order_number="PO-2024-001", tc_in_id=tc_in_1.id, start_date=date(2024, 2, 1),
            planned_input_qty=Decimal("2000.000"), planned_output_qty=Decimal("1700.000"),
        ))
        stage_svc.record_stage(ProductionStageCreate(
            batch_id=batch1.id, stage="cutting", stage_date=date(2024, 2, 5),
            input_quantity=Decimal("2000.000"), output_quantity=Decimal("1800.000"),
            operator_name="Nguyen Van A",
        ))
        stage_svc.record_stage(ProductionStageCreate(
            batch_id=batch1.id, stage="sewing", stage_date=date(2024, 2, 15),
            input_quantity=Decimal("1800.000"), output_quantity=Decimal("1710.000"),
        ))
        stage_svc.record_stage(ProductionStageCreate(
            batch_id=batch1.id, stage="packing", stage_date=date(2024, 2, 20),
            input_quantity=Decimal("1710.000"), output_quantity=Decimal("1675.800"),
        ))
        batch_svc.complete(batch1.id)

        batch2 = batch_svc.create(ProductionBatchCreate(
            batch_number="BATCH-2024-002", product_name="Women T-Shirt - Style EW-WT-002",
            order_number="PO-2024-002", tc_in_id=tc_in_1.id, start_date=date(2024, 3, 1),
        ))
        stage_svc.record_stage(ProductionStageCreate(
            batch_id=batch2.id, stage="cutting", stage_date=date(2024, 3, 5),
            input_quantity=Decimal("2500.000"), output_quantity=Decimal("2250.000"),
        ))
        stage_svc.record_stage(ProductionStageCreate(
            batch_id=batch2.id, stage="sewing", stage_date=date(2024, 3, 18),
            input_quantity=Decimal("2250.000"), output_quantity=Decimal("2137.500"),
        ))
        stage_svc.record_stage(ProductionStageCreate(
            batch_id=batch2.id, stage="packing", stage_date=date(2024, 3, 25),
            input_quantity=Decimal("2137.500"), output_quantity=Decimal("2094.750"),
        ))
        batch_svc.complete(batch2.id)

        batch3 = batch_svc.create(ProductionBatchCreate(
            batch_number="BATCH-2024-003", product_name="Kids Hoodie - Style EW-KH-003",
            order_number="PO-2024-003", tc_in_id=tc_in_2.id, start_date=date(2024, 5, 1),
        ))
        stage_svc.record_stage(ProductionStageCreate(
            batch_id=batch3.id, stage="cutting", stage_date=date(2024, 5, 8),
            input_quantity=Decimal("3000.000"), output_quantity=Decimal("2700.000"),
        ))
        stage_svc.record_stage(ProductionStageCreate(
            batch_id=batch3.id, stage="sewing", stage_date=date(2024, 5, 20),
            input_quantity=Decimal("2700.000"), output_quantity=Decimal("2565.000"),
        ))
        stage_svc.record_stage(ProductionStageCreate(
            batch_id=batch3.id, stage="packing", stage_date=date(2024, 5, 28),
            input_quantity=Decimal("2565.000"), output_quantity=Decimal("2513.700"),
        ))
        batch_svc.complete(batch3.id)
        db.commit()

        # -- Out TCs --
        tc_out_svc = TCOutService(db)
        tc_out_1 = tc_out_svc.create(TCOutCreate(
            tc_number="TC-OUT-2024-001", issue_date=date(2024, 3, 1),
            buyer_id=buyer.id, product_name="Men Polo Shirt 100% rPET",
            style_number="EW-MP-001", certification_standard="GRS",
            certified_quantity=Decimal("1500.000"), invoice_number="SINV-2024-001",
            po_number="PO-2024-001",
        ))
        tc_out_svc.issue(TCOutIssueRequest(
            tc_out_id=tc_out_1.id,
            allocations=[TCInAllocation(tc_in_id=tc_in_1.id, allocated_quantity=Decimal("1500.000"))],
        ))

        tc_out_2 = tc_out_svc.create(TCOutCreate(
            tc_number="TC-OUT-2024-002", issue_date=date(2024, 4, 15),
            buyer_id=buyer.id, product_name="Women T-Shirt 100% rPET",
            style_number="EW-WT-002", certification_standard="GRS",
            certified_quantity=Decimal("2000.000"), invoice_number="SINV-2024-002",
        ))
        tc_out_svc.issue(TCOutIssueRequest(
            tc_out_id=tc_out_2.id,
            allocations=[TCInAllocation(tc_in_id=tc_in_1.id, allocated_quantity=Decimal("2000.000"))],
        ))

        tc_out_3 = tc_out_svc.create(TCOutCreate(
            tc_number="TC-OUT-2024-003", issue_date=date(2024, 6, 10),
            buyer_id=buyer.id, product_name="Kids Hoodie 100% rPET",
            style_number="EW-KH-003", certification_standard="GRS",
            certified_quantity=Decimal("2200.000"), invoice_number="SINV-2024-003",
        ))
        tc_out_svc.issue(TCOutIssueRequest(
            tc_out_id=tc_out_3.id,
            allocations=[TCInAllocation(tc_in_id=tc_in_2.id, allocated_quantity=Decimal("2200.000"))],
        ))
        db.commit()

    except Exception as e:
        db.rollback()
        print(f"Auto-seed error: {e}")
    finally:
        db.close()


@st.cache_resource(show_spinner=False)
def _ensure_db() -> bool:
    """Initialize DB once per app lifecycle"""
    Base.metadata.create_all(bind=engine)
    _seed_demo_data()
    return True


def get_db() -> Session:
    """
    Returns a new DB session for each Streamlit request
    """
    _ensure_db()
    return SessionLocal()


def run_with_db(fn, *args, **kwargs):
    """
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
