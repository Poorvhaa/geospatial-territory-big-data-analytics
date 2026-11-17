"""Replay Controls Component for Live Simulation Dashboard (Day 4).

Renders START, PAUSE, RESUME, STOP, RESTART controls, playback speed selector,
progress indicators, and execution state badges.
"""

from __future__ import annotations

import streamlit as st

from src.realtime.replay_engine import ReplayEngine
from src.realtime.replay_state import ReplayStatus


def render_replay_controls(engine: ReplayEngine) -> None:
    """Render interactive control toolbar for GPS replay simulation."""
    snapshot = engine.get_snapshot()
    status = snapshot["status"]
    metrics = snapshot["metrics"]

    status_badges = {
        "STOPPED": '<span style="background: #334155; color: #CBD5E1; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 0.85rem;">⏹️ STOPPED</span>',
        "RUNNING": '<span style="background: #064E3B; color: #34D399; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 0.85rem; border: 1px solid #059669;">▶️ SIMULATING (LIVE)</span>',
        "PAUSED": '<span style="background: #78350F; color: #FCD34D; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 0.85rem; border: 1px solid #D97706;">⏸️ PAUSED</span>',
        "COMPLETED": '<span style="background: #1E3A8A; color: #93C5FD; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 0.85rem; border: 1px solid #3B82F6;">✅ REPLAY COMPLETED</span>',
    }

    st.markdown(
        f"""
        <div style="display: flex; align-items: center; justify-content: space-between; background: #0F172A; padding: 1rem 1.25rem; border-radius: 8px; border: 1px solid #1E293B; margin-bottom: 1rem;">
            <div>
                <span style="font-size: 1.05rem; font-weight: 700; color: #F8FAFC; margin-right: 1rem;">SIMULATED REAL-TIME REPLAY</span>
                {status_badges.get(status, status)}
            </div>
            <div style="font-size: 0.85rem; color: #94A3B8;">
                Current Event Time: <strong style="color: #38BDF8;">{metrics.get('current_event_timestamp') or 'Pending Start'}</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Action buttons and speed selector row
    c1, c2, c3, c4, c5, c6 = st.columns([1.2, 1.2, 1.2, 1.2, 1.2, 2.0])

    with c1:
        start_disabled = status == "RUNNING"
        if st.button("▶️ START", use_container_width=True, disabled=start_disabled, help="Begin GPS replay"):
            engine.start()
            st.rerun()

    with c2:
        pause_disabled = status != "RUNNING"
        if st.button("⏸️ PAUSE", use_container_width=True, disabled=pause_disabled, help="Pause simulated event advancement"):
            engine.pause()
            st.rerun()

    with c3:
        resume_disabled = status != "PAUSED"
        if st.button("⏯️ RESUME", use_container_width=True, disabled=resume_disabled, help="Resume replay without re-processing committed batches"):
            engine.resume()
            st.rerun()

    with c4:
        stop_disabled = status == "STOPPED"
        if st.button("⏹️ STOP", use_container_width=True, disabled=stop_disabled, help="Terminate replay worker cleanly"):
            engine.stop()
            st.rerun()

    with c5:
        if st.button("🔄 RESTART", use_container_width=True, help="Reset database and restart from event 0"):
            engine.restart()
            st.rerun()

    with c6:
        speeds = [1.0, 2.0, 5.0, 10.0]
        current_speed = metrics.get("playback_speed", 1.0)
        curr_idx = speeds.index(current_speed) if current_speed in speeds else 0
        new_speed = st.selectbox(
            "Playback Speed",
            options=speeds,
            index=curr_idx,
            format_func=lambda s: f"⚡ {int(s)}x Playback Speed",
            label_visibility="collapsed",
        )
        if new_speed != current_speed:
            engine.set_playback_speed(new_speed)
            st.rerun()

    # Progress bar and status descriptors
    progress_val = min(1.0, max(0.0, metrics.get("progress_pct", 0.0) / 100.0))
    st.progress(progress_val)

    p_col1, p_col2, p_col3, p_col4 = st.columns(4)
    with p_col1:
        st.caption(f"**Progress:** {metrics.get('progress_pct', 0.0):.1f}%")
    with p_col2:
        st.caption(f"**Processed:** {metrics.get('events_processed', 0):,} / {metrics.get('total_events', 0):,} events")
    with p_col3:
        st.caption(f"**Micro-Batch #:** {metrics.get('batches_processed', 0):,}")
    with p_col4:
        st.caption(f"**Remaining:** {metrics.get('remaining_events', 0):,} events")
