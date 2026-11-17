"""End-to-end integration tests for Replay Simulator & Batch vs Replay validation (Day 4)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.realtime.batch_processor import BatchProcessor
from src.realtime.incremental_ownership import IncrementalOwnershipEngine
from src.realtime.replay_engine import ReplayEngine
from src.utils import get_project_root


def test_batch_vs_replay_full_equivalence() -> None:
    """Critical academic validation: verify that replaying all eligible events

    yields the EXACT same current ownership and transition counts as Day 2 batch pipeline.
    """
    root = get_project_root()
    eligible_parquet = root / "data" / "parquet" / "eligible_points"
    current_parquet = root / "data" / "parquet" / "current_ownership"
    history_parquet = root / "data" / "parquet" / "ownership_history"

    if not eligible_parquet.exists() or not current_parquet.exists():
        pytest.skip("Eligible points or Day 2 Parquet datasets not present; skipping equivalence test.")

    df_eligible = pd.read_parquet(eligible_parquet)
    df_curr_batch = pd.read_parquet(current_parquet)
    df_hist_batch = pd.read_parquet(history_parquet)

    # Run replay simulation using BatchProcessor and IncrementalOwnershipEngine
    bp = BatchProcessor(batch_interval_s=5.0)
    engine = IncrementalOwnershipEngine()

    replayed_claims = []
    for batch in bp.partition_records_into_batches(df_eligible):
        proc_claims, _, _ = engine.process_claims_batch(batch.claims, batch_id=batch.batch_id)
        replayed_claims.extend(proc_claims)

    # 1. Total claims count must match
    assert len(replayed_claims) == len(df_hist_batch), (
        f"Replay claims {len(replayed_claims)} != Batch claims {len(df_hist_batch)}"
    )

    # 2. Total owned zones count must match
    assert engine.total_owned_zones == len(df_curr_batch), (
        f"Replay owned zones {engine.total_owned_zones} != Batch zones {len(df_curr_batch)}"
    )

    # 3. Transition event counts must match
    df_replayed = pd.DataFrame([c.to_dict() for c in replayed_claims])
    replay_event_counts = df_replayed["event_type"].value_counts().to_dict()
    batch_event_counts = df_hist_batch["event_type"].value_counts().to_dict()

    for event_type in ["INITIAL_CAPTURE", "TAKEOVER", "SAME_OWNER_REVISIT"]:
        assert replay_event_counts.get(event_type, 0) == batch_event_counts.get(event_type, 0), (
            f"Mismatch for {event_type}: Replay={replay_event_counts.get(event_type, 0)} "
            f"vs Batch={batch_event_counts.get(event_type, 0)}"
        )

    # 4. Final owners of EVERY zone must be 100% identical
    batch_owners = dict(zip(df_curr_batch["h3_cell"], df_curr_batch["current_owner_id"]))
    mismatches = []
    for cell, rec in engine.current_ownership.items():
        if batch_owners.get(cell) != rec.current_owner_id:
            mismatches.append((cell, rec.current_owner_id, batch_owners.get(cell)))

    assert len(mismatches) == 0, f"Found {len(mismatches)} owner mismatches: {mismatches[:5]}"


def test_replay_state_recovery_across_instances(tmp_path: Path) -> None:
    db_file = tmp_path / "recovery_test.db"

    # 4-point test dataset
    rows = [
        {"run_id": "r1", "runner_id": "u1", "timestamp": "2026-10-26T08:00:00Z", "timestamp_epoch": 1000.0, "latitude": 41.8781, "longitude": -87.6298, "h3_cell": "892664c1bc3ffff"},
        {"run_id": "r1", "runner_id": "u1", "timestamp": "2026-10-26T08:00:05Z", "timestamp_epoch": 1005.0, "latitude": 41.8781, "longitude": -87.6298, "h3_cell": "892664c1bc3ffff"},
    ]
    df = pd.DataFrame(rows)

    # Instance 1 processes a batch
    eng1 = ReplayEngine(
        session_id="recovery_sess",
        db_path=db_file,
        data_source=df,
        batch_interval_s=10.0,
    )
    batches = list(eng1.batch_processor.partition_records_into_batches(df))
    assert len(batches) == 1
    eng1.step_batch(batches[0])

    assert eng1.ownership_engine.total_owned_zones == 1

    # Instance 2 boots up pointing to same DB -> must recover state!
    eng2 = ReplayEngine(
        session_id="recovery_sess",
        db_path=db_file,
        data_source=df,
    )
    assert eng2.ownership_engine.total_owned_zones == 1
    assert "892664c1bc3ffff" in eng2.ownership_engine.current_ownership
    assert eng2.ownership_engine.current_ownership["892664c1bc3ffff"].current_owner_id == "u1"
