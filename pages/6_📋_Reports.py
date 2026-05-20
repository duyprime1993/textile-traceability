"""
Reports – All 5 report types + Excel export
"""

from __future__ import annotations

import os, sys, io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date

import streamlit as st

from ui.helpers import inject_css, sidebar_logo, section, fmt_kg, fmt_pct, show_alert, empty_state
from ui.db import get_db
from app.models import Material, TCIn
from app.reports.annual import AnnualMassBalanceReport
from app.reports.traceability import TraceabilityReport
from app.reports.loss_analysis import LossAnalysisReport
from app.reports.stock_card import StockCardReport, StockSummaryReport
from app.reports.excel_export import ExcelExporter

st.set_page_config(page_title="Reports – Textile Traceability", page_icon="📋", layout="wide")
inject_css()
sidebar_logo()

st.title("📋 Reports & Export")
st.markdown("Generate GRS-compliant reports and download Excel workbooks.")

# ─────────────────────────────────────────────────────────────────────────────
# Shared parameters
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("⚙️ Report Parameters", expanded=True):
    db_p = get_db()
    try:
        materials = db_p.query(Material).filter(Material.is_active == True).all()
        tc_ins    = db_p.query(TCIn).order_by(TCIn.issue_date.desc()).all()
    finally:
        db_p.close()

    pc1, pc2, pc3 = st.columns(3)
    with pc1:
        param_year  = st.number_input("Year", min_value=2020, max_value=2030, value=date.today().year, key="rpt_year")
        param_start = st.date_input("Period Start", value=date(int(param_year), 1, 1), key="rpt_start")
    with pc2:
        param_end = st.date_input("Period End", value=date(int(param_year), 12, 31), key="rpt_end")
        param_std = st.selectbox("Standard", ["GRS", "GOTS", "RCS", "OCS"], key="rpt_std")
    with pc3:
        param_company = st.text_input("Company Name", value="Textile Factory", key="rpt_company")
        param_mat_id  = (
            st.selectbox(
                "Material",
                options=[m.id for m in materials],
                format_func=lambda i: next((m.name for m in materials if m.id == i), str(i)),
                key="rpt_mat",
            )
            if materials else None
        )

tab_annual, tab_stock, tab_trace, tab_loss, tab_excel = st.tabs([
    "📊 Annual MB", "📦 Stock Card", "🔗 Traceability", "📉 Loss Analysis", "📥 Excel Export"
])

# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 – Annual Mass Balance
# ─────────────────────────────────────────────────────────────────────────────
with tab_annual:
    section("Annual Mass Balance Report", "📊")
    include_monthly = st.checkbox("Include monthly breakdown", value=True, key="mb_monthly")

    if st.button("▶ Generate Annual MB", type="primary", key="gen_annual"):
        if not param_mat_id:
            show_alert("Select a material first.", "warning")
        else:
            with st.spinner("Generating..."):
                db_a = get_db()
                try:
                    rpt = AnnualMassBalanceReport(db_a)
                    result = rpt.generate(
                        period_start=param_start,
                        period_end=param_end,
                        certification_standard=param_std,
                        material_id=param_mat_id,
                        save_to_db=False,
                    )
                    monthly = (
                        rpt.generate_monthly_breakdown(
                            year=int(param_year),
                            certification_standard=param_std,
                            material_id=param_mat_id,
                        )
                        if include_monthly else []
                    )
                    st.session_state["rpt_annual"] = result
                    st.session_state["rpt_monthly"] = monthly
                    st.success("Report generated.")
                except Exception as e:
                    show_alert(str(e), "critical")
                    import traceback; st.code(traceback.format_exc())
                finally:
                    db_a.close()

    if "rpt_annual" in st.session_state:
        r = st.session_state["rpt_annual"]
        import pandas as pd

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Opening Stock",  fmt_kg(r.opening_stock))
        c2.metric("Purchased",      fmt_kg(r.certified_purchased))
        c3.metric("Sold",           fmt_kg(r.certified_sold))
        c4.metric("Closing Stock",  fmt_kg(r.closing_stock_total))

        diff_pct = float(r.difference_pct)
        color    = "red" if abs(diff_pct) > 2 else ("orange" if abs(diff_pct) > 0.5 else "green")
        st.markdown(
            f"<h4 style='color:{color}'>Status: {r.balance_status} &nbsp;|&nbsp; Difference: {diff_pct:+.4f}%</h4>",
            unsafe_allow_html=True,
        )

        monthly_rows = st.session_state.get("rpt_monthly", [])
        if monthly_rows:
            st.markdown("**Monthly Breakdown:**")
            df_m = pd.DataFrame([
                {
                    "Month"       : row.get("month_name", row.get("period_start", "")),
                    "Purchased"   : f"{row.get('certified_purchased_kg', 0):,.3f}",
                    "Sold"        : f"{row.get('certified_sold_kg', 0):,.3f}",
                    "Process Loss": f"{row.get('total_process_loss_kg', 0):,.3f}",
                    "Diff %"      : f"{row.get('difference_pct', 0):+.4f}%",
                    "Status"      : row.get("status", "—"),
                }
                for row in monthly_rows
            ])
            st.dataframe(df_m, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 – Stock Card
# ─────────────────────────────────────────────────────────────────────────────
with tab_stock:
    section("Stock Card Report", "📦")

    if st.button("▶ Generate Stock Card", type="primary", key="gen_stock"):
        if not param_mat_id:
            show_alert("Select a material first.", "warning")
        else:
            with st.spinner("Generating..."):
                db_s = get_db()
                try:
                    sc_result = StockCardReport(db_s).generate_by_material(
                        material_id=param_mat_id,
                        date_from=param_start,
                        date_to=param_end,
                    )
                    summary = StockSummaryReport(db_s).generate(
                        period_start=param_start,
                        period_end=param_end,
                    )
                    st.session_state["rpt_stock_card"]    = sc_result
                    st.session_state["rpt_stock_summary"] = summary
                    st.success("Stock card generated.")
                except Exception as e:
                    show_alert(str(e), "critical")
                finally:
                    db_s.close()

    if "rpt_stock_card" in st.session_state:
        sc      = st.session_state["rpt_stock_card"]
        summary = st.session_state.get("rpt_stock_summary", [])
        import pandas as pd

        if summary:
            st.markdown("**Stock Summary (all materials):**")
            df_sum = pd.DataFrame([
                {
                    "Material"     : f"{row.material_code} – {row.material_name}",
                    "Standard"     : row.certification_std,
                    "Opening (kg)" : fmt_kg(row.opening_stock),
                    "Received"     : fmt_kg(row.received_kg),
                    "Issued"       : fmt_kg(row.issued_production),
                    "Sold"         : fmt_kg(row.sold_kg),
                    "Closing (kg)" : fmt_kg(row.closing_stock),
                    "Status"       : row.status,
                }
                for row in summary
            ])
            st.dataframe(df_sum, use_container_width=True, hide_index=True)

        st.markdown(
            f"**Stock Card — {sc.material_code} {sc.material_name} "
            f"({sc.date_from} → {sc.date_to}):**"
        )
        st.markdown(
            f"Opening: **{fmt_kg(sc.opening_balance)}**  |  "
            f"Total In: **{fmt_kg(sc.total_in)}**  |  "
            f"Total Out: **{fmt_kg(sc.total_out)}**  |  "
            f"Closing: **{fmt_kg(sc.closing_balance)}**"
        )
        if sc.lines:
            df_sc = pd.DataFrame([
                {
                    "Date"         : str(l.date),
                    "Type"         : l.label or l.transaction_type,
                    "In TC"        : l.tc_in_number or "—",
                    "Out TC"       : l.tc_out_number or "—",
                    "Batch"        : l.batch_number or "—",
                    "Ref"          : l.reference_number or "—",
                    "In (kg)"      : f"{float(l.qty_in):,.3f}" if l.qty_in is not None else "—",
                    "Out (kg)"     : f"{float(l.qty_out):,.3f}" if l.qty_out is not None else "—",
                    "Balance (kg)" : f"{float(l.running_balance):,.3f}",
                }
                for l in sc.lines
            ])
            st.dataframe(df_sc, use_container_width=True, hide_index=True)
        else:
            empty_state("No transactions in this period.")

# ─────────────────────────────────────────────────────────────────────────────
# Tab 3 – Traceability
# ─────────────────────────────────────────────────────────────────────────────
with tab_trace:
    section("Traceability by In TC", "🔗")

    if not tc_ins:
        empty_state("No In TCs to trace.")
    else:
        sel_tc = st.selectbox(
            "Select In TC",
            options=[t.id for t in tc_ins],
            format_func=lambda i: next(
                f"{t.tc_number} – {fmt_kg(t.certified_quantity)}" for t in tc_ins if t.id == i
            ),
            key="trace_tc",
        )

        if st.button("▶ Generate Traceability", type="primary", key="gen_trace"):
            with st.spinner("Tracing..."):
                db_tr = get_db()
                try:
                    trace_result = TraceabilityReport(db_tr).generate(tc_in_id=sel_tc)
                    st.session_state["rpt_trace"] = trace_result
                    st.success("Traceability chain built.")
                except Exception as e:
                    show_alert(str(e), "critical")
                finally:
                    db_tr.close()

        if "rpt_trace" in st.session_state:
            tr = st.session_state["rpt_trace"]
            import pandas as pd

            c1, c2, c3 = st.columns(3)
            c1.metric("Certified Purchased", fmt_kg(tr.certified_qty))
            c2.metric("Total Sold",          fmt_kg(tr.total_sold_with_tc))
            c3.metric("Utilization",         f"{float(tr.utilization_pct):.2f}%")

            if tr.batches:
                st.markdown("**Production Batches:**")
                df_b = pd.DataFrame([
                    {
                        "Batch"       : b.batch_number,
                        "Product"     : b.product_name,
                        "Input (kg)"  : fmt_kg(b.actual_in) if b.actual_in else "—",
                        "Output (kg)" : fmt_kg(b.actual_out) if b.actual_out else "—",
                        "Loss (kg)"   : fmt_kg(b.total_loss_kg) if b.total_loss_kg else "—",
                        "Loss %"      : f"{float(b.total_loss_pct):.2f}%" if b.total_loss_pct else "—",
                        "Status"      : b.status.upper(),
                    }
                    for b in tr.batches
                ])
                st.dataframe(df_b, use_container_width=True, hide_index=True)

            if tr.linked_tc_outs:
                st.markdown("**Linked Out TCs:**")
                df_l = pd.DataFrame([
                    {
                        "Out TC"         : lk.tc_out_number,
                        "Buyer"          : lk.buyer_name,
                        "Allocated (kg)" : fmt_kg(lk.allocated_qty),
                        "Allocation %"   : f"{float(lk.allocation_pct):.2f}%" if lk.allocation_pct else "—",
                        "Status"         : lk.status.upper(),
                    }
                    for lk in tr.linked_tc_outs
                ])
                st.dataframe(df_l, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# Tab 4 – Loss Analysis
# ─────────────────────────────────────────────────────────────────────────────
with tab_loss:
    section("Production Loss Analysis", "📉")

    if st.button("▶ Generate Loss Analysis", type="primary", key="gen_loss"):
        with st.spinner("Analysing..."):
            db_l = get_db()
            try:
                loss_result = LossAnalysisReport(db_l).generate(
                    period_start=param_start,
                    period_end=param_end,
                    material_id=param_mat_id,
                )
                st.session_state["rpt_loss"] = loss_result
                st.success("Loss analysis done.")
            except Exception as e:
                show_alert(str(e), "critical")
            finally:
                db_l.close()

    if "rpt_loss" in st.session_state:
        lr = st.session_state["rpt_loss"]
        import pandas as pd

        if lr.stage_summaries:
            st.markdown("**Stage Summary:**")
            df_ss = pd.DataFrame([
                {
                    "Stage"       : s.stage.upper(),
                    "Batches"     : s.num_batches,
                    "Total In"    : fmt_kg(s.total_input_kg),
                    "Total Out"   : fmt_kg(s.total_output_kg),
                    "Total Loss"  : fmt_kg(s.total_loss_kg),
                    "Avg Loss %"  : f"{float(s.avg_loss_pct):.2f}%",
                    "Max Loss %"  : f"{float(s.max_loss_pct):.2f}%",
                    "Threshold"   : f"{float(s.threshold_pct):.0f}%",
                    "Exceeded?"   : "🔴 YES" if s.above_threshold else "🟢 NO",
                }
                for s in lr.stage_summaries
            ])
            st.dataframe(df_ss, use_container_width=True, hide_index=True)

        if lr.top_loss_batches:
            st.markdown("**Top Loss Batches (Top 10):**")
            df_tb = pd.DataFrame([
                {
                    "Batch"     : b.batch_number,
                    "Product"   : b.product_name,
                    "Loss (kg)" : fmt_kg(b.total_loss_kg),
                    "Loss %"    : f"{float(b.total_loss_pct):.2f}%",
                    "Start"     : str(b.start_date),
                }
                for b in lr.top_loss_batches
            ])
            st.dataframe(df_tb, use_container_width=True, hide_index=True)

        if lr.monthly_trend:
            st.markdown("**Monthly Loss Trend:**")
            df_mt = pd.DataFrame([
                {
                    "Month"      : row.year_month,
                    "Batches"    : row.num_batches,
                    "Total Loss" : fmt_kg(row.total_loss_kg),
                    "Avg Loss %" : f"{float(row.avg_loss_pct):.2f}%",
                }
                for row in lr.monthly_trend
            ])
            st.dataframe(df_mt, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# Tab 5 – Excel Export
# ─────────────────────────────────────────────────────────────────────────────
with tab_excel:
    section("Export Full GRS Excel Workbook", "📥")
    st.markdown(
        "Generates a multi-sheet Excel workbook: Annual MB, Monthly MB, Summary Stock, "
        "Stock Card, Traceability, Loss Analysis — GRS color scheme."
    )

    if not param_mat_id:
        show_alert("Select a material in the parameters section above.", "warning")
    else:
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            excel_tc_in_id = (
                st.selectbox(
                    "Traceability In TC (optional)",
                    options=[None] + [t.id for t in tc_ins],
                    format_func=lambda i: "— skip —" if i is None else next(
                        (f"{t.tc_number}" for t in tc_ins if t.id == i), str(i)
                    ),
                    key="excel_trace_tc",
                )
                if tc_ins else None
            )
        with col_e2:
            excel_filename = st.text_input(
                "Filename",
                value=f"GRS_Mass_Balance_{int(param_year)}.xlsx",
                key="excel_fname",
            )

        if st.button("📥 Generate & Download Excel", type="primary", use_container_width=True, key="gen_excel"):
            with st.spinner("Building workbook..."):
                db_e = get_db()
                try:
                    rpt = AnnualMassBalanceReport(db_e)
                    annual  = rpt.generate(
                        period_start=param_start,
                        period_end=param_end,
                        certification_standard=param_std,
                        material_id=param_mat_id,
                        save_to_db=False,
                    )
                    monthly = rpt.generate_monthly_breakdown(
                        year=int(param_year),
                        certification_standard=param_std,
                        material_id=param_mat_id,
                    )
                    stock_card = StockCardReport(db_e).generate_by_material(
                        material_id=param_mat_id,
                        date_from=param_start,
                        date_to=param_end,
                    )
                    summary = StockSummaryReport(db_e).generate(
                        period_start=param_start,
                        period_end=param_end,
                    )
                    trace = (
                        TraceabilityReport(db_e).generate(tc_in_id=excel_tc_in_id)
                        if excel_tc_in_id else None
                    )
                    loss = LossAnalysisReport(db_e).generate(
                        period_start=param_start,
                        period_end=param_end,
                        material_id=param_mat_id,
                    )

                    buf = ExcelExporter().export_full_workbook(
                        annual_mb=annual,
                        monthly_rows=monthly,
                        summary_rows=summary,
                        stock_card=stock_card,
                        traceability=trace,
                        loss_analysis=loss,
                        company_name=param_company,
                        period_start=param_start,
                        period_end=param_end,
                    )

                    st.download_button(
                        label=f"⬇️ Download {excel_filename}",
                        data=buf.getvalue(),
                        file_name=excel_filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
                    st.success("Workbook ready for download.")
                except Exception as e:
                    show_alert(str(e), "critical")
                    import traceback; st.code(traceback.format_exc())
                finally:
                    db_e.close()
