"""Live Simulation Page for Territory Intelligence BI Platform (Day 4).

Renders real-time GPS stream simulation controls, incremental hexagonal territory
mapping, auto-refreshing rankings, and big data performance benchmarks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import folium
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

from dashboard.components.live_event_feed import render_live_event_feed
from dashboard.components.live_metrics import render_live_metrics
from dashboard.components.maps import calculate_map_center, get_h3_polygon_boundary
from dashboard.components.replay_controls import render_replay_controls
from dashboard.services.metrics import get_runner_color
from src.realtime.replay_engine import ReplayEngine
from src.utils import get_project_root


def render_live_folium_map(
    current_ownership_df: pd.DataFrame,
    newly_captured: List[str],
    takeovers: List[str],
    height: int = 520,
) -> None:
    """Render interactive Folium map for live simulated territory control."""
    if current_ownership_df.empty or "h3_cell" not in current_ownership_df.columns:
        st.info("No active territory claims committed yet. Click 'START' to begin simulation.")
        return

    center_lat, center_lon = calculate_map_center(current_ownership_df["h3_cell"].tolist())

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles="CartoDB dark_matter",
        prefer_canvas=True,
    )

    new_set = set(newly_captured)
    takeover_set = set(takeovers)

    # Render up to 500 active zones for smooth frame rates
    for _, row in current_ownership_df.head(500).iterrows():
        cell = row["h3_cell"]
        owner = row.get("current_owner_id", "Unknown")
        prev_owner = row.get("previous_owner_id") or "None (Initial)"
        claims = row.get("total_zone_claims", 1)
        takes = row.get("total_zone_takeovers", 0)
        revisits = row.get("total_zone_revisits", 0)
        unique_runners = row.get("unique_zone_runners", 1)
        acq_at = row.get("acquired_at", "")

        boundary = get_h3_polygon_boundary(cell)
        if not boundary:
            continue

        base_color = get_runner_color(owner)

        # Dynamic visual highlight for newly captured and takeover zones
        if cell in takeover_set:
            border_color = "#EF4444"  # bright red/flame border for takeovers
            weight = 3.5
            opacity = 1.0
            fill_opacity = 0.85
        elif cell in new_set:
            border_color = "#10B981"  # bright emerald green border for new captures
            weight = 3.5
            opacity = 1.0
            fill_opacity = 0.85
        else:
            border_color = "#FFFFFF"
            weight = 1.0
            opacity = 0.35
            fill_opacity = 0.65

        tooltip_html = f"""
        <div style="font-family: sans-serif; font-size: 11px; background: #0F172A; color: #F8FAFC; padding: 6px; border-radius: 4px;">
            <strong style="color: #38BDF8;">Zone {cell[:9]}...</strong><br/>
            <strong>Owner:</strong> <span style="color: {base_color}; font-weight: 700;">{owner}</span><br/>
            <strong>Previous:</strong> {prev_owner}<br/>
            <strong>Claims:</strong> {claims} • <strong>Takeovers:</strong> {takes}<br/>
            <strong>Unique Runners:</strong> {unique_runners}
        </div>
        """

        folium.Polygon(
            locations=boundary,
            color=border_color,
            weight=weight,
            opacity=opacity,
            fill=True,
            fill_color=base_color,
            fill_opacity=fill_opacity,
            tooltip=folium.Tooltip(tooltip_html),
        ).add_to(m)

    st_folium(
        m,
        key="live_sim_folium_map",
        width=None,
        height=height,
        returned_objects=[],
    )


def render_benchmarks_tab() -> None:
    """Render big data benchmark analytics and throughput comparison charts."""
    root = get_project_root()
    csv_file = root / "data" / "reports" / "final_benchmark.csv"
    if not csv_file.exists():
        csv_file = root / "data" / "reports" / "benchmark_results.csv"
    json_file = root / "data" / "reports" / "final_benchmark.json"
    if not json_file.exists():
        json_file = root / "data" / "reports" / "benchmark_results.json"

    if not csv_file.exists():
        st.info("No benchmark results available. Run benchmarks via CLI or scripts/run_benchmarks.ps1.")
        return

    try:
        df_bench = pd.read_csv(csv_file)
    except Exception as e:
        st.error(f"Error loading benchmark CSV: {e}")
        return

    st.markdown("#### ⚡ PySpark Scaling & Performance Profiling")

    # Display benchmark KPI summary
    b_cols = st.columns(4)
    with b_cols[0]:
        st.metric("Tested Scales", f"{len(df_bench)} Datasets")
    with b_cols[1]:
        fastest_thru = df_bench["records_per_second"].max() if not df_bench.empty else 0
        st.metric("Peak Throughput", f"{fastest_thru:,.0f} rec/s")
    with b_cols[2]:
        total_recs = df_bench["input_records"].sum() if not df_bench.empty else 0
        st.metric("Total Records Evaluated", f"{total_recs:,}")
    with b_cols[3]:
        max_duration = df_bench["total_duration_s"].max() if not df_bench.empty else 0
        st.metric("Max Batch Runtime", f"{max_duration:.1f} s")

    # Display Table
    st.dataframe(
        df_bench[[
            "scale", "status", "input_records", "file_size_mb",
            "total_duration_s", "records_per_second",
            "ingestion_s", "cleaning_s", "cheat_detection_s",
            "h3_indexing_s", "territory_conquest_s", "parquet_write_s",
        ]],
        use_container_width=True,
        hide_index=True,
    )

    # Plotly Visualizations: Throughput & Stage Breakdown
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        fig_thru = px.bar(
            df_bench,
            x="scale",
            y="records_per_second",
            color="scale",
            text="records_per_second",
            title="Processing Throughput by Scale (Records / Second)",
            labels={"records_per_second": "Records / Sec", "scale": "Dataset Scale"},
            template="plotly_dark",
        )
        fig_thru.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
        fig_thru.update_layout(showlegend=False, height=340, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_thru, use_container_width=True)

    with col_chart2:
        stage_cols = [
            ("Ingestion", "ingestion_s"),
            ("Cleaning", "cleaning_s"),
            ("Fraud Detection", "cheat_detection_s"),
            ("H3 Indexing", "h3_indexing_s"),
            ("Territory Conquest", "territory_conquest_s"),
            ("Parquet Writes", "parquet_write_s"),
        ]

        fig_stages = go.Figure()
        for label, col_name in stage_cols:
            if col_name in df_bench.columns:
                fig_stages.add_trace(go.Bar(
                    x=df_bench["scale"],
                    y=df_bench[col_name],
                    name=label,
                ))

        fig_stages.update_layout(
            barmode="stack",
            title="Stage Duration Breakdown by Dataset Scale (Seconds)",
            xaxis_title="Scale",
            yaxis_title="Duration (Seconds)",
            template="plotly_dark",
            height=340,
            margin=dict(l=10, r=10, t=40, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
        )
        st.plotly_chart(fig_stages, use_container_width=True)

    # 3. Processing Time vs Dataset Size (Measured Empirical vs Theoretical O(N) Scaling - Phase 11 requirement)
    st.markdown("##### 📈 Scalability Curve: Processing Duration vs Dataset Volume")

    fig_scale = go.Figure()

    # Measured execution times
    fig_scale.add_trace(go.Scatter(
        x=df_bench["input_records"],
        y=df_bench["total_duration_s"],
        mode="lines+markers+text",
        name="Measured Wall-Clock Duration",
        line=dict(color="#38BDF8", width=3),
        marker=dict(size=10, color="#0284C7", line=dict(color="#FFFFFF", width=2)),
        text=[f"{v:.1f}s" for v in df_bench["total_duration_s"]],
        textposition="top left",
    ))

    # Theoretical O(N) linear extrapolation based on first scale throughput
    if not df_bench.empty and df_bench["input_records"].iloc[0] > 0:
        base_rate = df_bench["records_per_second"].iloc[0]
        theo_x = [100000, 500000, 1000000]
        theo_y = [round(x / base_rate, 1) for x in theo_x]

        fig_scale.add_trace(go.Scatter(
            x=theo_x,
            y=theo_y,
            mode="lines",
            name="Theoretical Linear Scaling (O(N) @ 1,002 rec/s)",
            line=dict(color="#94A3B8", width=2, dash="dash"),
        ))

    fig_scale.update_layout(
        title="Processing Time vs Dataset Volume (Measured Empirical vs Theoretical Scaling)",
        xaxis_title="Input Records (Volume)",
        yaxis_title="Processing Duration (Seconds)",
        template="plotly_dark",
        height=320,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
    )
    st.plotly_chart(fig_scale, use_container_width=True)

    st.caption(
        "💡 **Empirical Benchmarking Notice:** Measured durations reflect actual wall-clock execution on local Windows 11 single-node PySpark (2 cores, 2GB heap). "
        "Theoretical linear scaling models idealized constant-throughput throughput prior to JVM garbage collection overhead."
    )


@st.fragment(run_every=1.0)
def render_live_simulation_fragment(engine: ReplayEngine) -> None:
    """Lightweight fragment updating replay controls, KPIs, live map, and feed every second."""
    snapshot = engine.get_snapshot()
    metrics = snapshot["metrics"]
    new_cells = snapshot.get("newly_captured_cells", [])
    takeover_cells = snapshot.get("takeover_cells", [])
    recent_events = snapshot.get("recent_events", [])

    # Replay Controls Toolbar
    render_replay_controls(engine)

    st.markdown("---")

    # Real-Time KPI Cards
    render_live_metrics(metrics)

    st.markdown("")

    # Main split view: Live Folium Map on left, Dynamic Analytics on right
    map_col, stats_col = st.columns([1.35, 1.0])

    curr_df = engine.get_current_ownership_df()
    lb_df = engine.get_leaderboard_df()

    with map_col:
        st.markdown("#### 🗺️ Live Hexagonal Territory Map")
        render_live_folium_map(
            current_ownership_df=curr_df,
            newly_captured=new_cells,
            takeovers=takeover_cells,
            height=530,
        )

        st.caption(
            "🟢 Emerald highlight = Newly captured zone • 🔥 Red highlight = Takeover in progress • "
            "Colors deterministically mapped to runner IDs."
        )

    with stats_col:
        tab_lb, tab_feed, tab_hotspots, tab_bench = st.tabs([
            "🏆 Live Leaderboard",
            "⚡ Conquest Feed",
            "🔥 Hotspots",
            "📊 Benchmarks",
        ])

        with tab_lb:
            st.markdown("##### 🏆 Current Territory Leaderboard")
            if not lb_df.empty:
                st.dataframe(
                    lb_df[["rank", "runner_id", "zones_owned", "total_captures", "takeovers"]],
                    use_container_width=True,
                    hide_index=True,
                    height=450,
                )
            else:
                st.info("Leaderboard will populate as territory claims are processed.")

        with tab_feed:
            render_live_event_feed(recent_events, max_display=15)

        with tab_hotspots:
            st.markdown("##### 🔥 Real-Time Hotspot Zones")
            hotspots_df = engine.get_hotspot_scores_df()
            if not hotspots_df.empty:
                st.dataframe(
                    hotspots_df[[
                        "hotspot_rank", "h3_cell", "hotspot_score",
                        "total_visits", "unique_runners", "takeovers",
                    ]],
                    use_container_width=True,
                    hide_index=True,
                    height=450,
                )
            else:
                st.info("Hotspot scores calculate incrementally as claims arrive.")

        with tab_bench:
            render_benchmarks_tab()


def render_live_simulation_page(datasets: Optional[Dict[str, Any]] = None) -> None:
    """Entrypoint for the Live Simulation dashboard page."""
    st.markdown(
        """
        <div style="margin-bottom: 1.25rem;">
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <h1 style="margin: 0; font-size: 1.85rem; font-weight: 800; color: #F8FAFC;">
                    ⚡ SIMULATED REAL-TIME REPLAY
                </h1>
                <span style="background: rgba(56, 189, 248, 0.15); color: #38BDF8; border: 1px solid rgba(56, 189, 248, 0.35); padding: 3px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 700;">
                    MICRO-BATCH PLAYBACK
                </span>
            </div>
            <p style="margin: 0.35rem 0 0 0; color: #94A3B8; font-size: 0.88rem;">
                Deterministic micro-batch simulated GPS stream playback, incremental Uber H3 territory ownership,
                and ACID SQLite state recovery.
            </p>
        </div>
        <div style="background: rgba(15, 23, 42, 0.6); border-left: 3px solid #38BDF8; padding: 0.55rem 0.9rem; border-radius: 4px; font-size: 0.76rem; color: #94A3B8; margin-bottom: 1rem;">
            <strong style="color: #F8FAFC;">Architecture Notice:</strong> This simulation demonstrates local micro-batch state machine transitions and incremental H3 territory acquisition. 
            <em>It is an academic simulation engine, not a production Apache Kafka streaming ingestion pipeline or live device GPS stream.</em>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Acquire replay engine singleton
    engine = ReplayEngine.get_instance()

    # Render refreshing fragment
    render_live_simulation_fragment(engine)


if __name__ == "__main__":
    from dashboard.app import inject_custom_css
    from dashboard.services.data_loader import load_all_datasets

    inject_custom_css()
    _datasets = load_all_datasets()
    render_live_simulation_page(_datasets)

