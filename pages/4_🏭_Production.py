"""
Production – Batch management + Stage recording
"""

from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

import streamlit as st

from ui.helpers import inject_css, sidebar_logo, section, badge, fmt_kg, show_alert, empty_state, confirm_dialog
from ui.db import get_db
from app.models import ProductionBatch, ProductionStage, TCIn
from app.schemas.production import ProductionBatchCreate, ProductionStageCreate
from app.crud.production import ProductionBatchService, ProductionStageService

st.set_page_config(page_title="Production – Textile Traceability", page_icon="🏭", layout="wide")
inject_css()
sidebar_logo()

st.title("🏭 Production Management")
st.markdown("Track production batches and record stage losses (Cutting → Sewing → Packing).")

tab_batches, tab_new_batch, tab_stages = st.tabs(["📋 Batches", "➕ New Batch", "🔧 Record Stage"])

STAGE_ORDER  = ["cutting", "sewing", "packing"]
STAGE_THRESH = {"cutting": 15.0, "sewing": 10.0, "packing": 5.0}

# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 – Batch list
# ─────────────────────────────────────────────────────────────────────────────
with tab_batches:
    db = get_db()
    try:
        batches = db.query(ProductionBatch).order_by(ProductionBatch.start_date.desc()).all()

        if not batches:
            empty_state("No production batches yet.")
        else:
            status_filter = st.selectbox(
                "Filter by status",
                ["All", "planned", "in_progress", "completed", "cancelled"],
                key="batch_status",
            )
            filtered = batches if status_filter == "All" else [b for b in batches if b.status == status_filter]

            stage_icons = {"cutting": "✂️ Cutting", "sewing": "🧵 Sewing", "packing": "📦 Packing"}

            for b in filtered:
                stages_done = [s.stage for s in b.stages] if b.stages else []
                stage_str = "  ".join(
                    f"{'✅' if s in stages_done else '⬜'} {stage_icons[s]}" for s in STAGE_ORDER
                )

                planned_in = b.planned_input_qty
                actual_out = b.actual_output_qty
                with st.expander(
                    f"{b.batch_number}  |  {b.product_name}  |  "
                    f"{fmt_kg(planned_in) if planned_in else '—'}  |  {b.status.upper()}",
                    expanded=False,
                ):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"**Batch No.:** {b.batch_number}")
                        st.markdown(f"**Product:** {b.product_name}")
                        st.markdown(f"**In TC:** {b.tc_in.tc_number if b.tc_in else '—'}")
                        st.markdown(f"**Order No.:** {b.order_number or '—'}")
                    with c2:
                        st.markdown(f"**Planned Input:** {fmt_kg(planned_in) if planned_in else '—'}")
                        st.markdown(f"**Actual Output:** {fmt_kg(actual_out) if actual_out else '—'}")
                        if planned_in and actual_out:
                            loss_kg  = float(planned_in - actual_out)
                            loss_pct = loss_kg / float(planned_in) * 100 if float(planned_in) else 0
                            st.markdown(f"**Total Loss:** {loss_kg:,.3f} kg ({loss_pct:.2f}%)")
                        st.markdown(f"**Start:** {b.start_date}  |  **End:** {b.end_date or '—'}")
                        st.markdown(f"**Status:** {badge(b.status)}", unsafe_allow_html=True)

                    st.markdown(stage_str)

                    if b.stages:
                        import pandas as pd
                        srows = []
                        for s in b.stages:
                            loss_kg  = float(s.input_quantity - s.output_quantity)
                            loss_pct = loss_kg / float(s.input_quantity) * 100 if float(s.input_quantity) else 0
                            thresh   = STAGE_THRESH.get(s.stage, 20.0)
                            flag     = "🔴" if loss_pct > thresh else ("🟡" if loss_pct > thresh * 0.8 else "🟢")
                            srows.append({
                                "Stage"     : s.stage.upper(),
                                "Input (kg)": fmt_kg(s.input_quantity),
                                "Output(kg)": fmt_kg(s.output_quantity),
                                "Loss (kg)" : f"{loss_kg:,.3f}",
                                "Loss %"    : f"{loss_pct:.2f}%",
                                "Threshold" : f"{thresh}%",
                                "Flag"      : flag,
                            })
                        st.dataframe(pd.DataFrame(srows), use_container_width=True, hide_index=True)

                    if b.notes:
                        st.caption(f"Notes: {b.notes}")
    finally:
        db.close()

# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 – New Batch
# ─────────────────────────────────────────────────────────────────────────────
with tab_new_batch:
    db2 = get_db()
    try:
        tc_ins = db2.query(TCIn).filter(TCIn.status.in_(["active", "partially_used"])).all()
    finally:
        db2.close()

    if not tc_ins:
        show_alert("No active In TCs available. Purchase certified material first.", "warning")
    else:
        with st.form("new_batch"):
            section("New Production Batch", "🏭")
            c1, c2 = st.columns(2)
            with c1:
                batch_number = st.text_input("Batch Number *", placeholder="BATCH-2024-001")
                product_name = st.text_input("Product Name *", placeholder="GRS T-shirt")
                tc_in_id_sel = st.selectbox(
                    "Source In TC",
                    options=[None] + [t.id for t in tc_ins],
                    format_func=lambda i: "— none —" if i is None else next(
                        f"{t.tc_number} (remaining: {float(t.quantity_remaining):.3f} kg)"
                        for t in tc_ins if t.id == i
                    ),
                )
            with c2:
                planned_qty = st.number_input(
                    "Planned Input Quantity (kg)", min_value=0.0, step=0.001, format="%.3f"
                )
                start_date = st.date_input("Start Date *", value=date.today(), key="batch_start")

            batch_notes = st.text_area("Notes", height=70, key="batch_notes")
            sub = st.form_submit_button("✅ Create Batch", type="primary", use_container_width=True)

        if sub:
            if not batch_number.strip() or not product_name.strip():
                show_alert("Batch Number and Product Name are required.", "critical")
            else:
                db_op = get_db()
                try:
                    data = ProductionBatchCreate(
                        batch_number=batch_number.strip(),
                        product_name=product_name.strip(),
                        tc_in_id=tc_in_id_sel,
                        planned_input_qty=Decimal(str(planned_qty)) if planned_qty > 0 else None,
                        start_date=start_date,
                        notes=batch_notes.strip() or None,
                    )
                    ProductionBatchService(db_op).create(data)
                    db_op.commit()
                    st.success(f"✅ Batch **{batch_number}** created!")
                    st.rerun()
                except Exception as e:
                    db_op.rollback()
                    show_alert(str(e), "critical")
                finally:
                    db_op.close()

# ─────────────────────────────────────────────────────────────────────────────
# Tab 3 – Record Stage
# ─────────────────────────────────────────────────────────────────────────────
with tab_stages:
    db3 = get_db()
    try:
        active_batches = db3.query(ProductionBatch).filter(
            ProductionBatch.status.in_(["planned", "in_progress"])
        ).all()
    finally:
        db3.close()

    if not active_batches:
        empty_state("No active batches. Create a batch first.")
    else:
        sel_batch_id = st.selectbox(
            "Select Batch",
            options=[b.id for b in active_batches],
            format_func=lambda i: next(
                f"{b.batch_number} – {b.product_name}" for b in active_batches if b.id == i
            ),
            key="stage_batch",
        )
        sel_batch = next(b for b in active_batches if b.id == sel_batch_id)

        done_stages  = [s.stage for s in sel_batch.stages] if sel_batch.stages else []
        avail_stages = [s for s in STAGE_ORDER if s not in done_stages]

        if not avail_stages:
            st.success("All stages recorded for this batch.")
        else:
            stage_choice = st.selectbox("Stage to Record", avail_stages, key="stage_choice")

            if done_stages and sel_batch.stages:
                default_in = float(sel_batch.stages[-1].output_quantity)
            elif sel_batch.planned_input_qty:
                default_in = float(sel_batch.planned_input_qty)
            else:
                default_in = 0.001

            section(f"Record {stage_choice.upper()} Stage", "🔧")
            with st.form("record_stage"):
                c1, c2 = st.columns(2)
                with c1:
                    stage_in  = st.number_input(
                        "Input Quantity (kg) *", value=default_in, min_value=0.001, step=0.001, format="%.3f"
                    )
                    stage_out = st.number_input(
                        "Output Quantity (kg) *", min_value=0.001, max_value=float(stage_in),
                        step=0.001, format="%.3f",
                    )
                with c2:
                    stage_date  = st.date_input("Stage Date", value=date.today(), key="stage_dt")
                    stage_notes = st.text_area("Notes", height=68, key="stage_notes")

                if stage_in > 0 and stage_out > 0:
                    loss_kg  = stage_in - stage_out
                    loss_pct = loss_kg / stage_in * 100
                    thresh   = STAGE_THRESH.get(stage_choice, 20.0)
                    color    = "red" if loss_pct > thresh else ("orange" if loss_pct > thresh * 0.8 else "green")
                    st.markdown(
                        f"<span style='color:{color};font-weight:600;'>"
                        f"Loss preview: {loss_kg:.3f} kg ({loss_pct:.2f}%) — threshold {thresh}%"
                        f"</span>",
                        unsafe_allow_html=True,
                    )

                sub_stage = st.form_submit_button("✅ Record Stage", type="primary", use_container_width=True)

            if sub_stage:
                db_op = get_db()
                try:
                    data = ProductionStageCreate(
                        batch_id=sel_batch_id,
                        stage=stage_choice,
                        input_quantity=Decimal(str(stage_in)),
                        output_quantity=Decimal(str(stage_out)),
                        stage_date=stage_date,
                        notes=stage_notes.strip() or None,
                    )
                    ProductionStageService(db_op).record_stage(data)
                    db_op.commit()
                    st.success(f"✅ {stage_choice.upper()} stage recorded!")
                    st.rerun()
                except Exception as e:
                    db_op.rollback()
                    show_alert(str(e), "critical")
                finally:
                    db_op.close()
