"""Hotspot Analysis Page for Territory Intelligence BI Platform.

Analyzes geographic activity density, takeover contention, and composite
analytical Hotspot Scores across Uber H3 hexagonal zones.
"""

from __future__ import annotations

from typing import Any, Dict

import plotly.graph_objects as go
import streamlit as st

from dashboard.components.charts import apply_dark_theme
from dashboard.components.maps import render_territory_map
from dashboard.components.tables import render_data_table, render_empty_state
from dashboard.services.exports import generate_csv_download
from dashboard.services.metrics import calculate_hotspot_scores


def render_hotspot_analysis_page(datasets: Dict[str, Any]) -> None:
    """Render the Hotspot & Zone Contention Analysis page."""
    st.markdown(
        """
        <div class="section-header">
            <div class="section-title">🔥 H3 Geographic Hotspot & Contention Analysis</div>
            <div class="section-desc">Identifies high-density transit corridors, contested battlegrounds, and composite geospatial hotspot dynamics.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    zone_stats = datasets.get("zone_statistics")
    contested_df = datasets.get("contested_zones")
    curr_df = datasets.get("current_ownership")

    if zone_stats is None or zone_stats.empty:
        render_empty_state(
            title="Hotspot Analytics Unavailable",
            message="Zone statistics Parquet dataset is not available.",
            icon="🔥",
        )
        return

    # 1. Configurable Hotspot Score Formula Weights
    with st.expander("⚙️ Configure Custom Hotspot Score Formula", expanded=False):
        st.markdown(
            """
            The **Composite Hotspot Score** synthesizes three normalized kinematic metrics:
            $$\\text{Score} = w_{\\text{takeovers}} \\cdot \\hat{T} + w_{\\text{runners}} \\cdot \\hat{R} + w_{\\text{visits}} \\cdot \\hat{V}$$
            *(All components are normalized via zero-variance safe Min-Max scaling to $[0.0, 1.0]$)*
            """
        )
        w_c1, w_c2, w_c3 = st.columns(3)
        with w_c1:
            w_takeovers = st.slider("Takeover Weight (w_takeovers)", 0.0, 1.0, 0.40, 0.05)
        with w_c2:
            w_runners = st.slider("Unique Runners Weight (w_runners)", 0.0, 1.0, 0.35, 0.05)
        with w_c3:
            w_visits = st.slider("Visits Weight (w_visits)", 0.0, 1.0, 0.25, 0.05)

    # Compute Hotspot Scores
    hotspot_df = calculate_hotspot_scores(
        zone_stats,
        contested_df if contested_df is not None else zone_stats,
        w_takeovers=w_takeovers,
        w_runners=w_runners,
        w_visits=w_visits,
    )

    # Merge owner from current_ownership if available
    if curr_df is not None and not curr_df.empty:
        hotspot_df = hotspot_df.merge(
            curr_df[["h3_cell", "current_owner_id", "acquired_at"]],
            on="h3_cell",
            how="left",
        )

    # 2. Ranking Metric Selection
    metric_map = {
        "Composite Hotspot Score": "hotspot_score",
        "Most Contested (Takeovers)": "takeover_count",
        "Unique Runners Density": "unique_runners",
        "Visit Frequency": "total_visits",
    }

    c_metric, c_top = st.columns([2, 1])
    with c_metric:
        chosen_metric = st.selectbox(
            "Rank Zones By",
            options=list(metric_map.keys()),
            index=0,
            help="Select the metric for table and bar chart ranking",
        )
        rank_metric_col = metric_map[chosen_metric]

    with c_top:
        top_limit = st.selectbox("Top N Zones", options=[10, 20, 50, 100], index=1)

    sorted_hotspots = hotspot_df.sort_values(by=rank_metric_col, ascending=False).reset_index(drop=True)
    top_hotspots = sorted_hotspots.head(top_limit)

    # 3. Chart & Map Grid
    chart_col, map_col = st.columns([1.1, 1.3])

    with chart_col:
        # Horizontal bar chart of top zones
        chart_data = top_hotspots.head(15).iloc[::-1]
        fig_bar = go.Figure(
            go.Bar(
                x=chart_data[rank_metric_col],
                y=chart_data["h3_cell"],
                orientation="h",
                marker=dict(
                    color=chart_data[rank_metric_col],
                    colorscale="Plasma",
                    line=dict(color="rgba(255,255,255,0.15)", width=1),
                ),
                text=chart_data[rank_metric_col],
                textposition="outside",
            )
        )
        fig_bar.update_layout(
            title=dict(text=f"Top 15 Zones by {chosen_metric}", font=dict(size=12, color="#F8FAFC")),
            xaxis_title=chosen_metric,
            yaxis_title="",
        )
        st.plotly_chart(apply_dark_theme(fig_bar, height=440), use_container_width=True)

    with map_col:
        st.markdown("**Hexagonal Hotspot Spatial Map:**")
        render_territory_map(
            zones_df=sorted_hotspots,
            mode="Activity Hotspots" if rank_metric_col != "takeover_count" else "Contested Zones",
            height=400,
            max_hexagons=350,
        )

    # 4. Data-Driven Spatial Interpretation Summary (Phase 6 requirement)
    top_zone_entry = sorted_hotspots.iloc[0]
    top_z_cell = top_zone_entry["h3_cell"]
    top_z_takes = int(top_zone_entry.get("takeover_count", 0))
    top_z_runners = int(top_zone_entry.get("unique_runners", 0))
    top_z_visits = int(top_zone_entry.get("total_visits", 0))
    top_z_owner = str(top_zone_entry.get("current_owner_id", "Unknown"))
    top_z_score = float(top_zone_entry.get("hotspot_score", 0.0))

    st.markdown(
        f"""
        <div style="background: rgba(56, 189, 248, 0.08); border-left: 3px solid #38BDF8; padding: 0.75rem 1rem; border-radius: 6px; font-size: 0.8rem; color: #CBD5E1; margin: 0.75rem 0;">
            <strong style="color: #38BDF8;">Analytical Interpretation:</strong>
            Zone <code style="color: #F8FAFC; background: #0B1120; padding: 2px 5px; border-radius: 3px;">{top_z_cell}</code> is highly contested (Hotspot Score: <strong style="color: #38BDF8;">{top_z_score:.4f}</strong>) because <strong style="color: #22C55E;">{top_z_runners} unique runners</strong> have mounted <strong style="color: #EF4444;">{top_z_takes} competitive takeovers</strong> across <strong style="color: #F59E0B;">{top_z_visits} total visits</strong>. Currently held by <strong>{top_z_owner}</strong>.
            <div style="margin-top: 0.35rem; font-size: 0.72rem; color: #94A3B8;">
                *Note: The Composite Hotspot Score is a custom Business Intelligence (BI) index combining normalized takeovers (40%), runner diversity (35%), and visit volume (25%).*
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 5. Zone Drill-Down Panel (Phase 6 requirement)
    with st.expander("🔍 Zone Drill-Down Inspector & Contention Profile", expanded=False):
        drill_cell = st.selectbox(
            "Select H3 Zone to Inspect",
            options=sorted_hotspots["h3_cell"].head(50).tolist(),
            index=0,
            key="hotspot_drill_cell",
        )
        drill_row = sorted_hotspots[sorted_hotspots["h3_cell"] == drill_cell].iloc[0]

        d1, d2, d3, d4, d5 = st.columns(5)
        with d1:
            st.metric("Hotspot Rank", f"#{int(drill_row.get('hotspot_rank', 0))}")
        with d2:
            st.metric("Hotspot Score", f"{float(drill_row.get('hotspot_score', 0)):.4f}")
        with d3:
            st.metric("Takeovers", f"{int(drill_row.get('takeover_count', 0))}")
        with d4:
            st.metric("Unique Runners", f"{int(drill_row.get('unique_runners', 0))}")
        with d5:
            st.metric("Total Visits", f"{int(drill_row.get('total_visits', 0))}")

        st.caption(
            f"Zone **{drill_cell}** is currently defended by **{drill_row.get('current_owner_id', 'Unclaimed')}**. "
            f"Normalized takeovers: `{drill_row.get('norm_takeovers', 0):.2f}`, "
            f"Normalized runners: `{drill_row.get('norm_unique_runners', 0):.2f}`, "
            f"Normalized visits: `{drill_row.get('norm_visits', 0):.2f}`."
        )

    # 6. Detailed Hotspot Table & Export
    st.markdown(
        """
        <div class="section-header" style="margin-top: 1rem;">
            <div class="section-title">📋 Hotspot Rankings Table</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    t_hdr, t_dl = st.columns([3, 1])
    with t_hdr:
        st.caption(f"Displaying top {len(top_hotspots)} zones ranked by {chosen_metric}")
    with t_dl:
        generate_csv_download(
            top_hotspots,
            filename=f"hotspot_rankings_{rank_metric_col}.csv",
            button_label="📥 Export Hotspots CSV",
            key="dl_hotspots",
        )

    table_cols = [
        "h3_cell",
        "hotspot_rank",
        "hotspot_score",
        "takeover_count",
        "unique_runners",
        "total_visits",
        "current_owner_id",
    ]
    render_df = top_hotspots[[c for c in table_cols if c in top_hotspots.columns]].copy()

    render_data_table(
        render_df,
        column_config={
            "hotspot_rank": st.column_config.NumberColumn("Rank", format="#%d", width="small"),
            "h3_cell": st.column_config.TextColumn("H3 Cell ID", width="medium"),
            "hotspot_score": st.column_config.NumberColumn("Hotspot Score", format="%.4f", width="small"),
            "takeover_count": st.column_config.NumberColumn("Takeovers", width="small"),
            "unique_runners": st.column_config.NumberColumn("Unique Runners", width="small"),
            "total_visits": st.column_config.NumberColumn("Total Visits", width="small"),
            "current_owner_id": st.column_config.TextColumn("Current Owner", width="medium"),
        },
    )


if __name__ == "__main__":
    from dashboard.app import inject_custom_css
    from dashboard.services.data_loader import load_all_datasets

    inject_custom_css()
    _datasets = load_all_datasets()
    render_hotspot_analysis_page(_datasets)

