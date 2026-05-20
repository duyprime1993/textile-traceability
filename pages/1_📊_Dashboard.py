"""
Dashboard – KPI overview, alerts, charts
"""

from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from decimal import Decimal

import streamlit as st

from ui.helpers import inject_css, sidebar_logo, section, kpi_row, show_alert, badge, fmt_kg, empty_state
from ui.db import get_db
from app.models import TCIn, TCOut, ProductionBatch, MassBalancePeriod
from sqlalchemy import func

st.set_page_config(page_title="Dashboard – Textile Traceability", page_icon="📊", layout="wide")
inject_css()
sidebar_logo()

st.title("📊 Dashboard")

db = get_db()
try:
    # ── KPI data ─────────────────────────────────────────────────────────────
    active_tc_in = db.query(func.count(TCIn.id)).filter(
        TCIn.status.in_(["active", "partially_used"])
    ).scalar() or 0
    total_stock  = db.query(func.sum(TCIn.quantity_remaining)).filter(
        TCIn.status.in_(["active", "partially_used"])
    ).scalar() or Decimal("0")

    issued_tc_out  = db.query(func.count(TCOut.id)).filter(TCOut.status == "issued").scalar() or 0
    batches_active = db.query(func.count(ProductionBatch.id)).filter(
        ProductionBatch.status == "in_progress"
    ).scalar() or 0

    latest_mb = (
        db.query(MassBalancePeriod)
        .order_by(MassBalancePeriod.period_end.desc())
        .first()
    )

    # ── KPI row ──────────────────────────────────────────────────────────────
    section("Key Performance Indicators", "📈")
    kpi_row([
        {"label": "Certified Stock (kg)",  "value": f"{float(total_stock):,.1f}"},
        {"label": "Active In TCs",         "value": str(active_tc_in)},
        {"label": "Batches In Progress",   "value": str(batches_active)},
        {"label": "Issued Out TCs",        "value": str(issued_tc_out)},
    ])

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Mass Balance status ───────────────────────────────────────────────────
    section("Latest Mass Balance", "⚖️")
    if latest_mb:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"**Period:** {latest_mb.period_start} → {latest_mb.period_end}")
        with col2:
            st.markdown(f"**Standard:** {latest_mb.certification_standard}")
        with col3:
            diff_pct = float(latest_mb.difference_pct or 0)
            st.markdown(f"**Difference:** {diff_pct:+.4f}%")
        with col4:
            st.markdown(
                f"**Status:** {badge(latest_mb.balance_status)}",
                unsafe_allow_html=True,
            )

        if latest_mb.balance_status == "FAIL":
            show_alert(
                f"Mass Balance FAIL – difference {diff_pct:+.4f}% exceeds 2.0% tolerance. "
                "Immediate review required.",
                "critical",
            )
        elif latest_mb.balance_status == "WARNING":
            show_alert(
                f"Mass Balance WARNING – difference {diff_pct:+.4f}% exceeds 0.5% tolerance.",
                "warning",
            )
        else:
            st.success(f"Mass Balance {latest_mb.balance_status} — within tolerance.")
    else:
        empty_state(
            "No Mass Balance periods calculated yet. Go to ⚖️ Mass Balance to run your first calculation.",
            "⚖️",
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── In TC utilization ─────────────────────────────────────────────────────
    section("In TC Utilization", "📥")
    tc_ins = (
        db.query(TCIn)
        .filter(TCIn.status.in_(["active", "partially_used", "fully_used"]))
        .order_by(TCIn.issue_date.desc())
        .limit(20)
        .all()
    )
    if tc_ins:
        import pandas as pd
        rows = []
        for t in tc_ins:
            used  = float(t.certified_quantity - t.quantity_remaining)
            total = float(t.certified_quantity)
            pct   = (used / total * 100) if total else 0
            rows.append({
                "TC Number"     : t.tc_number,
                "Standard"      : t.certification_standard,
                "Cert. Qty (kg)": f"{total:,.3f}",
                "Used (kg)"     : f"{used:,.3f}",
                "Remaining (kg)": f"{float(t.quantity_remaining):,.3f}",
                "Used %"        : f"{pct:.1f}%",
                "Status"        : t.status.upper(),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        empty_state("No active In TCs found.")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Recent batches ────────────────────────────────────────────────────────
    section("Recent Production Batches", "🏭")
    batches = (
        db.query(ProductionBatch)
        .order_by(ProductionBatch.start_date.desc())
        .limit(10)
        .all()
    )
    if batches:
        import pandas as pd
        rows = []
        for b in batches:
            rows.append({
                "Batch No."     : b.batch_number,
                "Product"       : b.product_name,
                "Planned In(kg)": f"{float(b.planned_input_qty):,.3f}" if b.planned_input_qty else "—",
                "Actual Out(kg)": f"{float(b.actual_output_qty):,.3f}" if b.actual_output_qty else "—",
                "Start"         : str(b.start_date),
                "Status"        : b.status.upper(),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        empty_state("No production batches yet.")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Recent Mass Balance history ───────────────────────────────────────────
    section("Mass Balance History", "📅")
    periods = (
        db.query(MassBalancePeriod)
        .order_by(MassBalancePeriod.period_end.desc())
        .limit(6)
        .all()
    )
    if periods:
        import pandas as pd
        p_rows = []
        for p in periods:
            p_rows.append({
                "Period"   : f"{p.period_start} → {p.period_end}",
                "Standard" : p.certification_standard,
                "Purchased": f"{float(p.certified_purchased):,.3f}",
                "Sold"     : f"{float(p.certified_sold):,.3f}",
                "Diff %"   : f"{float(p.difference_pct or 0):+.4f}%",
                "Status"   : p.balance_status,
            })
        st.dataframe(pd.DataFrame(p_rows), use_container_width=True, hide_index=True)
    else:
        empty_state("No Mass Balance periods calculated yet.")

finally:
    db.close()
