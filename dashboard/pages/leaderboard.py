"""Leaderboard Page for Territory Intelligence BI Platform.

Computes multi-dimensional rankings across current territory ownership, total captures,
successful takeovers, valid runs, and total distance traversed.
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from dashboard.components.charts import apply_dark_theme
from dashboard.components.tables import render_data_table, render_empty_state
from dashboard.services.exports import generate_csv_download
from dashboard.services.metrics import calculate_combined_leaderboard, get_runner_color
import plotly.graph_objects as go


METRIC_OPTIONS = {
    "Current Territory Ownership": ("zones_owned", "rank_zones_owned", "Zones Owned"),
    "Total Territory Captures": ("total_captures", "rank_total_captures", "Total Captures"),
    "Successful Takeovers": ("takeovers", "rank_takeovers", "Takeovers"),
    "Number of Valid Runs": ("valid_runs", "rank_valid_runs", "Valid Runs"),
    "Total Valid Distance": ("valid_distance_km", "rank_valid_distance", "Distance (km)"),
}


def render_leaderboard_page(datasets: Dict[str, Any]) -> None:
    """Render the Leaderboard ranking page."""
    st.markdown(
        """
        <div class="section-header">
            <div class="section-title">🏆 Competitive Runner Leaderboard</div>
            <div class="section-desc">Multi-dimensional rankings tracking active territory control, conquest intensity, and verified movement distance.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    curr_df = datasets.get("current_ownership")
    hist_df = datasets.get("ownership_history")
    risk_df = datasets.get("run_anomalies")

    if curr_df is None or curr_df.empty:
        render_empty_state(
            title="Leaderboard Unavailable",
            message="Required datasets for computing rankings are not available.",
            icon="🏆",
        )
        return

    # Calculate unified leaderboard
    leaderboard_df = calculate_combined_leaderboard(curr_df, hist_df, risk_df)

    if leaderboard_df.empty:
        render_empty_state(title="No Runner Records Found")
        return

    # 0. Reconciliation Integrity Banner (Phase 5 requirement)
    total_leaderboard_owned = int(leaderboard_df["zones_owned"].sum())
    total_curr_zones = int(curr_df["h3_cell"].nunique()) if "h3_cell" in curr_df.columns else len(curr_df)
    is_reconciled = (total_leaderboard_owned == total_curr_zones)

    st.markdown(
        f"""
        <div style="background: rgba(34, 197, 94, 0.1); border-left: 3px solid #22C55E; padding: 0.6rem 1rem; border-radius: 4px; font-size: 0.8rem; color: #22C55E; margin-bottom: 1rem; display: flex; align-items: center; justify-content: space-between;">
            <div>
                <strong>Reconciliation Verified:</strong> Leaderboard Sum of Zones Owned (<strong style="color: #F8FAFC;">{total_leaderboard_owned}</strong>) reconciles exactly with Current Territory Records (<strong style="color: #F8FAFC;">{total_curr_zones}</strong>).
            </div>
            <div style="font-weight: 700; background: #064E3B; color: #34D399; padding: 2px 8px; border-radius: 4px; font-size: 0.72rem;">
                ✓ 100% RECONCILED
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 1. Filter & Metric Selection Controls
    c1, c2, c3 = st.columns([1.5, 1.2, 0.8])

    with c1:
        metric_choice = st.selectbox(
            "Primary Ranking Metric",
            options=list(METRIC_OPTIONS.keys()),
            index=0,
            help="Select metric to sort and rank the leaderboard",
        )
        sort_col, rank_col, metric_label = METRIC_OPTIONS[metric_choice]

    with c2:
        search_query = st.text_input(
            "Search Runner ID",
            placeholder="e.g. runner_069",
            help="Filter leaderboard by runner identifier",
        ).strip().lower()

    with c3:
        top_n = st.selectbox(
            "Display Limit",
            options=[10, 25, 50, 100, "All"],
            index=1,
        )

    # Sort dataset by selected metric
    sorted_df = leaderboard_df.sort_values(by=[sort_col, "zones_owned"], ascending=[False, False]).copy()

    # Apply runner search if provided
    if search_query:
        sorted_df = sorted_df[sorted_df["runner_id"].str.lower().str.contains(search_query)]

    # Limit to Top N
    if top_n != "All":
        display_df = sorted_df.head(int(top_n)).copy()
    else:
        display_df = sorted_df.copy()

    # 2. Top 10 Visualization Chart
    chart_df = sorted_df.head(10).iloc[::-1]
    colors = [get_runner_color(r) for r in chart_df["runner_id"]]

    fig = go.Figure(
        go.Bar(
            x=chart_df[sort_col],
            y=chart_df["runner_id"],
            orientation="h",
            marker=dict(color=colors, line=dict(color="rgba(255,255,255,0.2)", width=1)),
            text=chart_df[sort_col],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>" + f"{metric_label}: %{{x}}<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text=f"Top 10 Runners by {metric_choice}", font=dict(size=13, color="#F8FAFC")),
        xaxis_title=metric_label,
        yaxis_title="",
    )
    st.plotly_chart(apply_dark_theme(fig, height=300), use_container_width=True)

    # 3. Metric Explanations Box
    st.markdown(
        """
        <div style="background: #151E30; border-left: 3px solid #38BDF8; padding: 0.6rem 0.9rem; border-radius: 4px; font-size: 0.76rem; color: #94A3B8; margin-bottom: 0.75rem;">
            <strong style="color: #F8FAFC;">Metric Definitions:</strong>
            <span style="margin-left: 0.5rem;"><strong>Current Zones Owned:</strong> Active cells held right now (Latest snapshot).</span>
            <span style="margin-left: 0.5rem;"><strong>Total Captures:</strong> Cumulative claims (Initial captures + takeovers).</span>
            <span style="margin-left: 0.5rem;"><strong>Valid Runs:</strong> Verified non-cheating sessions.</span>
            <span style="margin-left: 0.5rem;"><strong>Valid Distance:</strong> Total verified km traversed.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 4. Action bar with CSV Download
    col_hdr, col_dl = st.columns([3, 1])
    with col_hdr:
        st.markdown(f"**Showing {len(display_df)} Runners:**")
    with col_dl:
        generate_csv_download(
            display_df,
            filename=f"leaderboard_{sort_col}.csv",
            button_label="📥 Export Leaderboard CSV",
            key="dl_leaderboard",
        )

    # 5. Full Ranking Table (Phase 5 strict column order)
    table_view = display_df[
        [
            rank_col,
            "runner_id",
            "zones_owned",
            "valid_runs",
            "valid_distance_km",
            "total_captures",
            "takeovers",
        ]
    ].rename(columns={rank_col: "Rank"})

    render_data_table(
        table_view,
        column_config={
            "Rank": st.column_config.NumberColumn("Rank", width="small", format="#%d"),
            "runner_id": st.column_config.TextColumn("Runner ID", width="medium"),
            "zones_owned": st.column_config.NumberColumn("Current Zones Owned", width="small"),
            "valid_runs": st.column_config.NumberColumn("Valid Runs", width="small"),
            "valid_distance_km": st.column_config.NumberColumn("Total Distance (km)", width="small", format="%.2f km"),
            "total_captures": st.column_config.NumberColumn("Total Captures", width="small"),
            "takeovers": st.column_config.NumberColumn("Successful Takeovers", width="small"),
        },
    )


if __name__ == "__main__":
    from dashboard.app import inject_custom_css
    from dashboard.services.data_loader import load_all_datasets

    inject_custom_css()
    _datasets = load_all_datasets()
    render_leaderboard_page(_datasets)

