"""Unit tests for Chronological Batch Processor and Cross-Batch State (Day 4)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.realtime.batch_processor import BatchProcessor


def test_empty_dataframe_partitioning() -> None:
    bp = BatchProcessor(batch_interval_s=5.0)
    batches = list(bp.partition_records_into_batches(pd.DataFrame()))
    assert len(batches) == 0


def test_chronological_batch_partitioning() -> None:
    # 6 points spaced over 15 seconds: points at 1000, 1002, 1005, 1008, 1010, 1012
    records = [
        {"run_id": "r1", "runner_id": "u1", "timestamp": "2026-10-26T08:00:00Z", "timestamp_epoch": 1000.0, "latitude": 41.8781, "longitude": -87.6298, "h3_cell": "892664c1bc3ffff"},
        {"run_id": "r1", "runner_id": "u1", "timestamp": "2026-10-26T08:00:02Z", "timestamp_epoch": 1002.0, "latitude": 41.8781, "longitude": -87.6298, "h3_cell": "892664c1bc3ffff"},
        {"run_id": "r1", "runner_id": "u1", "timestamp": "2026-10-26T08:00:05Z", "timestamp_epoch": 1005.0, "latitude": 41.8781, "longitude": -87.6298, "h3_cell": "892664c1bc3ffff"},
        {"run_id": "r1", "runner_id": "u1", "timestamp": "2026-10-26T08:00:08Z", "timestamp_epoch": 1008.0, "latitude": 41.8781, "longitude": -87.6298, "h3_cell": "892664c1bc3ffff"},
        {"run_id": "r1", "runner_id": "u1", "timestamp": "2026-10-26T08:00:10Z", "timestamp_epoch": 1010.0, "latitude": 41.8826, "longitude": -87.6226, "h3_cell": "892664c1bd3ffff"},
        {"run_id": "r1", "runner_id": "u1", "timestamp": "2026-10-26T08:00:12Z", "timestamp_epoch": 1012.0, "latitude": 41.8826, "longitude": -87.6226, "h3_cell": "892664c1bd3ffff"},
    ]
    df = pd.DataFrame(records)

    bp = BatchProcessor(batch_interval_s=5.0)
    batches = list(bp.partition_records_into_batches(df))

    # Batches: [1000, 1005), [1005, 1010), [1010, 1015) -> 3 batches
    assert len(batches) == 3
    assert batches[0].events_count == 2
    assert batches[1].events_count == 2
    assert batches[2].events_count == 2


def test_cross_batch_boundary_run_state() -> None:
    # Run r1 point 1 is at 1000.0 (Batch 1), point 2 is at 1006.0 (Batch 2)
    # The claim must be emitted in Batch 2 upon confirming 2 consecutive points!
    records = [
        {"run_id": "r1", "runner_id": "u1", "timestamp": "2026-10-26T08:00:00Z", "timestamp_epoch": 1000.0, "latitude": 41.8781, "longitude": -87.6298, "h3_cell": "892664c1bc3ffff"},
        {"run_id": "r1", "runner_id": "u1", "timestamp": "2026-10-26T08:00:06Z", "timestamp_epoch": 1006.0, "latitude": 41.8781, "longitude": -87.6298, "h3_cell": "892664c1bc3ffff"},
    ]
    df = pd.DataFrame(records)

    bp = BatchProcessor(batch_interval_s=5.0)
    batches = list(bp.partition_records_into_batches(df))

    assert len(batches) == 2
    # Batch 1 has only 1 point, no claim yet
    assert len(batches[0].claims) == 0

    # Batch 2 has second point -> confirms visit and emits claim!
    assert len(batches[1].claims) == 1
    claim = batches[1].claims[0]
    assert claim.claim_id == "r1_v1_892664c1bc3ffff"
    assert claim.runner_id == "u1"
    assert claim.points_in_visit == 2


def test_equal_timestamp_deterministic_ordering() -> None:
    # Two different runners with the exact same timestamp
    records = [
        {"run_id": "run_B", "runner_id": "user_2", "timestamp": "2026-10-26T08:00:00Z", "timestamp_epoch": 1000.0, "latitude": 41.8781, "longitude": -87.6298, "h3_cell": "892664c1bc3ffff"},
        {"run_id": "run_A", "runner_id": "user_1", "timestamp": "2026-10-26T08:00:00Z", "timestamp_epoch": 1000.0, "latitude": 41.8781, "longitude": -87.6298, "h3_cell": "892664c1bc3ffff"},
        {"run_id": "run_B", "runner_id": "user_2", "timestamp": "2026-10-26T08:00:05Z", "timestamp_epoch": 1005.0, "latitude": 41.8781, "longitude": -87.6298, "h3_cell": "892664c1bc3ffff"},
        {"run_id": "run_A", "runner_id": "user_1", "timestamp": "2026-10-26T08:00:05Z", "timestamp_epoch": 1005.0, "latitude": 41.8781, "longitude": -87.6298, "h3_cell": "892664c1bc3ffff"},
    ]
    df = pd.DataFrame(records)

    bp = BatchProcessor(batch_interval_s=10.0)
    batches = list(bp.partition_records_into_batches(df))

    # All in batch 1, claims emitted deterministically sorted
    claims = batches[0].claims
    assert len(claims) == 2
    assert claims[0].run_id == "run_A"
    assert claims[1].run_id == "run_B"


def test_suspicious_run_exclusion() -> None:
    # Points with risk_category = HIGH_RISK must be excluded from claiming
    records = [
        {"run_id": "r_clean", "runner_id": "u1", "timestamp": "2026-10-26T08:00:00Z", "timestamp_epoch": 1000.0, "latitude": 41.8781, "longitude": -87.6298, "h3_cell": "892664c1bc3ffff", "risk_category": "NORMAL"},
        {"run_id": "r_clean", "runner_id": "u1", "timestamp": "2026-10-26T08:00:05Z", "timestamp_epoch": 1005.0, "latitude": 41.8781, "longitude": -87.6298, "h3_cell": "892664c1bc3ffff", "risk_category": "NORMAL"},
        {"run_id": "r_fraud", "runner_id": "u2", "timestamp": "2026-10-26T08:00:00Z", "timestamp_epoch": 1000.0, "latitude": 41.8826, "longitude": -87.6226, "h3_cell": "892664c1bd3ffff", "risk_category": "HIGH_RISK"},
        {"run_id": "r_fraud", "runner_id": "u2", "timestamp": "2026-10-26T08:00:05Z", "timestamp_epoch": 1005.0, "latitude": 41.8826, "longitude": -87.6226, "h3_cell": "892664c1bd3ffff", "risk_category": "HIGH_RISK"},
    ]
    df = pd.DataFrame(records)

    bp = BatchProcessor(batch_interval_s=10.0)
    batches = list(bp.partition_records_into_batches(df))

    assert len(batches) == 1
    assert batches[0].suspicious_events_count == 2
    # Only clean run can claim territory
    assert len(batches[0].claims) == 1
    assert batches[0].claims[0].run_id == "r_clean"
