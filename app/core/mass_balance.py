"""
╔══════════════════════════════════════════════════════════════════════════════╗
║   MASS BALANCE CALCULATION ENGINE                                            ║
║   Engine tính toán Mass Balance theo chuẩn GRS 4.0 / GOTS 6.0              ║
║                                                                              ║
║   Các class chính / Core classes:                                            ║
║     StageResult         – kết quả 1 công đoạn (cắt/may/đóng gói)           ║
║     MassBalanceResult   – kết quả đầy đủ 1 kỳ kiểm toán                   ║
║     MassBalanceCalculator – engine tính toán, pure functions, testable      ║
║     TCUtilizationResult – truy xuất nguồn gốc theo In TC                   ║
║                                                                              ║
║   Công thức chuẩn / Standard formula (Textile Exchange):                    ║
║     Opening Stock                                                            ║
║     + Certified Purchased (∑ In TC)                                         ║
║     ─────────────────────────────────                                        ║
║     = Total Available                                                        ║
║     − Issued to Production                                                   ║
║       ├─ Cutting Loss                                                        ║
║       ├─ Sewing  Loss                                                        ║
║       └─ Packing Loss                                                        ║
║     = Certified Produced                                                     ║
║     − Certified Sold (∑ Out TC)                                             ║
║     ─────────────────────────────────                                        ║
║     = Closing Stock (theoretical)                                            ║
║                                                                              ║
║     Difference = Actual Closing − Theoretical Closing                       ║
║     PASS    : |Diff| ≤ 0.5% of Total Available                              ║
║     WARNING : 0.5% < |Diff| ≤ 2.0%                                         ║
║     FAIL    : |Diff| > 2.0%                                                 ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Constants / Hằng số ngưỡng kiểm toán
# ─────────────────────────────────────────────────────────────────────────────

# Ngưỡng chênh lệch theo GRS 4.0 Section 5.3.2
# Balance tolerance thresholds per GRS 4.0 Section 5.3.2
PASS_THRESHOLD_PCT    = Decimal("0.50")   # ≤ 0.5%  → PASS
WARNING_THRESHOLD_PCT = Decimal("2.00")   # ≤ 2.0%  → WARNING (> 2% → FAIL)

# Ngưỡng cảnh báo hao hụt theo công đoạn (thông lệ ngành / industry norms)
CUTTING_LOSS_ALERT_PCT = Decimal("15.0")  # Cắt > 15% là bất thường
SEWING_LOSS_ALERT_PCT  = Decimal("10.0")  # May > 10% là bất thường
PACKING_LOSS_ALERT_PCT = Decimal("5.0")   # Đóng gói > 5% là bất thường
TOTAL_LOSS_ALERT_PCT   = Decimal("20.0")  # Tổng > 20% yêu cầu giải trình

# Độ chính xác số kg / kg precision
KG_DECIMAL_PLACES  = 3    # 0.001 kg
PCT_DECIMAL_PLACES = 4    # 0.0001%


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes / Cấu trúc dữ liệu kết quả
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StageResult:
    """
    Kết quả tính toán của một công đoạn sản xuất
    Calculation result for a single production stage
    """
    stage       : str      # "cutting" | "sewing" | "packing"
    input_qty   : Decimal  # kg đầu vào công đoạn / kg input to stage
    output_qty  : Decimal  # kg đầu ra công đoạn / kg output from stage
    loss_qty    : Decimal  # kg hao hụt / loss in kg
    loss_pct    : Decimal  # % hao hụt / loss percentage
    yield_pct   : Decimal  # % sản lượng = 100 − loss_pct / yield = 100 − loss%

    def to_dict(self) -> dict:
        return {
            "stage"      : self.stage,
            "input_kg"   : float(self.input_qty),
            "output_kg"  : float(self.output_qty),
            "loss_kg"    : float(self.loss_qty),
            "loss_pct"   : float(self.loss_pct),
            "yield_pct"  : float(self.yield_pct),
        }


@dataclass
class MassBalanceResult:
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Kết quả Mass Balance đầy đủ theo chuẩn GRS/GOTS                       │
    │  Complete Mass Balance result – GRS/GOTS audit-ready                    │
    │                                                                          │
    │  Có thể xuất thẳng ra báo cáo kiểm toán / Ready for audit reporting     │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    # ── Metadata ──────────────────────────────────────────────────────────────
    period_start           : date
    period_end             : date
    certification_standard : str
    material_code          : Optional[str] = None
    material_name          : Optional[str] = None

    # ── Section 1: Opening Balance / Số dư đầu kỳ ────────────────────────────
    opening_stock          : Decimal = field(default=Decimal("0"))

    # ── Section 2: Inputs / Đầu vào ──────────────────────────────────────────
    certified_purchased    : Decimal = field(default=Decimal("0"))   # ∑ In TC
    number_tc_in           : int     = 0
    total_available        : Decimal = field(default=Decimal("0"))   # = opening + purchased

    # ── Section 3: Production / Sản xuất ─────────────────────────────────────
    issued_to_production   : Decimal = field(default=Decimal("0"))   # Kg xuất sản xuất

    cutting  : Optional[StageResult] = None
    sewing   : Optional[StageResult] = None
    packing  : Optional[StageResult] = None

    total_process_loss     : Decimal = field(default=Decimal("0"))   # ∑ tất cả hao hụt
    total_loss_pct         : Decimal = field(default=Decimal("0"))   # % hao hụt trên issued
    overall_yield_pct      : Decimal = field(default=Decimal("0"))   # % sản lượng

    # ── Section 4: Outputs / Đầu ra ──────────────────────────────────────────
    certified_produced     : Decimal = field(default=Decimal("0"))   # Thành phẩm cuối
    certified_sold         : Decimal = field(default=Decimal("0"))   # ∑ Out TC
    number_tc_out          : int     = 0

    # ── Section 5: Closing Balance / Số dư cuối kỳ ───────────────────────────
    closing_stock_raw      : Decimal = field(default=Decimal("0"))   # Tồn nguyên liệu
    closing_stock_fg       : Decimal = field(default=Decimal("0"))   # Tồn thành phẩm
    closing_stock_total    : Decimal = field(default=Decimal("0"))   # Tổng tồn kho

    # ── Section 6: Reconciliation / Đối soát ─────────────────────────────────
    theoretical_closing    : Decimal = field(default=Decimal("0"))   # Số dư lý thuyết
    difference             : Decimal = field(default=Decimal("0"))   # Thực tế − Lý thuyết
    difference_pct         : Decimal = field(default=Decimal("0"))   # |diff| / total_available %
    balance_status         : str     = "PENDING"                     # PASS / WARNING / FAIL

    # ── Section 7: Alerts / Cảnh báo ─────────────────────────────────────────
    alerts                 : List[str] = field(default_factory=list)
    warnings               : List[str] = field(default_factory=list)

    # ── Section 8: Individual TC detail / Chi tiết từng TC ───────────────────
    tc_in_details          : List[dict] = field(default_factory=list)
    tc_out_details         : List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """
        Chuyển sang dict phù hợp xuất báo cáo kiểm toán
        Convert to dict suitable for audit report export
        """
        return {
            # Metadata
            "period"               : f"{self.period_start} → {self.period_end}",
            "period_start"         : str(self.period_start),
            "period_end"           : str(self.period_end),
            "certification"        : self.certification_standard,
            "material_code"        : self.material_code,
            "material_name"        : self.material_name,

            # Opening
            "opening_stock_kg"     : float(self.opening_stock),

            # Inputs
            "certified_purchased_kg" : float(self.certified_purchased),
            "number_tc_in"           : self.number_tc_in,
            "total_available_kg"     : float(self.total_available),

            # Production
            "issued_to_production_kg": float(self.issued_to_production),
            "cutting"                : self.cutting.to_dict()  if self.cutting  else None,
            "sewing"                 : self.sewing.to_dict()   if self.sewing   else None,
            "packing"                : self.packing.to_dict()  if self.packing  else None,
            "total_process_loss_kg"  : float(self.total_process_loss),
            "total_loss_pct"         : float(self.total_loss_pct),
            "overall_yield_pct"      : float(self.overall_yield_pct),

            # Outputs
            "certified_produced_kg"  : float(self.certified_produced),
            "certified_sold_kg"      : float(self.certified_sold),
            "number_tc_out"          : self.number_tc_out,

            # Closing
            "closing_stock_raw_kg"   : float(self.closing_stock_raw),
            "closing_stock_fg_kg"    : float(self.closing_stock_fg),
            "closing_stock_total_kg" : float(self.closing_stock_total),

            # Reconciliation
            "theoretical_closing_kg" : float(self.theoretical_closing),
            "difference_kg"          : float(self.difference),
            "difference_pct"         : float(self.difference_pct),
            "balance_status"         : self.balance_status,

            # Alerts
            "alerts"                 : self.alerts,
            "warnings"               : self.warnings,
        }

    def format_report(self) -> str:
        """
        In báo cáo dạng text (cho terminal / log)
        Print text-format report (for terminal / log output)
        """
        lines = [
            "═" * 70,
            f"  MASS BALANCE REPORT – {self.certification_standard}",
            f"  Period: {self.period_start} → {self.period_end}",
            f"  Material: {self.material_code or 'All'} {self.material_name or ''}",
            "═" * 70,
            "",
            "  SECTION 1 – OPENING BALANCE / SỐ DƯ ĐẦU KỲ",
            f"    Opening Stock               : {self.opening_stock:>12.3f} kg",
            "",
            "  SECTION 2 – INPUTS / ĐẦU VÀO",
            f"    Certified Purchased (In TC) : {self.certified_purchased:>12.3f} kg  ({self.number_tc_in} TCs)",
            f"    ────────────────────────────────────────────",
            f"    Total Available             : {self.total_available:>12.3f} kg",
            "",
            "  SECTION 3 – PRODUCTION LOSS / HAO HỤT SẢN XUẤT",
            f"    Issued to Cutting           : {self.issued_to_production:>12.3f} kg",
        ]

        for stage in [self.cutting, self.sewing, self.packing]:
            if stage:
                label = {
                    "cutting": "Cutting / Cắt",
                    "sewing" : "Sewing  / May",
                    "packing": "Packing / Đóng gói",
                }[stage.stage]
                lines += [
                    f"    {label}",
                    f"      Input   : {stage.input_qty:>10.3f} kg",
                    f"      Output  : {stage.output_qty:>10.3f} kg",
                    f"      Loss    : {stage.loss_qty:>10.3f} kg  ({stage.loss_pct:.2f}%)",
                    f"      Yield   : {stage.yield_pct:.2f}%",
                ]

        lines += [
            f"    ────────────────────────────────────────────",
            f"    Total Process Loss          : {self.total_process_loss:>12.3f} kg  ({self.total_loss_pct:.2f}%)",
            f"    Overall Yield               : {self.overall_yield_pct:.2f}%",
            "",
            "  SECTION 4 – OUTPUTS / ĐẦU RA",
            f"    Certified Produced          : {self.certified_produced:>12.3f} kg",
            f"    Certified Sold (Out TC)     : {self.certified_sold:>12.3f} kg  ({self.number_tc_out} TCs)",
            "",
            "  SECTION 5 – CLOSING BALANCE / SỐ DƯ CUỐI KỲ",
            f"    Closing Stock (Raw)         : {self.closing_stock_raw:>12.3f} kg",
            f"    Closing Stock (FG)          : {self.closing_stock_fg:>12.3f} kg",
            f"    Closing Stock (Total)       : {self.closing_stock_total:>12.3f} kg",
            "",
            "  SECTION 6 – RECONCILIATION / ĐỐI SOÁT",
            f"    Theoretical Closing         : {self.theoretical_closing:>12.3f} kg",
            f"    Actual Closing              : {self.closing_stock_total:>12.3f} kg",
            f"    Difference                  : {self.difference:>+12.3f} kg  ({self.difference_pct:.4f}%)",
            "",
            f"  ┌─ BALANCE STATUS: {self.balance_status:^8s} {'✓ COMPLIANT' if self.balance_status == 'PASS' else '⚠ REVIEW NEEDED' if self.balance_status == 'WARNING' else '✗ NON-COMPLIANT'} ─┐",
            "═" * 70,
        ]

        if self.alerts:
            lines.append("\n  ALERTS / CẢNH BÁO:")
            for alert in self.alerts:
                lines.append(f"    ⚠  {alert}")

        return "\n".join(lines)


@dataclass
class TCUtilizationResult:
    """
    Kết quả truy xuất nguồn gốc theo 1 In TC
    Traceability result for a single In TC – shows all downstream usage
    """
    tc_in_number     : str
    certified_qty    : Decimal
    issued_to_prod   : Decimal
    total_produced   : Decimal
    process_loss     : Decimal
    process_loss_pct : Decimal
    sold_with_tc_out : Decimal
    remaining_stock  : Decimal
    utilization_pct  : Decimal
    is_balanced      : bool                  # quantity_used ≤ certified_qty
    linked_batches   : List[dict] = field(default_factory=list)
    linked_tc_outs   : List[dict] = field(default_factory=list)
    alerts           : List[str]  = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Calculator / Engine tính toán
# ─────────────────────────────────────────────────────────────────────────────

class MassBalanceCalculator:
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  ENGINE TÍNH MASS BALANCE – Pure functions, fully testable              │
    │  Mass Balance Calculation Engine – Pure functions, fully testable        │
    │                                                                          │
    │  Thiết kế:                                                               │
    │    • Không phụ thuộc database (dependency-free, nhận Decimal input)     │
    │    • Pure functions – cùng input → cùng output                          │
    │    • Tất cả phép tính dùng Decimal (không mất độ chính xác float)       │
    │    • Có thể test độc lập không cần DB / unit-testable without DB         │
    └─────────────────────────────────────────────────────────────────────────┘

    Ví dụ sử dụng / Usage example:
        calc = MassBalanceCalculator()
        result = calc.calculate(
            period_start = date(2024, 1, 1),
            period_end   = date(2024, 12, 31),
            certification_standard = "GRS",
            opening_stock          = Decimal("500.000"),
            certified_purchased    = Decimal("10000.000"),
            number_tc_in           = 12,
            cutting_data           = (Decimal("9500.000"), Decimal("8550.000")),  # (input, output)
            sewing_data            = (Decimal("8550.000"), Decimal("8122.500")),
            packing_data           = (Decimal("8122.500"), Decimal("7962.050")),
            certified_sold         = Decimal("8000.000"),
            number_tc_out          = 8,
            closing_stock_raw      = Decimal("1000.000"),
            closing_stock_fg       = Decimal("962.050"),
        )
        print(result.balance_status)    # "PASS"
        print(result.format_report())
    """

    def __init__(
        self,
        pass_threshold_pct    : Decimal = PASS_THRESHOLD_PCT,
        warning_threshold_pct : Decimal = WARNING_THRESHOLD_PCT,
    ):
        self.pass_threshold    = pass_threshold_pct
        self.warning_threshold = warning_threshold_pct

    # ── Private helpers ────────────────────────────────────────────────────

    def _d(self, value) -> Decimal:
        """Chuyển sang Decimal an toàn / Safe Decimal conversion"""
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    def _round_kg(self, value: Decimal) -> Decimal:
        """Làm tròn kg 3 chữ số thập phân / Round kg to 3 decimal places"""
        return value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    def _round_pct(self, value: Decimal) -> Decimal:
        """Làm tròn % 4 chữ số thập phân / Round percentage to 4 decimal places"""
        return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def _safe_pct(self, numerator: Decimal, denominator: Decimal) -> Decimal:
        """
        Tính phần trăm an toàn (tránh chia 0)
        Safe percentage calculation (avoids ZeroDivisionError)
        """
        if denominator and denominator > Decimal("0"):
            return self._round_pct((numerator / denominator) * Decimal("100"))
        return Decimal("0")

    # ── Stage calculation / Tính từng công đoạn ───────────────────────────

    def calculate_stage(
        self,
        stage      : str,
        input_qty  : Decimal,
        output_qty : Decimal,
    ) -> StageResult:
        """
        Tính hao hụt cho một công đoạn sản xuất
        Calculate loss metrics for a single production stage

        Args:
            stage:      "cutting" | "sewing" | "packing"
            input_qty:  kg đầu vào / kg going into the stage
            output_qty: kg đầu ra  / kg coming out of the stage

        Returns:
            StageResult với loss_qty, loss_pct, yield_pct

        Raises:
            ValueError: nếu output > input (không hợp lý vật lý)
        """
        in_qty  = self._round_kg(self._d(input_qty))
        out_qty = self._round_kg(self._d(output_qty))

        if out_qty > in_qty:
            raise ValueError(
                f"[{stage}] output ({out_qty} kg) > input ({in_qty} kg). "
                f"Vật liệu không thể tăng trong sản xuất / Material cannot increase during production."
            )
        if in_qty < Decimal("0"):
            raise ValueError(f"[{stage}] input quantity must be positive, got {in_qty}")

        loss_qty  = self._round_kg(in_qty - out_qty)
        loss_pct  = self._safe_pct(loss_qty, in_qty)
        yield_pct = self._round_pct(Decimal("100") - loss_pct)

        return StageResult(
            stage      = stage,
            input_qty  = in_qty,
            output_qty = out_qty,
            loss_qty   = loss_qty,
            loss_pct   = loss_pct,
            yield_pct  = yield_pct,
        )

    # ── Main Mass Balance calculation ──────────────────────────────────────

    def calculate(
        self,
        # ── Metadata ──────────────────────────────────────────────────────
        period_start           : date,
        period_end             : date,
        certification_standard : str,
        material_code          : Optional[str] = None,
        material_name          : Optional[str] = None,

        # ── Opening balance / Số dư đầu kỳ ───────────────────────────────
        opening_stock          : Decimal = Decimal("0"),

        # ── Inputs / Đầu vào (In TCs) ─────────────────────────────────────
        certified_purchased    : Decimal = Decimal("0"),
        number_tc_in           : int     = 0,

        # ── Production stages ─────────────────────────────────────────────
        # Mỗi stage: (input_kg, output_kg) hoặc None nếu không có công đoạn
        # Each stage: (input_kg, output_kg) or None if stage not applicable
        cutting_data           : Optional[Tuple[Decimal, Decimal]] = None,
        sewing_data            : Optional[Tuple[Decimal, Decimal]] = None,
        packing_data           : Optional[Tuple[Decimal, Decimal]] = None,

        # ── Outputs / Đầu ra (Out TCs) ────────────────────────────────────
        certified_sold         : Decimal = Decimal("0"),
        number_tc_out          : int     = 0,

        # ── Closing balance (actual stock count) / Tồn kho thực tế ───────
        closing_stock_raw      : Decimal = Decimal("0"),   # Tồn nguyên liệu cuối kỳ
        closing_stock_fg       : Decimal = Decimal("0"),   # Tồn thành phẩm cuối kỳ

        # ── Optional: TC details for traceability ─────────────────────────
        tc_in_details          : Optional[List[dict]] = None,
        tc_out_details         : Optional[List[dict]] = None,

    ) -> MassBalanceResult:
        """
        Tính đầy đủ Mass Balance cho một kỳ kiểm toán
        Calculate complete Mass Balance for an audit period

        Đây là hàm trung tâm của toàn bộ hệ thống.
        This is the central function of the entire system.

        Returns:
            MassBalanceResult – đầy đủ thông tin sẵn sàng kiểm toán
        """
        # ── Khởi tạo kết quả / Initialize result ──────────────────────────
        r = MassBalanceResult(
            period_start           = period_start,
            period_end             = period_end,
            certification_standard = certification_standard,
            material_code          = material_code,
            material_name          = material_name,
            tc_in_details          = tc_in_details or [],
            tc_out_details         = tc_out_details or [],
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # BƯỚC 1: OPENING BALANCE / Số dư đầu kỳ
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        r.opening_stock = self._round_kg(self._d(opening_stock))

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # BƯỚC 2: INPUTS / Đầu vào
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        r.certified_purchased = self._round_kg(self._d(certified_purchased))
        r.number_tc_in        = number_tc_in
        r.total_available     = self._round_kg(r.opening_stock + r.certified_purchased)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # BƯỚC 3: PRODUCTION STAGES / Các công đoạn sản xuất
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        issued_to_production = Decimal("0")
        total_loss           = Decimal("0")
        final_output         = Decimal("0")

        if cutting_data:
            cut_in, cut_out = cutting_data
            r.cutting            = self.calculate_stage("cutting", self._d(cut_in), self._d(cut_out))
            issued_to_production = r.cutting.input_qty          # Issued = cutting input
            total_loss          += r.cutting.loss_qty
            final_output         = r.cutting.output_qty

            if sewing_data:
                sew_in, sew_out = sewing_data
                r.sewing     = self.calculate_stage("sewing", self._d(sew_in), self._d(sew_out))
                total_loss  += r.sewing.loss_qty
                final_output = r.sewing.output_qty

                if packing_data:
                    pack_in, pack_out = packing_data
                    r.packing    = self.calculate_stage("packing", self._d(pack_in), self._d(pack_out))
                    total_loss  += r.packing.loss_qty
                    final_output = r.packing.output_qty

        r.issued_to_production = self._round_kg(issued_to_production)
        r.total_process_loss   = self._round_kg(total_loss)
        r.total_loss_pct       = self._safe_pct(total_loss, issued_to_production)
        r.overall_yield_pct    = self._round_pct(Decimal("100") - r.total_loss_pct)
        r.certified_produced   = self._round_kg(final_output)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # BƯỚC 4: OUTPUTS / Đầu ra
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        r.certified_sold = self._round_kg(self._d(certified_sold))
        r.number_tc_out  = number_tc_out

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # BƯỚC 5: CLOSING BALANCE / Số dư cuối kỳ
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        r.closing_stock_raw   = self._round_kg(self._d(closing_stock_raw))
        r.closing_stock_fg    = self._round_kg(self._d(closing_stock_fg))
        r.closing_stock_total = self._round_kg(r.closing_stock_raw + r.closing_stock_fg)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # BƯỚC 6: RECONCILIATION / Đối soát – đây là bước quan trọng nhất
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        #
        # Công thức GRS cân đối:
        #   Opening + Purchased  =  Sold + Total_Loss + Closing
        #
        # Theoretical Closing = Opening + Purchased − Sold − Total_Loss
        # Difference = Actual_Closing − Theoretical_Closing
        #   Positive difference (+) = surplus  (tồn thực tế > lý thuyết)
        #   Negative difference (−) = deficit  (tồn thực tế < lý thuyết)
        #
        r.theoretical_closing = self._round_kg(
            r.opening_stock
            + r.certified_purchased
            - r.certified_sold
            - r.total_process_loss
        )

        r.difference = self._round_kg(r.closing_stock_total - r.theoretical_closing)

        # % chênh lệch tính trên total_available (mẫu số chuẩn GRS)
        # % difference calculated against total_available (GRS standard denominator)
        denominator = r.total_available if r.total_available > Decimal("0") else Decimal("1")
        r.difference_pct = self._safe_pct(abs(r.difference), denominator)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # BƯỚC 7: STATUS EVALUATION / Đánh giá trạng thái
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        r.balance_status = self._evaluate_status(r.difference_pct)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # BƯỚC 8: GENERATE ALERTS / Phát sinh cảnh báo
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        r.alerts, r.warnings = self._generate_alerts(r)

        return r

    # ── Status evaluation / Đánh giá trạng thái ───────────────────────────

    def _evaluate_status(self, difference_pct: Decimal) -> str:
        """
        Áp dụng ngưỡng GRS để phân loại PASS / WARNING / FAIL
        Apply GRS thresholds to classify PASS / WARNING / FAIL

        Tham chiếu: GRS 4.0 Section 5.3.2 – Mass Balance
        Reference  : GRS 4.0 Section 5.3.2 – Mass Balance
        """
        abs_diff = abs(difference_pct)

        if abs_diff <= self.pass_threshold:
            return "PASS"
        elif abs_diff <= self.warning_threshold:
            return "WARNING"
        else:
            return "FAIL"

    # ── Alert generation / Tạo cảnh báo ───────────────────────────────────

    def _generate_alerts(self, r: MassBalanceResult) -> Tuple[List[str], List[str]]:
        """
        Kiểm tra các điều kiện bất thường và phát sinh cảnh báo
        Check for abnormal conditions and generate alerts

        Returns:
            (alerts, warnings)  – alerts = critical, warnings = informational
        """
        alerts   : List[str] = []
        warnings : List[str] = []

        # ── Critical alerts / Cảnh báo nghiêm trọng ─────────────────────

        # Tồn kho âm – nghiêm trọng nhất / Negative stock – most critical
        if r.closing_stock_total < Decimal("0"):
            alerts.append(
                f"CRITICAL – Tồn kho âm: {r.closing_stock_total:.3f} kg. "
                f"Có thể đã bán vượt lượng TC hoặc hao hụt không được ghi nhận. "
                f"Negative stock detected – possible TC overclaim or unrecorded loss."
            )

        # Over-claiming – bán nhiều hơn lượng có chứng nhận
        if r.certified_sold > r.total_available:
            overclaim = r.certified_sold - r.total_available
            alerts.append(
                f"CRITICAL – Bán vượt TC: đã bán {r.certified_sold:.3f} kg nhưng "
                f"chỉ có {r.total_available:.3f} kg khả dụng. "
                f"Over-claiming {overclaim:.3f} kg – GRS non-compliant."
            )

        # Balance FAIL
        if r.balance_status == "FAIL":
            alerts.append(
                f"FAIL – Chênh lệch Mass Balance: {r.difference:+.3f} kg "
                f"({r.difference_pct:.4f}% of available). "
                f"Vượt ngưỡng cho phép {self.warning_threshold}%. "
                f"Yêu cầu điều tra và giải trình cho kiểm toán viên. "
                f"Exceeds {self.warning_threshold}% tolerance – audit action required."
            )

        # ── Warnings / Cảnh báo ──────────────────────────────────────────

        # Balance WARNING
        if r.balance_status == "WARNING":
            warnings.append(
                f"WARNING – Chênh lệch cần xem xét: {r.difference:+.3f} kg "
                f"({r.difference_pct:.4f}%). "
                f"Nằm trong ngưỡng {self.pass_threshold}%–{self.warning_threshold}%. "
                f"Review recommended before audit submission."
            )

        # Cutting loss / Hao hụt cắt cao
        if r.cutting and r.cutting.loss_pct > CUTTING_LOSS_ALERT_PCT:
            warnings.append(
                f"WARNING – Hao hụt Cắt cao: {r.cutting.loss_pct:.2f}% "
                f"(ngưỡng cảnh báo: >{CUTTING_LOSS_ALERT_PCT}%). "
                f"Unusual cutting loss – please verify measurement and records."
            )

        # Sewing loss / Hao hụt may cao
        if r.sewing and r.sewing.loss_pct > SEWING_LOSS_ALERT_PCT:
            warnings.append(
                f"WARNING – Hao hụt May cao: {r.sewing.loss_pct:.2f}% "
                f"(ngưỡng cảnh báo: >{SEWING_LOSS_ALERT_PCT}%). "
                f"Unusual sewing loss – please verify."
            )

        # Packing loss / Hao hụt đóng gói cao
        if r.packing and r.packing.loss_pct > PACKING_LOSS_ALERT_PCT:
            warnings.append(
                f"WARNING – Hao hụt Đóng gói cao: {r.packing.loss_pct:.2f}% "
                f"(ngưỡng cảnh báo: >{PACKING_LOSS_ALERT_PCT}%). "
                f"Unusual packing loss – please verify."
            )

        # Tổng hao hụt rất cao / Very high total loss
        if r.total_loss_pct > TOTAL_LOSS_ALERT_PCT:
            warnings.append(
                f"WARNING – Tổng hao hụt rất cao: {r.total_loss_pct:.2f}% "
                f"(ngưỡng cảnh báo: >{TOTAL_LOSS_ALERT_PCT}%). "
                f"Total process loss exceeds expected range – investigation recommended."
            )

        # Không có In TC / No In TCs in period
        if r.number_tc_in == 0 and r.certified_purchased > Decimal("0"):
            warnings.append(
                "WARNING – Có lượng mua nhưng không có In TC nào được liên kết. "
                "Purchased quantity recorded but no In TCs linked."
            )

        # Không có Out TC / No Out TCs in period
        if r.number_tc_out == 0 and r.certified_sold > Decimal("0"):
            warnings.append(
                "WARNING – Có lượng bán nhưng không có Out TC nào được liên kết. "
                "Sold quantity recorded but no Out TCs linked."
            )

        return alerts, warnings

    # ── Batch-level calculation / Tính theo lô sản xuất ────────────────────

    def calculate_batch_loss(
        self,
        batch_number  : str,
        cutting_in    : Optional[Decimal] = None,
        cutting_out   : Optional[Decimal] = None,
        sewing_in     : Optional[Decimal] = None,
        sewing_out    : Optional[Decimal] = None,
        packing_in    : Optional[Decimal] = None,
        packing_out   : Optional[Decimal] = None,
    ) -> dict:
        """
        Tính hao hụt chi tiết theo lô sản xuất
        Calculate detailed loss breakdown for a specific production batch
        """
        stages: Dict[str, StageResult] = {}
        total_input  = Decimal("0")
        total_loss   = Decimal("0")
        final_output = Decimal("0")

        if cutting_in is not None and cutting_out is not None:
            s = self.calculate_stage("cutting", self._d(cutting_in), self._d(cutting_out))
            stages["cutting"] = s
            total_input  = s.input_qty
            total_loss  += s.loss_qty
            final_output = s.output_qty

        if sewing_in is not None and sewing_out is not None:
            s = self.calculate_stage("sewing", self._d(sewing_in), self._d(sewing_out))
            stages["sewing"] = s
            if total_input == Decimal("0"):
                total_input = s.input_qty
            total_loss  += s.loss_qty
            final_output = s.output_qty

        if packing_in is not None and packing_out is not None:
            s = self.calculate_stage("packing", self._d(packing_in), self._d(packing_out))
            stages["packing"] = s
            if total_input == Decimal("0"):
                total_input = s.input_qty
            total_loss  += s.loss_qty
            final_output = s.output_qty

        return {
            "batch_number"      : batch_number,
            "total_input_kg"    : float(self._round_kg(total_input)),
            "total_output_kg"   : float(self._round_kg(final_output)),
            "total_loss_kg"     : float(self._round_kg(total_loss)),
            "total_loss_pct"    : float(self._safe_pct(total_loss, total_input)),
            "overall_yield_pct" : float(
                Decimal("100") - self._safe_pct(total_loss, total_input)
            ),
            "stages"            : {name: s.to_dict() for name, s in stages.items()},
        }

    # ── TC utilization / Mức độ sử dụng In TC ────────────────────────────

    def calculate_tc_utilization(
        self,
        tc_in_number      : str,
        certified_qty     : Decimal,
        batches           : List[dict],    # [{"batch": "B001", "qty_issued": 100, "qty_produced": 85}]
        tc_out_allocations: List[dict],    # [{"tc_out": "TC-OUT-001", "qty": 80}]
    ) -> TCUtilizationResult:
        """
        Tính mức độ sử dụng và truy xuất nguồn gốc của một In TC
        Calculate utilization and traceability for a single In TC

        Dùng cho báo cáo Traceability: chọn 1 In TC → hiện tất cả downstream
        Used for Traceability Report: select 1 In TC → show all downstream
        """
        cert_qty = self._d(certified_qty)

        total_issued   = sum(self._d(b["qty_issued"])   for b in batches)
        total_produced = sum(self._d(b["qty_produced"]) for b in batches)
        total_sold     = sum(self._d(t["qty"])           for t in tc_out_allocations)

        process_loss   = total_issued - total_produced
        remaining      = cert_qty - total_issued

        alerts: List[str] = []

        if total_issued > cert_qty:
            overclaim = total_issued - cert_qty
            alerts.append(
                f"CRITICAL – Sử dụng vượt TC: đã xuất {total_issued:.3f} kg "
                f"nhưng chỉ được phép {cert_qty:.3f} kg. "
                f"Over-allocation of {overclaim:.3f} kg detected."
            )

        if total_sold > total_produced:
            alerts.append(
                f"WARNING – Bán ({total_sold:.3f} kg) > sản xuất ({total_produced:.3f} kg). "
                f"Sold quantity exceeds produced quantity for this TC."
            )

        return TCUtilizationResult(
            tc_in_number      = tc_in_number,
            certified_qty     = self._round_kg(cert_qty),
            issued_to_prod    = self._round_kg(total_issued),
            total_produced    = self._round_kg(total_produced),
            process_loss      = self._round_kg(process_loss),
            process_loss_pct  = self._safe_pct(process_loss, total_issued),
            sold_with_tc_out  = self._round_kg(total_sold),
            remaining_stock   = self._round_kg(remaining),
            utilization_pct   = self._safe_pct(total_issued, cert_qty),
            is_balanced       = remaining >= Decimal("0"),
            linked_batches    = batches,
            linked_tc_outs    = tc_out_allocations,
            alerts            = alerts,
        )

    # ── Annual summary / Tóm tắt năm ──────────────────────────────────────

    def aggregate_annual(
        self,
        monthly_results: List[MassBalanceResult],
    ) -> MassBalanceResult:
        """
        Tổng hợp các kỳ tháng thành báo cáo năm
        Aggregate monthly Mass Balance results into an annual summary

        Lưu ý: Tổng hao hụt % tính trên tổng issued, không phải trung bình cộng
        Note: Total loss % is computed over total issued, not averaged
        """
        if not monthly_results:
            raise ValueError("Không có dữ liệu tháng để tổng hợp / No monthly data to aggregate")

        first = monthly_results[0]
        last  = monthly_results[-1]

        total_purchased  = sum(r.certified_purchased  for r in monthly_results)
        total_sold       = sum(r.certified_sold        for r in monthly_results)
        total_issued     = sum(r.issued_to_production  for r in monthly_results)

        total_cut_loss   = sum(r.cutting.loss_qty  if r.cutting  else Decimal("0") for r in monthly_results)
        total_sew_loss   = sum(r.sewing.loss_qty   if r.sewing   else Decimal("0") for r in monthly_results)
        total_pack_loss  = sum(r.packing.loss_qty  if r.packing  else Decimal("0") for r in monthly_results)
        total_loss       = total_cut_loss + total_sew_loss + total_pack_loss

        total_cut_in  = sum(r.cutting.input_qty  if r.cutting  else Decimal("0") for r in monthly_results)
        total_cut_out = sum(r.cutting.output_qty if r.cutting  else Decimal("0") for r in monthly_results)
        total_sew_in  = sum(r.sewing.input_qty   if r.sewing   else Decimal("0") for r in monthly_results)
        total_sew_out = sum(r.sewing.output_qty  if r.sewing   else Decimal("0") for r in monthly_results)
        total_pack_in = sum(r.packing.input_qty  if r.packing  else Decimal("0") for r in monthly_results)
        total_pack_out= sum(r.packing.output_qty if r.packing  else Decimal("0") for r in monthly_results)

        # Dùng tổng hao hụt thực tế để tính Mass Balance năm
        # Use actual cumulative loss for annual Mass Balance calculation
        return self.calculate(
            period_start           = first.period_start,
            period_end             = last.period_end,
            certification_standard = first.certification_standard,
            material_code          = first.material_code,
            material_name          = first.material_name,
            opening_stock          = first.opening_stock,
            certified_purchased    = total_purchased,
            number_tc_in           = sum(r.number_tc_in for r in monthly_results),
            cutting_data           = (total_cut_in,  total_cut_out)  if total_cut_in  > 0 else None,
            sewing_data            = (total_sew_in,  total_sew_out)  if total_sew_in  > 0 else None,
            packing_data           = (total_pack_in, total_pack_out) if total_pack_in > 0 else None,
            certified_sold         = total_sold,
            number_tc_out          = sum(r.number_tc_out for r in monthly_results),
            closing_stock_raw      = last.closing_stock_raw,
            closing_stock_fg       = last.closing_stock_fg,
        )
