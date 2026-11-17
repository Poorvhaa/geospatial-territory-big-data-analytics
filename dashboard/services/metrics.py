"""Metrics and Analytical Scoring Service for Territory Intelligence BI Platform.

Computes KPI summaries, multi-dimensional runner rankings, normalized hotspot scores,
and deterministic visual attributes across territory conquests.
"""

from __future__ import annotations

import colorsys
import hashlib
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

# Curated high-contrast palette for top runners to ensure maximum visual distinction
PALETTE_30 = [
    "#38BDF8",  # Sky Blue
    "#F43F5E",  # Rose Red
    "#10B981",  # Emerald
    "#F59E0B",  # Amber
    "#8B5CF6",  # Violet
    "#EC4899",  # Pink
    "#06B6D4",  # Cyan
    "#84CC16",  # Lime
    "#EAB308",  # Yellow
    "#6366F1",  # Indigo
    "#14B8A6",  # Teal
    "#F97316",  # Orange
    "#A855F7",  # Purple
    "#22C55E",  # Green
    "#D946EF",  # Fuchsia
    "#3B82F6",  # Blue
    "#FB7185",  # Light Rose
    "#2DD4BF",  # Light Teal
    "#FBBF24",  # Light Amber
    "#C084FC",  # Light Purple
    "#34D399",  # Mint
    "#60A5FA",  # Light Blue
    "#F472B6",  # Light Pink
    "#A3E635",  # Light Lime
    "#FB923C",  # Light Orange
    "#818CF8",  # Periwinkle
    "#4ADE80",  # Bright Green
    "#E879F9",  # Bright Fuchsia
    "#38E1FF",  # Bright Cyan
    "#FFA07A",  # Light Salmon
]


def get_runner_color(runner_id: Optional[str]) -> str:
    """Return a deterministic, high-contrast HEX color for any runner identifier.

    Guarantees that the same runner retains the identical color across refreshes,
    pages, and components, while maintaining readable contrast against dark surfaces.

    Args:
        runner_id: Unique runner string (e.g. 'runner_001').

    Returns:
        Hexadecimal color string (e.g. '#38BDF8').
    """
    if not runner_id or pd.isna(runner_id) or str(runner_id).strip() in ("", "Unclaimed", "nan", "None"):
        return "#64748B"  # Neutral Slate for unassigned/null

    r_str = str(runner_id).strip()

    # If runner follows 'runner_XXX' format, map directly into curated palette
    if r_str.startswith("runner_"):
        try:
            num = int(r_str.replace("runner_", ""))
            return PALETTE_30[num % len(PALETTE_30)]
        except ValueError:
            pass

    # Deterministic fallback via MD5 hash to HLS color space
    digest = hashlib.md5(r_str.encode("utf-8")).digest()
    hue = int.from_bytes(digest[:2], "big") % 360 / 360.0
    # S=0.82, L=0.58 ensures bright, vibrant pastel visibility on dark backgrounds
    r, g, b = colorsys.hls_to_rgb(hue, 0.58, 0.82)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def calculate_kpis(datasets: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate the core Key Performance Indicators directly from processed datasets.

    Derives values primarily from loaded analytical Parquet tables, with fallback
    to the pipeline validation report metadata.

    Returns:
        Dict containing counts for:
        1. total_gps_records
        2. total_runners (active_runners)
        3. valid_running_activities
        4. current_territory_zones (currently_owned_zones / total_h3_zones)
        5. ownership_takeovers
        6. contested_zones
        7. suspicious_activities (suspicious_runs + high_risk_runs)
        8. processing_status
    """
    report = datasets.get("report") or {}
    curr_df = datasets.get("current_ownership")
    hist_df = datasets.get("ownership_history")
    risk_df = datasets.get("run_anomalies")
    contested_df = datasets.get("contested_zones")

    # 1. Total GPS Records (from pipeline report or default 100,000)
    total_gps = report.get("ingestion_stats", {}).get("total_records")
    if total_gps is None or total_gps < 1000:
        total_gps = report.get("data_quality", {}).get("raw_records", 100000)

    # 2. Total / Active Runners (derived from risk_df or hist_df)
    if risk_df is not None and not risk_df.empty and "runner_id" in risk_df.columns:
        active_runners = int(risk_df["runner_id"].nunique())
    elif hist_df is not None and not hist_df.empty and "runner_id" in hist_df.columns:
        active_runners = int(hist_df["runner_id"].nunique())
    else:
        active_runners = int(report.get("runner_summary", {}).get("active_runners", 0))

    # 3. Total H3 Zones & Currently Owned (from current_ownership table)
    if curr_df is not None and not curr_df.empty and "h3_cell" in curr_df.columns:
        total_h3_zones = int(curr_df["h3_cell"].nunique())
    else:
        total_h3_zones = int(report.get("territory_conquest", {}).get("total_unique_zones", 0))

    if curr_df is not None and not curr_df.empty and "current_owner_id" in curr_df.columns:
        currently_owned_zones = int(curr_df["current_owner_id"].dropna().count())
    else:
        currently_owned_zones = total_h3_zones

    # 4. Valid Territory Claims (from ownership_history)
    if hist_df is not None and not hist_df.empty:
        valid_claims = int(len(hist_df))
    else:
        valid_claims = int(report.get("territory_conquest", {}).get("total_claims", 0))

    # 5. Ownership Takeovers (from ownership_history)
    if hist_df is not None and not hist_df.empty:
        if "is_takeover" in hist_df.columns:
            takeovers = int((hist_df["is_takeover"] == True).sum())  # noqa: E712
        elif "event_type" in hist_df.columns:
            takeovers = int((hist_df["event_type"] == "TAKEOVER").sum())
        else:
            takeovers = int(report.get("territory_conquest", {}).get("takeovers", 0))
    else:
        takeovers = int(report.get("territory_conquest", {}).get("takeovers", 0))

    # 6. Contested Zones (zones with at least one takeover)
    if curr_df is not None and not curr_df.empty and "total_zone_takeovers" in curr_df.columns:
        contested_zones = int((curr_df["total_zone_takeovers"] > 0).sum())
    elif contested_df is not None and not contested_df.empty:
        contested_zones = int(len(contested_df))
    else:
        contested_zones = int(report.get("territory_conquest", {}).get("contested_zones", 0))

    # 7. Suspicious, High-Risk, and Valid Activities (from run_anomalies)
    if risk_df is not None and not risk_df.empty and "risk_category" in risk_df.columns:
        counts = risk_df["risk_category"].value_counts().to_dict()
        normal_runs = int(counts.get("NORMAL", 0))
        suspicious_runs = int(counts.get("SUSPICIOUS", 0))
        high_risk_runs = int(counts.get("HIGH_RISK", 0))
    else:
        r_counts = report.get("cheating_detection", {}).get("risk_category_counts", {})
        normal_runs = int(r_counts.get("NORMAL", 0))
        suspicious_runs = int(r_counts.get("SUSPICIOUS", 0))
        high_risk_runs = int(r_counts.get("HIGH_RISK", 0))

    valid_running_activities = normal_runs
    suspicious_activities = suspicious_runs + high_risk_runs

    # 8. Processing Status
    is_valid = report.get("is_valid", True)
    processing_status = "SYNCHRONIZED (PASS)" if is_valid else "VALIDATION PENDING"

    return {
        # Legacy keys preserved for backwards compatibility with tests
        "total_gps_records": total_gps,
        "active_runners": active_runners,
        "total_h3_zones": total_h3_zones,
        "currently_owned_zones": currently_owned_zones,
        "valid_territory_claims": valid_claims,
        "ownership_takeovers": takeovers,
        "suspicious_runs": suspicious_runs,
        "high_risk_runs": high_risk_runs,
        # Day 5 Phase 3 formal KPI keys
        "total_runners": active_runners,
        "valid_running_activities": valid_running_activities,
        "current_territory_zones": currently_owned_zones,
        "contested_zones": contested_zones,
        "suspicious_activities": suspicious_activities,
        "processing_status": processing_status,
    }


def calculate_combined_leaderboard(
    current_ownership_df: pd.DataFrame,
    ownership_history_df: pd.DataFrame,
    run_anomalies_df: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate unified multi-metric runner rankings.

    Reconciles:
    - Current Territory Ownership (latest snapshot zones owned)
    - Total Territory Captures (INITIAL_CAPTURE + TAKEOVER)
    - Successful Takeovers
    - Number of Valid Runs (NORMAL runs)
    - Total Valid Distance (km traversed in normal runs)

    Returns:
        DataFrame with runner_id, metrics, and dense ranks.
    """
    all_runners = set()

    # 1. Current Zones Owned
    if not current_ownership_df.empty and "current_owner_id" in current_ownership_df.columns:
        curr_owners = (
            current_ownership_df.groupby("current_owner_id")
            .agg(zones_owned=("h3_cell", "count"))
            .reset_index()
            .rename(columns={"current_owner_id": "runner_id"})
        )
        all_runners.update(curr_owners["runner_id"])
    else:
        curr_owners = pd.DataFrame(columns=["runner_id", "zones_owned"])

    # 2. Total Captures & Takeovers from history
    if not ownership_history_df.empty and "runner_id" in ownership_history_df.columns:
        captures_mask = ownership_history_df["event_type"].isin(["INITIAL_CAPTURE", "TAKEOVER"])
        captures_df = (
            ownership_history_df[captures_mask]
            .groupby("runner_id")
            .agg(
                total_captures=("claim_id", "count"),
                takeovers=("is_takeover", lambda s: int(s.sum()) if not s.empty else 0),
            )
            .reset_index()
        )
        all_runners.update(captures_df["runner_id"])
    else:
        captures_df = pd.DataFrame(columns=["runner_id", "total_captures", "takeovers"])

    # 3. Valid runs and distance
    if not run_anomalies_df.empty and "runner_id" in run_anomalies_df.columns:
        normal_runs = run_anomalies_df[run_anomalies_df["risk_category"] == "NORMAL"]
        run_stats = (
            normal_runs.groupby("runner_id")
            .agg(
                valid_runs=("run_id", "count"),
                valid_distance_km=("total_distance_m", lambda s: round(float(s.sum()) / 1000.0, 2)),
            )
            .reset_index()
        )
        all_runners.update(run_anomalies_df["runner_id"])
    else:
        run_stats = pd.DataFrame(columns=["runner_id", "valid_runs", "valid_distance_km"])

    if not all_runners:
        return pd.DataFrame(
            columns=[
                "runner_id",
                "zones_owned",
                "total_captures",
                "takeovers",
                "valid_runs",
                "valid_distance_km",
                "rank_zones_owned",
                "rank_total_captures",
                "rank_takeovers",
                "rank_valid_runs",
                "rank_valid_distance",
            ]
        )

    base_df = pd.DataFrame({"runner_id": sorted(all_runners)})
    merged = base_df.merge(curr_owners, on="runner_id", how="left")
    merged = merged.merge(captures_df, on="runner_id", how="left")
    merged = merged.merge(run_stats, on="runner_id", how="left")

    merged["zones_owned"] = merged["zones_owned"].fillna(0).astype(int)
    merged["total_captures"] = merged["total_captures"].fillna(0).astype(int)
    merged["takeovers"] = merged["takeovers"].fillna(0).astype(int)
    merged["valid_runs"] = merged["valid_runs"].fillna(0).astype(int)
    merged["valid_distance_km"] = merged["valid_distance_km"].fillna(0.0).round(2)

    # Compute dense ranks (1 is best, ties get same rank)
    merged["rank_zones_owned"] = merged["zones_owned"].rank(method="dense", ascending=False).astype(int)
    merged["rank_total_captures"] = merged["total_captures"].rank(method="dense", ascending=False).astype(int)
    merged["rank_takeovers"] = merged["takeovers"].rank(method="dense", ascending=False).astype(int)
    merged["rank_valid_runs"] = merged["valid_runs"].rank(method="dense", ascending=False).astype(int)
    merged["rank_valid_distance"] = merged["valid_distance_km"].rank(method="dense", ascending=False).astype(int)

    return merged.sort_values(by=["zones_owned", "total_captures"], ascending=[False, False]).reset_index(drop=True)


def min_max_normalize(series: pd.Series) -> pd.Series:
    """Normalize a pandas Series to [0.0, 1.0] with zero-variance safety.

    If all values are identical (max == min), returns 0.0 for all elements.
    """
    if series.empty:
        return series
    s_min = float(series.min())
    s_max = float(series.max())
    if s_max == s_min:
        return pd.Series(0.0, index=series.index, dtype=float)
    return ((series.astype(float) - s_min) / (s_max - s_min)).round(4)


def calculate_hotspot_scores(
    zone_stats_df: pd.DataFrame,
    contested_df: pd.DataFrame,
    w_takeovers: float = 0.40,
    w_runners: float = 0.35,
    w_visits: float = 0.25,
) -> pd.DataFrame:
    """Compute composite analytical Hotspot Scores for each H3 cell.

    Formula:
        Hotspot Score = (
            w_takeovers * normalized_takeovers
            + w_runners * normalized_unique_runners
            + w_visits * normalized_visits
        )

    Handles zero-variance gracefully and bounds score within [0.0, 1.0].
    """
    if zone_stats_df.empty:
        return pd.DataFrame(
            columns=[
                "h3_cell",
                "total_visits",
                "unique_runners",
                "takeover_count",
                "norm_takeovers",
                "norm_unique_runners",
                "norm_visits",
                "hotspot_score",
                "hotspot_rank",
            ]
        )

    df = zone_stats_df.copy()

    # Join takeover counts from contested_df if present
    if not contested_df.empty and "takeover_count" in contested_df.columns:
        contested_subset = contested_df[["h3_cell", "takeover_count"]].drop_duplicates("h3_cell")
        df = df.merge(contested_subset, on="h3_cell", how="left")
        df["takeover_count"] = df["takeover_count"].fillna(0).astype(int)
    elif "takeover_count" not in df.columns:
        df["takeover_count"] = 0

    df["norm_takeovers"] = min_max_normalize(df["takeover_count"])
    df["norm_unique_runners"] = min_max_normalize(df["unique_runners"])
    df["norm_visits"] = min_max_normalize(df["total_visits"])

    # Composite weighted score
    df["hotspot_score"] = (
        float(w_takeovers) * df["norm_takeovers"]
        + float(w_runners) * df["norm_unique_runners"]
        + float(w_visits) * df["norm_visits"]
    ).round(4)

    # Rank
    df["hotspot_rank"] = df["hotspot_score"].rank(method="dense", ascending=False).astype(int)

    return df.sort_values(by="hotspot_score", ascending=False).reset_index(drop=True)
