"""Live KPI Metrics Cards Component for Real-Time Simulation (Day 4).

Renders responsive KPI cards updating synchronously with committed micro-batch state.
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from dashboard.components.metric_cards import render_kpi_card


def render_live_metrics(metrics: Dict[str, Any]) -> None:
    """Render top-level KPI cards for real-time replay simulation."""
    events_proc = metrics.get("events_processed", 0)
    total_events = metrics.get("total_events", 0)
    claims_proc = metrics.get("claims_processed", 0)
    zones_owned = metrics.get("total_zones_owned", 0)
    active_owners = metrics.get("active_owners_count", 0)
    takeovers = metrics.get("takeovers", 0)
    initial_caps = metrics.get("initial_captures", 0)
    suspicious = metrics.get("suspicious_runs_detected", 0)

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        render_kpi_card(
            label="GPS Points Replayed",
            value=events_proc,
            subtext=f"Total: {total_events:,} points",
            accent="blue",
            help_tooltip="Total GPS points processed chronologically by the simulation.",
        )

    with c2:
        render_kpi_card(
            label="Valid Territory Claims",
            value=claims_proc,
            subtext=f"{initial_caps:,} new • {takeovers:,} takeovers",
            accent="green",
            help_tooltip="Claims satisfying the consecutive observation threshold.",
        )

    with c3:
        render_kpi_card(
            label="Currently Owned Zones",
            value=zones_owned,
            subtext=f"Held by {active_owners} runners",
            accent="purple",
            help_tooltip="H3 hexagonal cells currently under active control.",
        )

    with c4:
        render_kpi_card(
            label="Ownership Takeovers",
            value=takeovers,
            subtext=f"{round(takeovers / claims_proc * 100, 1) if claims_proc else 0.0}% of total claims",
            accent="amber",
            help_tooltip="Zones conquered from a competing runner.",
        )

    with c5:
        render_kpi_card(
            label="Anomalous Runs Quarantined",
            value=suspicious,
            subtext="Prevalidated fraud exclusion",
            accent="red",
            help_tooltip="Points from runs classified as SUSPICIOUS or HIGH_RISK excluded from claiming territory.",
        )
