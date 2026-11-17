"""Chronological GPS Micro-Batch Processor (Day 4).

Partitions time-ordered GPS event streams into discrete micro-batches, persists
run state across batch boundaries, and emits deterministic H3 territory claims.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import h3
import pandas as pd

from src.realtime.replay_state import ClaimRecord

logger = logging.getLogger(__name__)

DEFAULT_BATCH_INTERVAL_S = 5.0
DEFAULT_MIN_CONSECUTIVE_OBSERVATIONS = 2
DEFAULT_H3_RESOLUTION = 9


@dataclass
class ActiveRunState:
    """Maintains kinematic and spatial visit state across batch boundaries."""
    run_id: str
    runner_id: str
    current_cell: Optional[str] = None
    points_in_current_cell: int = 0
    visit_idx: int = 0
    claimed_current_visit: bool = False
    last_timestamp: str = ""
    last_epoch: float = 0.0


@dataclass
class GPSMicroBatch:
    """A single chronological micro-batch of GPS events."""
    batch_id: int
    start_epoch: float
    end_epoch: float
    start_timestamp: str
    end_timestamp: str
    events_count: int
    events: List[Dict[str, Any]]
    claims: List[ClaimRecord]
    suspicious_events_count: int = 0


class BatchProcessor:
    """Slices GPS telemetry into time-ordered batches and extracts zone claims."""

    def __init__(
        self,
        batch_interval_s: float = DEFAULT_BATCH_INTERVAL_S,
        min_consecutive_points: int = DEFAULT_MIN_CONSECUTIVE_OBSERVATIONS,
        h3_resolution: int = DEFAULT_H3_RESOLUTION,
    ) -> None:
        self.batch_interval_s = float(batch_interval_s)
        self.min_consecutive_points = int(min_consecutive_points)
        self.h3_resolution = int(h3_resolution)
        # Cross-batch state: run_id -> ActiveRunState
        self._run_states: Dict[str, ActiveRunState] = {}

    def reset_state(self) -> None:
        """Clear cross-batch run visit states."""
        self._run_states.clear()

    def process_point(self, point: Dict[str, Any]) -> Optional[ClaimRecord]:
        """Process a single GPS point, updating cross-batch run state and emitting claim when eligible.

        Args:
            point: Dictionary of point attributes (run_id, runner_id, timestamp, timestamp_epoch, h3_cell).

        Returns:
            ClaimRecord if this point satisfies the consecutive observation threshold, else None.
        """
        run_id = str(point["run_id"])
        runner_id = str(point["runner_id"])
        timestamp = str(point["timestamp"])
        epoch = float(point["timestamp_epoch"])

        cell = point.get("h3_cell")
        if not cell or not isinstance(cell, str) or len(cell) < 15:
            # Compute H3 cell if missing or invalid
            lat = float(point["latitude"])
            lon = float(point["longitude"])
            try:
                cell = h3.latlng_to_cell(lat, lon, self.h3_resolution)
            except Exception:
                return None

        state = self._run_states.get(run_id)
        if state is None:
            state = ActiveRunState(
                run_id=run_id,
                runner_id=runner_id,
                current_cell=cell,
                points_in_current_cell=1,
                visit_idx=1,
                claimed_current_visit=False,
                last_timestamp=timestamp,
                last_epoch=epoch,
            )
            self._run_states[run_id] = state

            # If min_consecutive_points == 1, claim on first point
            if self.min_consecutive_points <= 1:
                state.claimed_current_visit = True
                claim_id = f"{run_id}_v{state.visit_idx}_{cell}"
                return ClaimRecord(
                    claim_id=claim_id,
                    h3_cell=cell,
                    runner_id=runner_id,
                    run_id=run_id,
                    claim_timestamp=timestamp,
                    claim_timestamp_epoch=epoch,
                    points_in_visit=1,
                )
            return None

        # Runner was already active
        state.last_timestamp = timestamp
        state.last_epoch = epoch

        if cell == state.current_cell:
            state.points_in_current_cell += 1
            if (
                state.points_in_current_cell >= self.min_consecutive_points
                and not state.claimed_current_visit
            ):
                state.claimed_current_visit = True
                claim_id = f"{run_id}_v{state.visit_idx}_{cell}"
                return ClaimRecord(
                    claim_id=claim_id,
                    h3_cell=cell,
                    runner_id=runner_id,
                    run_id=run_id,
                    claim_timestamp=timestamp,
                    claim_timestamp_epoch=epoch,
                    points_in_visit=state.points_in_current_cell,
                )
        else:
            # Transitioned into a new H3 cell!
            state.visit_idx += 1
            state.current_cell = cell
            state.points_in_current_cell = 1
            state.claimed_current_visit = False

            if self.min_consecutive_points <= 1:
                state.claimed_current_visit = True
                claim_id = f"{run_id}_v{state.visit_idx}_{cell}"
                return ClaimRecord(
                    claim_id=claim_id,
                    h3_cell=cell,
                    runner_id=runner_id,
                    run_id=run_id,
                    claim_timestamp=timestamp,
                    claim_timestamp_epoch=epoch,
                    points_in_visit=1,
                )

        return None

    def partition_records_into_batches(
        self,
        df: pd.DataFrame,
        start_batch_id: int = 1,
    ) -> Iterator[GPSMicroBatch]:
        """Generator yielding micro-batches chronologically partitioned by simulated event time.

        Args:
            df: DataFrame containing GPS points with 'timestamp_epoch'.
            start_batch_id: Sequence number for the first emitted batch.

        Yields:
            GPSMicroBatch instances.
        """
        if df.empty:
            return

        # Ensure deterministic chronological sorting
        sort_cols = ["timestamp_epoch", "run_id", "runner_id"]
        available_cols = [c for c in sort_cols if c in df.columns]
        df_sorted = df.sort_values(by=available_cols, ascending=True).reset_index(drop=True)

        min_epoch = float(df_sorted["timestamp_epoch"].min())
        max_epoch = float(df_sorted["timestamp_epoch"].max())

        batch_id = start_batch_id
        current_start_epoch = min_epoch

        # Pre-group or window-slice by event interval
        records = df_sorted.to_dict(orient="records")
        idx = 0
        total_records = len(records)

        while idx < total_records:
            current_end_epoch = current_start_epoch + self.batch_interval_s
            batch_records: List[Dict[str, Any]] = []

            while idx < total_records and records[idx]["timestamp_epoch"] < current_end_epoch:
                batch_records.append(records[idx])
                idx += 1

            # If no records in this interval, but still records remaining, advance window
            if not batch_records and idx < total_records:
                current_start_epoch = float(records[idx]["timestamp_epoch"])
                continue

            if batch_records:
                batch_claims: List[ClaimRecord] = []
                suspicious_count = 0

                for pt in batch_records:
                    # Check if pre-labeled as suspicious/rejected
                    is_rejected = pt.get("risk_category") in ["SUSPICIOUS", "HIGH_RISK"]
                    if is_rejected:
                        suspicious_count += 1
                        continue

                    claim = self.process_point(pt)
                    if claim:
                        batch_claims.append(claim)

                start_ts = str(batch_records[0].get("timestamp", ""))
                end_ts = str(batch_records[-1].get("timestamp", ""))

                yield GPSMicroBatch(
                    batch_id=batch_id,
                    start_epoch=current_start_epoch,
                    end_epoch=current_end_epoch,
                    start_timestamp=start_ts,
                    end_timestamp=end_ts,
                    events_count=len(batch_records),
                    events=batch_records,
                    claims=batch_claims,
                    suspicious_events_count=suspicious_count,
                )
                batch_id += 1

            current_start_epoch = current_end_epoch
