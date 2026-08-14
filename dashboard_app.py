"""Entry point for the Inflation Compass Streamlit app.

Run with: streamlit run dashboard_app.py
"""

import streamlit as st

st.set_page_config(page_title="Inflation Compass", layout="wide")

st.markdown(
    """
    <style>
    .ic-fixed-title {
        position: fixed; top: 0.85rem; left: 4rem; z-index: 1000000;
        font-size: 1.15rem; font-weight: 600; pointer-events: none;
    }
    </style>
    <div class="ic-fixed-title">Quant Strategy Dashboards</div>
    """,
    unsafe_allow_html=True,
)

pages = [
    st.Page("views/dashboard.py", title="Inflation Compass · 대시보드"),
    st.Page("views/position.py", title="Inflation Compass · 현재 포지션"),
    st.Page("views/methodology.py", title="Inflation Compass · 전략 설명"),
    st.Page("views/pct_dashboard.py", title="Percentile Channels · 대시보드", default=True),
    st.Page("views/pct_position.py", title="Percentile Channels · 현재 포지션"),
    st.Page("views/pct_methodology.py", title="Percentile Channels · 전략 설명"),
    st.Page("views/pension.py", title="연금 운용 · IC 50/25/25"),
]
st.navigation(pages).run()
