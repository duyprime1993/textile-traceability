"""
Demo script – seed dữ liệu mẫu + chạy tất cả báo cáo
Demo script – seeds sample data + runs all reports

Chạy: python seed_demo.py
Run : python seed_demo.py

Tạo file: GRS_Mass_Balance_Demo_2024.xlsx
Creates : GRS_Mass_Balance_Demo_2024.xlsx
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from datetime import date
from decimal import Decimal

from app.db.session import SessionLocal, init_db
from app.schemas.tc import (
    BuyerCreate, MaterialCreate, SupplierCreate,
    TCInCreate, TCOutCreate, TCOutIssueRequest, TCInAllocation,
)
from app.schemas.production import ProductionBatchCreate, ProductionStageCreate
from app.crud.tc import BuyerService, MaterialService, SupplierService, TCInService, TCOutService
from app.crud.production import ProductionBatchService, ProductionStageService
from app.reports.annual import AnnualMassBalanceReport
from app.reports.traceability import TraceabilityReport
from app.reports.loss_analysis import LossAnalysisReport
from app.reports.stock_card import StockCardReport, StockSummaryReport
from app.reports.excel_export import ExcelExporter


def seed_and_demo():
    init_db()
    db = SessionLocal()

    try:
        print("=" * 60)
        print("  TEXTILE TRACEABILITY SYSTEM – DEMO")
        print("  GRS/GOTS Mass Balance & Traceability")
        print("=" * 60)

        # ── 1. Tạo Master Data ────────────────────────────────────────
        print("\n[1] Tạo Master Data...")

        sup_svc = SupplierService(db)
        buy_svc = BuyerService(db)
        mat_svc = MaterialService(db)

        supplier = sup_svc.create(SupplierCreate(
            code                    = "SUP-001",
            name                    = "Green Fiber Co., Ltd.",
            country                 = "Taiwan",
            certification_body      = "Control Union",
            scope_cert_number       = "CU-GRS-2024-001",
            scope_cert_expiry       = date(2025, 6, 30),
            certification_standards = "GRS,RCS",
        ))
        print(f"   ✓ Supplier: {supplier.name}")

        buyer = buy_svc.create(BuyerCreate(
            code    = "BUY-001",
            name    = "EcoWear Europe B.V.",
            country = "Netherlands",
        ))
        print(f"   ✓ Buyer: {buyer.name}")

        material = mat_svc.create(MaterialCreate(
            code             = "FAB-rPET-100",
            name             = "100% Recycled PET Woven Fabric",
            unit             = "kg",
            recycled_content = Decimal("100.00"),
            composition      = "100% rPET",
        ))
        print(f"   ✓ Material: {material.name}")

        db.commit()

        # ── 2. Tạo In TCs ─────────────────────────────────────────────
        print("\n[2] Tạo In TCs...")

        tc_in_svc = TCInService(db)

        tc_in_1 = tc_in_svc.create(TCInCreate(
            tc_number              = "TC-IN-2024-001",
            issue_date             = date(2024, 1, 15),
            received_date          = date(2024, 1, 20),
            supplier_id            = supplier.id,
            material_id            = material.id,
            certification_standard = "GRS",
            certified_quantity     = Decimal("5000.000"),
            invoice_number         = "INV-2024-001",
            certification_body     = "Control Union",
        ))
        print(f"   ✓ In TC: {tc_in_1.tc_number} – {tc_in_1.certified_quantity} kg")

        tc_in_2 = tc_in_svc.create(TCInCreate(
            tc_number              = "TC-IN-2024-002",
            issue_date             = date(2024, 4, 10),
            received_date          = date(2024, 4, 15),
            supplier_id            = supplier.id,
            material_id            = material.id,
            certification_standard = "GRS",
            certified_quantity     = Decimal("5000.000"),
            invoice_number         = "INV-2024-002",
            certification_body     = "Control Union",
        ))
        print(f"   ✓ In TC: {tc_in_2.tc_number} – {tc_in_2.certified_quantity} kg")

        db.commit()

        # ── 3. Tạo Production Batches ─────────────────────────────────
        print("\n[3] Tạo Production Batches & Stages...")

        batch_svc = ProductionBatchService(db)
        stage_svc = ProductionStageService(db)

        # Batch 1 – từ TC-IN-001
        batch1 = batch_svc.create(ProductionBatchCreate(
            batch_number  = "BATCH-2024-001",
            product_name  = "Men Polo Shirt – Style EW-MP-001",
            order_number  = "PO-2024-001",
            tc_in_id      = tc_in_1.id,
            start_date    = date(2024, 2, 1),
            planned_input_qty  = Decimal("2000.000"),
            planned_output_qty = Decimal("1700.000"),
        ))
        # Cutting (10% loss)
        stage_svc.record_stage(ProductionStageCreate(
            batch_id        = batch1.id,
            stage           = "cutting",
            stage_date      = date(2024, 2, 5),
            input_quantity  = Decimal("2000.000"),
            output_quantity = Decimal("1800.000"),
            operator_name   = "Nguyen Van A",
        ))
        # Sewing (5% loss)
        stage_svc.record_stage(ProductionStageCreate(
            batch_id        = batch1.id,
            stage           = "sewing",
            stage_date      = date(2024, 2, 15),
            input_quantity  = Decimal("1800.000"),
            output_quantity = Decimal("1710.000"),
        ))
        # Packing (2% loss)
        stage_svc.record_stage(ProductionStageCreate(
            batch_id        = batch1.id,
            stage           = "packing",
            stage_date      = date(2024, 2, 20),
            input_quantity  = Decimal("1710.000"),
            output_quantity = Decimal("1675.800"),
        ))
        batch_svc.complete(batch1.id)
        print(f"   ✓ Batch {batch1.batch_number}: 2000 kg → 1675.8 kg (loss: 16.21%)")

        # Batch 2 – từ TC-IN-001 (dùng nốt phần còn lại)
        batch2 = batch_svc.create(ProductionBatchCreate(
            batch_number  = "BATCH-2024-002",
            product_name  = "Women T-Shirt – Style EW-WT-002",
            order_number  = "PO-2024-002",
            tc_in_id      = tc_in_1.id,
            start_date    = date(2024, 3, 1),
        ))
        stage_svc.record_stage(ProductionStageCreate(
            batch_id        = batch2.id,
            stage           = "cutting",
            stage_date      = date(2024, 3, 5),
            input_quantity  = Decimal("2500.000"),
            output_quantity = Decimal("2250.000"),
        ))
        stage_svc.record_stage(ProductionStageCreate(
            batch_id        = batch2.id,
            stage           = "sewing",
            stage_date      = date(2024, 3, 18),
            input_quantity  = Decimal("2250.000"),
            output_quantity = Decimal("2137.500"),
        ))
        stage_svc.record_stage(ProductionStageCreate(
            batch_id        = batch2.id,
            stage           = "packing",
            stage_date      = date(2024, 3, 25),
            input_quantity  = Decimal("2137.500"),
            output_quantity = Decimal("2094.750"),
        ))
        batch_svc.complete(batch2.id)
        print(f"   ✓ Batch {batch2.batch_number}: 2500 kg → 2094.75 kg")

        # Batch 3 – từ TC-IN-002
        batch3 = batch_svc.create(ProductionBatchCreate(
            batch_number  = "BATCH-2024-003",
            product_name  = "Kids Hoodie – Style EW-KH-003",
            order_number  = "PO-2024-003",
            tc_in_id      = tc_in_2.id,
            start_date    = date(2024, 5, 1),
        ))
        stage_svc.record_stage(ProductionStageCreate(
            batch_id        = batch3.id,
            stage           = "cutting",
            stage_date      = date(2024, 5, 8),
            input_quantity  = Decimal("3000.000"),
            output_quantity = Decimal("2700.000"),
        ))
        stage_svc.record_stage(ProductionStageCreate(
            batch_id        = batch3.id,
            stage           = "sewing",
            stage_date      = date(2024, 5, 20),
            input_quantity  = Decimal("2700.000"),
            output_quantity = Decimal("2565.000"),
        ))
        stage_svc.record_stage(ProductionStageCreate(
            batch_id        = batch3.id,
            stage           = "packing",
            stage_date      = date(2024, 5, 28),
            input_quantity  = Decimal("2565.000"),
            output_quantity = Decimal("2513.700"),
        ))
        batch_svc.complete(batch3.id)
        print(f"   ✓ Batch {batch3.batch_number}: 3000 kg → 2513.7 kg")

        db.commit()

        # ── 4. Tạo Out TCs ────────────────────────────────────────────
        print("\n[4] Tạo và phát hành Out TCs...")

        tc_out_svc = TCOutService(db)

        tc_out_1 = tc_out_svc.create(TCOutCreate(
            tc_number              = "TC-OUT-2024-001",
            issue_date             = date(2024, 3, 1),
            buyer_id               = buyer.id,
            product_name           = "Men Polo Shirt 100% rPET",
            style_number           = "EW-MP-001",
            certification_standard = "GRS",
            certified_quantity     = Decimal("1500.000"),
            invoice_number         = "SINV-2024-001",
            po_number              = "PO-2024-001",
        ))
        tc_out_svc.issue(TCOutIssueRequest(
            tc_out_id   = tc_out_1.id,
            allocations = [TCInAllocation(tc_in_id=tc_in_1.id, allocated_quantity=Decimal("1500.000"))],
        ))
        print(f"   ✓ Out TC: {tc_out_1.tc_number} – 1500 kg → {buyer.name}")

        tc_out_2 = tc_out_svc.create(TCOutCreate(
            tc_number              = "TC-OUT-2024-002",
            issue_date             = date(2024, 4, 15),
            buyer_id               = buyer.id,
            product_name           = "Women T-Shirt 100% rPET",
            style_number           = "EW-WT-002",
            certification_standard = "GRS",
            certified_quantity     = Decimal("2000.000"),
            invoice_number         = "SINV-2024-002",
        ))
        tc_out_svc.issue(TCOutIssueRequest(
            tc_out_id   = tc_out_2.id,
            allocations = [TCInAllocation(tc_in_id=tc_in_1.id, allocated_quantity=Decimal("2000.000"))],
        ))
        print(f"   ✓ Out TC: {tc_out_2.tc_number} – 2000 kg")

        tc_out_3 = tc_out_svc.create(TCOutCreate(
            tc_number              = "TC-OUT-2024-003",
            issue_date             = date(2024, 6, 10),
            buyer_id               = buyer.id,
            product_name           = "Kids Hoodie 100% rPET",
            style_number           = "EW-KH-003",
            certification_standard = "GRS",
            certified_quantity     = Decimal("2200.000"),
            invoice_number         = "SINV-2024-003",
        ))
        tc_out_svc.issue(TCOutIssueRequest(
            tc_out_id   = tc_out_3.id,
            allocations = [TCInAllocation(tc_in_id=tc_in_2.id, allocated_quantity=Decimal("2200.000"))],
        ))
        print(f"   ✓ Out TC: {tc_out_3.tc_number} – 2200 kg")

        db.commit()

        # ── 5. Chạy tất cả báo cáo ───────────────────────────────────
        print("\n[5] Tạo báo cáo...")

        mb_report = AnnualMassBalanceReport(db)
        annual = mb_report.generate_annual(
            year                   = 2024,
            certification_standard = "GRS",
            material_id            = material.id,
            save_to_db             = True,
        )
        print(f"\n{annual.format_report()}")

        # Traceability
        trace_rpt  = TraceabilityReport(db)
        trace_1    = trace_rpt.generate(tc_in_1.id)
        print(f"\n{trace_1.format_report()}")

        # Loss Analysis
        loss_rpt   = LossAnalysisReport(db)
        loss_result= loss_rpt.generate(date(2024, 1, 1), date(2024, 12, 31))

        # Stock Card
        sc_rpt    = StockCardReport(db)
        stock_card = sc_rpt.generate_by_material(material.id, date(2024, 1, 1), date(2024, 12, 31))
        print(f"\n{stock_card.format_report()}")

        # Summary
        summary_rpt  = StockSummaryReport(db)
        summary_rows = summary_rpt.generate(date(2024, 1, 1), date(2024, 12, 31))

        # Monthly breakdown
        monthly_rows = mb_report.generate_monthly_breakdown(
            year                   = 2024,
            certification_standard = "GRS",
            material_id            = material.id,
        )

        # Traceability cho TC-IN-002 cũng
        trace_2 = trace_rpt.generate(tc_in_2.id)

        # ── 6. Xuất Excel ─────────────────────────────────────────────
        print("\n[6] Xuất Excel...")

        exporter = ExcelExporter()
        buffer   = exporter.export_full_workbook(
            annual_mb      = annual,
            monthly_rows   = monthly_rows,
            summary_rows   = summary_rows,
            stock_card     = stock_card,
            traceability   = trace_1,
            loss_analysis  = loss_result,
            company_name   = "ABC Garment Factory Co., Ltd.",
            period_start   = date(2024, 1, 1),
            period_end     = date(2024, 12, 31),
        )

        out_file = "GRS_Mass_Balance_Demo_2024.xlsx"
        with open(out_file, "wb") as f:
            f.write(buffer.getvalue())

        print(f"   ✓ Excel xuất thành công: {out_file}")
        print(f"\n{'=' * 60}")
        print(f"  DEMO HOÀN THÀNH / DEMO COMPLETE")
        print(f"  File: {out_file}")
        print(f"  Balance Status: {annual.balance_status}")
        print(f"{'=' * 60}")

    except Exception as e:
        db.rollback()
        import traceback
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    seed_and_demo()
