"""
Stock Card Report / Thẻ kho
Sổ kho chi tiết theo từng vật liệu hoặc theo In TC
Shows every stock movement with running balance

Tương đương "Stock Card" trong hệ thống ERP dệt may
Equivalent to a "Stock Card" in textile ERP systems
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Material, StockTransaction, TCIn

# Mô tả thân thiện cho từng loại giao dịch / Human-readable transaction labels
TX_LABELS = {
    "tc_in_receipt"  : "Nhập kho từ In TC / Receipt from In TC",
    "issue_cutting"  : "Xuất Cắt / Issue to Cutting",
    "cutting_output" : "Nhập đầu ra Cắt / Cutting output",
    "issue_sewing"   : "Xuất May / Issue to Sewing",
    "sewing_output"  : "Nhập đầu ra May / Sewing output",
    "issue_packing"  : "Xuất Đóng gói / Issue to Packing",
    "packing_output" : "Nhập đầu ra Đóng gói / Packing output",
    "tc_out_sale"    : "Bán với Out TC / Sale with Out TC",
    "normal_sale"    : "Bán thường / Normal sale",
    "adjustment"     : "Điều chỉnh / Adjustment",
    "return_in"      : "Nhận trả hàng / Return in",
    "return_out"     : "Trả hàng NCC / Return to supplier",
}


@dataclass
class StockCardLine:
    """Một dòng trong thẻ kho / One line in the stock card"""
    date             : str
    tx_id            : int
    transaction_type : str
    label            : str
    tc_in_number     : Optional[str]
    tc_out_number    : Optional[str]
    batch_number     : Optional[str]
    reference_number : Optional[str]
    qty_in           : Optional[Decimal]   # Số lượng nhập / Quantity in
    qty_out          : Optional[Decimal]   # Số lượng xuất / Quantity out
    running_balance  : Decimal             # Tồn kho sau giao dịch / Balance after
    notes            : Optional[str]


@dataclass
class StockCardResult:
    """
    Thẻ kho hoàn chỉnh / Complete stock card
    """
    material_code    : str
    material_name    : str
    material_unit    : str
    date_from        : date
    date_to          : date
    tc_in_filter     : Optional[str]   # Lọc theo In TC nếu có

    opening_balance  : Decimal
    closing_balance  : Decimal
    total_in         : Decimal
    total_out        : Decimal

    lines            : List[StockCardLine]

    def to_dict(self) -> dict:
        return {
            "material"        : f"{self.material_code} – {self.material_name}",
            "period"          : f"{self.date_from} → {self.date_to}",
            "tc_in_filter"    : self.tc_in_filter,
            "opening_balance" : float(self.opening_balance),
            "total_in_kg"     : float(self.total_in),
            "total_out_kg"    : float(self.total_out),
            "closing_balance" : float(self.closing_balance),
            "transaction_count": len(self.lines),
            "lines"           : [
                {
                    "date"            : l.date,
                    "type"            : l.transaction_type,
                    "label"           : l.label,
                    "tc_in"           : l.tc_in_number,
                    "tc_out"          : l.tc_out_number,
                    "batch"           : l.batch_number,
                    "ref"             : l.reference_number,
                    "qty_in"          : float(l.qty_in)  if l.qty_in  is not None else None,
                    "qty_out"         : float(l.qty_out) if l.qty_out is not None else None,
                    "running_balance" : float(l.running_balance),
                    "notes"           : l.notes,
                }
                for l in self.lines
            ],
        }

    def format_report(self) -> str:
        """In thẻ kho dạng text / Print text-format stock card"""
        lines = [
            "═" * 100,
            f"  STOCK CARD / THẺ KHO – {self.material_code} – {self.material_name}",
            f"  Period: {self.date_from} → {self.date_to}"
            + (f"  |  TC Filter: {self.tc_in_filter}" if self.tc_in_filter else ""),
            "═" * 100,
            f"  Opening Balance: {self.opening_balance:>12.3f} kg",
            "─" * 100,
            f"  {'Date':12s}  {'Type':20s}  {'Reference':20s}  "
            f"{'In (kg)':>10s}  {'Out (kg)':>10s}  {'Balance':>12s}",
            "─" * 100,
        ]

        for l in self.lines:
            qty_in_str  = f"{l.qty_in:.3f}"  if l.qty_in  is not None else ""
            qty_out_str = f"{l.qty_out:.3f}" if l.qty_out is not None else ""
            ref = l.tc_in_number or l.tc_out_number or l.batch_number or l.reference_number or ""

            lines.append(
                f"  {l.date:12s}  {l.transaction_type:20s}  {ref:20s}  "
                f"{qty_in_str:>10s}  {qty_out_str:>10s}  {l.running_balance:>12.3f}"
            )

        lines += [
            "─" * 100,
            f"  {'':54s}Total In: {self.total_in:>10.3f}  Out: {self.total_out:>10.3f}",
            f"  Closing Balance: {self.closing_balance:>12.3f} kg",
            "═" * 100,
        ]
        return "\n".join(lines)


class StockCardReport:
    """
    Tạo thẻ kho theo vật liệu hoặc In TC
    Generate stock card by material or In TC
    """

    def __init__(self, db: Session):
        self.db = db

    def generate_by_material(
        self,
        material_id : int,
        date_from   : date,
        date_to     : date,
        tc_in_id    : Optional[int] = None,   # Lọc chỉ xem giao dịch của 1 In TC
    ) -> StockCardResult:
        """
        Thẻ kho cho một vật liệu trong kỳ
        Stock card for a material in a period
        """
        material = self.db.get(Material, material_id)
        if not material:
            raise ValueError(f"Material id={material_id} không tìm thấy")

        # Opening balance = tổng TX trước date_from
        from sqlalchemy import func
        opening = (
            self.db.query(func.sum(StockTransaction.quantity))
            .filter(
                StockTransaction.material_id    == material_id,
                StockTransaction.quantity_type  == "certified",
                StockTransaction.transaction_date < date_from,
            )
            .scalar()
        ) or Decimal("0")

        # Các giao dịch trong kỳ
        q = (
            self.db.query(StockTransaction)
            .filter(
                StockTransaction.material_id    == material_id,
                StockTransaction.quantity_type  == "certified",
                StockTransaction.transaction_date >= date_from,
                StockTransaction.transaction_date <= date_to,
            )
            .order_by(StockTransaction.transaction_date, StockTransaction.created_at)
        )
        if tc_in_id:
            q = q.filter(StockTransaction.tc_in_id == tc_in_id)

        transactions = q.all()

        # Xây dựng thẻ kho với running balance
        lines        = []
        balance      = opening
        total_in     = Decimal("0")
        total_out    = Decimal("0")

        for tx in transactions:
            if tx.quantity > 0:
                qty_in  = tx.quantity
                qty_out = None
                total_in += tx.quantity
            else:
                qty_in  = None
                qty_out = abs(tx.quantity)
                total_out += abs(tx.quantity)

            balance += tx.quantity

            # Lấy số reference
            tc_in_num  = tx.tc_in.tc_number  if tx.tc_in  else None
            tc_out_num = tx.tc_out.tc_number if tx.tc_out else None
            batch_num  = tx.batch.batch_number if tx.batch else None

            lines.append(StockCardLine(
                date             = str(tx.transaction_date),
                tx_id            = tx.id,
                transaction_type = tx.transaction_type,
                label            = TX_LABELS.get(tx.transaction_type, tx.transaction_type),
                tc_in_number     = tc_in_num,
                tc_out_number    = tc_out_num,
                batch_number     = batch_num,
                reference_number = tx.reference_number,
                qty_in           = qty_in,
                qty_out          = qty_out,
                running_balance  = balance,
                notes            = tx.notes,
            ))

        tc_in_number = None
        if tc_in_id:
            tc = self.db.get(TCIn, tc_in_id)
            tc_in_number = tc.tc_number if tc else None

        return StockCardResult(
            material_code   = material.code,
            material_name   = material.name,
            material_unit   = material.unit,
            date_from       = date_from,
            date_to         = date_to,
            tc_in_filter    = tc_in_number,
            opening_balance = opening,
            closing_balance = balance,
            total_in        = total_in,
            total_out       = total_out,
            lines           = lines,
        )

    def generate_by_tc_in(self, tc_in_id: int) -> StockCardResult:
        """
        Thẻ kho lọc theo 1 In TC (từ ngày nhận đến hiện tại)
        Stock card filtered by 1 In TC (from receipt date to today)
        """
        tc = self.db.get(TCIn, tc_in_id)
        if not tc:
            raise ValueError(f"In TC id={tc_in_id} không tìm thấy")

        start_date = tc.received_date or tc.issue_date
        end_date   = date.today()

        return self.generate_by_material(
            material_id = tc.material_id,
            date_from   = start_date,
            date_to     = end_date,
            tc_in_id    = tc_in_id,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Summary Maintain Stock / Tóm tắt tồn kho
# Tương đương sheet "Summary" trong file Excel mẫu
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StockSummaryRow:
    material_code      : str
    material_name      : str
    certification_std  : str
    opening_stock      : Decimal
    received_kg        : Decimal    # Nhập từ In TC
    issued_production  : Decimal    # Xuất sản xuất
    sold_kg            : Decimal    # Xuất bán Out TC
    closing_stock      : Decimal    # Tồn cuối kỳ
    tc_in_count        : int
    tc_out_count       : int
    status             : str        # "OK" hoặc "NEGATIVE STOCK"


class StockSummaryReport:
    """
    Summary Maintain Stock – tóm tắt tồn kho tất cả vật liệu cuối kỳ
    Equivalent to "Summary" sheet in GRS/GOTS Mass Balance workbooks
    """

    def __init__(self, db: Session):
        self.db = db

    def generate(
        self,
        period_start : date,
        period_end   : date,
    ) -> List[StockSummaryRow]:
        """Tạo bảng tóm tắt tồn kho cuối kỳ / Generate end-of-period stock summary"""
        from sqlalchemy import func
        from app.models import TCIn as TCInModel, TCOut as TCOutModel

        materials = self.db.query(Material).filter(Material.is_active == True).all()
        rows = []

        for mat in materials:
            # Opening: tổng TX trước period_start
            opening = (
                self.db.query(func.sum(StockTransaction.quantity))
                .filter(
                    StockTransaction.material_id    == mat.id,
                    StockTransaction.quantity_type  == "certified",
                    StockTransaction.transaction_date < period_start,
                )
                .scalar()
            ) or Decimal("0")

            # Nhập từ In TC trong kỳ / Received from In TC in period
            received = (
                self.db.query(func.sum(StockTransaction.quantity))
                .filter(
                    StockTransaction.material_id    == mat.id,
                    StockTransaction.quantity_type  == "certified",
                    StockTransaction.transaction_type == "tc_in_receipt",
                    StockTransaction.transaction_date >= period_start,
                    StockTransaction.transaction_date <= period_end,
                )
                .scalar()
            ) or Decimal("0")

            # Xuất sản xuất / Issued to production
            issued = abs(
                self.db.query(func.sum(StockTransaction.quantity))
                .filter(
                    StockTransaction.material_id    == mat.id,
                    StockTransaction.quantity_type  == "certified",
                    StockTransaction.transaction_type == "issue_cutting",
                    StockTransaction.transaction_date >= period_start,
                    StockTransaction.transaction_date <= period_end,
                )
                .scalar() or Decimal("0")
            )

            # Bán với Out TC / Sold with Out TC
            sold = abs(
                self.db.query(func.sum(StockTransaction.quantity))
                .filter(
                    StockTransaction.material_id    == mat.id,
                    StockTransaction.quantity_type  == "certified",
                    StockTransaction.transaction_type == "tc_out_sale",
                    StockTransaction.transaction_date >= period_start,
                    StockTransaction.transaction_date <= period_end,
                )
                .scalar() or Decimal("0")
            )

            # Closing = opening + received - issued - sold (+ adjustments)
            closing = (
                self.db.query(func.sum(StockTransaction.quantity))
                .filter(
                    StockTransaction.material_id    == mat.id,
                    StockTransaction.quantity_type  == "certified",
                    StockTransaction.transaction_date <= period_end,
                )
                .scalar()
            ) or Decimal("0")

            if received == 0 and closing == 0:
                continue   # Bỏ qua vật liệu không có hoạt động

            # Đếm số lượng TC
            tc_in_count = (
                self.db.query(func.count(TCInModel.id))
                .filter(
                    TCInModel.material_id == mat.id,
                    TCInModel.status      != "cancelled",
                    func.coalesce(TCInModel.received_date, TCInModel.issue_date) >= period_start,
                    func.coalesce(TCInModel.received_date, TCInModel.issue_date) <= period_end,
                )
                .scalar() or 0
            )

            rows.append(StockSummaryRow(
                material_code     = mat.code,
                material_name     = mat.name,
                certification_std = "",   # Could join to tc_in for standard
                opening_stock     = opening,
                received_kg       = received,
                issued_production = issued,
                sold_kg           = sold,
                closing_stock     = closing,
                tc_in_count       = tc_in_count,
                tc_out_count      = 0,
                status            = "OK" if closing >= 0 else "NEGATIVE STOCK",
            ))

        return sorted(rows, key=lambda r: r.material_code)
