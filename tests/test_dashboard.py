"""Unit and integration tests for Territory Intelligence BI Dashboard (Day 3).

Tests:
1. Parquet data loading and schema validation
2. Missing dataset handling and graceful fallbacks
3. KPI calculations from datasets and metadata
4. Leaderboard multi-metric ranking and sorting
5. Deterministic runner color mapping
6. Uber H3 polygon boundary conversion (H3 4.x)
7. Hotspot score composite weighting and zero-variance normalization
8. Filter correctness (runner, risk category, temporal scoping)
9. CSV export serialization
10. Current vs historical territory conquest logic
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd
import pytest

from dashboard.components.charts import (
    render_activity_over_time_chart,
    render_contested_zones_chart,
    render_risk_category_donut,
    render_top_owners_chart,
)
from dashboard.components.maps import get_h3_polygon_boundary, interpolate_color
from dashboard.services.data_loader import (
    load_all_datasets,
    load_current_ownership,
    load_ownership_history,
    load_pipeline_report,
    load_run_anomalies,
    read_parquet_dataset,
    validate_schema,
)
from dashboard.services.exports import convert_df_to_csv
from dashboard.services.filters import (
    filter_by_metric,
    filter_by_risk_category,
    filter_by_runner,
    filter_by_time_range,
    filter_by_top_n,
    filter_by_zone,
)
from dashboard.services.metrics import (
    calculate_combined_leaderboard,
    calculate_hotspot_scores,
    calculate_kpis,
    get_runner_color,
    min_max_normalize,
)


# =====================================================================
# 1. PARQUET DATA LOADING & SCHEMA VALIDATION TESTS
# =====================================================================

def test_parquet_data_loading() -> None:
    """Verify that core Parquet datasets load cleanly into pandas DataFrames."""
    curr_df = load_current_ownership()
    assert not curr_df.empty, "current_ownership should not be empty"
    assert len(curr_df) == 308, f"Expected 308 current zones, got {len(curr_df)}"
    assert "h3_cell" in curr_df.columns
    assert "current_owner_id" in curr_df.columns

    hist_df = load_ownership_history()
    assert not hist_df.empty, "ownership_history should not be empty"
    assert len(hist_df) == 5075, f"Expected 5075 history claims, got {len(hist_df)}"

    risk_df = load_run_anomalies()
    assert not risk_df.empty, "run_anomalies should not be empty"
    assert len(risk_df) == 1250, f"Expected 1250 runs, got {len(risk_df)}"


def test_missing_dataset_handling(tmp_path: Path) -> None:
    """Verify that non-existent Parquet datasets return empty DataFrames without exceptions."""
    empty_df = read_parquet_dataset("non_existent_folder_xyz", base_dir=tmp_path)
    assert isinstance(empty_df, pd.DataFrame)
    assert empty_df.empty


def test_schema_validation() -> None:
    """Verify that expected schema validator identifies missing columns."""
    valid_df = pd.DataFrame(
        {
            "h3_cell": ["892664c112bffff"],
            "current_owner_id": ["runner_001"],
            "acquired_in_run": ["run_001"],
            "acquired_at": [pd.Timestamp.now(tz="UTC")],
            "total_zone_claims": [1],
            "total_zone_takeovers": [0],
        }
    )
    is_valid, missing = validate_schema(valid_df, "current_ownership")
    assert is_valid is True
    assert len(missing) == 0

    # Incomplete schema
    invalid_df = pd.DataFrame({"h3_cell": ["892664c112bffff"]})
    is_valid, missing = validate_schema(invalid_df, "current_ownership")
    assert is_valid is False
    assert "current_owner_id" in missing


# =====================================================================
# 2. KPI CALCULATIONS & PROVENANCE TESTS
# =====================================================================

def test_kpi_calculations_real_data() -> None:
    """Verify that KPI calculations reconcile exactly with Day 2 figures."""
    datasets = load_all_datasets()
    kpis = calculate_kpis(datasets)

    assert kpis["total_gps_records"] == 100000
    assert kpis["active_runners"] == 250
    assert kpis["total_h3_zones"] == 308
    assert kpis["currently_owned_zones"] == 308
    assert kpis["valid_territory_claims"] == 5075
    assert kpis["ownership_takeovers"] == 4729
    assert kpis["suspicious_runs"] == 168
    assert kpis["high_risk_runs"] == 139


def test_kpi_calculations_empty_fallback() -> None:
    """Verify that KPI calculation returns safe zeroes when datasets are empty."""
    kpis = calculate_kpis({})
    assert kpis["total_h3_zones"] == 0
    assert kpis["currently_owned_zones"] == 0
    assert kpis["valid_territory_claims"] == 0
    assert kpis["ownership_takeovers"] == 0
    assert kpis["suspicious_runs"] == 0
    assert kpis["high_risk_runs"] == 0


# =====================================================================
# 3. LEADERBOARD & CURRENT VS HISTORICAL OWNERSHIP LOGIC TESTS
# =====================================================================

def test_combined_leaderboard_sorting_and_ranks() -> None:
    """Verify that multi-dimensional rankings sort accurately and calculate dense ranks."""
    curr_df = load_current_ownership()
    hist_df = load_ownership_history()
    risk_df = load_run_anomalies()

    leaderboard = calculate_combined_leaderboard(curr_df, hist_df, risk_df)
    assert not leaderboard.empty
    assert len(leaderboard) == 250

    # Top runner should be runner_069 with 11 zones owned
    top_runner = leaderboard.iloc[0]
    assert top_runner["runner_id"] == "runner_069"
    assert top_runner["zones_owned"] == 11
    assert top_runner["rank_zones_owned"] == 1

    # Runner 201 should be #2 with 10 zones
    second_runner = leaderboard.iloc[1]
    assert second_runner["runner_id"] == "runner_201"
    assert second_runner["zones_owned"] == 10
    assert second_runner["rank_zones_owned"] == 2


def test_current_vs_historical_territory_distinction() -> None:
    """Verify that current ownership is strictly distinguished from cumulative captures."""
    curr_df = load_current_ownership()
    hist_df = load_ownership_history()
    risk_df = load_run_anomalies()

    leaderboard = calculate_combined_leaderboard(curr_df, hist_df, risk_df)

    # For runner_069: currently owned is 11, but total captures is 27!
    r69 = leaderboard[leaderboard["runner_id"] == "runner_069"].iloc[0]
    assert r69["zones_owned"] == 11
    assert r69["total_captures"] == 27
    assert r69["total_captures"] > r69["zones_owned"]

    # Sum of current zones owned across all runners must equal total unique zones (308)
    assert leaderboard["zones_owned"].sum() == 308


# =====================================================================
# 4. DETERMINISTIC RUNNER COLORS
# =====================================================================

def test_deterministic_runner_colors() -> None:
    """Verify that runner color assignment is deterministic, non-empty, and consistent."""
    c1 = get_runner_color("runner_001")
    c2 = get_runner_color("runner_001")
    assert c1 == c2, "Same runner ID must yield identical color"
    assert c1.startswith("#") and len(c1) == 7

    # Distinct runners should have different colors
    c3 = get_runner_color("runner_002")
    c4 = get_runner_color("runner_069")
    assert c1 != c3 or c1 != c4

    # Unclaimed or null runner
    assert get_runner_color(None) == "#64748B"
    assert get_runner_color("Unclaimed") == "#64748B"
    assert get_runner_color("") == "#64748B"


# =====================================================================
# 5. UBER H3 POLYGON CONVERSION (H3 4.x)
# =====================================================================

def test_h3_polygon_conversion() -> None:
    """Verify H3 4.x cell_to_boundary polygon coordinate conversion."""
    sample_cell = "892664c112bffff"
    boundary = get_h3_polygon_boundary(sample_cell)

    assert boundary is not None
    assert len(boundary) == 6, "H3 hexagon must have 6 vertices"

    for vertex in boundary:
        lat, lon = vertex
        assert -90.0 <= lat <= 90.0, f"Latitude {lat} out of bounds"
        assert -180.0 <= lon <= 180.0, f"Longitude {lon} out of bounds"

    # Invalid H3 cell should return None without throwing
    invalid_boundary = get_h3_polygon_boundary("invalid_h3_cell")
    assert invalid_boundary is None


# =====================================================================
# 6. HOTSPOT SCORE NORMALIZATION & ZERO-VARIANCE SAFETY
# =====================================================================

def test_hotspot_score_normalization_and_weights() -> None:
    """Verify min-max normalization and composite weighting for hotspot scoring."""
    dummy_stats = pd.DataFrame(
        {
            "h3_cell": ["hex_1", "hex_2", "hex_3"],
            "total_visits": [10, 50, 100],
            "unique_runners": [2, 10, 20],
        }
    )
    dummy_contested = pd.DataFrame(
        {
            "h3_cell": ["hex_1", "hex_2", "hex_3"],
            "takeover_count": [0, 25, 50],
        }
    )

    scores_df = calculate_hotspot_scores(
        dummy_stats, dummy_contested, w_takeovers=0.4, w_runners=0.35, w_visits=0.25
    )

    assert len(scores_df) == 3
    # Top zone (hex_3) has maximum across all metrics, so normalized score must be 1.0
    top_zone = scores_df.iloc[0]
    assert top_zone["h3_cell"] == "hex_3"
    assert pytest.approx(top_zone["hotspot_score"], 0.001) == 1.0

    # Bottom zone (hex_1) has min across all metrics, so normalized score must be 0.0
    bottom_zone = scores_df.iloc[-1]
    assert bottom_zone["h3_cell"] == "hex_1"
    assert pytest.approx(bottom_zone["hotspot_score"], 0.001) == 0.0


def test_min_max_normalize_zero_variance() -> None:
    """Verify that zero-variance series (all values identical) normalize to 0.0 without div-by-zero."""
    constant_series = pd.Series([5.0, 5.0, 5.0, 5.0])
    normalized = min_max_normalize(constant_series)
    assert (normalized == 0.0).all()

    empty_series = pd.Series([], dtype=float)
    assert min_max_normalize(empty_series).empty


# =====================================================================
# 7. FILTER CORRECTNESS & SCOPING
# =====================================================================

def test_runner_filter() -> None:
    """Verify runner filtering across single string, list, and 'All Runners'."""
    df = pd.DataFrame({"runner_id": ["r1", "r2", "r3", "r1"]})

    f1 = filter_by_runner(df, "r1")
    assert len(f1) == 2
    assert (f1["runner_id"] == "r1").all()

    f2 = filter_by_runner(df, ["r1", "r2"])
    assert len(f2) == 3

    f3 = filter_by_runner(df, "All Runners")
    assert len(f3) == len(df)

    f4 = filter_by_runner(df, None)
    assert len(f4) == len(df)


def test_risk_filter() -> None:
    """Verify risk classification filtering."""
    df = pd.DataFrame(
        {"run_id": [1, 2, 3], "risk_category": ["NORMAL", "SUSPICIOUS", "HIGH_RISK"]}
    )

    f_norm = filter_by_risk_category(df, "NORMAL")
    assert len(f_norm) == 1
    assert f_norm.iloc[0]["run_id"] == 1

    f_multi = filter_by_risk_category(df, ["NORMAL", "HIGH_RISK"])
    assert len(f_multi) == 2


def test_time_range_filter() -> None:
    """Verify time range filtering preserves UTC timestamps and bounds."""
    timestamps = [
        pd.Timestamp("2026-10-26 06:00:00", tz="UTC"),
        pd.Timestamp("2026-10-26 07:00:00", tz="UTC"),
        pd.Timestamp("2026-10-26 08:00:00", tz="UTC"),
    ]
    df = pd.DataFrame({"claim_timestamp": timestamps, "val": [1, 2, 3]})

    filtered = filter_by_time_range(
        df,
        start_time="2026-10-26 06:30:00+00:00",
        end_time="2026-10-26 07:30:00+00:00",
    )
    assert len(filtered) == 1
    assert filtered.iloc[0]["val"] == 2


# =====================================================================
# 8. CSV EXPORT SERIALIZATION
# =====================================================================

def test_csv_export_serialization() -> None:
    """Verify DataFrame export to UTF-8 CSV bytes with timestamp formatting."""
    df = pd.DataFrame(
        {
            "runner_id": ["runner_001", "runner_002"],
            "zones_owned": [5, 3],
            "last_active": [
                pd.Timestamp("2026-10-26 08:00:00", tz="UTC"),
                pd.Timestamp("2026-10-26 09:00:00", tz="UTC"),
            ],
            "sensitive_internal_key": ["secret1", "secret2"],
        }
    )

    csv_bytes = convert_df_to_csv(df, exclude_cols=["sensitive_internal_key"])
    assert isinstance(csv_bytes, bytes)
    assert len(csv_bytes) > 0

    decoded = csv_bytes.decode("utf-8")
    assert "runner_001" in decoded
    assert "sensitive_internal_key" not in decoded
    assert "2026-10-26 08:00:00 UTC" in decoded


# =====================================================================
# 9. COMPONENT RESILIENCE ON EMPTY DATA
# =====================================================================

def test_charts_empty_dataframe_resilience() -> None:
    """Verify that Plotly chart generators do not raise exceptions when passed empty DataFrames."""
    empty_df = pd.DataFrame()

    fig1 = render_activity_over_time_chart(empty_df)
    assert fig1 is not None

    fig2 = render_top_owners_chart(empty_df)
    assert fig2 is not None

    fig3 = render_contested_zones_chart(empty_df)
    assert fig3 is not None

    fig4 = render_risk_category_donut(empty_df)
    assert fig4 is not None
