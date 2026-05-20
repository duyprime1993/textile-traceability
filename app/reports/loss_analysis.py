"""
Loss Analysis Report / Báo cáo phân tích hao hụt
Phân tích hao hụt theo công đoạn, lô sản xuất, và kỳ thời gian

Trả lời các câu hỏi:
  • Hao hụt cắt tháng này so với tháng trước thế nào?
  • Lô nào có hao hụt cao nhất?
  • Xu hướng hao hụt theo thời gian?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import ProductionBatch, ProductionStage, StageType


@dataclass
class StageLossSummary:
    """Tổng hợp hao hụt một công đoạn / Summary for one stage type"""
    stage          : str
    total_input_kg : Decimal
    total_output_kg: Decimal
    total_loss_kg  : Decimal
    avg_loss_pct   : Decimal
    min_loss_pct   : Decimal
    max_loss_pct   : Decimal
    num_batches    : int
    # Cảnh báo nếu trung bình vượt ngưỡng / Alert if avg exceeds threshold
    above_threshold: bool
    threshold_pct  : Decimal


@dataclass
class BatchLossRow:
    """Một dòng trong bảng hao hụt theo lô / One row in batch loss table"""
    batch_number     : str
    product_name     : str
    order_number     : Optional[str]
    tc_in_number     : Optional[str]
    start_date       : str
    end_date         : Optional[str]
    total_input_kg   : Decimal
    total_output_kg  : Decimal
    total_loss_kg    : Decimal
    total_loss_pct   : Decimal
    cutting_loss_pct : Optional[Decimal]
    sewing_loss_pct  : Optional[Decimal]
    packing_loss_pct : Optional[Decimal]
    status           : str


@dataclass
class MonthlyTrend:
    """Xu hướng hao hụt theo tháng / Monthly loss trend"""
    year_month       : str      # "2024-01"
    total_input_kg   : Decimal
    total_output_kg  : Decimal
    total_loss_kg    : Decimal
    avg_loss_pct     : Decimal
    cutting_loss_pct : Decimal
    sewing_loss_pct  : Decimal
    packing_loss_pct : Decimal
    num_batches      : int


@dataclass
class LossAnalysisResult:
    """
    Kết quả phân tích hao hụt đầy đủ
    Complete loss analysis result
    """
    period_start    : date
    period_end      : date

    # Tổng quan / Overview
    stage_summaries : List[StageLossSummary]
    batch_rows      : List[BatchLossRow]
    monthly_trend   : List[MonthlyTrend]

    # Lô có hao hụt cao nhất / Top loss batches
    top_loss_batches: List[BatchLossRow]   # top 10 by loss_pct

    def to_dict(self) -> dict:
        return {
            "period"          : f"{self.period_start} → {self.period_end}",
            "stage_summaries" : [
                {
                    "stage"            : s.stage,
                    "total_input_kg"   : float(s.total_input_kg),
                    "total_output_kg"  : float(s.total_output_kg),
                    "total_loss_kg"    : float(s.total_loss_kg),
                    "avg_loss_pct"     : float(s.avg_loss_pct),
                    "min_loss_pct"     : float(s.min_loss_pct),
                    "max_loss_pct"     : float(s.max_loss_pct),
                    "above_threshold"  : s.above_threshold,
                }
                for s in self.stage_summaries
            ],
            "batch_count"     : len(self.batch_rows),
            "top_loss_batches": [
                {
                    "batch"          : b.batch_number,
                    "product"        : b.product_name,
                    "total_loss_kg"  : float(b.total_loss_kg),
                    "total_loss_pct" : float(b.total_loss_pct),
                }
                for b in self.top_loss_batches
            ],
            "monthly_trend"   : [
                {
                    "month"          : m.year_month,
                    "total_input_kg" : float(m.total_input_kg),
                    "total_loss_kg"  : float(m.total_loss_kg),
                    "avg_loss_pct"   : float(m.avg_loss_pct),
                }
                for m in self.monthly_trend
            ],
        }


# Ngưỡng cảnh báo / Alert thresholds (có thể override qua settings)
THRESHOLDS = {
    "cutting": Decimal("15.0"),
    "sewing" : Decimal("10.0"),
    "packing": Decimal("5.0"),
}


class LossAnalysisReport:
    """
    Phân tích hao hụt theo nhiều chiều
    Multi-dimensional loss analysis
    """

    def __init__(self, db: Session):
        self.db = db

    def generate(
        self,
        period_start : date,
        period_end   : date,
        material_id  : Optional[int] = None,
        tc_in_id     : Optional[int] = None,
    ) -> LossAnalysisResult:
        """
        Tạo báo cáo phân tích hao hụt đầy đủ
        Generate complete loss analysis report
        """
        stage_summaries = self._calc_stage_summaries(period_start, period_end, material_id)
        batch_rows      = self._calc_batch_rows(period_start, period_end, material_id, tc_in_id)
        monthly_trend   = self._calc_monthly_trend(period_start, period_end, material_id)
        top_loss        = sorted(batch_rows, key=lambda b: b.total_loss_pct, reverse=True)[:10]

        return LossAnalysisResult(
            period_start     = period_start,
            period_end       = period_end,
            stage_summaries  = stage_summaries,
            batch_rows       = batch_rows,
            monthly_trend    = monthly_trend,
            top_loss_batches = top_loss,
        )

    # ── Stage summary / Tổng hợp theo công đoạn ──────────────────────────

    def _calc_stage_summaries(
        self,
        period_start : date,
        period_end   : date,
        material_id  : Optional[int],
    ) -> List[StageLossSummary]:
        """Tổng hợp input/output/loss cho từng loại công đoạn"""

        q = (
            self.db.query(
                ProductionStage.stage,
                func.sum(ProductionStage.input_quantity).label("total_in"),
                func.sum(ProductionStage.output_quantity).label("total_out"),
                func.count(ProductionStage.id).label("num_batches"),
            )
            .join(ProductionStage.batch)
            .filter(
                ProductionStage.stage_date >= period_start,
                ProductionStage.stage_date <= period_end,
            )
            .group_by(ProductionStage.stage)
        )

        if material_id:
            q = q.filter(
                ProductionBatch.tc_in_id.in_(
                    self.db.query(ProductionBatch.tc_in_id).filter(
                        ProductionBatch.tc_in_id.isnot(None)
                    )
                )
            )

        summaries = []
        for row in q.all():
            total_in  = row.total_in  or Decimal("0")
            total_out = row.total_out or Decimal("0")
            total_loss = total_in - total_out
            avg_pct    = (total_loss / total_in * Decimal("100")) if total_in > 0 else Decimal("0")

            # Min/Max từ từng lô
            stage_stages = (
                self.db.query(ProductionStage)
                .join(ProductionStage.batch)
                .filter(
                    ProductionStage.stage      == row.stage,
                    ProductionStage.stage_date >= period_start,
                    ProductionStage.stage_date <= period_end,
                )
                .all()
            )
            loss_pcts = [s.loss_pct for s in stage_stages if s.input_quantity > 0]
            min_pct   = min(loss_pcts) if loss_pcts else Decimal("0")
            max_pct   = max(loss_pcts) if loss_pcts else Decimal("0")
            threshold = THRESHOLDS.get(row.stage, Decimal("20"))

            summaries.append(StageLossSummary(
                stage           = row.stage,
                total_input_kg  = total_in,
                total_output_kg = total_out,
                total_loss_kg   = total_loss,
                avg_loss_pct    = avg_pct.quantize(Decimal("0.0001")),
                min_loss_pct    = min_pct,
                max_loss_pct    = max_pct,
                num_batches     = row.num_batches,
                above_threshold = avg_pct > threshold,
                threshold_pct   = threshold,
            ))

        # Sắp xếp đúng thứ tự công đoạn / Sort by stage order
        order = {"cutting": 0, "sewing": 1, "packing": 2}
        summaries.sort(key=lambda s: order.get(s.stage, 9))
        return summaries

    # ── Batch-level table / Bảng theo lô ────────────────────────────────

    def _calc_batch_rows(
        self,
        period_start : date,
        period_end   : date,
        material_id  : Optional[int],
        tc_in_id     : Optional[int],
    ) -> List[BatchLossRow]:
        """Chi tiết hao hụt theo từng lô / Detailed loss per batch"""

        q = (
            self.db.query(ProductionBatch)
            .filter(
                ProductionBatch.start_date >= period_start,
                ProductionBatch.start_date <= period_end,
            )
        )
        if tc_in_id:
            q = q.filter(ProductionBatch.tc_in_id == tc_in_id)

        rows = []
        for batch in q.all():
            # Lấy từng stage / Get each stage
            stage_map = {s.stage: s for s in batch.stages}
            cutting = stage_map.get("cutting")
            sewing  = stage_map.get("sewing")
            packing = stage_map.get("packing")

            total_in  = cutting.input_quantity  if cutting else Decimal("0")
            final_out = (
                packing.output_quantity if packing else
                (sewing.output_quantity if sewing else
                 (cutting.output_quantity if cutting else Decimal("0")))
            )
            total_loss     = total_in - final_out
            total_loss_pct = (total_loss / total_in * Decimal("100")).quantize(Decimal("0.0001")) \
                             if total_in > 0 else Decimal("0")

            rows.append(BatchLossRow(
                batch_number     = batch.batch_number,
                product_name     = batch.product_name,
                order_number     = batch.order_number,
                tc_in_number     = batch.tc_in.tc_number if batch.tc_in else None,
                start_date       = str(batch.start_date),
                end_date         = str(batch.end_date) if batch.end_date else None,
                total_input_kg   = total_in,
                total_output_kg  = final_out,
                total_loss_kg    = total_loss,
                total_loss_pct   = total_loss_pct,
                cutting_loss_pct = cutting.loss_pct if cutting else None,
                sewing_loss_pct  = sewing.loss_pct  if sewing  else None,
                packing_loss_pct = packing.loss_pct if packing else None,
                status           = batch.status,
            ))

        return sorted(rows, key=lambda r: r.start_date)

    # ── Monthly trend / Xu hướng tháng ──────────────────────────────────

    def _calc_monthly_trend(
        self,
        period_start : date,
        period_end   : date,
        material_id  : Optional[int],
    ) -> List[MonthlyTrend]:
        """Xu hướng hao hụt theo tháng / Monthly loss trend"""
        from calendar import monthrange

        trends = []
        current = date(period_start.year, period_start.month, 1)

        while current <= period_end:
            m_end = date(current.year, current.month,
                         monthrange(current.year, current.month)[1])
            m_end = min(m_end, period_end)

            # Lấy tổng theo từng stage trong tháng
            stage_rows = (
                self.db.query(
                    ProductionStage.stage,
                    func.sum(ProductionStage.input_quantity).label("qty_in"),
                    func.sum(ProductionStage.output_quantity).label("qty_out"),
                )
                .join(ProductionStage.batch)
                .filter(
                    ProductionStage.stage_date >= current,
                    ProductionStage.stage_date <= m_end,
                )
                .group_by(ProductionStage.stage)
                .all()
            )

            stage_map_monthly = {r.stage: (r.qty_in or Decimal("0"), r.qty_out or Decimal("0"))
                                 for r in stage_rows}

            cut_in,  cut_out  = stage_map_monthly.get("cutting", (Decimal("0"), Decimal("0")))
            sew_in,  sew_out  = stage_map_monthly.get("sewing",  (Decimal("0"), Decimal("0")))
            pack_in, pack_out = stage_map_monthly.get("packing", (Decimal("0"), Decimal("0")))

            total_in  = cut_in
            total_out = pack_out if pack_out > 0 else (sew_out if sew_out > 0 else cut_out)
            total_loss = total_in - total_out
            avg_pct    = (total_loss / total_in * Decimal("100")).quantize(Decimal("0.0001")) \
                         if total_in > 0 else Decimal("0")

            def pct(loss_val, in_val):
                return (loss_val / in_val * Decimal("100")).quantize(Decimal("0.0001")) \
                       if in_val > 0 else Decimal("0")

            num_batches = (
                self.db.query(func.count(ProductionBatch.id))
                .filter(
                    ProductionBatch.start_date >= current,
                    ProductionBatch.start_date <= m_end,
                )
                .scalar() or 0
            )

            trends.append(MonthlyTrend(
                year_month       = current.strftime("%Y-%m"),
                total_input_kg   = total_in,
                total_output_kg  = total_out,
                total_loss_kg    = total_loss,
                avg_loss_pct     = avg_pct,
                cutting_loss_pct = pct(cut_in - cut_out,   cut_in),
                sewing_loss_pct  = pct(sew_in - sew_out,   sew_in),
                packing_loss_pct = pct(pack_in - pack_out, pack_in),
                num_batches      = num_batches,
            ))

            # Next month
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)

        return trends
