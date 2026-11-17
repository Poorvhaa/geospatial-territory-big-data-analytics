"""Persistent Transactional State Store for Real-Time Replay (Day 4).

Uses SQLite with ACID guarantees, idempotent claim ingestion, and checkpoint
recovery to maintain territory ownership, conquest history, and analytical state.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from src.realtime.replay_state import (
    ClaimRecord,
    HotspotRecord,
    ReplayCheckpoint,
    ZoneOwnershipRecord,
)

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data") / "replay_state.db"


class SQLiteStateStore:
    """ACID-compliant SQLite persistence store for real-time replay simulation."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a configured SQLite connection with WAL journal mode for concurrency."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            check_same_thread=False,
            isolation_level=None,  # Autocommit mode; we manage explicit transactions
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        """Initialize database tables, indices, and constraints."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE")
                # 1. Replay session state
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS replay_session (
                        session_id TEXT PRIMARY KEY,
                        dataset_fingerprint TEXT,
                        current_position INTEGER DEFAULT 0,
                        last_committed_batch INTEGER DEFAULT 0,
                        last_event_timestamp TEXT DEFAULT '',
                        last_event_epoch REAL DEFAULT 0.0,
                        replay_status TEXT DEFAULT 'STOPPED',
                        total_events INTEGER DEFAULT 0,
                        events_processed INTEGER DEFAULT 0,
                        total_claims_processed INTEGER DEFAULT 0,
                        created_at TEXT,
                        updated_at TEXT
                    )
                """)

                # 2. Current zone ownership snapshot
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS current_ownership (
                        h3_cell TEXT PRIMARY KEY,
                        current_owner_id TEXT NOT NULL,
                        previous_owner_id TEXT,
                        acquired_in_run TEXT,
                        acquired_at TEXT,
                        acquired_epoch REAL DEFAULT 0.0,
                        latest_claim_id TEXT,
                        total_zone_claims INTEGER DEFAULT 1,
                        total_zone_takeovers INTEGER DEFAULT 0,
                        total_zone_revisits INTEGER DEFAULT 0,
                        unique_zone_runners INTEGER DEFAULT 1,
                        updated_at TEXT
                    )
                """)

                # 3. Complete ownership transitions history
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ownership_history (
                        claim_id TEXT PRIMARY KEY,
                        h3_cell TEXT NOT NULL,
                        runner_id TEXT NOT NULL,
                        run_id TEXT NOT NULL,
                        claim_timestamp TEXT NOT NULL,
                        claim_timestamp_epoch REAL NOT NULL,
                        event_type TEXT NOT NULL,
                        is_takeover INTEGER DEFAULT 0,
                        is_ownership_change INTEGER DEFAULT 1,
                        prev_runner_id TEXT,
                        points_in_visit INTEGER DEFAULT 2,
                        batch_id INTEGER DEFAULT 0,
                        created_at TEXT
                    )
                """)

                # 4. Processed batches tracker (prevents duplicate submission)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS committed_batches (
                        session_id TEXT,
                        batch_id INTEGER,
                        events_count INTEGER,
                        claims_count INTEGER,
                        committed_at TEXT,
                        PRIMARY KEY (session_id, batch_id)
                    )
                """)

                # 5. Incremental hotspot metrics
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS hotspot_metrics (
                        h3_cell TEXT PRIMARY KEY,
                        total_visits INTEGER DEFAULT 0,
                        unique_runners INTEGER DEFAULT 0,
                        unique_runs INTEGER DEFAULT 0,
                        takeovers INTEGER DEFAULT 0,
                        norm_takeovers REAL DEFAULT 0.0,
                        norm_unique_runners REAL DEFAULT 0.0,
                        norm_visits REAL DEFAULT 0.0,
                        hotspot_score REAL DEFAULT 0.0,
                        hotspot_rank INTEGER DEFAULT 1,
                        last_activity_time TEXT,
                        updated_at TEXT
                    )
                """)

                # 6. Real-time event activity feed
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS replay_events_feed (
                        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT,
                        batch_id INTEGER,
                        event_timestamp TEXT,
                        event_type TEXT,
                        runner_id TEXT,
                        h3_cell TEXT,
                        message TEXT,
                        created_at TEXT
                    )
                """)

                # Indices for fast queries
                conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_cell ON ownership_history(h3_cell)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_runner ON ownership_history(runner_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_epoch ON ownership_history(claim_timestamp_epoch)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_feed_batch ON replay_events_feed(batch_id)")
                conn.execute("COMMIT")
            except Exception as e:
                conn.execute("ROLLBACK")
                logger.error(f"Failed to initialize SQLite schema: {e}")
                raise
            finally:
                conn.close()

    def is_batch_committed(self, session_id: str, batch_id: int) -> bool:
        """Check if a batch was already committed for this session."""
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT 1 FROM committed_batches WHERE session_id = ? AND batch_id = ?",
                    (session_id, batch_id),
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    def has_claim(self, claim_id: str) -> bool:
        """Check if a claim_id has already been recorded."""
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT 1 FROM ownership_history WHERE claim_id = ?",
                    (claim_id,),
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    def commit_batch(
        self,
        session_id: str,
        batch_id: int,
        checkpoint: ReplayCheckpoint,
        claims: List[ClaimRecord],
        ownership_updates: List[ZoneOwnershipRecord],
        hotspot_updates: Optional[List[HotspotRecord]] = None,
        feed_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Atomically commit all batch updates, claims, ownership transitions, and checkpoints."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE")

                now_iso = datetime.now(timezone.utc).isoformat()

                # 1. Prevent duplicate batch processing
                already_committed = conn.execute(
                    "SELECT 1 FROM committed_batches WHERE session_id = ? AND batch_id = ?",
                    (session_id, batch_id),
                ).fetchone()
                if already_committed:
                    logger.warning(f"Batch {batch_id} already committed for session {session_id}. Skipping.")
                    conn.execute("ROLLBACK")
                    return False

                # 2. Insert claims idempotently into ownership_history
                for c in claims:
                    conn.execute("""
                        INSERT OR IGNORE INTO ownership_history (
                            claim_id, h3_cell, runner_id, run_id, claim_timestamp,
                            claim_timestamp_epoch, event_type, is_takeover,
                            is_ownership_change, prev_runner_id, points_in_visit,
                            batch_id, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        c.claim_id,
                        c.h3_cell,
                        c.runner_id,
                        c.run_id,
                        c.claim_timestamp,
                        c.claim_timestamp_epoch,
                        c.event_type,
                        1 if c.is_takeover else 0,
                        1 if c.is_ownership_change else 0,
                        c.prev_runner_id,
                        c.points_in_visit,
                        c.batch_id,
                        now_iso,
                    ))

                # 3. Update current ownership records
                for ow in ownership_updates:
                    conn.execute("""
                        INSERT INTO current_ownership (
                            h3_cell, current_owner_id, previous_owner_id, acquired_in_run,
                            acquired_at, acquired_epoch, latest_claim_id, total_zone_claims,
                            total_zone_takeovers, total_zone_revisits, unique_zone_runners,
                            updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(h3_cell) DO UPDATE SET
                            current_owner_id = excluded.current_owner_id,
                            previous_owner_id = excluded.previous_owner_id,
                            acquired_in_run = excluded.acquired_in_run,
                            acquired_at = excluded.acquired_at,
                            acquired_epoch = excluded.acquired_epoch,
                            latest_claim_id = excluded.latest_claim_id,
                            total_zone_claims = excluded.total_zone_claims,
                            total_zone_takeovers = excluded.total_zone_takeovers,
                            total_zone_revisits = excluded.total_zone_revisits,
                            unique_zone_runners = excluded.unique_zone_runners,
                            updated_at = excluded.updated_at
                    """, (
                        ow.h3_cell,
                        ow.current_owner_id,
                        ow.previous_owner_id,
                        ow.acquired_in_run,
                        ow.acquired_at,
                        ow.acquired_epoch,
                        ow.latest_claim_id,
                        ow.total_zone_claims,
                        ow.total_zone_takeovers,
                        ow.total_zone_revisits,
                        ow.unique_zone_runners,
                        now_iso,
                    ))

                # 4. Hotspot updates if provided
                if hotspot_updates:
                    for h in hotspot_updates:
                        conn.execute("""
                            INSERT INTO hotspot_metrics (
                                h3_cell, total_visits, unique_runners, unique_runs,
                                takeovers, norm_takeovers, norm_unique_runners,
                                norm_visits, hotspot_score, hotspot_rank,
                                last_activity_time, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(h3_cell) DO UPDATE SET
                                total_visits = excluded.total_visits,
                                unique_runners = excluded.unique_runners,
                                unique_runs = excluded.unique_runs,
                                takeovers = excluded.takeovers,
                                norm_takeovers = excluded.norm_takeovers,
                                norm_unique_runners = excluded.norm_unique_runners,
                                norm_visits = excluded.norm_visits,
                                hotspot_score = excluded.hotspot_score,
                                hotspot_rank = excluded.hotspot_rank,
                                last_activity_time = excluded.last_activity_time,
                                updated_at = excluded.updated_at
                        """, (
                            h.h3_cell,
                            h.total_visits,
                            h.unique_runners,
                            h.unique_runs,
                            h.takeovers,
                            h.norm_takeovers,
                            h.norm_unique_runners,
                            h.norm_visits,
                            h.hotspot_score,
                            h.hotspot_rank,
                            h.last_activity_time,
                            now_iso,
                        ))

                # 5. Feed messages
                if feed_messages:
                    for msg in feed_messages:
                        conn.execute("""
                            INSERT INTO replay_events_feed (
                                session_id, batch_id, event_timestamp, event_type,
                                runner_id, h3_cell, message, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            session_id,
                            batch_id,
                            msg.get("event_timestamp", ""),
                            msg.get("event_type", "INFO"),
                            msg.get("runner_id", ""),
                            msg.get("h3_cell", ""),
                            msg.get("message", ""),
                            now_iso,
                        ))

                # 6. Mark batch committed
                conn.execute("""
                    INSERT INTO committed_batches (session_id, batch_id, events_count, claims_count, committed_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (session_id, batch_id, checkpoint.events_processed, len(claims), now_iso))

                # 7. Update session checkpoint
                conn.execute("""
                    INSERT INTO replay_session (
                        session_id, dataset_fingerprint, current_position, last_committed_batch,
                        last_event_timestamp, last_event_epoch, replay_status, total_events,
                        events_processed, total_claims_processed, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        dataset_fingerprint = excluded.dataset_fingerprint,
                        current_position = excluded.current_position,
                        last_committed_batch = excluded.last_committed_batch,
                        last_event_timestamp = excluded.last_event_timestamp,
                        last_event_epoch = excluded.last_event_epoch,
                        replay_status = excluded.replay_status,
                        total_events = excluded.total_events,
                        events_processed = excluded.events_processed,
                        total_claims_processed = excluded.total_claims_processed,
                        updated_at = excluded.updated_at
                """, (
                    checkpoint.session_id,
                    checkpoint.dataset_fingerprint,
                    checkpoint.current_position,
                    checkpoint.last_committed_batch,
                    checkpoint.last_event_timestamp,
                    checkpoint.last_event_epoch,
                    checkpoint.replay_status,
                    checkpoint.total_events,
                    checkpoint.events_processed,
                    checkpoint.total_claims_processed,
                    checkpoint.created_at,
                    now_iso,
                ))

                conn.execute("COMMIT")
                return True
            except Exception as e:
                conn.execute("ROLLBACK")
                logger.error(f"Error committing batch {batch_id}: {e}")
                raise
            finally:
                conn.close()

    def get_checkpoint(self, session_id: str) -> Optional[ReplayCheckpoint]:
        """Load the latest checkpoint for a given session."""
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM replay_session WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if not row:
                    return None
                return ReplayCheckpoint(
                    session_id=row["session_id"],
                    dataset_fingerprint=row["dataset_fingerprint"],
                    current_position=row["current_position"],
                    last_committed_batch=row["last_committed_batch"],
                    last_event_timestamp=row["last_event_timestamp"],
                    last_event_epoch=row["last_event_epoch"],
                    replay_status=row["replay_status"],
                    total_events=row["total_events"],
                    events_processed=row["events_processed"],
                    total_claims_processed=row["total_claims_processed"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            finally:
                conn.close()

    def get_current_ownership_df(self) -> pd.DataFrame:
        """Fetch current ownership table as a pandas DataFrame."""
        with self._lock:
            conn = self._get_connection()
            try:
                df = pd.read_sql_query("SELECT * FROM current_ownership ORDER BY acquired_epoch DESC", conn)
                return df
            finally:
                conn.close()

    def get_ownership_history_df(self, limit: Optional[int] = None) -> pd.DataFrame:
        """Fetch ownership conquest history as a pandas DataFrame."""
        with self._lock:
            conn = self._get_connection()
            try:
                query = "SELECT * FROM ownership_history ORDER BY claim_timestamp_epoch ASC"
                if limit and limit > 0:
                    query += f" LIMIT {int(limit)}"
                df = pd.read_sql_query(query, conn)
                return df
            finally:
                conn.close()

    def get_hotspot_metrics_df(self) -> pd.DataFrame:
        """Fetch latest calculated hotspot metrics as a pandas DataFrame."""
        with self._lock:
            conn = self._get_connection()
            try:
                df = pd.read_sql_query("SELECT * FROM hotspot_metrics ORDER BY hotspot_score DESC", conn)
                return df
            finally:
                conn.close()

    def get_leaderboard_df(self) -> pd.DataFrame:
        """Fetch real-time leaderboard ranked by current zones owned."""
        with self._lock:
            conn = self._get_connection()
            try:
                query = """
                    SELECT
                        current_owner_id AS runner_id,
                        COUNT(h3_cell) AS zones_owned
                    FROM current_ownership
                    GROUP BY current_owner_id
                    ORDER BY zones_owned DESC, runner_id ASC
                """
                df = pd.read_sql_query(query, conn)
                if not df.empty:
                    df["rank"] = df["zones_owned"].rank(ascending=False, method="dense").astype(int)
                return df
            finally:
                conn.close()

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent events from the replay events feed."""
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    "SELECT * FROM replay_events_feed ORDER BY event_id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def reset_session(self, session_id: str) -> None:
        """Reset replay state for a session, clearing all claims and ownership."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM replay_session WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM committed_batches WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM replay_events_feed WHERE session_id = ?", (session_id,))
                # For clean single-session academic demo, reset current ownership and history
                conn.execute("DELETE FROM current_ownership")
                conn.execute("DELETE FROM ownership_history")
                conn.execute("DELETE FROM hotspot_metrics")
                conn.execute("COMMIT")
                logger.info(f"Replay session '{session_id}' state reset cleanly.")
            except Exception as e:
                conn.execute("ROLLBACK")
                logger.error(f"Error resetting replay session '{session_id}': {e}")
                raise
            finally:
                conn.close()
