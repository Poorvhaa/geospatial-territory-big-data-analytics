"""Filtering Services for Territory Intelligence BI Platform.

Provides reusable filtering functions with strictly defined analytical scopes:
- Temporal filters apply strictly to historical time-series datasets (claim events, ownership history, runs).
- Current ownership is a latest-state snapshot and is preserved intact to avoid misleading analytics.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Union

import pandas as pd

logger = logging.getLogger(__name__)


def filter_by_runner(
    df: pd.DataFrame,
    runner_ids: Union[str, List[str], None],
    runner_col: str = "runner_id",
) -> pd.DataFrame:
    """Filter DataFrame by one or multiple runner identifiers.

    Args:
        df: Input DataFrame.
        runner_ids: Single runner ID, list of runner IDs, or None (returns unfiltered).
        runner_col: Column name containing runner identifier.

    Returns:
        Filtered DataFrame.
    """
    if df.empty or runner_ids is None:
        return df

    if runner_col not in df.columns:
        # Check alternative common column names
        if "current_owner_id" in df.columns:
            runner_col = "current_owner_id"
        else:
            return df

    if isinstance(runner_ids, str):
        if runner_ids in ("", "All", "All Runners"):
            return df
        return df[df[runner_col] == runner_ids]

    if isinstance(runner_ids, (list, set, tuple)):
        clean_ids = [r for r in runner_ids if r not in ("", "All", "All Runners")]
        if not clean_ids:
            return df
        return df[df[runner_col].isin(clean_ids)]

    return df


def filter_by_time_range(
    df: pd.DataFrame,
    start_time: Optional[Union[datetime, str, pd.Timestamp]] = None,
    end_time: Optional[Union[datetime, str, pd.Timestamp]] = None,
    time_col: str = "claim_timestamp",
) -> pd.DataFrame:
    """Filter historical time-series DataFrame by UTC timestamp range.

    NOTE: This must NOT be applied to `current_ownership` snapshots, which represent
    the latest state of the board.

    Args:
        df: Input time-series DataFrame.
        start_time: Inclusive start timestamp.
        end_time: Inclusive end timestamp.
        time_col: Name of datetime column.

    Returns:
        Filtered DataFrame.
    """
    if df.empty or time_col not in df.columns:
        return df

    if start_time is None and end_time is None:
        return df

    filtered_df = df.copy()

    # Ensure time_col is datetime with UTC tz
    if not pd.api.types.is_datetime64_any_dtype(filtered_df[time_col]):
        filtered_df[time_col] = pd.to_datetime(filtered_df[time_col], utc=True)
    elif filtered_df[time_col].dt.tz is None:
        filtered_df[time_col] = filtered_df[time_col].dt.tz_localize("UTC")
    else:
        filtered_df[time_col] = filtered_df[time_col].dt.tz_convert("UTC")

    if start_time is not None:
        ts_start = pd.to_datetime(start_time, utc=True)
        filtered_df = filtered_df[filtered_df[time_col] >= ts_start]

    if end_time is not None:
        ts_end = pd.to_datetime(end_time, utc=True)
        filtered_df = filtered_df[filtered_df[time_col] <= ts_end]

    return filtered_df


def filter_by_risk_category(
    df: pd.DataFrame,
    categories: Union[str, List[str], None],
    risk_col: str = "risk_category",
) -> pd.DataFrame:
    """Filter run-level anomaly DataFrame by risk classification.

    Args:
        df: Input DataFrame.
        categories: Single category or list (e.g. ['NORMAL', 'HIGH_RISK']).
        risk_col: Column containing risk category.

    Returns:
        Filtered DataFrame.
    """
    if df.empty or categories is None or risk_col not in df.columns:
        return df

    if isinstance(categories, str):
        if categories in ("", "All", "ALL"):
            return df
        return df[df[risk_col] == categories]

    if isinstance(categories, (list, set, tuple)):
        clean_cats = [c for c in categories if c not in ("", "All", "ALL")]
        if not clean_cats:
            return df
        return df[df[risk_col].isin(clean_cats)]

    return df


def filter_by_zone(
    df: pd.DataFrame,
    h3_cells: Union[str, List[str], None],
    zone_col: str = "h3_cell",
) -> pd.DataFrame:
    """Filter DataFrame by specific H3 cell index or list of cells."""
    if df.empty or h3_cells is None or zone_col not in df.columns:
        return df

    if isinstance(h3_cells, str):
        if h3_cells in ("", "All"):
            return df
        return df[df[zone_col] == h3_cells]

    if isinstance(h3_cells, (list, set, tuple)):
        clean_cells = [c for c in h3_cells if c not in ("", "All")]
        if not clean_cells:
            return df
        return df[df[zone_col].isin(clean_cells)]

    return df


def filter_by_top_n(
    df: pd.DataFrame,
    top_n: Optional[int],
    sort_col: Optional[str] = None,
    ascending: bool = False,
) -> pd.DataFrame:
    """Sort and limit DataFrame to Top N rows."""
    if df.empty or top_n is None or top_n <= 0:
        return df

    target_df = df
    if sort_col and sort_col in df.columns:
        target_df = df.sort_values(by=sort_col, ascending=ascending)

    return target_df.head(top_n).reset_index(drop=True)


def filter_by_metric(
    df: pd.DataFrame,
    metric_col: str,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
) -> pd.DataFrame:
    """Filter DataFrame by numeric range on specified metric column."""
    if df.empty or metric_col not in df.columns:
        return df

    res = df
    if min_val is not None:
        res = res[res[metric_col] >= min_val]
    if max_val is not None:
        res = res[res[metric_col] <= max_val]
    return res
