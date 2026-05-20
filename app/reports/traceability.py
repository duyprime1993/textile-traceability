"""
Traceability Report / Báo cáo truy xuất nguồn gốc
Chọn 1 In TC → hiển thị toàn bộ chuỗi downstream

Chain: In TC → Production Batches → Stages → Out TCs

Dùng để trả lời câu hỏi kiểm toán:
"Lượng vải có chứng nhận GRS này đi đâu?"
"Batch nào đã sử dụng TC này và hao hụt bao nhiêu?"
"Out TC nào được cấp nguồn từ TC này?"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.mass_balance import MassBalanceCalculator
from app.models import ProductionBatch, ProductionStage, TCIn, TCLinkage, TCOut
from app.reports.queries import get_batches_for_tc_in, get_linkages_for_tc_in


@dataclass
class StageDetail:
    stage          : str
    stage_date     : str
    input_qty      : Decimal
    output_qty     : Decimal
    loss_qty       : Decimal
    loss_pct       : Decimal
    operator_name  : Optional[str]
    loss_reason    : Optional[str]


@dataclass
class BatchDetail:
    batch_number   : str
    product_name   : str
    order_number   : Optional[str]
    start_date     : str
    end_date       : Optional[str]
    status         : str
    planned_in     : Optional[Decimal]
    actual_in      : Optional[Decimal]
    actual_out     : Optional[Decimal]
    total_loss_kg  : Optional[Decimal]
    total_loss_pct : Optional[Decimal]
    stages         : List[StageDetail] = field(default_factory=list)


@dataclass
class LinkageDetail:
    tc_out_number  : str
    issue_date     : str
    buyer_name     : str
    product_name   : str
    allocated_qty  : Decimal
    allocation_pct : Optional[Decimal]
    status         : str


@dataclass
class TraceabilityResult:
    """
    Kết quả truy xuất nguồn gốc đầy đủ cho 1 In TC
    Complete traceability result for a single In TC
    """
    # ── In TC Info ──────────────────────────────────────────────────────────
    tc_in_number           : str
    tc_in_issue_date       : str
    supplier_name          : str
    material_code          : str
    material_name          : str
    certification_standard : str
    certified_qty          : Decimal

    # ── Production ──────────────────────────────────────────────────────────
    batches                : List[BatchDetail]

    # ── Out TCs ─────────────────────────────────────────────────────────────
    linked_tc_outs         : List[LinkageDetail]

    # ── Summary / Tóm tắt ───────────────────────────────────────────────────
    total_issued_to_prod   : Decimal
    total_produced         : Decimal
    total_process_loss_kg  : Decimal
    total_process_loss_pct : Decimal
    total_sold_with_tc     : Decimal
    remaining_in_stock     : Decimal
    utilization_pct        : Decimal
    is_balanced            : bool   # total_issued <= certified_qty

    # ── Alerts ──────────────────────────────────────────────────────────────
    alerts                 : List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tc_in"                  : self.tc_in_number,
            "supplier"               : self.supplier_name,
            "material"               : f"{self.material_code} – {self.material_name}",
            "certified_qty_kg"       : float(self.certified_qty),
            "total_issued_kg"        : float(self.total_issued_to_prod),
            "total_produced_kg"      : float(self.total_produced),
            "process_loss_kg"        : float(self.total_process_loss_kg),
            "process_loss_pct"       : float(self.total_process_loss_pct),
            "total_sold_kg"          : float(self.total_sold_with_tc),
            "remaining_stock_kg"     : float(self.remaining_in_stock),
            "utilization_pct"        : float(self.utilization_pct),
            "is_balanced"            : self.is_balanced,
            "number_of_batches"      : len(self.batches),
            "number_of_tc_outs"      : len(self.linked_tc_outs),
            "alerts"                 : self.alerts,
            "batches"                : [
                {
                    "batch"        : b.batch_number,
                    "product"      : b.product_name,
                    "order"        : b.order_number,
                    "actual_in_kg" : float(b.actual_in)  if b.actual_in  else None,
                    "actual_out_kg": float(b.actual_out) if b.actual_out else None,
                    "loss_kg"      : float(b.total_loss_kg)  if b.total_loss_kg  else None,
                    "loss_pct"     : float(b.total_loss_pct) if b.total_loss_pct else None,
                    "stages"       : [
                        {
                            "stage"      : s.stage,
                            "date"       : s.stage_date,
                            "input_kg"   : float(s.input_qty),
                            "output_kg"  : float(s.output_qty),
                            "loss_kg"    : float(s.loss_qty),
                            "loss_pct"   : float(s.loss_pct),
                        }
                        for s in b.stages
                    ],
                }
                for b in self.batches
            ],
            "tc_outs"                : [
                {
                    "tc_out"        : t.tc_out_number,
                    "buyer"         : t.buyer_name,
                    "product"       : t.product_name,
                    "allocated_kg"  : float(t.allocated_qty),
                    "allocation_pct": float(t.allocation_pct) if t.allocation_pct else None,
                    "status"        : t.status,
                }
                for t in self.linked_tc_outs
            ],
        }

    def format_report(self) -> str:
        lines = [
            "═" * 68,
            f"  TRACEABILITY REPORT – In TC: {self.tc_in_number}",
            "═" * 68,
            f"  Supplier    : {self.supplier_name}",
            f"  Material    : {self.material_code} – {self.material_name}",
            f"  Standard    : {self.certification_standard}",
            f"  Certified   : {self.certified_qty:.3f} kg",
            f"  Issue Date  : {self.tc_in_issue_date}",
            "─" * 68,
            "",
            "  PRODUCTION FLOW / LUỒNG SẢN XUẤT:",
        ]

        for b in self.batches:
            lines += [
                f"",
                f"  ┌─ Batch: {b.batch_number}  [{b.status}]",
                f"  │  Product: {b.product_name}  |  Order: {b.order_number or 'N/A'}",
                f"  │  Period : {b.start_date} → {b.end_date or 'ongoing'}",
            ]
            for s in b.stages:
                bar = "├" if s != b.stages[-1] else "└"
                lines.append(
                    f"  │  {bar}─ {s.stage.upper():8s}: "
                    f"{s.input_qty:.3f} kg → {s.output_qty:.3f} kg  "
                    f"(loss: {s.loss_qty:.3f} kg = {s.loss_pct:.2f}%)"
                )
            if b.total_loss_kg is not None:
                lines.append(f"  │  TOTAL LOSS: {b.total_loss_kg:.3f} kg ({b.total_loss_pct:.2f}%)")

        lines += [
            "",
            "─" * 68,
            "  LINKED OUT TCs / TC ĐẦU RA LIÊN KẾT:",
        ]
        for t in self.linked_tc_outs:
            lines.append(
                f"  • {t.tc_out_number:25s}  {t.buyer_name:20s}  "
                f"{t.allocated_qty:.3f} kg  [{t.status}]"
            )

        lines += [
            "",
            "─" * 68,
            "  SUMMARY / TÓM TẮT:",
            f"  Certified Quantity      : {self.certified_qty:.3f} kg",
            f"  Issued to Production    : {self.total_issued_to_prod:.3f} kg",
            f"  Produced (finished)     : {self.total_produced:.3f} kg",
            f"  Total Process Loss      : {self.total_process_loss_kg:.3f} kg  "
            f"({self.total_process_loss_pct:.2f}%)",
            f"  Sold with Out TC        : {self.total_sold_with_tc:.3f} kg",
            f"  Remaining in Stock      : {self.remaining_in_stock:.3f} kg",
            f"  Utilization             : {self.utilization_pct:.2f}%",
            f"  Balance OK              : {'YES ✓' if self.is_balanced else 'NO ✗ – OVERCLAIM!'}",
            "═" * 68,
        ]
        if self.alerts:
            lines += ["", "  ALERTS:"]
            for a in self.alerts:
                lines.append(f"  ⚠  {a}")

        return "\n".join(lines)


class TraceabilityReport:
    """
    Tạo báo cáo truy xuất nguồn gốc cho một In TC
    Generate traceability report for a single In TC
    """

    def __init__(self, db: Session, calculator: Optional[MassBalanceCalculator] = None):
        self.db   = db
        self.calc = calculator or MassBalanceCalculator()

    def generate(self, tc_in_id: int) -> TraceabilityResult:
        """
        Tạo báo cáo truy xuất đầy đủ cho In TC
        Generate full traceability report for an In TC

        Raises:
            ValueError: nếu TC không tồn tại
        """
        tc_in = self.db.get(TCIn, tc_in_id)
        if not tc_in:
            raise ValueError(f"In TC id={tc_in_id} không tìm thấy / not found")

        # ── Thu thập dữ liệu ───────────────────────────────────────────────

        batches  = get_batches_for_tc_in(self.db, tc_in_id)
        linkages = get_linkages_for_tc_in(self.db, tc_in_id)

        # ── Tính toán batch details ────────────────────────────────────────

        batch_details = []
        total_issued   = Decimal("0")
        total_produced = Decimal("0")

        for batch in batches:
            # Lấy cutting input = lượng thực tế xuất cho lô này
            cutting_stage = next((s for s in batch.stages if s.stage == "cutting"), None)
            packing_stage = next((s for s in batch.stages if s.stage == "packing"), None)
            sewing_stage  = next((s for s in batch.stages if s.stage == "sewing"),  None)

            batch_input    = cutting_stage.input_quantity   if cutting_stage else (batch.actual_input_qty or Decimal("0"))
            final_output   = (
                packing_stage.output_quantity if packing_stage else
                (sewing_stage.output_quantity if sewing_stage else
                 (cutting_stage.output_quantity if cutting_stage else Decimal("0")))
            )
            batch_loss     = batch_input - final_output
            batch_loss_pct = (batch_loss / batch_input * Decimal("100")) if batch_input > 0 else Decimal("0")

            total_issued   += batch_input
            total_produced += final_output

            stage_details = [
                StageDetail(
                    stage         = s.stage,
                    stage_date    = str(s.stage_date),
                    input_qty     = s.input_quantity,
                    output_qty    = s.output_quantity,
                    loss_qty      = s.loss_quantity,
                    loss_pct      = s.loss_pct,
                    operator_name = s.operator_name,
                    loss_reason   = s.loss_reason,
                )
                for s in sorted(batch.stages, key=lambda x: {"cutting": 0, "sewing": 1, "packing": 2}.get(x.stage, 9))
            ]

            batch_details.append(BatchDetail(
                batch_number   = batch.batch_number,
                product_name   = batch.product_name,
                order_number   = batch.order_number,
                start_date     = str(batch.start_date),
                end_date       = str(batch.end_date) if batch.end_date else None,
                status         = batch.status,
                planned_in     = batch.planned_input_qty,
                actual_in      = batch_input if batch_input > 0 else None,
                actual_out     = final_output if final_output > 0 else None,
                total_loss_kg  = batch_loss  if batch_input > 0 else None,
                total_loss_pct = batch_loss_pct.quantize(Decimal("0.0001")) if batch_input > 0 else None,
                stages         = stage_details,
            ))

        # ── TC Out details ────────────────────────────────────────────────

        linkage_details = []
        total_sold = Decimal("0")

        for link in linkages:
            tc_out = link.tc_out
            if tc_out:
                linkage_details.append(LinkageDetail(
                    tc_out_number  = tc_out.tc_number,
                    issue_date     = str(tc_out.issue_date),
                    buyer_name     = tc_out.buyer.name if tc_out.buyer else "",
                    product_name   = tc_out.product_name,
                    allocated_qty  = link.allocated_quantity,
                    allocation_pct = link.allocation_pct,
                    status         = tc_out.status,
                ))
                if tc_out.status == "issued":
                    total_sold += link.allocated_quantity

        # ── Sử dụng calculator để kiểm tra balance ────────────────────────
        util = self.calc.calculate_tc_utilization(
            tc_in_number       = tc_in.tc_number,
            certified_qty      = tc_in.certified_quantity,
            batches            = [
                {
                    "batch"        : b.batch_number,
                    "qty_issued"   : b.actual_in  or 0,
                    "qty_produced" : b.actual_out or 0,
                }
                for b in batch_details
            ],
            tc_out_allocations = [
                {"tc_out": l.tc_out_number, "qty": l.allocated_qty}
                for l in linkage_details if l.status == "issued"
            ],
        )

        return TraceabilityResult(
            tc_in_number           = tc_in.tc_number,
            tc_in_issue_date       = str(tc_in.issue_date),
            supplier_name          = tc_in.supplier.name if tc_in.supplier else "",
            material_code          = tc_in.material.code if tc_in.material else "",
            material_name          = tc_in.material.name if tc_in.material else "",
            certification_standard = tc_in.certification_standard,
            certified_qty          = tc_in.certified_quantity,
            batches                = batch_details,
            linked_tc_outs         = linkage_details,
            total_issued_to_prod   = util.issued_to_prod,
            total_produced         = util.total_produced,
            total_process_loss_kg  = util.process_loss,
            total_process_loss_pct = util.process_loss_pct,
            total_sold_with_tc     = util.sold_with_tc_out,
            remaining_in_stock     = util.remaining_stock,
            utilization_pct        = util.utilization_pct,
            is_balanced            = util.is_balanced,
            alerts                 = util.alerts,
        )

    def generate_by_number(self, tc_number: str) -> TraceabilityResult:
        """Truy xuất bằng TC number / Look up by TC number"""
        tc = self.db.query(TCIn).filter(TCIn.tc_number == tc_number).first()
        if not tc:
            raise ValueError(f"In TC '{tc_number}' không tìm thấy")
        return self.generate(tc.id)
