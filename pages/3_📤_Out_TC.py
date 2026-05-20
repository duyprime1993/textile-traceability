"""
Out TC – List, Issue (with In TC allocation), Cancel
"""

from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

import streamlit as st

from ui.helpers import inject_css, sidebar_logo, section, badge, fmt_kg, show_alert, empty_state, confirm_dialog
from ui.db import get_db
from app.models import TCOut, TCIn, Buyer
from app.schemas.tc import TCOutCreate, TCOutIssueRequest, TCInAllocation
from app.crud.tc import TCOutService

st.set_page_config(page_title="Out TC – Textile Traceability", page_icon="📤", layout="wide")
inject_css()
sidebar_logo()

st.title("📤 Out TC Management")
st.markdown("Manage certified product sale Transaction Certificates.")

tab_list, tab_create, tab_issue = st.tabs(["📋 TC List", "➕ Create Draft", "📨 Issue TC"])

# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 – List
# ─────────────────────────────────────────────────────────────────────────────
with tab_list:
    db = get_db()
    try:
        tc_outs = db.query(TCOut).order_by(TCOut.created_at.desc()).all()

        if not tc_outs:
            empty_state("No Out TCs yet. Create a draft first, then issue it.")
        else:
            status_filter = st.selectbox(
                "Filter by status",
                ["All", "draft", "issued", "cancelled"],
                key="outtc_status",
            )
            filtered = tc_outs if status_filter == "All" else [t for t in tc_outs if t.status == status_filter]

            for t in filtered:
                with st.expander(
                    f"{t.tc_number}  |  {t.certification_standard}  |  "
                    f"{fmt_kg(t.certified_quantity)}  |  {t.status.upper()}",
                    expanded=False,
                ):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown(f"**Buyer:** {t.buyer.name if t.buyer else '—'}")
                        # Derive material from first linkage (TCOut has no direct material FK)
                        mat_name = (
                            t.linkages[0].tc_in.material.name
                            if t.linkages and t.linkages[0].tc_in
                            else "—"
                        )
                        st.markdown(f"**Material:** {mat_name}")
                        st.markdown(f"**Standard:** {t.certification_standard}")
                    with c2:
                        st.markdown(f"**Issue Date:** {t.issue_date or '—'}")
                        st.markdown(f"**Shipment Date:** {t.shipment_date or '—'}")
                        st.markdown(f"**Status:** {badge(t.status)}", unsafe_allow_html=True)
                    with c3:
                        st.markdown(f"**Certified Qty:** {fmt_kg(t.certified_quantity)}")
                        st.markdown(f"**Product Name:** {t.product_name or '—'}")
                        st.markdown(f"**Invoice No.:** {t.invoice_number or '—'}")

                    if t.linkages:
                        st.markdown("**In TC Allocations:**")
                        import pandas as pd
                        link_rows = [
                            {
                                "In TC": lk.tc_in.tc_number if lk.tc_in else str(lk.tc_in_id),
                                "Allocated (kg)": fmt_kg(lk.allocated_quantity),
                                "Allocation %": f"{float(lk.allocation_pct or 0):.2f}%",
                            }
                            for lk in t.linkages
                        ]
                        st.dataframe(pd.DataFrame(link_rows), use_container_width=True, hide_index=True)

                    if t.notes:
                        st.caption(f"Notes: {t.notes}")

                    if t.status == "issued":
                        st.markdown("---")
                        if confirm_dialog(f"cancel_out_{t.id}", "🗑️ Cancel this Out TC"):
                            db_op = get_db()
                            try:
                                TCOutService(db_op).cancel(t.id)
                                db_op.commit()
                                show_alert(f"Out TC {t.tc_number} cancelled and In TC stock restored.", "info")
                                st.rerun()
                            except Exception as e:
                                db_op.rollback()
                                show_alert(str(e), "critical")
                            finally:
                                db_op.close()
    finally:
        db.close()

# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 – Create Draft
# ─────────────────────────────────────────────────────────────────────────────
with tab_create:
    db2 = get_db()
    try:
        buyers = db2.query(Buyer).filter(Buyer.is_active == True).all()
    finally:
        db2.close()

    if not buyers:
        show_alert("Need at least one active Buyer.", "warning")
    else:
        with st.form("create_out_tc"):
            section("Out TC Details", "📄")
            c1, c2 = st.columns(2)
            with c1:
                out_tc_number = st.text_input("TC Number *", placeholder="TC-OUT-2024-001")
                buyer_id = st.selectbox(
                    "Buyer *",
                    options=[b.id for b in buyers],
                    format_func=lambda i: next(b.name for b in buyers if b.id == i),
                )
                out_standard = st.selectbox("Certification Standard *", ["GRS", "GOTS", "RCS", "OCS"], key="out_std")
            with c2:
                out_qty = st.number_input(
                    "Certified Quantity (kg) *", min_value=0.001, step=0.001, format="%.3f", key="out_qty"
                )
                product_name = st.text_input("Product Name *", placeholder="GRS-certified T-shirt")
                out_issue_date = st.date_input("Issue Date *", value=date.today(), key="out_issue_dt")

            out_notes = st.text_area("Notes", height=70, key="out_notes")
            sub_create = st.form_submit_button("✅ Create Draft", type="primary", use_container_width=True)

        if sub_create:
            if not out_tc_number.strip():
                show_alert("TC Number required.", "critical")
            elif not product_name.strip():
                show_alert("Product Name required.", "critical")
            elif out_qty <= 0:
                show_alert("Quantity must be > 0.", "critical")
            else:
                db_op = get_db()
                try:
                    data = TCOutCreate(
                        tc_number=out_tc_number.strip(),
                        buyer_id=buyer_id,
                        certification_standard=out_standard,
                        certified_quantity=Decimal(str(out_qty)),
                        product_name=product_name.strip(),
                        issue_date=out_issue_date,
                        notes=out_notes.strip() or None,
                    )
                    TCOutService(db_op).create(data)
                    db_op.commit()
                    st.success(f"✅ Draft **{out_tc_number}** created. Go to 'Issue TC' tab to allocate and issue.")
                    st.rerun()
                except Exception as e:
                    db_op.rollback()
                    show_alert(str(e), "critical")
                finally:
                    db_op.close()

# ─────────────────────────────────────────────────────────────────────────────
# Tab 3 – Issue
# ─────────────────────────────────────────────────────────────────────────────
with tab_issue:
    db3 = get_db()
    try:
        drafts = db3.query(TCOut).filter(TCOut.status == "draft").all()
        tc_ins = db3.query(TCIn).filter(TCIn.status.in_(["active", "partially_used"])).all()
    finally:
        db3.close()

    if not drafts:
        empty_state("No draft Out TCs to issue. Create a draft first.")
    elif not tc_ins:
        show_alert("No available In TCs with remaining certified stock.", "warning")
    else:
        selected_draft_id = st.selectbox(
            "Select Draft Out TC",
            options=[d.id for d in drafts],
            format_func=lambda i: next(
                f"{d.tc_number} – {fmt_kg(d.certified_quantity)}" for d in drafts if d.id == i
            ),
        )
        draft = next(d for d in drafts if d.id == selected_draft_id)

        st.markdown(f"**Quantity to allocate:** {fmt_kg(draft.certified_quantity)}")

        section("In TC Allocations", "📥")
        allocations: list[dict] = []
        total_allocated = 0.0

        for tc in tc_ins:
            remaining = float(tc.quantity_remaining)
            with st.expander(f"{tc.tc_number} — remaining {fmt_kg(tc.quantity_remaining)}", expanded=False):
                alloc = st.number_input(
                    f"Allocate from {tc.tc_number} (max {remaining:.3f} kg)",
                    min_value=0.0,
                    max_value=remaining,
                    value=0.0,
                    step=0.001,
                    format="%.3f",
                    key=f"alloc_{selected_draft_id}_{tc.id}",
                )
                if alloc > 0:
                    allocations.append({"tc_in_id": tc.id, "quantity": alloc})
                    total_allocated += alloc

        st.markdown(
            f"**Total allocated:** {total_allocated:,.3f} kg  |  "
            f"**Required:** {float(draft.certified_quantity):,.3f} kg"
        )

        if st.button("📨 Issue Out TC", type="primary", use_container_width=True):
            if not allocations:
                show_alert("Allocate at least one In TC.", "critical")
            elif abs(total_allocated - float(draft.certified_quantity)) > 0.001:
                show_alert(
                    f"Total allocated ({total_allocated:.3f} kg) must match TC quantity "
                    f"({float(draft.certified_quantity):.3f} kg).",
                    "critical",
                )
            else:
                db_op = get_db()
                try:
                    alloc_objs = [
                        TCInAllocation(
                            tc_in_id=a["tc_in_id"],
                            allocated_quantity=Decimal(str(a["quantity"])),
                        )
                        for a in allocations
                    ]
                    req = TCOutIssueRequest(
                        tc_out_id=draft.id,
                        allocations=alloc_objs,
                    )
                    TCOutService(db_op).issue(req)
                    db_op.commit()
                    st.success(f"✅ Out TC **{draft.tc_number}** issued successfully!")
                    st.rerun()
                except Exception as e:
                    db_op.rollback()
                    show_alert(str(e), "critical")
                finally:
                    db_op.close()
