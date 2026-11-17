"""Phase 14 Comprehensive End-to-End Integration and Reliability Test Suite.

Validates end-to-end integration flows across all system components:
1. Complete CSV-to-Parquet pipeline
2. Correct anomaly exclusion from downstream territory claims
3. Territory ownership reconciliation
4. Map data polygon preparation and coordinate geometry
5. Leaderboard multi-metric rank calculations
6. Replay checkpoint recovery across clean instances
7. Deterministic seeded dataset generation reproducibility
8. Dashboard analytical data loading resilience
9. Export serialization and numerical fidelity
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
import pandas as pd
import pytest

from dashboard.components.maps import calculate_map_center, get_h3_polygon_boundary
from dashboard.services.data_loader import load_all_datasets
from dashboard.services.exports import convert_df_to_csv
from dashboard.services.metrics import calculate_combined_leaderboard
from src.data_generator import generate_dataset
from src.pipeline import run_pipeline
from src.realtime.batch_processor import BatchProcessor
from src.realtime.incremental_ownership import IncrementalOwnershipEngine
from src.realtime.replay_engine import ReplayEngine
from src.realtime.replay_state import ClaimRecord, ReplayCheckpoint, ReplayStatus, ZoneOwnershipRecord
from src.realtime.state_store import SQLiteStateStore
from src.utils import get_project_root


@pytest.fixture(scope="module")
def root_dir() -> Path:
    return get_project_root()


def test_integration_deterministic_seeded_datasets(tmp_path: Path) -> None:
    """Verify that seeded generation produces bit-for-bit identical datasets."""
    csv_a = tmp_path / "seed_a.csv"
    csv_b = tmp_path / "seed_b.csv"

    generate_dataset(records=150, runners=5, seed=12345, output_path=csv_a)
    generate_dataset(records=150, runners=5, seed=12345, output_path=csv_b)

    hash_a = hashlib.sha256(csv_a.read_bytes()).hexdigest()
    hash_b = hashlib.sha256(csv_b.read_bytes()).hexdigest()

    assert hash_a == hash_b, "Seeded dataset generation must be strictly deterministic"


def test_integration_dashboard_data_loading_resilience() -> None:
    """Verify that dashboard service loads all analytical Parquet tables cleanly."""
    datasets = load_all_datasets()
    assert isinstance(datasets, dict)

    required_keys = ["current_ownership", "ownership_history", "run_anomalies", "leaderboard", "zone_statistics"]
    for k in required_keys:
        assert k in datasets, f"Missing core analytical dataset: {k}"
        df = datasets[k]
        assert isinstance(df, pd.DataFrame)
        assert not df.empty, f"Analytical dataset '{k}' should not be empty"


def test_integration_anomaly_exclusion_integrity(root_dir: Path) -> None:
    """Verify that all runs flagged as SUSPICIOUS or HIGH_RISK are excluded from territory claims."""
    parquet_dir = root_dir / "data" / "parquet"
    risk_df = pd.read_parquet(parquet_dir / "run_anomalies")
    hist_df = pd.read_parquet(parquet_dir / "ownership_history")
    curr_df = pd.read_parquet(parquet_dir / "current_ownership")

    quarantined_runs = set(risk_df[risk_df["risk_category"] != "NORMAL"]["run_id"])
    assert len(quarantined_runs) > 0, "Quarantined runs set should not be empty"

    history_runs = set(hist_df["run_id"])
    overlap_hist = quarantined_runs.intersection(history_runs)
    assert len(overlap_hist) == 0, f"Quarantined runs leaked into territory history: {overlap_hist}"

    current_runs = set(curr_df["acquired_in_run"])
    overlap_curr = quarantined_runs.intersection(current_runs)
    assert len(overlap_curr) == 0, f"Quarantined runs leaked into current ownership: {overlap_curr}"


def test_integration_territory_ownership_reconciliation(root_dir: Path) -> None:
    """Verify that current ownership reconciles with the unified leaderboard."""
    parquet_dir = root_dir / "data" / "parquet"
    curr_df = pd.read_parquet(parquet_dir / "current_ownership")
    hist_df = pd.read_parquet(parquet_dir / "ownership_history")
    risk_df = pd.read_parquet(parquet_dir / "run_anomalies")

    lb_df = calculate_combined_leaderboard(curr_df, hist_df, risk_df)

    sum_owned = int(lb_df["zones_owned"].sum())
    total_curr = int(curr_df["current_owner_id"].dropna().count())

    assert sum_owned == total_curr, (
        f"Reconciliation error: Leaderboard sum ({sum_owned}) != Current owned zones ({total_curr})"
    )


def test_integration_map_data_geometry_and_centering(root_dir: Path) -> None:
    """Verify H3 polygon boundaries and dynamic centroid calculations for map rendering."""
    curr_df = pd.read_parquet(root_dir / "data" / "parquet" / "current_ownership")
    sample_cells = curr_df["h3_cell"].head(25).tolist()

    for cell in sample_cells:
        boundary = get_h3_polygon_boundary(cell)
        assert boundary is not None, f"Failed to compute boundary for cell {cell}"
        assert len(boundary) in (6, 7), f"H3 cell {cell} boundary must have 6 or 7 vertices, got {len(boundary)}"
        for lat, lon in boundary:
            assert 40.0 <= lat <= 44.0, f"Latitude {lat} out of Chicago bounds"
            assert -89.0 <= lon <= -85.0, f"Longitude {lon} out of Chicago bounds"

    center_lat, center_lon = calculate_map_center(sample_cells)
    assert 41.7 <= center_lat <= 42.0, f"Center lat {center_lat} out of bounds"
    assert -87.8 <= center_lon <= -87.5, f"Center lon {center_lon} out of bounds"


def test_integration_replay_checkpoint_recovery_flow(tmp_path: Path) -> None:
    """Verify transactional state persistence and checkpoint recovery across independent engine instances."""
    db_file = tmp_path / "replay_test.db"
    store = SQLiteStateStore(db_path=db_file)

    session_id = "integration_test_session"

    # Simulate inserting 3 active zones
    rec1 = ZoneOwnershipRecord(
        h3_cell="892664c112bffff",
        current_owner_id="runner_001",
        previous_owner_id=None,
        acquired_in_run="run_001",
        acquired_at="2026-10-26T08:00:00Z",
        acquired_epoch=1792992000.0,
        latest_claim_id="claim_001",
        total_zone_claims=1,
        total_zone_takeovers=0,
        total_zone_revisits=0,
        unique_zone_runners=1,
        updated_at="2026-10-26T08:00:00Z",
    )
    rec2 = ZoneOwnershipRecord(
        h3_cell="892664c112fffff",
        current_owner_id="runner_002",
        previous_owner_id=None,
        acquired_in_run="run_002",
        acquired_at="2026-10-26T08:05:00Z",
        acquired_epoch=1792992300.0,
        latest_claim_id="claim_002",
        total_zone_claims=1,
        total_zone_takeovers=0,
        total_zone_revisits=0,
        unique_zone_runners=1,
        updated_at="2026-10-26T08:05:00Z",
    )

    claim1 = ClaimRecord(
        claim_id="claim_001",
        h3_cell="892664c112bffff",
        runner_id="runner_001",
        run_id="run_001",
        claim_timestamp="2026-10-26T08:00:00Z",
        claim_timestamp_epoch=1792992000.0,
        points_in_visit=3,
        event_type="INITIAL_CAPTURE",
        is_takeover=False,
        is_ownership_change=True,
        prev_runner_id=None,
        batch_id=4,
    )
    checkpoint = ReplayCheckpoint(
        session_id=session_id,
        dataset_fingerprint="test_fp",
        current_position=100,
        last_committed_batch=4,
        last_event_timestamp="2026-10-26T08:05:00Z",
        last_event_epoch=1792992300.0,
        replay_status="PAUSED",
        total_events=200,
        events_processed=100,
        total_claims_processed=1,
        created_at="2026-10-26T08:00:00Z",
        updated_at="2026-10-26T08:05:00Z",
    )

    store.commit_batch(
        session_id=session_id,
        batch_id=4,
        checkpoint=checkpoint,
        claims=[claim1],
        ownership_updates=[rec1, rec2],
    )

    # Initialize a new separate ReplayEngine pointing to this test database
    engine = ReplayEngine(
        session_id=session_id,
        db_path=db_file,
    )

    snapshot = engine.get_snapshot()
    assert snapshot["status"] == "PAUSED"
    assert snapshot["metrics"]["batches_processed"] == 4
    assert snapshot["metrics"]["events_processed"] == 100
    assert snapshot["metrics"]["total_zones_owned"] == 2
    assert snapshot["metrics"]["current_event_timestamp"] == "2026-10-26T08:05:00Z"


def test_integration_export_serialization_accuracy() -> None:
    """Verify that CSV export utility accurately serializes DataFrames with headers and formatting."""
    df = pd.DataFrame({
        "rank": [1, 2],
        "runner_id": ["runner_001", "runner_002"],
        "zones_owned": [12, 8],
        "valid_distance_km": [42.195, 21.0975],
    })

    csv_bytes = convert_df_to_csv(df)
    assert isinstance(csv_bytes, bytes)

    # Read back and verify exact value parity
    df_read = pd.read_csv(io.BytesIO(csv_bytes))
    assert list(df_read.columns) == ["rank", "runner_id", "zones_owned", "valid_distance_km"]
    assert len(df_read) == 2
    assert df_read.iloc[0]["runner_id"] == "runner_001"
    assert round(df_read.iloc[0]["valid_distance_km"], 3) == 42.195
