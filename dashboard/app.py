"""TERRITORY INTELLIGENCE - BI Production Dashboard (Day 3 Implementation).

Real-Time Territory Control and Hotspot Analysis Using Geospatial Big Data.
An interactive, high-performance Business Intelligence analytics platform built with
Streamlit, Plotly, Folium, and Uber H3.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys

# Ensure repository root is on sys.path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import streamlit as st

from dashboard.components.sidebar import render_sidebar
from dashboard.pages.activity_analytics import render_activity_analytics_page
from dashboard.pages.cheat_detection import render_cheat_detection_page
from dashboard.pages.hotspot_analysis import render_hotspot_analysis_page
from dashboard.pages.leaderboard import render_leaderboard_page
from dashboard.pages.live_simulation import render_live_simulation_page
from dashboard.pages.overview import render_overview_page
from dashboard.pages.runner_explorer import render_runner_explorer_page
from dashboard.pages.territory_map import render_territory_map_page
from dashboard.services.data_loader import load_all_datasets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Dashboard")

# Configure Streamlit page layout
st.set_page_config(
    page_title="TERRITORY INTELLIGENCE",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_custom_css() -> None:
    """Load and inject custom dark theme styling into the Streamlit app."""
    css_path = Path(__file__).resolve().parent / "assets" / "custom.css"
    if css_path.exists():
        with open(css_path, "r", encoding="utf-8") as f:
            css_content = f.read()
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)


def main() -> None:
    """Main application lifecycle and page routing entrypoint."""
    inject_custom_css()

    # Load preaggregated pipeline datasets
    with st.spinner("Loading analytical tables..."):
        datasets = load_all_datasets()

    report_meta = datasets.get("report", {})

    # Render sidebar and acquire selected page key
    selected_page = render_sidebar(report_meta)

    # Route to selected page
    if selected_page == "overview":
        render_overview_page(datasets)
    elif selected_page == "live_simulation":
        render_live_simulation_page(datasets)
    elif selected_page == "territory_map":
        render_territory_map_page(datasets)
    elif selected_page == "leaderboard":
        render_leaderboard_page(datasets)
    elif selected_page == "hotspot_analysis":
        render_hotspot_analysis_page(datasets)
    elif selected_page == "cheat_detection":
        render_cheat_detection_page(datasets)
    elif selected_page == "activity_analytics":
        render_activity_analytics_page(datasets)
    elif selected_page == "runner_explorer":
        render_runner_explorer_page(datasets)
    else:
        render_overview_page(datasets)


if __name__ == "__main__":
    main()
