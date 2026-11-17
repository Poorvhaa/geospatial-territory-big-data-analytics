"""Unit tests for Incremental Territory Ownership Engine (Day 4)."""

from __future__ import annotations

import pytest

from src.realtime.incremental_ownership import IncrementalOwnershipEngine
from src.realtime.replay_state import ClaimRecord


def test_initial_capture_and_takeover_logic() -> None:
    engine = IncrementalOwnershipEngine()
    cell = "892664c1bc3ffff"

    # Claim 1 by runner_A -> INITIAL_CAPTURE
    claim1 = ClaimRecord(
        claim_id="r1_v1_cellA",
        h3_cell=cell,
        runner_id="runner_A",
        run_id="run_1",
        claim_timestamp="2026-10-26T08:00:00Z",
        claim_timestamp_epoch=1000.0,
        points_in_visit=2,
    )
    p_claims, updated, feed = engine.process_claims_batch([claim1], batch_id=1)

    assert len(p_claims) == 1
    assert p_claims[0].event_type == "INITIAL_CAPTURE"
    assert p_claims[0].is_takeover is False
    assert engine.current_ownership[cell].current_owner_id == "runner_A"
    assert engine.current_ownership[cell].total_zone_takeovers == 0
    assert engine.current_ownership[cell].unique_zone_runners == 1

    # Claim 2 by runner_B -> TAKEOVER
    claim2 = ClaimRecord(
        claim_id="r2_v1_cellA",
        h3_cell=cell,
        runner_id="runner_B",
        run_id="run_2",
        claim_timestamp="2026-10-26T08:05:00Z",
        claim_timestamp_epoch=1300.0,
        points_in_visit=2,
    )
    p_claims2, updated2, feed2 = engine.process_claims_batch([claim2], batch_id=2)

    assert len(p_claims2) == 1
    assert p_claims2[0].event_type == "TAKEOVER"
    assert p_claims2[0].is_takeover is True
    assert p_claims2[0].prev_runner_id == "runner_A"
    assert engine.current_ownership[cell].current_owner_id == "runner_B"
    assert engine.current_ownership[cell].previous_owner_id == "runner_A"
    assert engine.current_ownership[cell].total_zone_takeovers == 1
    assert engine.current_ownership[cell].unique_zone_runners == 2


def test_same_owner_revisit_does_not_count_as_takeover() -> None:
    engine = IncrementalOwnershipEngine()
    cell = "892664c1bc3ffff"

    # Initial capture by runner_A
    claim1 = ClaimRecord(
        claim_id="r1_v1_cellA",
        h3_cell=cell,
        runner_id="runner_A",
        run_id="run_1",
        claim_timestamp="2026-10-26T08:00:00Z",
        claim_timestamp_epoch=1000.0,
        points_in_visit=2,
    )
    engine.process_claims_batch([claim1], batch_id=1)

    # Revisit by runner_A in a later run
    claim2 = ClaimRecord(
        claim_id="r3_v1_cellA",
        h3_cell=cell,
        runner_id="runner_A",
        run_id="run_3",
        claim_timestamp="2026-10-26T08:10:00Z",
        claim_timestamp_epoch=1600.0,
        points_in_visit=2,
    )
    p_claims, updated, feed = engine.process_claims_batch([claim2], batch_id=2)

    assert len(p_claims) == 1
    assert p_claims[0].event_type == "SAME_OWNER_REVISIT"
    assert p_claims[0].is_takeover is False
    assert engine.current_ownership[cell].current_owner_id == "runner_A"
    assert engine.current_ownership[cell].total_zone_takeovers == 0
    assert engine.current_ownership[cell].total_zone_revisits == 1
    assert engine.current_ownership[cell].total_zone_claims == 2


def test_claim_idempotency_and_duplicate_protection() -> None:
    engine = IncrementalOwnershipEngine()
    cell = "892664c1bc3ffff"

    claim1 = ClaimRecord(
        claim_id="dup_claim_001",
        h3_cell=cell,
        runner_id="runner_A",
        run_id="run_1",
        claim_timestamp="2026-10-26T08:00:00Z",
        claim_timestamp_epoch=1000.0,
        points_in_visit=2,
    )
    p1, _, _ = engine.process_claims_batch([claim1], batch_id=1)
    assert len(p1) == 1

    # Resubmitting identical claim_id must be ignored
    p2, _, _ = engine.process_claims_batch([claim1], batch_id=2)
    assert len(p2) == 0
    assert engine.current_ownership[cell].total_zone_claims == 1
