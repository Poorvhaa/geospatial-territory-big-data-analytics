"""Unit tests for Replay State and Data Models (Day 4)."""

from __future__ import annotations

import pytest

from src.realtime.replay_state import (
    ClaimRecord,
    HotspotRecord,
    ReplayCheckpoint,
    ReplayMetrics,
    ReplayState,
    ReplayStatus,
    ZoneOwnershipRecord,
)


def test_claim_record_serialization() -> None:
    claim = ClaimRecord(
        claim_id="run_1_v1_cell123456789",
        h3_cell="cell123456789",
        runner_id="runner_alpha",
        run_id="run_1",
        claim_timestamp="2026-10-26T08:00:05Z",
        claim_timestamp_epoch=1005.0,
        points_in_visit=2,
        event_type="INITIAL_CAPTURE",
        is_takeover=False,
    )
    d = claim.to_dict()
    assert d["claim_id"] == "run_1_v1_cell123456789"
    assert d["event_type"] == "INITIAL_CAPTURE"
    assert d["is_takeover"] is False
    assert d["points_in_visit"] == 2


def test_zone_ownership_record_and_hotspot_record() -> None:
    zone = ZoneOwnershipRecord(
        h3_cell="cell_hex_001",
        current_owner_id="runner_A",
        previous_owner_id="runner_B",
        acquired_in_run="run_10",
        acquired_at="2026-10-26T08:01:00Z",
        acquired_epoch=1060.0,
        latest_claim_id="run_10_v2_cell_hex_001",
        total_zone_claims=4,
        total_zone_takeovers=2,
        total_zone_revisits=1,
        unique_zone_runners=3,
        updated_at="2026-10-26T08:01:00Z",
    )
    zd = zone.to_dict()
    assert zd["total_zone_claims"] == 4
    assert zd["unique_zone_runners"] == 3

    hotspot = HotspotRecord(
        h3_cell="cell_hex_001",
        total_visits=4,
        unique_runners=3,
        takeovers=2,
        hotspot_score=0.85,
        hotspot_rank=1,
    )
    hd = hotspot.to_dict()
    assert hd["hotspot_score"] == 0.85


def test_replay_metrics_and_status() -> None:
    metrics = ReplayMetrics(
        events_processed=500,
        total_events=1000,
        remaining_events=500,
        progress_pct=50.0,
        batches_processed=25,
        claims_processed=42,
        total_zones_owned=15,
        status=ReplayStatus.RUNNING,
    )
    md = metrics.to_dict()
    assert md["progress_pct"] == 50.0
    assert md["status"] == "RUNNING"
    assert md["remaining_events"] == 500


def test_replay_state_snapshot() -> None:
    state = ReplayState(session_id="test_sess", status=ReplayStatus.PAUSED)
    state.newly_captured_cells.append("cell_A")
    state.takeover_cells.append("cell_B")
    snap = state.to_dict()
    assert snap["session_id"] == "test_sess"
    assert snap["status"] == "PAUSED"
    assert "cell_A" in snap["newly_captured_cells"]
    assert "cell_B" in snap["takeover_cells"]
