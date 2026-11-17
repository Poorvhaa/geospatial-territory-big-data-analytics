"""Activity Analytics Page for Territory Intelligence BI Platform.

Presents temporal patterns, diurnal distributions, run distance metrics, and
conquest velocity over time.
"""

from __future__ import annotations

from typing import Any, Dict

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from dashboard.components.charts import (
    apply_dark_theme,
    render_activity_over_time_chart,
    render_distance_distribution_chart,
    render_hourly_activity_chart,
)
from dashboard.components.tables import render_empty_state


def render_activity_analytics_page(datasets: Dict[str, Any]) -> None:
    """Render the temporal and behavioral activity analytics page."""
    st.markdown(
        """
        <div class="section-header">
            <div class="section-title">📈 Temporal & Behavioral Activity Analytics</div>
            <div class="section-desc">Diurnal patterns, cumulative territory conquest dynamics, and running session kinematics.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Timezone notification
    st.caption("🌐 **Timezone Reference:** All timestamps and diurnal intervals are rendered in **Coordinated Universal Time (UTC)**.")

    hist_df = datasets.get("ownership_history")
    risk_df = datasets.get("run_anomalies")

    if (hist_df is None or hist_df.empty) and (risk_df is None or risk_df.empty):
        render_empty_state(
            title="Activity Data Unavailable",
            message="No historical activity or run records found.",
            icon="📈",
        )
        return

    # 1. Macro Activity Trends
    st.markdown("### ⏱️ Conquest Timeline & Hourly Diurnal Breakdown")
    col_timeline, col_hourly = st.columns([1.5, 1.0])

    with col_timeline:
        if hist_df is not None and not hist_df.empty:
            fig_timeline = render_activity_over_time_chart(hist_df, freq="15min")
            st.plotly_chart(fig_timeline, use_container_width=True)

    with col_hourly:
        if hist_df is not None and not hist_df.empty:
            fig_hourly = render_hourly_activity_chart(hist_df)
            st.plotly_chart(fig_hourly, use_container_width=True)

    # 2. Peak Activity Period Summary
    if hist_df is not None and not hist_df.empty and "claim_timestamp" in hist_df.columns:
        df_time = hist_df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df_time["claim_timestamp"]):
            df_time["claim_timestamp"] = pd.to_datetime(df_time["claim_timestamp"], utc=True)

        df_time["hour"] = df_time["claim_timestamp"].dt.hour
        peak_hour = df_time["hour"].value_counts().idxmax()
        peak_count = df_time["hour"].value_counts().max()
        earliest = df_time["claim_timestamp"].min()
        latest = df_time["claim_timestamp"].max()

        p1, p2, p3, p4 = st.columns(4)
        with p1:
            st.metric("Peak Activity Hour", f"{peak_hour}:00 UTC", help="Hour with highest confirmed claims")
        with p2:
            st.metric("Claims in Peak Hour", f"{peak_count:,}")
        with p3:
            st.metric("Session Start", earliest.strftime("%H:%M:%S UTC") if pd.notnull(earliest) else "N/A")
        with p4:
            st.metric("Session End", latest.strftime("%H:%M:%S UTC") if pd.notnull(latest) else "N/A")

    # 3. Kinematic Session Distributions
    st.markdown("### 🏃 Session Kinematics & Distribution")
    col_dist, col_speed = st.columns(2)

    with col_dist:
        if risk_df is not None and not risk_df.empty:
            fig_dist = render_distance_distribution_chart(risk_df)
            st.plotly_chart(fig_dist, use_container_width=True)

    with col_speed:
        if risk_df is not None and not risk_df.empty and "max_speed_kmh" in risk_df.columns:
            fig_speed = go.Figure(
                go.Histogram(
                    x=risk_df["max_speed_kmh"],
                    nbinsx=30,
                    marker=dict(color="#38BDF8", line=dict(color="#0B1120", width=1)),
                    hovertemplate="Max Speed: %{x} km/h<br>Runs: %{y}<extra></extra>",
                )
            )
            fig_speed.add_vline(x=25.0, line_dash="dash", line_color="#EF4444", annotation_text="Human Limit (25 km/h)")
            fig_speed.update_layout(
                title=dict(text="Maximum Observed Speed per Run (km/h)", font=dict(size=13, color="#F8FAFC")),
                xaxis_title="Max Speed (km/h)",
                yaxis_title="Runs Evaluated",
            )
            st.plotly_chart(apply_dark_theme(fig_speed, height=280), use_container_width=True)

    # 4. Valid Runs by Runner Frequency
    if risk_df is not None and not risk_df.empty:
        normal_runs = risk_df[risk_df["risk_category"] == "NORMAL"]
        runs_per_runner = normal_runs["runner_id"].value_counts().reset_index()
        runs_per_runner.columns = ["runner_id", "valid_runs"]

        fig_runs_hist = go.Figure(
            go.Histogram(
                x=runs_per_runner["valid_runs"],
                nbinsx=10,
                marker=dict(color="#A855F7", line=dict(color="#0B1120", width=1)),
                hovertemplate="Runs Completed: %{x}<br>Runners: %{y}<extra></extra>",
            )
        )
        fig_runs_hist.update_layout(
            title=dict(text="Distribution of Valid Runs Completed per Runner", font=dict(size=13, color="#F8FAFC")),
            xaxis_title="Completed Valid Runs",
            yaxis_title="Number of Active Runners",
        )
        st.plotly_chart(apply_dark_theme(fig_runs_hist, height=260), use_container_width=True)


if __name__ == "__main__":
    from dashboard.app import inject_custom_css
    from dashboard.services.data_loader import load_all_datasets

    inject_custom_css()
    _datasets = load_all_datasets()
    render_activity_analytics_page(_datasets)

