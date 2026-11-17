"""Metric Cards Component for Territory Intelligence BI Platform.

Renders responsive KPI cards adhering to the platform's dark theme design system.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st


def render_kpi_card(
    label: str,
    value: Any,
    subtext: Optional[str] = None,
    accent: str = "blue",
    help_tooltip: Optional[str] = None,
) -> None:
    """Render a single styled KPI card.

    Args:
        label: Card header metric title.
        value: Numeric or text metric value.
        subtext: Contextual descriptor or delta.
        accent: Border accent color ('blue', 'green', 'amber', 'red', 'purple').
        help_tooltip: Optional tooltip information text.
    """
    accent_class = f"kpi-accent-{accent}"

    # Format numeric value with commas if integer
    if isinstance(value, (int, float)):
        if isinstance(value, int) or value.is_integer():
            formatted_val = f"{int(value):,}"
        else:
            formatted_val = f"{value:,.2f}"
    else:
        formatted_val = str(value)

    tooltip_html = f'<span title="{help_tooltip}" style="cursor: help; color: #64748B;">ⓘ</span>' if help_tooltip else ""
    subtext_html = f'<div class="kpi-subtext">{subtext}</div>' if subtext else ""

    # Prevent awkward text wrapping and scale font for large numbers or long strings
    val_len = len(formatted_val)
    if val_len > 12:
        val_style = 'style="font-size: 1.15rem;"'
    elif val_len > 8:
        val_style = 'style="font-size: 1.35rem;"'
    elif val_len > 6:
        val_style = 'style="font-size: 1.55rem;"'
    else:
        val_style = ""

    html = f"""
    <div class="kpi-container {accent_class}">
        <div class="kpi-label">
            <span>{label}</span>
            {tooltip_html}
        </div>
        <div class="kpi-value" {val_style}>{formatted_val}</div>
        {subtext_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_kpi_grid(cards: List[Dict[str, Any]], cols_per_row: int = 4) -> None:
    """Render a responsive grid of KPI cards.

    Args:
        cards: List of dicts with keys: 'label', 'value', 'subtext', 'accent', 'help'.
        cols_per_row: Number of columns per row.
    """
    for i in range(0, len(cards), cols_per_row):
        batch = cards[i : i + cols_per_row]
        cols = st.columns(len(batch))
        for col, card in zip(cols, batch):
            with col:
                render_kpi_card(
                    label=card["label"],
                    value=card["value"],
                    subtext=card.get("subtext"),
                    accent=card.get("accent", "blue"),
                    help_tooltip=card.get("help"),
                )
        st.markdown("<div style='margin-bottom: 0.65rem;'></div>", unsafe_allow_html=True)
