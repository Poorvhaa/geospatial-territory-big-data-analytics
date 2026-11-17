"""Replay State and Data Models for Real-Time Simulation (Day 4).

Defines strongly-typed data structures, state enums, and metrics representations
used across the replay engine, batch processor, and UI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ReplayStatus(str, Enum):
    """Execution status of the GPS replay simulation engine."""
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


@dataclass
class ClaimRecord:
    """Represents a validated territory claim event."""
    claim_id: str
    h3_cell: str
    runner_id: str
    run_id: str
    claim_timestamp: str
    claim_timestamp_epoch: float
    points_in_visit: int
    event_type: str = "INITIAL_CAPTURE"  # INITIAL_CAPTURE, TAKEOVER, SAME_OWNER_REVISIT
    is_takeover: bool = False
    is_ownership_change: bool = True
    prev_runner_id: Optional[str] = None
    batch_id: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ZoneOwnershipRecord:
    """Represents the current ownership status of an H3 hexagonal zone."""
    h3_cell: str
    current_owner_id: str
    previous_owner_id: Optional[str] = None
    acquired_in_run: str = ""
    acquired_at: str = ""
    acquired_epoch: float = 0.0
    latest_claim_id: str = ""
    total_zone_claims: int = 1
    total_zone_takeovers: int = 0
    total_zone_revisits: int = 0
    unique_zone_runners: int = 1
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HotspotRecord:
    """Composite hotspot metrics for an H3 cell."""
    h3_cell: str
    total_visits: int = 0
    unique_runners: int = 0
    unique_runs: int = 0
    takeovers: int = 0
    norm_takeovers: float = 0.0
    norm_unique_runners: float = 0.0
    norm_visits: float = 0.0
    hotspot_score: float = 0.0
    hotspot_rank: int = 1
    last_activity_time: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayMetrics:
    """Real-time simulation execution and analytical KPIs."""
    events_processed: int = 0
    total_events: int = 0
    remaining_events: int = 0
    progress_pct: float = 0.0
    batches_processed: int = 0
    total_batches: int = 0
    claims_processed: int = 0
    active_owners_count: int = 0
    total_zones_owned: int = 0
    initial_captures: int = 0
    takeovers: int = 0
    same_owner_revisits: int = 0
    suspicious_runs_detected: int = 0
    current_event_timestamp: str = ""
    current_event_epoch: float = 0.0
    playback_speed: float = 1.0
    batch_interval_s: float = 5.0
    status: ReplayStatus = ReplayStatus.STOPPED

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class ReplayCheckpoint:
    """Persistent recovery checkpoint for replay resumption."""
    session_id: str
    dataset_fingerprint: str
    current_position: int
    last_committed_batch: int
    last_event_timestamp: str
    last_event_epoch: float
    replay_status: str
    total_events: int
    events_processed: int
    total_claims_processed: int
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayState:
    """Thread-safe aggregate snapshot of replay progress and analytical tables."""
    session_id: str = "default_replay_session"
    status: ReplayStatus = ReplayStatus.STOPPED
    metrics: ReplayMetrics = field(default_factory=ReplayMetrics)
    recent_events: List[Dict[str, Any]] = field(default_factory=list)
    newly_captured_cells: List[str] = field(default_factory=list)
    takeover_cells: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "metrics": self.metrics.to_dict(),
            "recent_events": self.recent_events,
            "newly_captured_cells": self.newly_captured_cells,
            "takeover_cells": self.takeover_cells,
        }
