"""
Shared helpers, CSS, và formatters cho Streamlit UI
Shared helpers, CSS, and formatters for Streamlit UI
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional
import streamlit as st


# ─────────────────────────────────────────────────────────────────────────────
# Global CSS
# ─────────────────────────────────────────────────────────────────────────────

GLOBAL_CSS = """
<style>
/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1F4E79 0%, #2E75B6 100%);
}
[data-testid="stSidebar"] * { color: #FFFFFF !important; }
[data-testid="stSidebar"] .stRadio label { font-size: 15px; padding: 4px 0; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.3); }

/* ── Metric cards ── */
div[data-testid="metric-container"] {
    background   : #FFFFFF;
    border       : 1px solid #E2E8F0;
    border-radius: 12px;
    padding      : 16px 20px;
    box-shadow   : 0 2px 8px rgba(31,78,121,0.08);
}
div[data-testid="metric-container"] label { font-size: 13px !important; color: #64748B !important; }
div[data-testid="metric-container"] div[data-testid="stMetricValue"] { font-size: 28px !important; font-weight: 700; color: #1F4E79; }

/* ── Status badges ── */
.badge-pass    { background:#E2EFDA; color:#276221; padding:3px 10px; border-radius:20px; font-weight:600; font-size:12px; }
.badge-warning { background:#FFEB9C; color:#7D5A00; padding:3px 10px; border-radius:20px; font-weight:600; font-size:12px; }
.badge-fail    { background:#FFC7CE; color:#9C0006; padding:3px 10px; border-radius:20px; font-weight:600; font-size:12px; }
.badge-pending { background:#DBEAFE; color:#1E40AF; padding:3px 10px; border-radius:20px; font-weight:600; font-size:12px; }
.badge-active  { background:#D1FAE5; color:#065F46; padding:3px 10px; border-radius:20px; font-weight:600; font-size:12px; }
.badge-issued  { background:#D1FAE5; color:#065F46; padding:3px 10px; border-radius:20px; font-weight:600; font-size:12px; }
.badge-draft   { background:#E5E7EB; color:#374151; padding:3px 10px; border-radius:20px; font-weight:600; font-size:12px; }
.badge-cancelled { background:#FEE2E2; color:#991B1B; padding:3px 10px; border-radius:20px; font-weight:600; font-size:12px; }

/* ── Section header ── */
.section-header {
    background   : #1F4E79;
    color        : #FFFFFF;
    padding      : 8px 18px;
    border-radius: 8px;
    font-weight  : 600;
    font-size    : 15px;
    margin-bottom: 12px;
}

/* ── Alert boxes ── */
.alert-critical { background:#FEF2F2; border-left:4px solid #DC2626; padding:10px 16px; border-radius:6px; margin:6px 0; }
.alert-warning  { background:#FFFBEB; border-left:4px solid #D97706; padding:10px 16px; border-radius:6px; margin:6px 0; }
.alert-info     { background:#EFF6FF; border-left:4px solid #2563EB; padding:10px 16px; border-radius:6px; margin:6px 0; }

/* ── Progress bar (TC utilization) ── */
.util-bar-wrap { background:#E5E7EB; border-radius:99px; height:10px; width:100%; margin-top:4px; }
.util-bar      { background:#1F4E79; border-radius:99px; height:10px; }

/* ── Table tweaks ── */
.stDataFrame { border-radius: 10px; overflow: hidden; }

/* ── Form sections ── */
.form-section { background:#F8FAFC; border:1px solid #E2E8F0; border-radius:10px; padding:16px; margin-bottom:12px; }
</style>
"""


def inject_css() -> None:
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Badges / Formatters
# ─────────────────────────────────────────────────────────────────────────────

def badge(text: str, cls: str = "pending") -> str:
    """Trả về HTML badge / Return HTML badge"""
    key = text.lower().replace(" ", "_").replace("-", "_")
    cls_map = {
        "pass"          : "pass",
        "warning"       : "warning",
        "fail"          : "fail",
        "pending"       : "pending",
        "active"        : "active",
        "issued"        : "issued",
        "draft"         : "draft",
        "cancelled"     : "cancelled",
        "partially_used": "warning",
        "fully_used"    : "fail",
        "in_progress"   : "active",
        "completed"     : "pass",
        "planned"       : "pending",
    }
    css = cls_map.get(key, cls)
    return f'<span class="badge-{css}">{text.upper()}</span>'


def fmt_kg(val: Any, show_unit: bool = True) -> str:
    """Format số kg / Format kg number"""
    if val is None:
        return "—"
    try:
        f = float(val)
        s = f"{f:,.3f}"
        return f"{s} kg" if show_unit else s
    except Exception:
        return str(val)


def fmt_pct(val: Any) -> str:
    """Format phần trăm / Format percentage"""
    if val is None:
        return "—"
    try:
        return f"{float(val):.2f}%"
    except Exception:
        return str(val)


def status_color(status: str) -> str:
    """Màu nền theo status / Background color for status"""
    return {
        "PASS"    : "#E2EFDA",
        "WARNING" : "#FFEB9C",
        "FAIL"    : "#FFC7CE",
    }.get(status, "#DBEAFE")


# ─────────────────────────────────────────────────────────────────────────────
# Reusable UI components
# ─────────────────────────────────────────────────────────────────────────────

def section(title: str, icon: str = "") -> None:
    """Vẽ section header / Draw section header"""
    st.markdown(f'<div class="section-header">{icon}  {title}</div>',
                unsafe_allow_html=True)


def kpi_row(metrics: list[dict]) -> None:
    """
    Vẽ hàng KPI cards / Draw KPI metric row
    metrics = [{"label": "...", "value": "...", "delta": "..."}, ...]
    """
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            st.metric(
                label = m["label"],
                value = m["value"],
                delta = m.get("delta"),
                delta_color = m.get("delta_color", "normal"),
            )


def show_alert(text: str, level: str = "info") -> None:
    """Hiển thị alert box / Display alert box"""
    css = {"critical": "alert-critical", "warning": "alert-warning"}.get(level, "alert-info")
    icon = {"critical": "🚨", "warning": "⚠️"}.get(level, "ℹ️")
    st.markdown(f'<div class="{css}">{icon} {text}</div>', unsafe_allow_html=True)


def util_bar(pct: float, label: str = "") -> None:
    """Progress bar cho TC utilization / Progress bar for TC utilization"""
    pct_clamped = min(max(pct, 0), 100)
    color = "#DC2626" if pct_clamped > 95 else ("#D97706" if pct_clamped > 75 else "#1F4E79")
    html = f"""
    <div style="font-size:12px; color:#64748B; margin-bottom:2px;">
        {label}  <strong style="color:{color}">{pct_clamped:.1f}%</strong>
    </div>
    <div class="util-bar-wrap">
        <div class="util-bar" style="width:{pct_clamped}%; background:{color};"></div>
    </div>"""
    st.markdown(html, unsafe_allow_html=True)


def empty_state(message: str, icon: str = "📭") -> None:
    """Hiển thị trạng thái rỗng / Display empty state"""
    st.markdown(
        f"""<div style="text-align:center; padding:48px; color:#94A3B8;">
            <div style="font-size:48px;">{icon}</div>
            <div style="font-size:16px; margin-top:12px;">{message}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def confirm_dialog(key: str, label: str = "Xác nhận xoá / Confirm delete") -> bool:
    """
    Nút xác nhận hai bước / Two-step confirm button
    Returns True nếu user đã confirm
    """
    if st.session_state.get(f"confirm_{key}"):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✓ Xác nhận / Yes, confirm", key=f"yes_{key}", type="primary"):
                st.session_state[f"confirm_{key}"] = False
                return True
        with col2:
            if st.button("✗ Huỷ / Cancel", key=f"no_{key}"):
                st.session_state[f"confirm_{key}"] = False
        return False
    else:
        if st.button(label, key=f"ask_{key}"):
            st.session_state[f"confirm_{key}"] = True
            st.rerun()
        return False


def sidebar_logo() -> None:
    """Logo và title trong sidebar / Logo and title in sidebar"""
    st.sidebar.markdown("""
    <div style="text-align:center; padding:20px 10px 10px;">
        <div style="font-size:36px;">🧵</div>
        <div style="font-size:16px; font-weight:700; letter-spacing:0.5px;">
            Textile Traceability
        </div>
        <div style="font-size:11px; opacity:0.8; margin-top:2px;">
            GRS · GOTS · RCS · OCS
        </div>
    </div>
    <hr style="margin:10px 0; border-color:rgba(255,255,255,0.3);">
    """, unsafe_allow_html=True)
