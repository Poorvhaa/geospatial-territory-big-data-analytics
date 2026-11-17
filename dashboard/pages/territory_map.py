"""Interactive Territory Map Page for Territory Intelligence BI Platform.

Displays full Uber H3 hexagonal polygon boundaries across Chicago Loop with
mode switching:
A. Territory Ownership: Color-coded by current runner with deterministic palette.
B. Activity Hotspots: Sequential gradient based on zone visit intensity.
C. Contested Zones: Sequential gradient based on takeover counts.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

from dashboard.components.maps import render_map_legend, render_territory_map
from dashboard.components.tables import render_data_table, render_empty_state
from dashboard.services.metrics import get_runner_color


def render_territory_map_page(datasets: Dict[str, Any]) -> None:
    """Render the Interactive H3 Geospatial Territory Map page."""
    st.markdown(
        """
        <div class="section-header">
            <div class="section-title">🗺️ Interactive Geospatial Territory Map</div>
            <div class="section-desc">Discrete Uber H3 hexagonal zones (Res 9, ~0.1 km²) with competitive conquest status, activity hotspots, and takeover intensity.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    curr_df = datasets.get("current_ownership")
    if curr_df is None or curr_df.empty:
        render_empty_state(
            title="Territory Dataset Unavailable",
            message="The current_ownership Parquet table was not found or contains no records.",
            icon="🗺️",
        )
        return

    # Prepare merged working dataset
    map_data = curr_df.copy()
    zone_stats = datasets.get("zone_statistics")
    if zone_stats is not None and not zone_stats.empty:
        # Merge total_visits if needed
        cols_to_use = [c for c in ["total_visits", "first_visit_time", "latest_visit_time"] if c in zone_stats.columns]
        if cols_to_use:
            map_data = map_data.merge(zone_stats[["h3_cell"] + cols_to_use], on="h3_cell", how="left")
            if "total_visits" in map_data.columns:
                map_data["total_visits"] = map_data["total_visits"].fillna(map_data["total_zone_claims"]).astype(int)

    # 1. Map Controls Bar
    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4, ctrl_col5 = st.columns([1.2, 1.1, 1.0, 0.9, 0.9])

    with ctrl_col1:
        mode = st.selectbox(
            "Visualization Mode (Layer)",
            options=["Territory Ownership", "Activity Heatmap", "Contested Zones", "Recent Captures"],
            index=0,
            help="Select the metric governing hexagon coloring and visual layer",
        )

    with ctrl_col2:
        all_runners = ["All Runners"] + sorted(map_data["current_owner_id"].dropna().unique().tolist())
        selected_runner = st.selectbox(
            "Filter / Highlight Runner",
            options=all_runners,
            index=0,
            help="Isolate or highlight zones owned by a specific runner",
        )
        runner_filter = None if selected_runner == "All Runners" else selected_runner

    with ctrl_col3:
        all_zones = ["All Zones"] + sorted(map_data["h3_cell"].unique().tolist())
        selected_zone = st.selectbox(
            "Inspect H3 Cell",
            options=all_zones,
            index=0,
            help="Zoom into and highlight a specific H3 hexagon",
        )
        zone_filter = None if selected_zone == "All Zones" else selected_zone

    with ctrl_col4:
        min_takeovers = st.number_input(
            "Min Takeovers",
            min_value=0,
            max_value=int(map_data["total_zone_takeovers"].max()),
            value=0,
            step=1,
            help="Filter visible zones by minimum takeover count",
        )

    with ctrl_col5:
        max_hex_choice = st.selectbox(
            "Max Hexagons",
            options=[50, 100, 200, 308, "All"],
            index=3,
            help="Configurable polygon display limit to optimize rendering performance",
        )
        max_polygons = 1000 if max_hex_choice == "All" else int(max_hex_choice)

    # Apply filters
    filtered_df = map_data.copy()
    if min_takeovers > 0:
        filtered_df = filtered_df[filtered_df["total_zone_takeovers"] >= min_takeovers]

    # Metrics summary strip
    total_visible_zones = min(len(filtered_df), max_polygons)
    unique_owners = filtered_df.head(max_polygons)["current_owner_id"].nunique()
    total_takeovers = int(filtered_df.head(max_polygons)["total_zone_takeovers"].sum())
    total_claims = int(filtered_df.head(max_polygons)["total_zone_claims"].sum())

    st.markdown(
        f"""
        <div style="display: flex; gap: 1.5rem; background: #151E30; padding: 0.6rem 1rem; border-radius: 6px; border: 1px solid rgba(255,255,255,0.06); margin-bottom: 0.75rem; font-size: 0.8rem;">
            <div><span style="color: #94A3B8;">Visible Zones:</span> <strong style="color: #38BDF8;">{total_visible_zones}</strong></div>
            <div><span style="color: #94A3B8;">Active Owners:</span> <strong style="color: #22C55E;">{unique_owners}</strong></div>
            <div><span style="color: #94A3B8;">Takeovers:</span> <strong style="color: #F59E0B;">{total_takeovers:,}</strong></div>
            <div><span style="color: #94A3B8;">Total Visits:</span> <strong style="color: #A855F7;">{total_claims:,}</strong></div>
            <div><span style="color: #94A3B8;">Layer:</span> <strong style="color: #38BDF8;">{mode}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if filtered_df.empty:
        render_empty_state(
            title="No Zones Match Filter Criteria",
            message=f"No H3 zones found with takeovers >= {min_takeovers}. Please lower the filter threshold.",
        )
        return

    # 2. Folium Map Render
    map_state = render_territory_map(
        zones_df=filtered_df,
        mode=mode,
        selected_runner_id=runner_filter,
        highlight_zone_id=zone_filter,
        height=560,
        max_hexagons=max_polygons,
    )

    # Render readable on-screen map legend (Phase 4 requirement)
    render_map_legend(mode)

    # 3. Zone Details Inspector Panel
    st.markdown("### 🔍 Zone Inspector & Detailed Audit")

    # If user selected a zone or clicked one on the map
    inspected_cell = zone_filter
    if not inspected_cell and runner_filter:
        runner_zones = filtered_df[filtered_df["current_owner_id"] == runner_filter]
        if not runner_zones.empty:
            inspected_cell = runner_zones.iloc[0]["h3_cell"]

    if inspected_cell and inspected_cell in map_data["h3_cell"].values:
        zone_row = map_data[map_data["h3_cell"] == inspected_cell].iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("H3 Cell ID", str(zone_row["h3_cell"]))
        with c2:
            st.metric("Current Owner", str(zone_row["current_owner_id"]))
        with c3:
            st.metric("Total Takeovers", int(zone_row["total_zone_takeovers"]))
        with c4:
            st.metric("Unique Runners", int(zone_row["unique_zone_runners"]))

        # Show historical visits for this zone from ownership_history
        hist_df = datasets.get("ownership_history")
        if hist_df is not None and not hist_df.empty:
            zone_hist = (
                hist_df[hist_df["h3_cell"] == inspected_cell]
                .sort_values(by="claim_timestamp", ascending=False)
                .head(10)[
                    [
                        "claim_id",
                        "runner_id",
                        "claim_timestamp",
                        "event_type",
                        "prev_runner_id",
                        "points_in_visit",
                    ]
                ]
            )
            st.markdown(f"**Recent Claims & Conquests in Zone {inspected_cell}:**")
            render_data_table(zone_hist)
    else:
        st.caption("Select an H3 Cell from the dropdown above to inspect its full historical conquest audit log.")


if __name__ == "__main__":
    from dashboard.app import inject_custom_css
    from dashboard.services.data_loader import load_all_datasets

    inject_custom_css()
    _datasets = load_all_datasets()
    render_territory_map_page(_datasets)

