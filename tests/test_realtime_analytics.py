"""Unit tests for Real-Time Analytics and Live Leaderboard (Day 4)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.realtime.realtime_analytics import RealtimeAnalyticsEngine
from src.realtime.replay_state import ClaimRecord, ZoneOwnershipRecord


def test_empty_analytics_and_hotspots() -> None:
    analytics = RealtimeAnalyticsEngine()
    hotspots = analytics.compute_hotspot_scores()
    assert len(hotspots) == 0

    lb = analytics.compute_leaderboard_from_ownership({})
    assert lb.empty


def test_hotspot_scoring_and_weights() -> None:
    analytics = RealtimeAnalyticsEngine(w_takeovers=0.40, w_unique_runners=0.35, w_visits=0.25)

    claims = [
        # Cell A: 3 visits, 2 runners, 1 takeover
        ClaimRecord("c1", "cell_A", "u1", "r1", "2026-10-26T08:00:00Z", 1000.0, 2, "INITIAL_CAPTURE", False),
        ClaimRecord("c2", "cell_A", "u2", "r2", "2026-10-26T08:05:00Z", 1005.0, 2, "TAKEOVER", True),
        ClaimRecord("c3", "cell_A", "u2", "r3", "2026-10-26T08:10:00Z", 1010.0, 2, "SAME_OWNER_REVISIT", False),
        # Cell B: 1 visit, 1 runner, 0 takeovers
        ClaimRecord("c4", "cell_B", "u1", "r4", "2026-10-26T08:00:00Z", 1000.0, 2, "INITIAL_CAPTURE", False),
    ]

    hotspots = analytics.update_from_claims(claims)
    assert len(hotspots) == 2

    # cell_A has highest takeovers, runners, and visits -> score must be 1.0 (rank 1)
    # cell_B has min takeovers, runners, and visits -> normalized are 0.0 -> score 0.0 (rank 2)
    h_dict = {h.h3_cell: h for h in hotspots}
    assert h_dict["cell_A"].hotspot_score == 1.0
    assert h_dict["cell_A"].hotspot_rank == 1
    assert h_dict["cell_B"].hotspot_score == 0.0
    assert h_dict["cell_B"].hotspot_rank == 2


def test_leaderboard_conservation_of_owned_zones() -> None:
    analytics = RealtimeAnalyticsEngine()

    current_ownership = {
        "cell_1": ZoneOwnershipRecord("cell_1", "runner_A"),
        "cell_2": ZoneOwnershipRecord("cell_2", "runner_A"),
        "cell_3": ZoneOwnershipRecord("cell_3", "runner_B"),
        "cell_4": ZoneOwnershipRecord("cell_4", "runner_C"),
    }

    lb = analytics.compute_leaderboard_from_ownership(current_ownership)

    # 3 runners: runner_A (2), runner_B (1), runner_C (1)
    assert len(lb) == 3
    assert lb[lb["runner_id"] == "runner_A"]["zones_owned"].iloc[0] == 2
    assert lb[lb["runner_id"] == "runner_B"]["zones_owned"].iloc[0] == 1
    assert lb[lb["runner_id"] == "runner_C"]["zones_owned"].iloc[0] == 1

    # CRITICAL: Sum of owned zones across all runners must equal total owned zones
    assert lb["zones_owned"].sum() == len(current_ownership)
