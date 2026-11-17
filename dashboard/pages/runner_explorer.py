"""Runner Explorer Page for Territory Intelligence BI Platform.

Enables in-depth profile drill-down into any specific runner:
- Active territory footprint vs cumulative historical conquests
- Verified running distance, session volume, and kinematic risk profile
- Interactive map highlighting currently owned H3 zones
- Full chronological conquest log with CSV export
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from dashboard.components.maps import render_territory_map
from dashboard.components.metric_cards import render_kpi_grid
from dashboard.components.tables import render_data_table, render_empty_state
from dashboard.services.exports import generate_csv_download
from dashboard.services.metrics import calculate_combined_leaderboard, get_runner_color


def render_runner_explorer_page(datasets: Dict[str, Any]) -> None:
    """Render the Runner Explorer drill-down profile page."""
    st.markdown(
        """
        <div class="section-header">
            <div class="section-title">🏃 Runner Profile & Territory Explorer</div>
            <div class="section-desc">Individual athlete dossier: active territory control, verified distance, kinematic compliance, and conquest history.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    curr_df = datasets.get("current_ownership")
    hist_df = datasets.get("ownership_history")
    risk_df = datasets.get("run_anomalies")

    if curr_df is None and hist_df is None and risk_df is None:
        render_empty_state(title="No Runner Data Available")
        return

    # Calculate unified runner metrics
    all_metrics = calculate_combined_leaderboard(
        curr_df if curr_df is not None else pd.DataFrame(),
        hist_df if hist_df is not None else pd.DataFrame(),
        risk_df if risk_df is not None else pd.DataFrame(),
    )

    if all_metrics.empty:
        render_empty_state(title="No Runner Profiles Found")
        return

    runner_list = all_metrics["runner_id"].tolist()

    # 1. Runner Selector
    col_sel, col_stat = st.columns([1.5, 2])
    with col_sel:
        selected_runner = st.selectbox(
            "Select Runner to Inspect",
            options=runner_list,
            index=0,
            help="Choose a runner to view their comprehensive analytical dossier",
        )

    runner_row = all_metrics[all_metrics["runner_id"] == selected_runner].iloc[0]
    runner_color = get_runner_color(selected_runner)

    with col_stat:
        st.markdown(
            f"""
            <div style="background: #151E30; padding: 0.6rem 1rem; border-radius: 6px; border-left: 4px solid {runner_color}; margin-top: 0.4rem; display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <span style="font-size: 1.1rem; font-weight: 700; color: #F8FAFC;">{selected_runner}</span>
                    <div style="font-size: 0.75rem; color: #94A3B8;">Verified Athlete Profile</div>
                </div>
                <div style="text-align: right;">
                    <span style="font-size: 0.72rem; color: #64748B;">Overall Ownership Rank:</span>
                    <strong style="color: #38BDF8; font-size: 1.1rem; display: block;">#{runner_row['rank_zones_owned']}</strong>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 2. Runner Profile KPIs
    # Kinematic risk summary for this runner
    risk_summary = "CLEAN"
    if risk_df is not None and not risk_df.empty:
        r_runs = risk_df[risk_df["runner_id"] == selected_runner]
        if not r_runs.empty:
            high_count = (r_runs["risk_category"] == "HIGH_RISK").sum()
            susp_count = (r_runs["risk_category"] == "SUSPICIOUS").sum()
            if high_count > 0:
                risk_summary = f"{high_count} High Risk Flags"
            elif susp_count > 0:
                risk_summary = f"{susp_count} Suspicious Flags"
            else:
                risk_summary = "100% Verified Clean"

    cards = [
        {
            "label": "Currently Owned Zones",
            "value": int(runner_row["zones_owned"]),
            "subtext": f"Rank #{runner_row['rank_zones_owned']} overall",
            "accent": "blue",
            "help": "Active discrete H3 cells currently held by this runner right now",
        },
        {
            "label": "Total Captures",
            "value": int(runner_row["total_captures"]),
            "subtext": f"{runner_row['takeovers']} takeovers executed",
            "accent": "purple",
            "help": "Cumulative historical zone captures (initial + takeovers)",
        },
        {
            "label": "Verified Distance",
            "value": f"{runner_row['valid_distance_km']:.2f} km",
            "subtext": f"{runner_row['valid_runs']} verified sessions",
            "accent": "green",
            "help": "Total valid running distance traversed in normal non-cheating sessions",
        },
        {
            "label": "Kinematic Risk Profile",
            "value": risk_summary,
            "subtext": "Rule-based audit status",
            "accent": "amber" if "Flags" in risk_summary else "green",
            "help": "Automated kinematic assessment across all evaluated runs",
        },
    ]
    render_kpi_grid(cards, cols_per_row=4)

    # Explanatory distinction note
    st.markdown(
        """
        <div style="font-size: 0.74rem; color: #94A3B8; background: #0B1120; border: 1px solid rgba(255,255,255,0.06); padding: 0.45rem 0.75rem; border-radius: 4px; margin-bottom: 0.75rem;">
            ℹ️ <strong>Analytical Scope Notice:</strong> A runner's <em>Currently Owned Zones</em> represents their active latest-state territory snapshot. It does not equate to the total historical territory they have ever visited or contested over time.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 3. Interactive Map Highlighting Runner's Territory
    st.markdown("### 🗺️ Active Territory Spatial Footprint")

    zones_owned_count = int(runner_row["zones_owned"])
    if zones_owned_count > 0 and curr_df is not None and not curr_df.empty:
        # Show map highlighting selected runner's zones
        render_territory_map(
            zones_df=curr_df,
            mode="Territory Ownership",
            selected_runner_id=selected_runner,
            height=460,
        )
    else:
        st.info(
            f"ℹ️ **{selected_runner} currently holds 0 active zones.** "
            "They may have previously captured zones that were subsequently taken over by competitors, "
            "or completed non-claiming sessions."
        )

    # 4. Historical Claims & Transitions Log
    st.markdown(
        f"""
        <div class="section-header" style="margin-top: 1.5rem;">
            <div class="section-title">⏱️ Historical Claims & Conquest Audit for {selected_runner}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if hist_df is not None and not hist_df.empty:
        runner_claims = (
            hist_df[hist_df["runner_id"] == selected_runner]
            .sort_values(by="claim_timestamp", ascending=False)
            .copy()
        )

        if not runner_claims.empty:
            c_hdr, c_dl = st.columns([3, 1])
            with c_hdr:
                st.caption(f"Showing all {len(runner_claims)} recorded claims by {selected_runner}")
            with c_dl:
                generate_csv_download(
                    runner_claims,
                    filename=f"{selected_runner}_claims_history.csv",
                    button_label="📥 Export Claims CSV",
                    key=f"dl_{selected_runner}",
                )

            view_cols = [
                "claim_id",
                "h3_cell",
                "run_id",
                "claim_timestamp",
                "event_type",
                "prev_runner_id",
                "points_in_visit",
            ]
            display_claims = runner_claims[[c for c in view_cols if c in runner_claims.columns]].copy()
            display_claims["prev_runner_id"] = display_claims["prev_runner_id"].fillna("None (Initial)")

            render_data_table(
                display_claims,
                column_config={
                    "claim_id": st.column_config.TextColumn("Claim ID", width="medium"),
                    "h3_cell": st.column_config.TextColumn("H3 Cell ID", width="small"),
                    "run_id": st.column_config.TextColumn("Run ID", width="small"),
                    "claim_timestamp": st.column_config.DatetimeColumn("Timestamp (UTC)", format="YYYY-MM-DD HH:mm:ss"),
                    "event_type": st.column_config.TextColumn("Claim Event", width="small"),
                    "prev_runner_id": st.column_config.TextColumn("Defeated / Prev Owner", width="small"),
                    "points_in_visit": st.column_config.NumberColumn("Points in Stay", width="small"),
                },
            )
        else:
            st.caption(f"No historical claim events recorded for {selected_runner}.")
    else:
        st.caption("No historical dataset available.")


if __name__ == "__main__":
    from dashboard.app import inject_custom_css
    from dashboard.services.data_loader import load_all_datasets

    inject_custom_css()
    _datasets = load_all_datasets()
    render_runner_explorer_page(_datasets)

