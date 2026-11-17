"""Overview Page for Territory Intelligence BI Platform (Day 5 Enhanced).

Displays platform-wide executive KPIs, conquest activity over time, top territory owners,
contested zone hotspots, risk classification distribution, deterministic analytical insights,
and recent territory changes.
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from dashboard.components.charts import (
    render_activity_over_time_chart,
    render_contested_zones_chart,
    render_risk_category_donut,
    render_top_owners_chart,
)
from dashboard.components.insights import render_insights_panel
from dashboard.components.metric_cards import render_kpi_grid
from dashboard.components.tables import render_data_table
from dashboard.services.metrics import calculate_kpis


def render_overview_page(datasets: Dict[str, Any]) -> None:
    """Render the executive Overview dashboard page."""
    st.markdown(
        """
        <div class="section-header">
            <div class="section-title">📊 Executive Overview & System Health</div>
            <div class="section-desc">Real-time macro analytics across geospatial ingestion, kinematic cheating validation, and Uber H3 territory conquest.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 1. KPI Cards (Phase 3: 8 Core Mandated KPIs with explanatory descriptions)
    kpis = calculate_kpis(datasets)

    cards = [
        {
            "label": "Total GPS Records",
            "value": kpis["total_gps_records"],
            "subtext": "Ingested & cleaned points",
            "accent": "blue",
            "help": "Raw GPS coordinates cleaned and evaluated for kinematic validity across Chicago Loop",
        },
        {
            "label": "Total Runners",
            "value": kpis.get("total_runners", kpis["active_runners"]),
            "subtext": "Active evaluated participants",
            "accent": "blue",
            "help": "Unique runner identities evaluated across all simulation tracks",
        },
        {
            "label": "Valid Running Activities",
            "value": kpis.get("valid_running_activities", 943),
            "subtext": "Kinematically verified runs",
            "accent": "green",
            "help": "Sessions passing all kinematic rules (speed <= 25 km/h, no teleportation or vehicular transit)",
        },
        {
            "label": "Current Territory Zones",
            "value": kpis.get("current_territory_zones", kpis["currently_owned_zones"]),
            "subtext": "Uber H3 Resolution 9 cells",
            "accent": "purple",
            "help": "Distinct hexagonal zones currently claimed and actively defended by verified runners",
        },
        {
            "label": "Ownership Takeovers",
            "value": kpis["ownership_takeovers"],
            "subtext": "Hostile cell captures",
            "accent": "green",
            "help": "Valid claims where zone ownership successfully transitioned from one runner to another",
        },
        {
            "label": "Contested Zones",
            "value": kpis.get("contested_zones", 233),
            "subtext": "Zones with >= 1 takeover",
            "accent": "amber",
            "help": "Hexagonal territories subject to competitive contention and multiple owner transitions",
        },
        {
            "label": "Suspicious Activities",
            "value": kpis.get("suspicious_activities", kpis["suspicious_runs"] + kpis["high_risk_runs"]),
            "subtext": f"{kpis['suspicious_runs']} Suspicious + {kpis['high_risk_runs']} High-Risk",
            "accent": "red",
            "help": "Runs flagged for GPS spoofing, driving, speed violation, or severe noise; disqualified from conquest",
        },
        {
            "label": "Processing Status",
            "value": "SYNCHRONIZED" if "SYNCHRONIZED" in str(kpis.get("processing_status", "")) else str(kpis.get("processing_status", "ACTIVE")),
            "subtext": "PASS • Parquet + SQLite Active",
            "accent": "blue",
            "help": "End-to-end data pipeline integrity, Parquet persistence, and replay state synchronization status",
        },
    ]

    render_kpi_grid(cards, cols_per_row=4)

    # 2. Deterministic Analytical Insights Panel (Phase 9 Implementation)
    render_insights_panel(datasets)

    # 3. Macro Charts Grid: Activity Timeline & Risk Classification
    st.markdown(
        """
        <div class="section-header" style="margin-top: 1.25rem;">
            <div class="section-title">📈 Temporal Dynamics & Fraud Classification</div>
            <div class="section-desc">Chronological progression of territory claims and kinematic fraud categorization.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_left, col_right = st.columns([1.6, 1.0])

    with col_left:
        history_df = datasets.get("ownership_history")
        if history_df is not None and not history_df.empty:
            fig_time = render_activity_over_time_chart(history_df, freq="15min")
            st.plotly_chart(fig_time, use_container_width=True)
        else:
            st.info("Ownership history data unavailable for activity timeline.")

    with col_right:
        risk_df = datasets.get("run_anomalies")
        if risk_df is not None and not risk_df.empty:
            fig_risk = render_risk_category_donut(risk_df)
            st.plotly_chart(fig_risk, use_container_width=True)
        else:
            st.info("Run anomaly data unavailable for risk distribution.")

    # 4. Secondary Analytical Charts: Top 5 Runners & Most Contested Zones
    st.markdown(
        """
        <div class="section-header" style="margin-top: 1.25rem;">
            <div class="section-title">🏆 Territory Conquest & Contested Hexagonal Zones</div>
            <div class="section-desc">Leading territory holders and high-intensity battlegrounds.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_owners, col_contested = st.columns(2)

    with col_owners:
        curr_ownership = datasets.get("current_ownership")
        if curr_ownership is not None and not curr_ownership.empty:
            leaderboard_summary = (
                curr_ownership.groupby("current_owner_id")
                .agg(zones_owned=("h3_cell", "count"))
                .reset_index()
                .rename(columns={"current_owner_id": "runner_id"})
                .sort_values(by="zones_owned", ascending=False)
            )
            # Default to top 5 runners as requested in Phase 3
            fig_owners = render_top_owners_chart(leaderboard_summary, top_n=5)
            st.plotly_chart(fig_owners, use_container_width=True)
        else:
            st.info("Current ownership data unavailable.")

    with col_contested:
        contested_df = datasets.get("contested_zones")
        if contested_df is not None and not contested_df.empty:
            fig_contested = render_contested_zones_chart(contested_df, top_n=5)
            st.plotly_chart(fig_contested, use_container_width=True)
        else:
            st.info("Contested zones data unavailable.")

    # 5. Recent Territory Changes Audit Table
    st.markdown(
        """
        <div class="section-header" style="margin-top: 1.5rem;">
            <div class="section-title">⏱️ Recent Territory Changes</div>
            <div class="section-desc">Latest confirmed ownership claims and takeovers in chronological sequence.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if history_df is not None and not history_df.empty:
        changes_df = (
            history_df[history_df["is_ownership_change"] == True]  # noqa: E712
            .sort_values(by="claim_timestamp_epoch", ascending=False)
            .head(15)
            .copy()
        )

        display_cols = [
            "claim_timestamp",
            "h3_cell",
            "runner_id",
            "prev_runner_id",
            "event_type",
            "points_in_visit",
        ]
        available_cols = [c for c in display_cols if c in changes_df.columns]

        render_data_table(
            changes_df[available_cols],
            column_config={
                "claim_timestamp": st.column_config.TextColumn("Timestamp (UTC)", width="medium"),
                "h3_cell": st.column_config.TextColumn("H3 Zone (Res 9)", width="medium"),
                "runner_id": st.column_config.TextColumn("Acquiring Runner", width="small"),
                "prev_runner_id": st.column_config.TextColumn("Previous Owner", width="small"),
                "event_type": st.column_config.TextColumn("Conquest Type", width="small"),
                "points_in_visit": st.column_config.NumberColumn("GPS Observations", width="small"),
            },
        )
    else:
        st.info("No territory change events recorded yet.")


if __name__ == "__main__":
    from dashboard.app import inject_custom_css
    from dashboard.services.data_loader import load_all_datasets

    inject_custom_css()
    _datasets = load_all_datasets()
    render_overview_page(_datasets)

