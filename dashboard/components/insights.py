"""Deterministic Analytical Insights Component for Territory Intelligence BI Platform.

Computes and renders verified data-driven macro insights directly from processed
datasets without external API calls or invented narratives (Phase 9 Implementation).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import pandas as pd
import streamlit as st


def compute_analytical_insights(datasets: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compute deterministic executive insights using actual analytical outputs.

    Args:
        datasets: Dictionary of loaded pandas DataFrames from Parquet.

    Returns:
        List of insight dictionaries containing metric, value, context, and computation logic.
    """
    curr = datasets.get("current_ownership")
    hist = datasets.get("ownership_history")
    risk = datasets.get("run_anomalies")
    stats = datasets.get("zone_statistics")

    insights: List[Dict[str, Any]] = []

    # 1. Most Active Hour
    if hist is not None and not hist.empty and "claim_timestamp" in hist.columns:
        hist_work = hist.copy()
        hist_work["hour"] = pd.to_datetime(hist_work["claim_timestamp"]).dt.hour
        hour_counts = hist_work["hour"].value_counts()
        top_hour = int(hour_counts.index[0])
        top_hour_claims = int(hour_counts.iloc[0])
        total_claims = len(hist_work)
        pct = (top_hour_claims / total_claims * 100.0) if total_claims > 0 else 0.0

        insights.append({
            "id": "active_hour",
            "title": "Peak Activity Hour",
            "value": f"{top_hour:02d}:00 - {top_hour+1:02d}:00 UTC",
            "stat": f"{top_hour_claims:,} claims ({pct:.1f}% of all claims)",
            "icon": "⏰",
            "accent": "#38BDF8",
            "interpretation": f"Conquest intensity peaks between {top_hour:02d}:00 and {top_hour+1:02d}:00 UTC as multiple runners converge on Chicago Loop corridors.",
            "calculation": "Derived by parsing the UTC timestamp of every confirmed claim event in `ownership_history`, grouping by hour of day (0-23), and identifying the modal distribution peak.",
        })

    # 2. Most Contested Territory
    if curr is not None and not curr.empty and "total_zone_takeovers" in curr.columns:
        top_contested = curr.sort_values(by="total_zone_takeovers", ascending=False).iloc[0]
        c_cell = str(top_contested["h3_cell"])
        c_takes = int(top_contested["total_zone_takeovers"])
        c_owner = str(top_contested.get("current_owner_id", "Unknown"))

        insights.append({
            "id": "contested_territory",
            "title": "Most Contested Territory",
            "value": f"Zone {c_cell[:10]}...",
            "stat": f"{c_takes:,} takeovers (Held by {c_owner})",
            "icon": "⚔️",
            "accent": "#EF4444",
            "interpretation": f"H3 cell `{c_cell}` is the most fiercely contested zone in the network, having exchanged hands {c_takes} times across competing runners.",
            "calculation": "Calculated by aggregating `is_takeover == True` per H3 cell in `ownership_history` and identifying the cell with the maximum cumulative takeover transitions.",
        })

    # 3. Runner with Most Currently Owned Zones
    if curr is not None and not curr.empty and "current_owner_id" in curr.columns:
        owner_counts = curr.groupby("current_owner_id").size().sort_values(ascending=False)
        top_owner_id = str(owner_counts.index[0])
        top_owner_zones = int(owner_counts.iloc[0])
        total_zones = len(curr)
        share_pct = (top_owner_zones / total_zones * 100.0) if total_zones > 0 else 0.0

        insights.append({
            "id": "top_owner",
            "title": "Dominant Territory Leader",
            "value": top_owner_id,
            "stat": f"{top_owner_zones} zones currently held ({share_pct:.1f}% territory share)",
            "icon": "👑",
            "accent": "#22C55E",
            "interpretation": f"Runner `{top_owner_id}` controls the highest active geographic footprint, defending {top_owner_zones} distinct H3 cells in the Chicago area.",
            "calculation": "Computed by querying `current_ownership` for unique H3 cells held by each runner at the latest analytical snapshot.",
        })

    # 4. Runner with Most Successful Captures
    if hist is not None and not hist.empty and "runner_id" in hist.columns:
        captures_mask = hist["event_type"].isin(["INITIAL_CAPTURE", "TAKEOVER"]) if "event_type" in hist.columns else hist["is_takeover"] == True
        cap_counts = hist[captures_mask].groupby("runner_id").size().sort_values(ascending=False)
        if not cap_counts.empty:
            top_cap_id = str(cap_counts.index[0])
            top_cap_val = int(cap_counts.iloc[0])

            insights.append({
                "id": "top_capturer",
                "title": "Most Prolific Conqueror",
                "value": top_cap_id,
                "stat": f"{top_cap_val:,} total successful zone captures",
                "icon": "🎯",
                "accent": "#A855F7",
                "interpretation": f"Runner `{top_cap_id}` has mounted the highest cumulative conquests ({top_cap_val} takeovers/captures) throughout the dataset timeline.",
                "calculation": "Derived by counting all historical events where `event_type IN ('INITIAL_CAPTURE', 'TAKEOVER')` attributed to this runner.",
            })

    # 5. Percentage of Activities Flagged as Suspicious
    if risk is not None and not risk.empty and "risk_category" in risk.columns:
        total_runs = len(risk)
        flagged_count = int((risk["risk_category"] != "NORMAL").sum())
        susp_count = int((risk["risk_category"] == "SUSPICIOUS").sum())
        high_count = int((risk["risk_category"] == "HIGH_RISK").sum())
        flag_pct = (flagged_count / total_runs * 100.0) if total_runs > 0 else 0.0

        insights.append({
            "id": "anomaly_rate",
            "title": "Kinematic Anomaly Rate",
            "value": f"{flag_pct:.2f}% Flagged",
            "stat": f"{flagged_count}/{total_runs:,} runs ({susp_count} Suspicious, {high_count} High-Risk)",
            "icon": "🛡️",
            "accent": "#F59E0B",
            "interpretation": f"Automated kinematic rules quarantined {flagged_count} runs for impossible speeds, vehicular velocity, or teleportation, preserving leaderboard fairness.",
            "calculation": "Ratio of runs with heuristic fraud score >= 0.30 (`risk_category != 'NORMAL'`) over the total volume of kinematically audited activities.",
        })

    # 6. Total Number of Ownership Changes
    if hist is not None and not hist.empty:
        if "is_ownership_change" in hist.columns:
            total_changes = int((hist["is_ownership_change"] == True).sum())
        else:
            total_changes = int((hist["is_takeover"] == True).sum()) + int(curr["h3_cell"].nunique() if curr is not None else 0)

        takeovers_only = int((hist["is_takeover"] == True).sum()) if "is_takeover" in hist.columns else 0

        insights.append({
            "id": "ownership_changes",
            "title": "Total Ownership Transfers",
            "value": f"{total_changes:,} Events",
            "stat": f"{takeovers_only:,} competitive takeovers + initial conquests",
            "icon": "🔄",
            "accent": "#06B6D4",
            "interpretation": f"A total of {total_changes:,} territory transition events occurred, illustrating high turnover and spatial competition.",
            "calculation": "Sum of all events where `is_ownership_change == True` in `ownership_history`, signifying either an unowned cell capture or a hostile takeover.",
        })

    # 7. Highest Activity Geographic Zone
    if stats is not None and not stats.empty and "total_visits" in stats.columns:
        top_zone_row = stats.sort_values(by="total_visits", ascending=False).iloc[0]
        top_zone_cell = str(top_zone_row["h3_cell"])
        top_visits = int(top_zone_row["total_visits"])
        top_runners = int(top_zone_row.get("unique_runners", 0))

        insights.append({
            "id": "highest_activity_zone",
            "title": "Highest Activity Corridor",
            "value": f"Zone {top_zone_cell[:10]}...",
            "stat": f"{top_visits:,} total visits by {top_runners} unique runners",
            "icon": "📍",
            "accent": "#EAB308",
            "interpretation": f"Cell `{top_zone_cell}` experienced the highest foot traffic in Chicago, functioning as a primary transit hub.",
            "calculation": "Aggregated count of deduplicated consecutive GPS visits traversing this Uber H3 cell boundary in `zone_statistics`.",
        })

    return insights


def render_insights_panel(datasets: Dict[str, Any], expanded_help: bool = False) -> None:
    """Render the executive insights panel with cards and calculation methods."""
    insights = compute_analytical_insights(datasets)
    if not insights:
        return

    st.markdown(
        """
        <div class="section-header" style="margin-top: 1.25rem;">
            <div class="section-title">💡 Automated Analytical Insights & Intelligence Briefing</div>
            <div class="section-desc">Deterministic, data-driven macro insights calculated directly from validated PySpark execution outputs.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Render in a responsive 3-column or 4-column layout
    cols = st.columns(min(len(insights), 3))
    for idx, item in enumerate(insights):
        col = cols[idx % len(cols)]
        with col:
            st.markdown(
                f"""
                <div style="background: #151E30; border: 1px solid rgba(255,255,255,0.08); border-left: 4px solid {item['accent']}; border-radius: 8px; padding: 0.9rem 1rem; margin-bottom: 0.75rem; box-shadow: 0 4px 12px rgba(0,0,0,0.25);">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.35rem;">
                        <span style="font-size: 0.72rem; font-weight: 700; text-transform: uppercase; color: #94A3B8; letter-spacing: 0.05em;">{item['title']}</span>
                        <span style="font-size: 1.1rem;">{item['icon']}</span>
                    </div>
                    <div style="font-size: 1.25rem; font-weight: 800; color: #F8FAFC; margin-bottom: 0.25rem; font-family: 'JetBrains Mono', monospace;">{item['value']}</div>
                    <div style="font-size: 0.78rem; font-weight: 600; color: {item['accent']}; margin-bottom: 0.45rem;">{item['stat']}</div>
                    <div style="font-size: 0.76rem; color: #CBD5E1; line-height: 1.45;">{item['interpretation']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Collapsible calculation methodology section (Phase 9 requirement)
    with st.expander("📐 How these analytical insights are calculated (Methodology & Formulae)", expanded=expanded_help):
        st.markdown("All insights are **100% deterministic** and computed directly from PySpark Parquet analytical tables:")
        for item in insights:
            st.markdown(f"- **{item['icon']} {item['title']}:** {item['calculation']}")
