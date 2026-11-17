"""Data Table and Empty State Components for Territory Intelligence BI Platform."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st


def render_empty_state(
    title: str = "No Data Available",
    message: str = "No records match the current selection or filters. Try adjusting your filter parameters.",
    icon: str = "🔍",
) -> None:
    """Render a clean, informative empty-state container."""
    html = f"""
    <div class="empty-state-box">
        <div style="font-size: 2.2rem; margin-bottom: 0.5rem;">{icon}</div>
        <div class="empty-state-title">{title}</div>
        <div style="font-size: 0.85rem; max-width: 480px; margin: 0 auto; color: #94A3B8;">{message}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_data_table(
    df: pd.DataFrame,
    column_config: Optional[Dict[str, Any]] = None,
    hide_index: bool = True,
    use_container_width: bool = True,
    height: Optional[int] = None,
    empty_title: str = "No Records Found",
    empty_message: str = "No table rows to display.",
) -> None:
    """Render an interactive styled Streamlit data table with empty-state fallback.

    Args:
        df: Input DataFrame.
        column_config: Streamlit ColumnConfig mapping.
        hide_index: Whether to hide DataFrame index.
        use_container_width: Stretch table across container width.
        height: Fixed scrollable height in pixels.
        empty_title: Title for empty fallback.
        empty_message: Description for empty fallback.
    """
    if df.empty:
        render_empty_state(title=empty_title, message=empty_message)
        return

    kwargs: Dict[str, Any] = {
        "column_config": column_config,
        "hide_index": hide_index,
        "width": "stretch" if use_container_width else "content",
    }
    if height is not None:
        kwargs["height"] = height

    st.dataframe(df, **kwargs)
