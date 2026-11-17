"""Data Export Service for Territory Intelligence BI Platform.

Enables secure, filtered CSV downloads corresponding directly to user-facing tables
without leaking sensitive or raw intermediate personal tracking data.
"""

from __future__ import annotations

import io
from typing import Optional

import pandas as pd
import streamlit as st


def convert_df_to_csv(df: pd.DataFrame, exclude_cols: Optional[list] = None) -> bytes:
    """Serialize DataFrame to UTF-8 encoded CSV bytes.

    Args:
        df: Input DataFrame.
        exclude_cols: List of column names to omit from export.

    Returns:
        UTF-8 encoded CSV bytes.
    """
    if df.empty:
        return b""

    export_df = df.copy()
    if exclude_cols:
        export_df = export_df.drop(columns=[c for c in exclude_cols if c in export_df.columns])

    # Convert timestamps to ISO string format for clean Excel / BI import
    for col in export_df.columns:
        if pd.api.types.is_datetime64_any_dtype(export_df[col]):
            export_df[col] = export_df[col].dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    buffer = io.StringIO()
    export_df.to_csv(buffer, index=False, encoding="utf-8")
    return buffer.getvalue().encode("utf-8")


def generate_csv_download(
    df: pd.DataFrame,
    filename: str,
    button_label: str = "📥 Export CSV",
    key: Optional[str] = None,
    help_text: str = "Download displayed records as CSV",
) -> None:
    """Render a styled Streamlit CSV download button for the current table view.

    Args:
        df: Filtered DataFrame matching current UI view.
        filename: Destination filename (e.g. 'leaderboard.csv').
        button_label: Label displayed on the download button.
        key: Unique Streamlit component key.
        help_text: Tooltip description.
    """
    if df.empty:
        st.button(button_label, disabled=True, key=key, help="No records available to export")
        return

    csv_data = convert_df_to_csv(df)
    st.download_button(
        label=button_label,
        data=csv_data,
        file_name=filename,
        mime="text/csv",
        key=key,
        help=help_text,
    )
