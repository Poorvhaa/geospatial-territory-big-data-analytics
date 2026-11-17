"""Live Event Feed Component for Real-Time Territory Conquest (Day 4).

Renders a chronological live feed of territory conquest, takeovers, and initial captures.
"""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st


def render_live_event_feed(events: List[Dict[str, Any]], max_display: int = 20) -> None:
    """Render real-time conquest notifications feed."""
    st.markdown("#### ⚡ Live Conquest Feed")

    if not events:
        st.markdown(
            """
            <div style="background: #0F172A; padding: 1.5rem; border-radius: 8px; border: 1px dashed #334155; text-align: center; color: #64748B;">
                <em>No territory events in the current batch. Press <strong>START</strong> above to begin replay.</em>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    feed_items = []
    for evt in events[:max_display]:
        e_type = evt.get("event_type", "INFO")
        ts = evt.get("event_timestamp", "")
        if "T" in ts:
            ts_short = ts.split("T")[1].replace("Z", "")
        else:
            ts_short = ts

        runner = evt.get("runner_id", "")
        cell = evt.get("h3_cell", "")
        msg = evt.get("message", "")

        if e_type == "INITIAL_CAPTURE":
            badge = '<span style="background: #064E3B; color: #34D399; padding: 2px 8px; border-radius: 4px; font-size: 0.72rem; font-weight: 600;">NEW CAPTURE</span>'
            border_col = "#059669"
        elif e_type == "TAKEOVER":
            badge = '<span style="background: #78350F; color: #FBA04B; padding: 2px 8px; border-radius: 4px; font-size: 0.72rem; font-weight: 600;">🔥 TAKEOVER</span>'
            border_col = "#D97706"
        else:
            badge = '<span style="background: #1E293B; color: #94A3B8; padding: 2px 8px; border-radius: 4px; font-size: 0.72rem; font-weight: 600;">ACTIVITY</span>'
            border_col = "#334155"

        feed_items.append(f"""
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 0.5rem 0.75rem; margin-bottom: 0.4rem; background: #0F172A; border-left: 3px solid {border_col}; border-radius: 4px; font-size: 0.82rem;">
                <div>
                    {badge}
                    <span style="color: #F8FAFC; font-weight: 600; margin-left: 0.5rem;">{runner}</span>
                    <span style="color: #94A3B8; margin-left: 0.25rem;">in zone</span>
                    <code style="color: #38BDF8; background: rgba(56, 189, 248, 0.1); padding: 1px 4px; border-radius: 3px; font-size: 0.75rem;">{cell[:9]}...</code>
                </div>
                <div style="color: #64748B; font-size: 0.75rem;">
                    {ts_short}
                </div>
            </div>
        """)

    feed_html = f"""
    <div style="max-height: 380px; overflow-y: auto; padding-right: 0.25rem;">
        {''.join(feed_items)}
    </div>
    """
    st.markdown(feed_html, unsafe_allow_html=True)
