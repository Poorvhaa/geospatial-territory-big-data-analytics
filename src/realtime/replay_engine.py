"""Real-Time GPS Replay Simulation Engine (Day 4).

Coordinates time-ordered batch processing, incremental territory conquest,
state persistence, and playback controls (START, PAUSE, RESUME, STOP, RESTART).
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from src.realtime.batch_processor import BatchProcessor, GPSMicroBatch
from src.realtime.incremental_ownership import IncrementalOwnershipEngine
from src.realtime.realtime_analytics import RealtimeAnalyticsEngine
from src.realtime.replay_state import (
    ClaimRecord,
    HotspotRecord,
    ReplayCheckpoint,
    ReplayMetrics,
    ReplayState,
    ReplayStatus,
    ZoneOwnershipRecord,
)
from src.realtime.state_store import SQLiteStateStore
from src.utils import get_project_root

logger = logging.getLogger(__name__)

DEFAULT_SESSION_ID = "academic_demo_replay"


class ReplayEngine:
    """Thread-safe controller for real-time GPS stream simulation and state commit."""

    _instance: Optional[ReplayEngine] = None
    _singleton_lock = threading.Lock()

    @classmethod
    def get_instance(
        cls,
        session_id: str = DEFAULT_SESSION_ID,
        db_path: Optional[Path | str] = None,
        data_source: Optional[Union[str, Path, pd.DataFrame]] = None,
        batch_interval_s: float = 5.0,
        playback_speed: float = 1.0,
    ) -> ReplayEngine:
        """Acquire process-level singleton instance of the replay engine."""
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = cls(
                    session_id=session_id,
                    db_path=db_path,
                    data_source=data_source,
                    batch_interval_s=batch_interval_s,
                    playback_speed=playback_speed,
                )
            return cls._instance

    def __init__(
        self,
        session_id: str = DEFAULT_SESSION_ID,
        db_path: Optional[Path | str] = None,
        data_source: Optional[Union[str, Path, pd.DataFrame]] = None,
        batch_interval_s: float = 5.0,
        playback_speed: float = 1.0,
    ) -> None:
        self.session_id = session_id
        self.batch_interval_s = float(batch_interval_s)
        self.playback_speed = float(playback_speed)

        self.state_store = SQLiteStateStore(db_path=db_path)
        self.ownership_engine = IncrementalOwnershipEngine()
        self.batch_processor = BatchProcessor(batch_interval_s=self.batch_interval_s)
        self.analytics_engine = RealtimeAnalyticsEngine()

        self._state = ReplayState(session_id=session_id)
        self._lock = threading.RLock()

        # Threading controls
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_requested = threading.Event()
        self._pause_requested = threading.Event()

        # Dataset buffer
        self._dataset_df: Optional[pd.DataFrame] = None
        self._data_source = data_source

        # In-memory history cache of emitted claims in this session
        self._session_claims: List[ClaimRecord] = []

        # Attempt to recover checkpoint if exists
        self._recover_state()

    def set_playback_speed(self, speed: float) -> None:
        """Update playback speed multiplier (1x, 2x, 5x, 10x)."""
        with self._lock:
            self.playback_speed = max(0.1, float(speed))
            self._state.metrics.playback_speed = self.playback_speed
            logger.info(f"Playback speed adjusted to {self.playback_speed}x")

    def _load_data_if_needed(self) -> pd.DataFrame:
        """Load and cache the GPS telemetry dataset for replay."""
        if self._dataset_df is not None and not self._dataset_df.empty:
            return self._dataset_df

        root = get_project_root()

        if isinstance(self._data_source, pd.DataFrame):
            df = self._data_source.copy()
        elif self._data_source is not None and Path(self._data_source).exists():
            path = Path(self._data_source)
            if path.suffix == ".parquet" or path.is_dir():
                df = pd.read_parquet(path)
            else:
                df = pd.read_csv(path)
        else:
            # Default fallback: check prevalidated parquet first, then raw csv
            eligible_parquet = root / "data" / "parquet" / "eligible_points"
            raw_100k_csv = root / "data" / "raw" / "gps_100k.csv"
            raw_demo_csv = root / "data" / "raw" / "gps_demo.csv"

            if eligible_parquet.exists():
                logger.info(f"Loading prevalidated eligible points from {eligible_parquet}")
                df = pd.read_parquet(eligible_parquet)
            elif raw_100k_csv.exists():
                logger.info(f"Loading raw GPS dataset from {raw_100k_csv}")
                df = pd.read_csv(raw_100k_csv)
            elif raw_demo_csv.exists():
                logger.info(f"Loading demo GPS dataset from {raw_demo_csv}")
                df = pd.read_csv(raw_demo_csv)
            else:
                df = pd.DataFrame()

        # Prepare epoch timestamp if not present
        if not df.empty and "timestamp_epoch" not in df.columns:
            if "timestamp" in df.columns:
                df["timestamp_epoch"] = pd.to_datetime(df["timestamp"], utc=True).astype("int64") / 1e9

        self._dataset_df = df
        with self._lock:
            self._state.metrics.total_events = len(df)
            self._state.metrics.remaining_events = len(df) - self._state.metrics.events_processed
        return self._dataset_df

    def _recover_state(self) -> None:
        """Recover state from SQLite database if an earlier checkpoint exists."""
        checkpoint = self.state_store.get_checkpoint(self.session_id)
        if checkpoint:
            # Populate ownership engine from current_ownership table
            curr_df = self.state_store.get_current_ownership_df()
            initial_ownership: Dict[str, ZoneOwnershipRecord] = {}
            for _, row in curr_df.iterrows():
                rec = ZoneOwnershipRecord(
                    h3_cell=row["h3_cell"],
                    current_owner_id=row["current_owner_id"],
                    previous_owner_id=row.get("previous_owner_id"),
                    acquired_in_run=row.get("acquired_in_run", ""),
                    acquired_at=row.get("acquired_at", ""),
                    acquired_epoch=row.get("acquired_epoch", 0.0),
                    latest_claim_id=row.get("latest_claim_id", ""),
                    total_zone_claims=int(row.get("total_zone_claims", 1)),
                    total_zone_takeovers=int(row.get("total_zone_takeovers", 0)),
                    total_zone_revisits=int(row.get("total_zone_revisits", 0)),
                    unique_zone_runners=int(row.get("unique_zone_runners", 1)),
                    updated_at=row.get("updated_at", ""),
                )
                initial_ownership[row["h3_cell"]] = rec

            self.ownership_engine = IncrementalOwnershipEngine(initial_ownership)

            # Recover metrics
            with self._lock:
                self._state.status = ReplayStatus(checkpoint.replay_status)
                m = self._state.metrics
                m.events_processed = checkpoint.events_processed
                m.total_events = checkpoint.total_events
                m.remaining_events = max(0, checkpoint.total_events - checkpoint.events_processed)
                m.progress_pct = (
                    round(m.events_processed / m.total_events * 100.0, 2)
                    if m.total_events > 0
                    else 0.0
                )
                m.batches_processed = checkpoint.last_committed_batch
                m.claims_processed = checkpoint.total_claims_processed
                m.current_event_timestamp = checkpoint.last_event_timestamp
                m.current_event_epoch = checkpoint.last_event_epoch
                m.total_zones_owned = len(initial_ownership)
                m.active_owners_count = len({r.current_owner_id for r in initial_ownership.values()})
                m.status = self._state.status

            logger.info(
                f"Recovered checkpoint for session '{self.session_id}': "
                f"batch {checkpoint.last_committed_batch}, {m.events_processed}/{m.total_events} events"
            )

    def start(self) -> bool:
        """Start or initiate replay from current or beginning position."""
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                if self._pause_requested.is_set():
                    # If paused, resume it
                    self.resume()
                    return True
                logger.info("Replay simulation already running.")
                return False

            self._load_data_if_needed()
            if self._dataset_df is None or self._dataset_df.empty:
                logger.error("No GPS dataset available to replay.")
                return False

            self._stop_requested.clear()
            self._pause_requested.clear()
            self._state.status = ReplayStatus.RUNNING
            self._state.metrics.status = ReplayStatus.RUNNING

            self._worker_thread = threading.Thread(
                target=self._run_simulation_loop,
                name="GPSReplayWorker",
                daemon=True,
            )
            self._worker_thread.start()
            logger.info("GPS Replay worker thread started successfully.")
            return True

    def pause(self) -> None:
        """Pause event advancement without discarding committed state."""
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                self._pause_requested.set()
                self._state.status = ReplayStatus.PAUSED
                self._state.metrics.status = ReplayStatus.PAUSED
                logger.info("GPS Replay paused.")

    def resume(self) -> None:
        """Resume execution from paused checkpoint."""
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                self._pause_requested.clear()
                self._state.status = ReplayStatus.RUNNING
                self._state.metrics.status = ReplayStatus.RUNNING
                logger.info("GPS Replay resumed.")
            else:
                self.start()

    def stop(self) -> None:
        """Stop replay cleanly."""
        self._stop_requested.set()
        self._pause_requested.clear()
        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3.0)
        with self._lock:
            self._state.status = ReplayStatus.STOPPED
            self._state.metrics.status = ReplayStatus.STOPPED
            logger.info("GPS Replay stopped.")

    def restart(self) -> None:
        """Reset all committed state and restart from event 0."""
        self.stop()
        with self._lock:
            self.state_store.reset_session(self.session_id)
            self.ownership_engine.reset()
            self.batch_processor.reset_state()
            self.analytics_engine.reset()
            self._session_claims.clear()

            self._state = ReplayState(session_id=self.session_id)
            if self._dataset_df is not None:
                self._state.metrics.total_events = len(self._dataset_df)
                self._state.metrics.remaining_events = len(self._dataset_df)
            self._state.metrics.playback_speed = self.playback_speed
            self._state.metrics.batch_interval_s = self.batch_interval_s

        self.start()
        logger.info("GPS Replay restarted from beginning.")

    def step_batch(self, batch: GPSMicroBatch) -> bool:
        """Execute and commit a single micro-batch. Can be called directly for testing or stepping."""
        # 1. Skip if already committed
        if self.state_store.is_batch_committed(self.session_id, batch.batch_id):
            return False

        # 2. Incrementally process claims
        proc_claims, updated_zones, feed_events = self.ownership_engine.process_claims_batch(
            batch.claims,
            batch_id=batch.batch_id,
        )
        self._session_claims.extend(proc_claims)

        # 3. Update realtime hotspot analytics
        hotspot_records = self.analytics_engine.update_from_claims(proc_claims)

        # 4. Prepare checkpoint
        with self._lock:
            m = self._state.metrics
            m.events_processed += batch.events_count
            m.remaining_events = max(0, m.total_events - m.events_processed)
            m.progress_pct = (
                round(m.events_processed / m.total_events * 100.0, 2)
                if m.total_events > 0
                else 100.0
            )
            m.batches_processed = batch.batch_id
            m.claims_processed += len(proc_claims)
            m.suspicious_runs_detected += batch.suspicious_events_count
            m.current_event_timestamp = batch.end_timestamp
            m.current_event_epoch = batch.end_epoch
            m.total_zones_owned = self.ownership_engine.total_owned_zones
            m.active_owners_count = len({
                r.current_owner_id for r in self.ownership_engine.current_ownership.values()
            })

            # Event counts
            for c in proc_claims:
                if c.event_type == "INITIAL_CAPTURE":
                    m.initial_captures += 1
                elif c.event_type == "TAKEOVER":
                    m.takeovers += 1
                elif c.event_type == "SAME_OWNER_REVISIT":
                    m.same_owner_revisits += 1

            # Visual highlight cells
            self._state.newly_captured_cells = [
                c.h3_cell for c in proc_claims if c.event_type == "INITIAL_CAPTURE"
            ]
            self._state.takeover_cells = [
                c.h3_cell for c in proc_claims if c.event_type == "TAKEOVER"
            ]

            # Recent feed events
            if feed_events:
                self._state.recent_events = (feed_events + self._state.recent_events)[:50]

            now_iso = datetime.now(timezone.utc).isoformat()
            checkpoint = ReplayCheckpoint(
                session_id=self.session_id,
                dataset_fingerprint="chicago_loop_gps_100k",
                current_position=m.events_processed,
                last_committed_batch=batch.batch_id,
                last_event_timestamp=batch.end_timestamp,
                last_event_epoch=batch.end_epoch,
                replay_status=self._state.status.value,
                total_events=m.total_events,
                events_processed=m.events_processed,
                total_claims_processed=m.claims_processed,
                created_at=now_iso,
                updated_at=now_iso,
            )

        # 5. Commit atomic transaction to SQLite
        self.state_store.commit_batch(
            session_id=self.session_id,
            batch_id=batch.batch_id,
            checkpoint=checkpoint,
            claims=proc_claims,
            ownership_updates=updated_zones,
            hotspot_updates=hotspot_records,
            feed_messages=feed_events,
        )
        return True

    def _run_simulation_loop(self) -> None:
        """Internal simulation thread loop processing batches chronologically."""
        logger.info("Entering replay simulation loop.")
        df = self._load_data_if_needed()

        last_committed = self._state.metrics.batches_processed
        start_batch_id = last_committed + 1

        batch_generator = self.batch_processor.partition_records_into_batches(
            df,
            start_batch_id=start_batch_id,
        )

        for batch in batch_generator:
            if self._stop_requested.is_set():
                break

            while self._pause_requested.is_set():
                if self._stop_requested.is_set():
                    break
                time.sleep(0.1)

            if self._stop_requested.is_set():
                break

            # Execute batch
            self.step_batch(batch)

            # Controlled sleep according to playback speed
            # Target delay in seconds between batches: (batch_interval_s / playback_speed)
            # Scaled so 10x is snappy while 1x is visible
            delay = max(0.01, (self.batch_interval_s / max(0.1, self.playback_speed)) * 0.05)
            time.sleep(delay)

        with self._lock:
            if not self._stop_requested.is_set():
                self._state.status = ReplayStatus.COMPLETED
                self._state.metrics.status = ReplayStatus.COMPLETED
                logger.info("GPS Replay reached end of dataset: COMPLETED.")

    def get_snapshot(self) -> Dict[str, Any]:
        """Return a thread-safe snapshot of current state and metrics for UI."""
        with self._lock:
            return self._state.to_dict()

    def get_current_ownership_df(self) -> pd.DataFrame:
        """Retrieve current ownership table as a DataFrame."""
        return self.state_store.get_current_ownership_df()

    def get_ownership_history_df(self) -> pd.DataFrame:
        """Retrieve full conquest history as a DataFrame."""
        return self.state_store.get_ownership_history_df()

    def get_leaderboard_df(self) -> pd.DataFrame:
        """Retrieve real-time leaderboard as a DataFrame."""
        return self.analytics_engine.compute_leaderboard_from_ownership(
            self.ownership_engine.current_ownership,
            self._session_claims,
        )

    def get_hotspot_scores_df(self) -> pd.DataFrame:
        """Retrieve real-time hotspot scores table as a DataFrame."""
        return self.state_store.get_hotspot_metrics_df()
