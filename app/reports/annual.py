"""
Annual Mass Balance Report / Báo cáo Mass Balance năm
Tương đương sheet "Xuat nhap Ton" trong file Excel mẫu
Equivalent to "Xuat nhap Ton" sheet in the sample Excel file

Output: MassBalanceResult + lưu vào bảng mass_balance_periods
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.mass_balance import MassBalanceCalculator, MassBalanceResult
from app.models import MassBalancePeriod, Material
from app.reports.queries import (
    get_closing_balance, get_opening_balance,
    get_stage_totals_for_period, get_tc_in_for_period, get_tc_out_for_period,
)


class AnnualMassBalanceReport:
    """
    Tạo báo cáo Mass Balance cho một kỳ (tháng/quý/năm)
    Generate Mass Balance report for any period (monthly/quarterly/annually)

    Có thể chạy cho:
    • Toàn bộ vật liệu (material_id=None)
    • Một loại vật liệu cụ thể (material_id=X)
    • Một tiêu chuẩn cụ thể (GRS / GOTS / RCS / OCS)
    """

    def __init__(self, db: Session, calculator: Optional[MassBalanceCalculator] = None):
        self.db   = db
        self.calc = calculator or MassBalanceCalculator()

    # ─────────────────────────────────────────────────────────────────────────
    # Main entry point
    # ─────────────────────────────────────────────────────────────────────────

    def generate(
        self,
        period_start           : date,
        period_end             : date,
        certification_standard : str,
        material_id            : Optional[int]  = None,
        save_to_db             : bool           = True,
        user_id                : Optional[int]  = None,
    ) -> MassBalanceResult:
        """
        Tính Mass Balance cho kỳ chỉ định
        Calculate Mass Balance for the specified period

        Args:
            period_start:           Ngày bắt đầu kỳ
            period_end:             Ngày kết thúc kỳ
            certification_standard: "GRS" | "GOTS" | "RCS" | "OCS"
            material_id:            None = tất cả vật liệu / specific material ID
            save_to_db:             Lưu kết quả vào bảng mass_balance_periods
            user_id:                User thực hiện tính toán
        """
        # Lấy thông tin vật liệu nếu có
        material_code = material_name = None
        if material_id:
            mat = self.db.get(Material, material_id)
            if mat:
                material_code = mat.code
                material_name = mat.name

        # ── Bước 1: Opening balance ────────────────────────────────────────
        # Tồn kho ngày cuối của kỳ trước (= tổng tất cả TX trước period_start)
        opening_stock = get_opening_balance(self.db, material_id or 0, period_start) \
                        if material_id else self._get_opening_all_materials(period_start)

        # ── Bước 2: In TCs trong kỳ ───────────────────────────────────────
        tc_ins         = get_tc_in_for_period(self.db, period_start, period_end,
                                              certification_standard, material_id)
        certified_purchased = sum(tc.certified_quantity for tc in tc_ins)
        number_tc_in        = len(tc_ins)

        # ── Bước 3: Production stages trong kỳ ──────────────────────────
        stage_totals = get_stage_totals_for_period(
            self.db, period_start, period_end, material_id
        )

        cutting_data = stage_totals.get("cutting")
        sewing_data  = stage_totals.get("sewing")
        packing_data = stage_totals.get("packing")

        # ── Bước 4: Out TCs trong kỳ ─────────────────────────────────────
        tc_outs         = get_tc_out_for_period(self.db, period_start, period_end,
                                                certification_standard)
        certified_sold  = sum(tc.certified_quantity for tc in tc_outs)
        number_tc_out   = len(tc_outs)

        # ── Bước 5: Closing balance (from stock transactions) ─────────────
        if material_id:
            closing_raw = get_closing_balance(self.db, material_id, period_end)
            closing_fg  = Decimal("0")  # Single material → all in one balance
        else:
            closing_raw = self._get_closing_all_materials(period_end)
            closing_fg  = Decimal("0")

        # ── Bước 6: Tính Mass Balance ─────────────────────────────────────
        result = self.calc.calculate(
            period_start           = period_start,
            period_end             = period_end,
            certification_standard = certification_standard,
            material_code          = material_code,
            material_name          = material_name,
            opening_stock          = opening_stock,
            certified_purchased    = certified_purchased,
            number_tc_in           = number_tc_in,
            cutting_data           = cutting_data,
            sewing_data            = sewing_data,
            packing_data           = packing_data,
            certified_sold         = certified_sold,
            number_tc_out          = number_tc_out,
            closing_stock_raw      = closing_raw,
            closing_stock_fg       = closing_fg,
            # Truyền chi tiết từng TC để hiển thị trong báo cáo
            tc_in_details  = [self._tc_in_to_dict(t)  for t in tc_ins],
            tc_out_details = [self._tc_out_to_dict(t) for t in tc_outs],
        )

        # ── Bước 7: Lưu vào DB ───────────────────────────────────────────
        if save_to_db:
            self._save_to_db(result, material_id, user_id)

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Monthly breakdown / Phân tích theo tháng
    # ─────────────────────────────────────────────────────────────────────────

    def generate_monthly_breakdown(
        self,
        year                   : int,
        certification_standard : str,
        material_id            : Optional[int] = None,
        save_to_db             : bool          = False,
    ) -> List[dict]:
        """
        Tạo bảng Mass Balance theo từng tháng trong năm
        Generate monthly Mass Balance table for a full year

        Trả về list 12 dòng (hoặc ít hơn nếu chưa đến cuối năm)
        Returns list of 12 rows (or fewer if the year is not complete yet)
        """
        from calendar import monthrange
        rows = []

        prev_closing = Decimal("0")   # Tồn đầu tháng 1 = tồn cuối năm trước

        for month in range(1, 13):
            m_start = date(year, month, 1)
            m_end   = date(year, month, monthrange(year, month)[1])

            if m_start > date.today():
                break    # Chưa đến tháng này

            try:
                result = self.generate(
                    period_start           = m_start,
                    period_end             = m_end,
                    certification_standard = certification_standard,
                    material_id            = material_id,
                    save_to_db             = save_to_db,
                )
                row = result.to_dict()
                row["month"] = month
                row["month_name"] = m_start.strftime("%b %Y")
                rows.append(row)
                prev_closing = result.closing_stock_total

            except Exception as e:
                rows.append({
                    "month": month,
                    "month_name": m_start.strftime("%b %Y"),
                    "error": str(e),
                })

        return rows

    def generate_annual(
        self,
        year                   : int,
        certification_standard : str,
        material_id            : Optional[int] = None,
        save_to_db             : bool          = True,
        user_id                : Optional[int] = None,
    ) -> MassBalanceResult:
        """
        Tạo báo cáo Mass Balance cả năm (aggregate 12 tháng)
        Generate full-year Mass Balance (aggregates 12 months)
        """
        period_start = date(year, 1, 1)
        period_end   = date(year, 12, 31)
        return self.generate(period_start, period_end, certification_standard,
                             material_id, save_to_db, user_id)

    # ─────────────────────────────────────────────────────────────────────────
    # History / Lịch sử các kỳ đã tính
    # ─────────────────────────────────────────────────────────────────────────

    def get_history(
        self,
        certification_standard : Optional[str] = None,
        material_id            : Optional[int] = None,
        limit                  : int           = 20,
    ) -> List[MassBalancePeriod]:
        """Lấy lịch sử các kỳ đã tính / Get history of calculated periods"""
        q = self.db.query(MassBalancePeriod)
        if certification_standard:
            q = q.filter(MassBalancePeriod.certification_standard == certification_standard)
        if material_id is not None:
            q = q.filter(MassBalancePeriod.material_id == material_id)
        return q.order_by(MassBalancePeriod.period_end.desc()).limit(limit).all()

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _get_opening_all_materials(self, before_date: date) -> Decimal:
        """Tổng tồn kho tất cả vật liệu trước ngày / Total stock all materials before date"""
        from sqlalchemy import func
        from app.models import StockTransaction
        result = (
            self.db.query(func.sum(StockTransaction.quantity))
            .filter(
                StockTransaction.quantity_type    == "certified",
                StockTransaction.transaction_date <  before_date,
            )
            .scalar()
        )
        return result or Decimal("0")

    def _get_closing_all_materials(self, as_of_date: date) -> Decimal:
        """Tổng tồn kho tất cả vật liệu đến ngày / Total stock all materials as of date"""
        from sqlalchemy import func
        from app.models import StockTransaction
        result = (
            self.db.query(func.sum(StockTransaction.quantity))
            .filter(
                StockTransaction.quantity_type    == "certified",
                StockTransaction.transaction_date <= as_of_date,
            )
            .scalar()
        )
        return result or Decimal("0")

    def _save_to_db(
        self,
        result      : MassBalanceResult,
        material_id : Optional[int],
        user_id     : Optional[int],
    ) -> MassBalancePeriod:
        """Lưu hoặc cập nhật kết quả Mass Balance vào DB / Save or update MB result to DB"""
        from datetime import datetime

        # Tìm bản ghi đã có (upsert)
        existing = (
            self.db.query(MassBalancePeriod)
            .filter(
                MassBalancePeriod.period_start           == result.period_start,
                MassBalancePeriod.period_end             == result.period_end,
                MassBalancePeriod.certification_standard == result.certification_standard,
                MassBalancePeriod.material_id            == material_id,
            )
            .first()
        )

        data = dict(
            certified_purchased    = result.certified_purchased,
            number_of_tc_in        = result.number_tc_in,
            opening_stock_raw      = result.opening_stock,
            issued_to_production   = result.issued_to_production,

            cutting_input          = result.cutting.input_qty   if result.cutting  else Decimal("0"),
            cutting_output         = result.cutting.output_qty  if result.cutting  else Decimal("0"),
            cutting_loss           = result.cutting.loss_qty    if result.cutting  else Decimal("0"),
            cutting_loss_pct       = result.cutting.loss_pct    if result.cutting  else Decimal("0"),

            sewing_input           = result.sewing.input_qty    if result.sewing   else Decimal("0"),
            sewing_output          = result.sewing.output_qty   if result.sewing   else Decimal("0"),
            sewing_loss            = result.sewing.loss_qty     if result.sewing   else Decimal("0"),
            sewing_loss_pct        = result.sewing.loss_pct     if result.sewing   else Decimal("0"),

            packing_input          = result.packing.input_qty   if result.packing  else Decimal("0"),
            packing_output         = result.packing.output_qty  if result.packing  else Decimal("0"),
            packing_loss           = result.packing.loss_qty    if result.packing  else Decimal("0"),
            packing_loss_pct       = result.packing.loss_pct    if result.packing  else Decimal("0"),

            total_process_loss     = result.total_process_loss,
            total_loss_pct         = result.total_loss_pct,

            certified_produced     = result.certified_produced,
            certified_sold         = result.certified_sold,
            number_of_tc_out       = result.number_tc_out,

            closing_stock_raw      = result.closing_stock_raw,
            closing_stock_fg       = result.closing_stock_fg,
            closing_stock_total    = result.closing_stock_total,

            theoretical_closing    = result.theoretical_closing,
            difference             = result.difference,
            difference_pct         = result.difference_pct,
            balance_status         = result.balance_status,

            calculated_at          = datetime.now(),
            calculated_by          = user_id,
        )

        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            mb = existing
        else:
            mb = MassBalancePeriod(
                period_start           = result.period_start,
                period_end             = result.period_end,
                certification_standard = result.certification_standard,
                material_id            = material_id,
                **data,
            )
            self.db.add(mb)

        self.db.flush()
        return mb

    @staticmethod
    def _tc_in_to_dict(tc: "TCIn") -> dict:
        return {
            "tc_number"    : tc.tc_number,
            "issue_date"   : str(tc.issue_date),
            "supplier"     : tc.supplier.name if tc.supplier else "",
            "quantity_kg"  : float(tc.certified_quantity),
            "standard"     : tc.certification_standard,
        }

    @staticmethod
    def _tc_out_to_dict(tc: "TCOut") -> dict:
        return {
            "tc_number"    : tc.tc_number,
            "issue_date"   : str(tc.issue_date),
            "buyer"        : tc.buyer.name if tc.buyer else "",
            "quantity_kg"  : float(tc.certified_quantity),
            "product"      : tc.product_name,
        }
