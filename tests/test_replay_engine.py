"""Unit tests for Replay Engine controls, persistence, and state transitions (Day 4)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.realtime.batch_processor import GPSMicroBatch
from src.realtime.replay_engine import ReplayEngine
from src.realtime.replay_state import ClaimRecord, ReplayStatus
from src.realtime.state_store import SQLiteStateStore


def test_sqlite_state_store_transactions_and_duplicate_batch(tmp_path: Path) -> None:
    db_file = tmp_path / "test_replay.db"
    store = SQLiteStateStore(db_path=db_file)

    session_id = "test_session_1"
    assert not store.is_batch_committed(session_id, 1)

    # Create dummy claims and checkpoint
    claim1 = ClaimRecord("c1", "cell1", "u1", "r1", "2026-10-26T08:00:00Z", 1000.0, 2)
    from src.realtime.replay_state import ReplayCheckpoint, ZoneOwnershipRecord

    cp = ReplayCheckpoint(session_id, "fp", 10, 1, "2026-10-26T08:00:00Z", 1000.0, "RUNNING", 100, 10, 1, "", "")
    z1 = ZoneOwnershipRecord("cell1", "u1", acquired_at="2026-10-26T08:00:00Z", acquired_epoch=1000.0)

    # First commit -> True
    committed = store.commit_batch(session_id, 1, cp, [claim1], [z1])
    assert committed is True
    assert store.is_batch_committed(session_id, 1)
    assert store.has_claim("c1")

    # Duplicate batch submission -> False
    committed_dup = store.commit_batch(session_id, 1, cp, [claim1], [z1])
    assert committed_dup is False


def test_replay_engine_start_pause_resume_stop(tmp_path: Path) -> None:
    db_file = tmp_path / "engine_test.db"

    # Small 10-point test dataset
    rows = []
    for i in range(10):
        rows.append({
            "run_id": "r1",
            "runner_id": "u1",
            "timestamp": f"2026-10-26T08:00:{i:02d}Z",
            "timestamp_epoch": 1000.0 + i,
            "latitude": 41.8781,
            "longitude": -87.6298,
            "h3_cell": "892664c1bc3ffff",
        })
    test_df = pd.DataFrame(rows)

    engine = ReplayEngine(
        session_id="engine_test_sess",
        db_path=db_file,
        data_source=test_df,
        batch_interval_s=2.0,
        playback_speed=10.0,
    )

    # 1. Start
    started = engine.start()
    assert started is True
    assert engine.get_snapshot()["status"] in ["RUNNING", "COMPLETED"]

    # 2. Pause
    engine.pause()
    assert engine.get_snapshot()["status"] in ["PAUSED", "COMPLETED"]

    # 3. Resume
    engine.resume()
    assert engine.get_snapshot()["status"] in ["RUNNING", "COMPLETED"]

    # 4. Stop
    engine.stop()
    assert engine.get_snapshot()["status"] in ["STOPPED", "COMPLETED"]


def test_playback_speed_adjustment(tmp_path: Path) -> None:
    engine = ReplayEngine(
        session_id="speed_test",
        db_path=tmp_path / "speed.db",
        playback_speed=1.0,
    )
    assert engine.playback_speed == 1.0

    for speed in [2.0, 5.0, 10.0]:
        engine.set_playback_speed(speed)
        assert engine.playback_speed == speed
        assert engine.get_snapshot()["metrics"]["playback_speed"] == speed
