"""Plotly Charting Components for Territory Intelligence BI Platform.

Implements high-tech dark theme visual styling, consistent color scales, and
interactive tooltips across analytical views.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from dashboard.services.metrics import get_runner_color

THEME_BG = "#151E30"
THEME_GRID = "#1E293B"
THEME_TEXT = "#F8FAFC"
THEME_MUTED = "#94A3B8"
ACCENT_BLUE = "#38BDF8"
ACCENT_GREEN = "#22C55E"
ACCENT_AMBER = "#F59E0B"
ACCENT_RED = "#EF4444"
ACCENT_PURPLE = "#A855F7"


def apply_dark_theme(fig: go.Figure, height: int = 340) -> go.Figure:
    """Apply uniform high-tech dark theme styling to Plotly figure."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=height,
        margin=dict(l=15, r=15, t=35, b=25),
        font=dict(family="Inter, sans-serif", color=THEME_TEXT, size=11),
        xaxis=dict(
            gridcolor=THEME_GRID,
            zerolinecolor=THEME_GRID,
            tickfont=dict(color=THEME_MUTED),
            title_font=dict(color=THEME_TEXT, size=12),
        ),
        yaxis=dict(
            gridcolor=THEME_GRID,
            zerolinecolor=THEME_GRID,
            tickfont=dict(color=THEME_MUTED),
            title_font=dict(color=THEME_TEXT, size=12),
        ),
        legend=dict(
            font=dict(color=THEME_TEXT, size=10),
            bgcolor="rgba(21, 30, 48, 0.8)",
            bordercolor=THEME_GRID,
            borderwidth=1,
        ),
        hoverlabel=dict(
            bgcolor="#0F172A",
            bordercolor=ACCENT_BLUE,
            font=dict(family="Inter", color="#FFFFFF", size=11),
        ),
    )
    return fig


def render_activity_over_time_chart(
    history_df: pd.DataFrame,
    freq: str = "15min",
) -> go.Figure:
    """Render territory claim events and takeovers over time."""
    if history_df.empty or "claim_timestamp" not in history_df.columns:
        fig = go.Figure()
        fig.add_annotation(text="No activity data available", showarrow=False, font=dict(color=THEME_MUTED))
        return apply_dark_theme(fig)

    df = history_df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["claim_timestamp"]):
        df["claim_timestamp"] = pd.to_datetime(df["claim_timestamp"], utc=True)

    # Floor by frequency
    df["time_bin"] = df["claim_timestamp"].dt.floor(freq)
    grouped = (
        df.groupby(["time_bin", "event_type"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )

    fig = go.Figure()

    if "INITIAL_CAPTURE" in grouped.columns:
        fig.add_trace(
            go.Scatter(
                x=grouped["time_bin"],
                y=grouped["INITIAL_CAPTURE"],
                name="Initial Captures",
                mode="lines+markers",
                line=dict(color=ACCENT_BLUE, width=2),
                marker=dict(size=4),
                stackgroup="one",
            )
        )

    if "TAKEOVER" in grouped.columns:
        fig.add_trace(
            go.Scatter(
                x=grouped["time_bin"],
                y=grouped["TAKEOVER"],
                name="Takeovers",
                mode="lines+markers",
                line=dict(color=ACCENT_PURPLE, width=2),
                marker=dict(size=4),
                stackgroup="one",
            )
        )

    if "SAME_OWNER_REVISIT" in grouped.columns:
        fig.add_trace(
            go.Scatter(
                x=grouped["time_bin"],
                y=grouped["SAME_OWNER_REVISIT"],
                name="Revisits",
                mode="lines+markers",
                line=dict(color=ACCENT_GREEN, width=1.5, dash="dot"),
                marker=dict(size=3),
            )
        )

    fig.update_layout(
        title=dict(text="Territory Conquest Activity Over Time (UTC)", font=dict(size=13, color=THEME_TEXT)),
        xaxis_title="Timeline (UTC)",
        yaxis_title="Events / 15-Min",
        hovermode="x unified",
    )
    return apply_dark_theme(fig, height=320)


def render_top_owners_chart(
    leaderboard_df: pd.DataFrame,
    top_n: int = 10,
) -> go.Figure:
    """Render horizontal bar chart of top runners by zones owned."""
    if leaderboard_df.empty or "zones_owned" not in leaderboard_df.columns:
        fig = go.Figure()
        fig.add_annotation(text="No leaderboard data available", showarrow=False, font=dict(color=THEME_MUTED))
        return apply_dark_theme(fig)

    top_df = leaderboard_df.head(top_n).iloc[::-1]  # Invert for horizontal bar
    colors = [get_runner_color(r) for r in top_df["runner_id"]]

    fig = go.Figure(
        go.Bar(
            x=top_df["zones_owned"],
            y=top_df["runner_id"],
            orientation="h",
            marker=dict(color=colors, line=dict(color="rgba(255,255,255,0.2)", width=1)),
            text=top_df["zones_owned"],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Currently Owned Zones: %{x}<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text=f"Top {top_n} Territory Owners (Active Zones)", font=dict(size=13, color=THEME_TEXT)),
        xaxis_title="Zones Owned",
        yaxis_title="",
    )
    return apply_dark_theme(fig, height=320)


def render_contested_zones_chart(
    contested_df: pd.DataFrame,
    top_n: int = 10,
) -> go.Figure:
    """Render horizontal bar chart of most fiercely contested H3 zones."""
    if contested_df.empty or "takeover_count" not in contested_df.columns:
        fig = go.Figure()
        fig.add_annotation(text="No contested zone data available", showarrow=False, font=dict(color=THEME_MUTED))
        return apply_dark_theme(fig)

    top_df = contested_df.head(top_n).iloc[::-1]

    fig = go.Figure(
        go.Bar(
            x=top_df["takeover_count"],
            y=top_df["h3_cell"],
            orientation="h",
            marker=dict(
                color=top_df["takeover_count"],
                colorscale="Reds",
                line=dict(color="rgba(255,255,255,0.15)", width=1),
            ),
            text=top_df["takeover_count"],
            textposition="outside",
            hovertemplate="<b>Zone: %{y}</b><br>Takeover Count: %{x}<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text=f"Top {top_n} Most Contested H3 Zones", font=dict(size=13, color=THEME_TEXT)),
        xaxis_title="Takeover Events",
        yaxis_title="",
    )
    return apply_dark_theme(fig, height=320)


def render_risk_category_donut(risk_df: pd.DataFrame) -> go.Figure:
    """Render donut chart of kinematic risk category distribution."""
    if risk_df.empty or "risk_category" not in risk_df.columns:
        fig = go.Figure()
        fig.add_annotation(text="No risk data available", showarrow=False, font=dict(color=THEME_MUTED))
        return apply_dark_theme(fig)

    counts = risk_df["risk_category"].value_counts().reset_index()
    counts.columns = ["category", "count"]

    color_map = {
        "NORMAL": ACCENT_GREEN,
        "SUSPICIOUS": ACCENT_AMBER,
        "HIGH_RISK": ACCENT_RED,
    }
    slice_colors = [color_map.get(cat, ACCENT_BLUE) for cat in counts["category"]]

    fig = go.Figure(
        go.Pie(
            labels=counts["category"],
            values=counts["count"],
            hole=0.62,
            marker=dict(colors=slice_colors, line=dict(color="#0B1120", width=2)),
            textinfo="label+percent",
            hoverinfo="label+value+percent",
        )
    )
    fig.update_layout(
        title=dict(text="Kinematic Risk Classification", font=dict(size=13, color=THEME_TEXT)),
        showlegend=True,
    )
    return apply_dark_theme(fig, height=280)


def render_risk_score_histogram(risk_df: pd.DataFrame) -> go.Figure:
    """Render histogram of continuous fraud risk scores [0.0 - 1.0]."""
    if risk_df.empty or "fraud_score" not in risk_df.columns:
        fig = go.Figure()
        fig.add_annotation(text="No risk scores available", showarrow=False, font=dict(color=THEME_MUTED))
        return apply_dark_theme(fig)

    fig = go.Figure(
        go.Histogram(
            x=risk_df["fraud_score"],
            nbinsx=25,
            marker=dict(
                color=ACCENT_BLUE,
                line=dict(color="#0B1120", width=1),
            ),
            hovertemplate="Fraud Score: %{x}<br>Runs: %{y}<extra></extra>",
        )
    )
    # Add vertical threshold lines
    fig.add_vline(x=0.30, line_dash="dash", line_color=ACCENT_AMBER, annotation_text="Suspicious", annotation_position="top left")
    fig.add_vline(x=0.60, line_dash="dash", line_color=ACCENT_RED, annotation_text="High Risk", annotation_position="top right")

    fig.update_layout(
        title=dict(text="Fraud Risk Score Distribution", font=dict(size=13, color=THEME_TEXT)),
        xaxis_title="Composite Fraud Score [0.0 - 1.0]",
        yaxis_title="Evaluated Runs",
    )
    return apply_dark_theme(fig, height=280)


def render_anomaly_reasons_chart(risk_df: pd.DataFrame) -> go.Figure:
    """Render bar chart of detected anomaly reasons across runs."""
    if risk_df.empty or "anomaly_reasons" not in risk_df.columns:
        fig = go.Figure()
        fig.add_annotation(text="No anomaly reasons data", showarrow=False, font=dict(color=THEME_MUTED))
        return apply_dark_theme(fig)

    # Explode comma-separated reasons
    all_reasons = (
        risk_df["anomaly_reasons"]
        .dropna()
        .str.split(",")
        .explode()
        .str.strip()
    )
    counts = all_reasons.value_counts().reset_index()
    counts.columns = ["reason", "count"]

    fig = go.Figure(
        go.Bar(
            x=counts["count"],
            y=counts["reason"],
            orientation="h",
            marker=dict(
                color=counts["count"],
                colorscale="Viridis",
                line=dict(color="rgba(255,255,255,0.15)", width=1),
            ),
            text=counts["count"],
            textposition="outside",
        )
    )
    fig.update_layout(
        title=dict(text="Kinematic Violation Reasons", font=dict(size=13, color=THEME_TEXT)),
        xaxis_title="Flagged Occurrences",
        yaxis_title="",
    )
    return apply_dark_theme(fig, height=300)


def render_hourly_activity_chart(history_df: pd.DataFrame) -> go.Figure:
    """Render bar chart of activity aggregated by hour of day (0-23 UTC)."""
    if history_df.empty or "claim_timestamp" not in history_df.columns:
        fig = go.Figure()
        fig.add_annotation(text="No activity data available", showarrow=False, font=dict(color=THEME_MUTED))
        return apply_dark_theme(fig)

    df = history_df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["claim_timestamp"]):
        df["claim_timestamp"] = pd.to_datetime(df["claim_timestamp"], utc=True)

    df["hour"] = df["claim_timestamp"].dt.hour
    hourly = df.groupby("hour").size().reindex(range(24), fill_value=0).reset_index()
    hourly.columns = ["hour", "claims"]

    fig = go.Figure(
        go.Bar(
            x=hourly["hour"],
            y=hourly["claims"],
            marker=dict(color=ACCENT_BLUE, line=dict(color="#0B1120", width=1)),
            text=hourly["claims"],
            textposition="auto",
            hovertemplate="Hour %{x}:00 UTC<br>Claims: %{y}<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text="Diurnal Activity Pattern (Hourly UTC)", font=dict(size=13, color=THEME_TEXT)),
        xaxis_title="Hour of Day (UTC)",
        yaxis_title="Total Confirmed Claims",
        xaxis=dict(tickmode="linear", tick0=0, dtick=2),
    )
    return apply_dark_theme(fig, height=300)


def render_distance_distribution_chart(risk_df: pd.DataFrame) -> go.Figure:
    """Render histogram of total distances traversed per run in km."""
    if risk_df.empty or "total_distance_m" not in risk_df.columns:
        fig = go.Figure()
        fig.add_annotation(text="No distance data available", showarrow=False, font=dict(color=THEME_MUTED))
        return apply_dark_theme(fig)

    dist_km = (risk_df["total_distance_m"] / 1000.0).round(2)

    fig = go.Figure(
        go.Histogram(
            x=dist_km,
            nbinsx=30,
            marker=dict(color=ACCENT_GREEN, line=dict(color="#0B1120", width=1)),
            hovertemplate="Distance: %{x} km<br>Runs: %{y}<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text="Run Distance Distribution (km)", font=dict(size=13, color=THEME_TEXT)),
        xaxis_title="Distance (km)",
        yaxis_title="Number of Runs",
    )
    return apply_dark_theme(fig, height=280)
