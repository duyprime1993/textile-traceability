"""
In TC – List, Create, View Detail, Cancel
"""

from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

import streamlit as st

from ui.helpers import inject_css, sidebar_logo, section, badge, fmt_kg, show_alert, empty_state, confirm_dialog, util_bar
from ui.db import get_db
from app.models import TCIn, Supplier, Material
from app.schemas.tc import TCInCreate
from app.crud.tc import TCInService

st.set_page_config(page_title="In TC – Textile Traceability", page_icon="📥", layout="wide")
inject_css()
sidebar_logo()

st.title("📥 In TC Management")
st.markdown("Manage certified material purchase Transaction Certificates.")

tab_list, tab_create = st.tabs(["📋 TC List", "➕ Create In TC"])

# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 – TC List
# ─────────────────────────────────────────────────────────────────────────────
with tab_list:
    db = get_db()
    try:
        tc_ins = db.query(TCIn).order_by(TCIn.issue_date.desc()).all()

        if not tc_ins:
            empty_state("No In TCs recorded yet. Use 'Create In TC' tab to add one.")
        else:
            col_f1, col_f2 = st.columns([2, 1])
            with col_f1:
                search = st.text_input("Search TC number / supplier", key="intc_search")
            with col_f2:
                status_filter = st.selectbox(
                    "Status filter",
                    ["All", "active", "partially_used", "fully_used", "cancelled"],
                    key="intc_status_filter",
                )

            filtered = tc_ins
            if search:
                q = search.lower()
                filtered = [t for t in filtered if q in t.tc_number.lower()
                            or (t.supplier and q in t.supplier.name.lower())]
            if status_filter != "All":
                filtered = [t for t in filtered if t.status == status_filter]

            st.markdown(f"**{len(filtered)}** record(s) found")

            for t in filtered:
                used  = float(t.certified_quantity - t.quantity_remaining)
                total = float(t.certified_quantity)
                pct   = (used / total * 100) if total else 0

                with st.expander(
                    f"{t.tc_number}  |  {t.certification_standard}  |  "
                    f"{fmt_kg(t.certified_quantity)}  |  {t.status.upper()}",
                    expanded=False,
                ):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown(f"**Supplier:** {t.supplier.name if t.supplier else '—'}")
                        st.markdown(f"**Material:** {t.material.name if t.material else '—'}")
                        st.markdown(f"**Standard:** {t.certification_standard}")
                    with c2:
                        st.markdown(f"**Issue Date:** {t.issue_date}")
                        st.markdown(f"**Expiry Date:** {t.expiry_date or '—'}")
                        st.markdown(f"**Status:** {badge(t.status)}", unsafe_allow_html=True)
                    with c3:
                        st.markdown(f"**Certified Qty:** {fmt_kg(t.certified_quantity)}")
                        st.markdown(f"**Remaining:** {fmt_kg(t.quantity_remaining)}")
                        st.markdown(f"**Used:** {used:,.3f} kg ({pct:.1f}%)")

                    util_bar(pct, "Utilization")

                    if t.notes:
                        st.caption(f"Notes: {t.notes}")

                    if t.status in ("active", "partially_used"):
                        st.markdown("---")
                        if confirm_dialog(f"cancel_tc_{t.id}", "🗑️ Cancel this TC"):
                            db_op = get_db()
                            try:
                                TCInService(db_op).cancel(t.id)
                                db_op.commit()
                                show_alert(f"TC {t.tc_number} cancelled.", "info")
                                st.rerun()
                            except Exception as e:
                                db_op.rollback()
                                show_alert(str(e), "critical")
                            finally:
                                db_op.close()
    finally:
        db.close()

# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 – Create
# ─────────────────────────────────────────────────────────────────────────────
with tab_create:
    db2 = get_db()
    try:
        suppliers = db2.query(Supplier).filter(Supplier.is_active == True).all()
        materials = db2.query(Material).filter(Material.is_active == True).all()
    finally:
        db2.close()

    if not suppliers or not materials:
        show_alert("You need at least one active Supplier and one active Material before creating an In TC.", "warning")
        st.stop()

    with st.form("create_in_tc"):
        section("Transaction Certificate Details", "📄")
        c1, c2 = st.columns(2)
        with c1:
            tc_number = st.text_input("TC Number *", placeholder="TC-IN-2024-001")
            supplier_id = st.selectbox(
                "Supplier *",
                options=[s.id for s in suppliers],
                format_func=lambda i: next(s.name for s in suppliers if s.id == i),
            )
            certification_standard = st.selectbox(
                "Certification Standard *",
                ["GRS", "GOTS", "RCS", "OCS"],
            )
        with c2:
            certified_quantity = st.number_input(
                "Certified Quantity (kg) *", min_value=0.001, step=0.001, format="%.3f"
            )
            material_id = st.selectbox(
                "Material *",
                options=[m.id for m in materials],
                format_func=lambda i: next(m.name for m in materials if m.id == i),
            )
            issue_date = st.date_input("Issue Date *", value=date.today())

        c3, c4 = st.columns(2)
        with c3:
            expiry_date = st.date_input("Expiry Date (TC valid until)", value=None)
        with c4:
            notes = st.text_area("Notes", height=80)

        submitted = st.form_submit_button("✅ Create In TC", type="primary", use_container_width=True)

    if submitted:
        if not tc_number.strip():
            show_alert("TC Number is required.", "critical")
        elif certified_quantity <= 0:
            show_alert("Certified Quantity must be > 0.", "critical")
        else:
            db_op = get_db()
            try:
                data = TCInCreate(
                    tc_number=tc_number.strip(),
                    supplier_id=supplier_id,
                    material_id=material_id,
                    certification_standard=certification_standard,
                    certified_quantity=Decimal(str(certified_quantity)),
                    issue_date=issue_date,
                    expiry_date=expiry_date,
                    notes=notes.strip() or None,
                )
                TCInService(db_op).create(data)
                db_op.commit()
                st.success(f"✅ In TC **{tc_number}** created successfully!")
                st.rerun()
            except Exception as e:
                db_op.rollback()
                show_alert(str(e), "critical")
            finally:
                db_op.close()
