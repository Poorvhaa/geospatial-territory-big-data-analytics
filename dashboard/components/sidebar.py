"""Sidebar Component for Territory Intelligence BI Platform.

Renders navigation, platform branding, dataset provenance metadata, and explicit
cache refresh controls.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

from dashboard.services.data_loader import clear_cache

PAGES = [
    ("📊 Overview", "overview"),
    ("⚡ Live Simulation", "live_simulation"),
    ("🗺️ Territory Map", "territory_map"),
    ("🏆 Leaderboard", "leaderboard"),
    ("🔥 Hotspot Analysis", "hotspot_analysis"),
    ("🛡️ Cheat Detection", "cheat_detection"),
    ("📈 Activity Analytics", "activity_analytics"),
    ("🏃 Runner Explorer", "runner_explorer"),
]


def render_sidebar(report_metadata: Optional[Dict[str, Any]] = None) -> str:
    """Render sidebar navigation, branding, and provenance metadata.

    Args:
        report_metadata: Loaded JSON execution report with timestamps and stats.

    Returns:
        Selected page identifier key string.
    """
    report = report_metadata or {}

    with st.sidebar:
        # Branding Header
        st.markdown(
            """
            <div class="sidebar-brand">
                <h1>🗺️ TERRITORY INTELLIGENCE</h1>
                <p>Geospatial Big Data Analytics Platform</p>
                <div class="system-badge">⚡ Day 3 BI Production Dashboard</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Page Navigation
        st.markdown("### Navigation")
        page_labels = [p[0] for p in PAGES]
        page_keys = [p[1] for p in PAGES]

        selected_label = st.radio(
            "Select View",
            options=page_labels,
            index=0,
            label_visibility="collapsed",
        )
        selected_page = page_keys[page_labels.index(selected_label)]

        st.markdown("---")

        # Provenance & Metadata Panel
        st.markdown("### System Provenance")

        exec_time = report.get("execution_timestamp", "2026-10-26T19:00:27Z")
        total_records = report.get("ingestion_stats", {}).get("total_records", 100000)
        h3_res = report.get("configuration", {}).get("h3_resolution", 9)

        st.markdown(
            f"""
            <div style="font-size: 0.78rem; color: #94A3B8; background: #151E30; padding: 0.75rem; border-radius: 6px; border: 1px solid rgba(255,255,255,0.06); line-height: 1.6;">
                <div><strong style="color: #F8FAFC;">Data Mode:</strong> <span style="color: #38BDF8;">Batch Analytics</span></div>
                <div><strong style="color: #F8FAFC;">Dataset:</strong> Chicago Loop GPS</div>
                <div><strong style="color: #F8FAFC;">GPS Records:</strong> {total_records:,}</div>
                <div><strong style="color: #F8FAFC;">H3 Spatial Res:</strong> Level {h3_res} (~0.1 km²)</div>
                <div style="margin-top: 0.25rem; font-size: 0.72rem; color: #64748B;">
                    <strong>Last Pipeline Run:</strong><br/>{exec_time}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("")

        # Cache Refresh Action
        if st.button("🔄 Refresh Data", use_container_width=True, help="Invalidate caches and reload Parquet tables"):
            clear_cache()
            st.success("Caches cleared. Reloading...")
            st.rerun()

        st.markdown(
            """
            <div style="font-size: 0.7rem; color: #64748B; text-align: center; margin-top: 1rem;">
                Territory Intelligence v0.3.0<br/>
                Apache PySpark • Uber H3 • Streamlit • Folium
            </div>
            """,
            unsafe_allow_html=True,
        )

    return selected_page
