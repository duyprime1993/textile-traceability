"""
Textile Traceability – Streamlit main entry point
"""

from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from ui.helpers import inject_css, sidebar_logo
from ui.db import get_db

st.set_page_config(
    page_title="Textile Traceability",
    page_icon="🧵",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()
sidebar_logo()

st.sidebar.markdown("""
<div style="font-size:13px; opacity:0.85; padding:0 4px;">
Navigate using the pages below
</div>
""", unsafe_allow_html=True)

st.title("🧵 Textile Traceability System")
st.markdown(
    "**GRS · GOTS · RCS · OCS** — Volume Reconciliation & Transaction Certificate Management"
)

col1, col2, col3 = st.columns(3)
with col1:
    st.info("📊 **Dashboard** — KPIs & alerts")
with col2:
    st.info("📥 **In TC** — Purchase certificates")
with col3:
    st.info("📤 **Out TC** — Sales certificates")

col4, col5, col6 = st.columns(3)
with col4:
    st.info("🏭 **Production** — Batch & stages")
with col5:
    st.info("⚖️ **Mass Balance** — GRS reconciliation")
with col6:
    st.info("📋 **Reports** — Excel export")

st.markdown("---")
st.caption("Use the sidebar to navigate between pages.")
