"""
Mass Balance – Period selection, calculation, result display
"""

from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

import streamlit as st

from ui.helpers import inject_css, sidebar_logo, section, badge, fmt_kg, show_alert, empty_state, kpi_row, util_bar
from ui.db import get_db
from app.models import MassBalancePeriod, Material
from app.reports.annual import AnnualMassBalanceReport

st.set_page_config(page_title="Mass Balance – Textile Traceability", page_icon="⚖️", layout="wide")
inject_css()
sidebar_logo()

st.title("⚖️ Mass Balance")
st.markdown("GRS/GOTS reconciliation per GRS 4.0 §5.3.2 — PASS ≤0.5%, WARNING ≤2.0%, FAIL >2.0%")

tab_calc, tab_history = st.tabs(["🧮 Calculate", "📅 History"])

# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 – Calculate
# ─────────────────────────────────────────────────────────────────────────────
with tab_calc:
    db_p = get_db()
    try:
        materials = db_p.query(Material).filter(Material.is_active == True).all()
    finally:
        db_p.close()

    if not materials:
        show_alert("No active materials configured.", "warning")
        st.stop()

    section("Period & Parameters", "📅")
    c1, c2, c3 = st.columns(3)
    with c1:
        year        = st.number_input("Year", min_value=2020, max_value=2030, value=date.today().year)
        period_type = st.radio("Period Type", ["Annual", "Custom"], horizontal=True)
    with c2:
        if period_type == "Annual":
            period_start = date(int(year), 1, 1)
            period_end   = date(int(year), 12, 31)
            st.markdown(f"**Period:** {period_start} → {period_end}")
        else:
            period_start = st.date_input("Period Start", value=date(int(year), 1, 1))
            period_end   = st.date_input("Period End",   value=date(int(year), 12, 31))
    with c3:
        standard = st.selectbox("Certification Standard", ["GRS", "GOTS", "RCS", "OCS"])
        mat_id   = st.selectbox(
            "Material",
            options=[m.id for m in materials],
            format_func=lambda i: next(m.name for m in materials if m.id == i),
        )

    calc_button = st.button("⚖️ Calculate Mass Balance", type="primary", use_container_width=True)

    if calc_button:
        with st.spinner("Calculating..."):
            db_calc = get_db()
            try:
                result = AnnualMassBalanceReport(db_calc).generate(
                    period_start=period_start,
                    period_end=period_end,
                    certification_standard=standard,
                    material_id=mat_id,
                    save_to_db=True,
                )
                db_calc.commit()
                st.session_state["mb_result"] = result
            except Exception as e:
                db_calc.rollback()
                show_alert(f"Calculation error: {e}", "critical")
                import traceback; st.code(traceback.format_exc())
            finally:
                db_calc.close()

    if "mb_result" in st.session_state:
        r = st.session_state["mb_result"]

        st.markdown("---")
        section("Mass Balance Result", "📊")

        status_style = {"PASS": "success", "WARNING": "warning", "FAIL": "error"}
        getattr(st, status_style.get(r.balance_status, "info"))(
            f"Status: {r.balance_status}  |  Difference: {float(r.difference_pct):.4f}%"
        )

        kpi_row([
            {"label": "Opening Stock",       "value": fmt_kg(r.opening_stock)},
            {"label": "Certified Purchased", "value": fmt_kg(r.certified_purchased)},
            {"label": "Certified Sold",      "value": fmt_kg(r.certified_sold)},
            {"label": "Closing Stock",       "value": fmt_kg(r.closing_stock_total)},
        ])

        st.markdown("<br>", unsafe_allow_html=True)

        c_left, c_right = st.columns(2)
        with c_left:
            section("Production Losses", "📉")
            import pandas as pd
            STAGE_THRESH = {"cutting": 15.0, "sewing": 10.0, "packing": 5.0}
            loss_rows = []
            for stage_name, stage_obj in [("cutting", r.cutting), ("sewing", r.sewing), ("packing", r.packing)]:
                if stage_obj:
                    pct    = float(stage_obj.loss_pct)
                    thresh = STAGE_THRESH.get(stage_name, 20.0)
                    flag   = "🔴" if pct > thresh else ("🟡" if pct > thresh * 0.8 else "🟢")
                    loss_rows.append({
                        "Stage"    : stage_name.upper(),
                        "Input"    : fmt_kg(stage_obj.input_qty),
                        "Output"   : fmt_kg(stage_obj.output_qty),
                        "Loss"     : fmt_kg(stage_obj.loss_qty),
                        "Loss %"   : f"{pct:.2f}%",
                        "Threshold": f"{thresh}%",
                        "Flag"     : flag,
                    })
            if loss_rows:
                st.dataframe(pd.DataFrame(loss_rows), use_container_width=True, hide_index=True)
            else:
                st.info("No production stage data for this period.")

        with c_right:
            section("Reconciliation", "⚖️")
            st.markdown(f"**Total Available:** {fmt_kg(r.total_available)}")
            st.markdown(f"**Total Process Loss:** {fmt_kg(r.total_process_loss)}")
            st.markdown(f"**Certified Produced:** {fmt_kg(r.certified_produced)}")
            st.markdown(f"**Certified Sold:** {fmt_kg(r.certified_sold)}")
            st.markdown("---")
            st.markdown(f"**Theoretical Closing:** {fmt_kg(r.theoretical_closing)}")
            st.markdown(f"**Actual Closing:** {fmt_kg(r.closing_stock_total)}")
            diff     = float(r.difference)
            diff_pct = float(r.difference_pct)
            color    = "red" if abs(diff_pct) > 2 else ("orange" if abs(diff_pct) > 0.5 else "green")
            st.markdown(
                f"<strong style='color:{color};'>Difference: {diff:+,.3f} kg ({diff_pct:+.4f}%)</strong>",
                unsafe_allow_html=True,
            )

        if r.alerts:
            st.markdown("<br>", unsafe_allow_html=True)
            section("Alerts", "🚨")
            for alert in r.alerts:
                lvl = "critical" if "FAIL" in alert or "CRITICAL" in alert else "warning"
                show_alert(alert, lvl)

# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 – History
# ─────────────────────────────────────────────────────────────────────────────
with tab_history:
    db_h = get_db()
    try:
        periods = (
            db_h.query(MassBalancePeriod)
            .order_by(MassBalancePeriod.period_end.desc())
            .all()
        )
    finally:
        db_h.close()

    if not periods:
        empty_state("No Mass Balance periods saved yet.")
    else:
        import pandas as pd
        rows = []
        for p in periods:
            opening = float((p.opening_stock_raw or 0) + (p.opening_stock_wip or 0) + (p.opening_stock_fg or 0))
            rows.append({
                "Period"      : f"{p.period_start} → {p.period_end}",
                "Standard"    : p.certification_standard,
                "Opening (kg)": f"{opening:,.3f}",
                "Purchased"   : fmt_kg(p.certified_purchased),
                "Sold"        : fmt_kg(p.certified_sold),
                "Closing"     : fmt_kg(p.closing_stock_raw),
                "Diff %"      : f"{float(p.difference_pct or 0):+.4f}%",
                "Status"      : p.balance_status,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
