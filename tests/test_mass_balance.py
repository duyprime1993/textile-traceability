"""
Unit tests cho Mass Balance Calculation Engine
Tests for the Mass Balance Calculation Engine

Chạy: pytest tests/ -v
Run : pytest tests/ -v
"""

from decimal import Decimal
from datetime import date
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.mass_balance import MassBalanceCalculator, StageResult


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def calc() -> MassBalanceCalculator:
    return MassBalanceCalculator()


@pytest.fixture
def grs_annual_result(calc):
    """
    Bộ số mẫu cho kiểm thử GRS annual mass balance
    Sample dataset for GRS annual mass balance testing

    Kịch bản:
        Opening stock      :   500 kg
        Purchased (In TCs) : 10000 kg
        ──────────────────────────────
        Total Available    : 10500 kg

        Issued to cutting  :  9500 kg
        Cutting  loss      :   950 kg (10%)
        Sewing   loss      :   427.5 kg (5%)
        Packing  loss      :   160.2 kg (2%)
        Total process loss :  1537.7 kg (16.19%)

        Certified produced :  7962.3 kg
        Certified sold     :  7500 kg
        ──────────────────────────────
        Theoretical closing:  1462.3 kg (500 + 10000 - 7500 - 1537.7)
        Actual closing     :  raw=500, fg=962.3 → total=1462.3 kg
        Difference         :    0.0 kg  → PASS
    """
    return calc.calculate(
        period_start           = date(2024,  1,  1),
        period_end             = date(2024, 12, 31),
        certification_standard = "GRS",
        opening_stock          = Decimal("500.000"),
        certified_purchased    = Decimal("10000.000"),
        number_tc_in           = 12,
        cutting_data           = (Decimal("9500.000"), Decimal("8550.000")),
        sewing_data            = (Decimal("8550.000"), Decimal("8122.500")),
        packing_data           = (Decimal("8122.500"), Decimal("7962.300")),
        certified_sold         = Decimal("7500.000"),
        number_tc_out          = 8,
        closing_stock_raw      = Decimal("500.000"),
        closing_stock_fg       = Decimal("962.300"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test: Stage calculation / Tính từng công đoạn
# ─────────────────────────────────────────────────────────────────────────────

class TestStageCalculation:

    def test_cutting_10pct_loss(self, calc):
        """Hao hụt cắt 10% / 10% cutting loss"""
        stage = calc.calculate_stage("cutting", Decimal("9500"), Decimal("8550"))
        assert stage.loss_qty  == Decimal("950.000")
        assert stage.loss_pct  == Decimal("10.0000")
        assert stage.yield_pct == Decimal("90.0000")

    def test_zero_loss(self, calc):
        """Không hao hụt / Zero loss"""
        stage = calc.calculate_stage("sewing", Decimal("100"), Decimal("100"))
        assert stage.loss_qty  == Decimal("0.000")
        assert stage.loss_pct  == Decimal("0.0000")
        assert stage.yield_pct == Decimal("100.0000")

    def test_output_exceeds_input_raises(self, calc):
        """Output > Input phải raise ValueError / Output > Input must raise ValueError"""
        with pytest.raises(ValueError, match="output.*input"):
            calc.calculate_stage("cutting", Decimal("100"), Decimal("101"))

    def test_loss_rounded_3dp(self, calc):
        """Làm tròn 3 chữ số thập phân / Rounded to 3 decimal places"""
        stage = calc.calculate_stage("packing", Decimal("8122.5"), Decimal("7962.3"))
        assert stage.loss_qty == Decimal("160.200")

    def test_pct_rounded_4dp(self, calc):
        """% hao hụt làm tròn 4 chữ số thập phân / Loss % rounded to 4 dp"""
        stage = calc.calculate_stage("sewing", Decimal("8550"), Decimal("8122.5"))
        # 427.5 / 8550 * 100 = 5.0000%
        assert stage.loss_pct == Decimal("5.0000")


# ─────────────────────────────────────────────────────────────────────────────
# Test: Mass Balance calculation / Tính Mass Balance
# ─────────────────────────────────────────────────────────────────────────────

class TestMassBalanceCalculation:

    def test_total_available(self, grs_annual_result):
        """Total available = opening + purchased"""
        r = grs_annual_result
        assert r.total_available == Decimal("10500.000")

    def test_issued_to_production(self, grs_annual_result):
        """Issued = cutting input"""
        assert grs_annual_result.issued_to_production == Decimal("9500.000")

    def test_cutting_loss(self, grs_annual_result):
        """Cutting loss = 950 kg = 10%"""
        r = grs_annual_result
        assert r.cutting is not None
        assert r.cutting.loss_qty  == Decimal("950.000")
        assert r.cutting.loss_pct  == Decimal("10.0000")

    def test_sewing_loss(self, grs_annual_result):
        """Sewing loss = 427.5 kg = 5%"""
        r = grs_annual_result
        assert r.sewing is not None
        assert r.sewing.loss_qty  == Decimal("427.500")
        assert r.sewing.loss_pct  == Decimal("5.0000")

    def test_packing_loss(self, grs_annual_result):
        """Packing loss = 160.2 kg ≈ 1.97%"""
        r = grs_annual_result
        assert r.packing is not None
        assert r.packing.loss_qty == Decimal("160.200")

    def test_total_process_loss(self, grs_annual_result):
        """Total process loss = 950 + 427.5 + 160.2 = 1537.7 kg"""
        r = grs_annual_result
        assert r.total_process_loss == Decimal("1537.700")

    def test_certified_produced(self, grs_annual_result):
        """Certified produced = packing output"""
        assert grs_annual_result.certified_produced == Decimal("7962.300")

    def test_theoretical_closing(self, grs_annual_result):
        """
        Theoretical closing = Opening + Purchased − Sold − Loss
                            = 500 + 10000 − 7500 − 1537.7
                            = 1462.300
        """
        r = grs_annual_result
        expected = Decimal("500") + Decimal("10000") - Decimal("7500") - Decimal("1537.700")
        assert r.theoretical_closing == expected

    def test_balance_pass(self, grs_annual_result):
        """Difference = 0 → PASS"""
        r = grs_annual_result
        assert r.difference == Decimal("0.000")
        assert r.balance_status == "PASS"

    def test_closing_stock_total(self, grs_annual_result):
        """Closing total = raw + fg = 500 + 962.3 = 1462.3"""
        r = grs_annual_result
        assert r.closing_stock_total == Decimal("1462.300")


# ─────────────────────────────────────────────────────────────────────────────
# Test: Balance Status thresholds / Ngưỡng trạng thái
# ─────────────────────────────────────────────────────────────────────────────

class TestBalanceStatus:

    def _make_result(self, calc, actual_closing: str):
        """Helper: tạo kết quả với closing stock tuỳ chỉnh"""
        raw = Decimal(actual_closing)
        fg  = Decimal("0")
        return calc.calculate(
            period_start           = date(2024, 1, 1),
            period_end             = date(2024, 12, 31),
            certification_standard = "GRS",
            opening_stock          = Decimal("0"),
            certified_purchased    = Decimal("10000"),
            number_tc_in           = 1,
            cutting_data           = (Decimal("10000"), Decimal("9000")),
            certified_sold         = Decimal("8000"),
            number_tc_out          = 1,
            closing_stock_raw      = raw,
            closing_stock_fg       = fg,
        )
        # theoretical_closing = 0 + 10000 - 8000 - 1000 = 1000 kg

    def test_exact_pass(self, calc):
        """Difference = 0 → PASS"""
        r = self._make_result(calc, "1000.000")
        assert r.balance_status == "PASS"

    def test_small_surplus_pass(self, calc):
        """Surplus 0.4% → PASS (≤ 0.5% threshold)"""
        # 0.4% of 10000 = 40 kg surplus
        r = self._make_result(calc, "1040.000")
        assert r.balance_status == "PASS"

    def test_warning_zone(self, calc):
        """Surplus 1% → WARNING"""
        # 1% of 10000 = 100 kg surplus
        r = self._make_result(calc, "1100.000")
        assert r.balance_status == "WARNING"

    def test_fail_zone(self, calc):
        """Surplus 3% → FAIL"""
        # 3% of 10000 = 300 kg surplus
        r = self._make_result(calc, "1300.000")
        assert r.balance_status == "FAIL"

    def test_deficit_fail(self, calc):
        """Deficit 5% → FAIL (âm cũng fail / negative difference also fails)"""
        r = self._make_result(calc, "500.000")    # deficit 500 kg = 5%
        assert r.balance_status == "FAIL"


# ─────────────────────────────────────────────────────────────────────────────
# Test: Alert generation / Phát sinh cảnh báo
# ─────────────────────────────────────────────────────────────────────────────

class TestAlerts:

    def test_overclaim_alert(self, calc):
        """Bán > khả dụng → CRITICAL alert"""
        r = calc.calculate(
            period_start           = date(2024, 1, 1),
            period_end             = date(2024, 12, 31),
            certification_standard = "GRS",
            opening_stock          = Decimal("0"),
            certified_purchased    = Decimal("1000"),
            number_tc_in           = 1,
            certified_sold         = Decimal("1500"),   # sold > available!
            number_tc_out          = 1,
            closing_stock_raw      = Decimal("0"),
        )
        assert any("Over-claiming" in a for a in r.alerts)

    def test_negative_stock_alert(self, calc):
        """Tồn kho âm → CRITICAL alert"""
        r = calc.calculate(
            period_start           = date(2024, 1, 1),
            period_end             = date(2024, 12, 31),
            certification_standard = "GRS",
            opening_stock          = Decimal("100"),
            certified_purchased    = Decimal("900"),
            number_tc_in           = 1,
            certified_sold         = Decimal("1100"),
            number_tc_out          = 1,
            closing_stock_raw      = Decimal("-100"),   # negative!
        )
        assert any("Negative stock" in a for a in r.alerts)

    def test_high_cutting_loss_warning(self, calc):
        """Hao hụt cắt > 15% → WARNING"""
        r = calc.calculate(
            period_start           = date(2024, 1, 1),
            period_end             = date(2024, 12, 31),
            certification_standard = "GRS",
            opening_stock          = Decimal("0"),
            certified_purchased    = Decimal("10000"),
            number_tc_in           = 1,
            cutting_data           = (Decimal("10000"), Decimal("8300")),  # 17% loss
            certified_sold         = Decimal("8000"),
            number_tc_out          = 1,
            closing_stock_raw      = Decimal("0"),
            closing_stock_fg       = Decimal("300"),
        )
        assert any("Hao hụt Cắt" in w or "cutting loss" in w.lower() for w in r.warnings)

    def test_no_alerts_when_perfect(self, calc, grs_annual_result):
        """Không có critical alerts khi cân đối hoàn hảo"""
        assert len(grs_annual_result.alerts) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test: TC Utilization / Truy xuất TC
# ─────────────────────────────────────────────────────────────────────────────

class TestTCUtilization:

    def test_normal_utilization(self, calc):
        """TC sử dụng bình thường"""
        result = calc.calculate_tc_utilization(
            tc_in_number = "TC-IN-2024-001",
            certified_qty = Decimal("1000"),
            batches = [
                {"batch": "BATCH-001", "qty_issued": 600, "qty_produced": 510},
                {"batch": "BATCH-002", "qty_issued": 300, "qty_produced": 255},
            ],
            tc_out_allocations = [
                {"tc_out": "TC-OUT-001", "qty": 700},
            ],
        )
        assert result.issued_to_prod  == Decimal("900.000")
        assert result.total_produced  == Decimal("765.000")
        assert result.process_loss    == Decimal("135.000")
        assert result.remaining_stock == Decimal("100.000")
        assert result.is_balanced     == True
        assert len(result.alerts) == 0

    def test_overallocation_alert(self, calc):
        """Dùng vượt TC → alert"""
        result = calc.calculate_tc_utilization(
            tc_in_number  = "TC-IN-OVER",
            certified_qty = Decimal("500"),
            batches = [
                {"batch": "BATCH-X", "qty_issued": 600, "qty_produced": 540},  # over!
            ],
            tc_out_allocations = [],
        )
        assert result.is_balanced == False
        assert len(result.alerts) > 0
        assert any("Over-allocation" in a for a in result.alerts)


# ─────────────────────────────────────────────────────────────────────────────
# Test: Batch loss calculation / Tính hao hụt lô
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchLoss:

    def test_three_stage_batch(self, calc):
        result = calc.calculate_batch_loss(
            batch_number = "BATCH-001",
            cutting_in   = Decimal("1000"),
            cutting_out  = Decimal("900"),    # 10%
            sewing_in    = Decimal("900"),
            sewing_out   = Decimal("855"),    # 5%
            packing_in   = Decimal("855"),
            packing_out  = Decimal("838"),    # ~2%
        )
        assert result["total_input_kg"]    == 1000.0
        assert result["total_output_kg"]   == 838.0
        assert result["total_loss_kg"]     == 162.0
        assert "cutting" in result["stages"]
        assert "sewing"  in result["stages"]
        assert "packing" in result["stages"]

    def test_cutting_only_batch(self, calc):
        """Chỉ có công đoạn cắt"""
        result = calc.calculate_batch_loss(
            batch_number = "CUT-ONLY",
            cutting_in   = Decimal("500"),
            cutting_out  = Decimal("450"),
        )
        assert result["total_loss_kg"]  == 50.0
        assert result["total_loss_pct"] == 10.0
        assert "sewing"  not in result["stages"]
        assert "packing" not in result["stages"]


# ─────────────────────────────────────────────────────────────────────────────
# Test: Edge cases / Trường hợp đặc biệt
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_zero_opening_stock(self, calc):
        """Opening stock = 0 (nhà máy mới bắt đầu)"""
        r = calc.calculate(
            period_start           = date(2024, 1, 1),
            period_end             = date(2024, 3, 31),
            certification_standard = "GRS",
            opening_stock          = Decimal("0"),
            certified_purchased    = Decimal("5000"),
            number_tc_in           = 1,
            certified_sold         = Decimal("4000"),
            number_tc_out          = 1,
            closing_stock_raw      = Decimal("1000"),
        )
        assert r.total_available == Decimal("5000.000")
        assert r.balance_status  == "PASS"

    def test_no_production_stages(self, calc):
        """Không có dữ liệu sản xuất (chỉ mua và bán)"""
        r = calc.calculate(
            period_start           = date(2024, 1, 1),
            period_end             = date(2024, 3, 31),
            certification_standard = "GOTS",
            opening_stock          = Decimal("0"),
            certified_purchased    = Decimal("1000"),
            number_tc_in           = 2,
            # Không truyền cutting/sewing/packing
            certified_sold         = Decimal("800"),
            number_tc_out          = 2,
            closing_stock_raw      = Decimal("200"),
        )
        assert r.cutting is None
        assert r.sewing  is None
        assert r.packing is None
        assert r.total_process_loss == Decimal("0")
        assert r.balance_status     == "PASS"

    def test_string_inputs_accepted(self, calc):
        """Engine chấp nhận string và int (tự convert sang Decimal)"""
        r = calc.calculate(
            period_start           = date(2024, 1, 1),
            period_end             = date(2024, 12, 31),
            certification_standard = "RCS",
            opening_stock          = "100",       # string
            certified_purchased    = 5000,         # int
            number_tc_in           = 1,
            cutting_data           = ("4800", 4320),  # mixed
            certified_sold         = Decimal("4000"),
            number_tc_out          = 1,
            closing_stock_raw      = "0",
            closing_stock_fg       = 320,
        )
        # Không raise exception là đủ
        assert r.balance_status in ("PASS", "WARNING", "FAIL")

    def test_format_report_output(self, calc, grs_annual_result):
        """format_report() trả về string không rỗng"""
        report = grs_annual_result.format_report()
        assert isinstance(report, str)
        assert "MASS BALANCE REPORT" in report
        assert "PASS" in report

    def test_to_dict_completeness(self, calc, grs_annual_result):
        """to_dict() phải có đủ các key cần thiết cho báo cáo"""
        d = grs_annual_result.to_dict()
        required_keys = [
            "period", "certification", "opening_stock_kg",
            "certified_purchased_kg", "total_available_kg",
            "total_process_loss_kg", "total_loss_pct",
            "certified_sold_kg", "closing_stock_total_kg",
            "theoretical_closing_kg", "difference_kg",
            "difference_pct", "balance_status",
        ]
        for key in required_keys:
            assert key in d, f"Missing key in to_dict(): {key}"


# ─────────────────────────────────────────────────────────────────────────────
# Demo: in báo cáo mẫu / Demo: print sample report
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    calc = MassBalanceCalculator()
    result = calc.calculate(
        period_start           = date(2024, 1, 1),
        period_end             = date(2024, 12, 31),
        certification_standard = "GRS",
        material_code          = "MAT-rPET-100",
        material_name          = "100% Recycled PET Fabric",
        opening_stock          = Decimal("500.000"),
        certified_purchased    = Decimal("10000.000"),
        number_tc_in           = 12,
        cutting_data           = (Decimal("9500.000"), Decimal("8550.000")),
        sewing_data            = (Decimal("8550.000"), Decimal("8122.500")),
        packing_data           = (Decimal("8122.500"), Decimal("7962.300")),
        certified_sold         = Decimal("7500.000"),
        number_tc_out          = 8,
        closing_stock_raw      = Decimal("500.000"),
        closing_stock_fg       = Decimal("962.300"),
    )
    print(result.format_report())
