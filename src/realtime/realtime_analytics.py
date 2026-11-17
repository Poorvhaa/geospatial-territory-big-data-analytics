"""Real-Time Hotspot and Leaderboard Analytics (Day 4).

Computes incremental hotspot scores, live runner rankings, and data quality
KPIs synchronously after each micro-batch commit.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

import numpy as np
import pandas as pd

from src.realtime.replay_state import (
    ClaimRecord,
    HotspotRecord,
    ReplayMetrics,
    ZoneOwnershipRecord,
)

logger = logging.getLogger(__name__)


class RealtimeAnalyticsEngine:
    """Incremental analytical engine maintaining live rankings and hotspot scores."""

    def __init__(
        self,
        w_takeovers: float = 0.40,
        w_unique_runners: float = 0.35,
        w_visits: float = 0.25,
    ) -> None:
        self.w_takeovers = float(w_takeovers)
        self.w_unique_runners = float(w_unique_runners)
        self.w_visits = float(w_visits)

        # In-memory aggregations: h3_cell -> tracking dict
        # {visits: int, unique_runners: Set[str], unique_runs: Set[str], takeovers: int, last_time: str}
        self._zone_stats: Dict[str, Dict[str, Any]] = {}

    def update_from_claims(self, claims: List[ClaimRecord]) -> List[HotspotRecord]:
        """Incrementally update zone visit and takeover counters from newly processed claims.

        Args:
            claims: Claims emitted in current micro-batch.

        Returns:
            List of updated HotspotRecord instances.
        """
        if not claims:
            return []

        impacted_cells: Set[str] = set()

        for c in claims:
            cell = c.h3_cell
            impacted_cells.add(cell)

            if cell not in self._zone_stats:
                self._zone_stats[cell] = {
                    "visits": 0,
                    "runners": set(),
                    "runs": set(),
                    "takeovers": 0,
                    "last_time": c.claim_timestamp,
                }

            stats = self._zone_stats[cell]
            stats["visits"] += 1
            stats["runners"].add(c.runner_id)
            stats["runs"].add(c.run_id)
            stats["last_time"] = c.claim_timestamp
            if c.is_takeover:
                stats["takeovers"] += 1

        return self.compute_hotspot_scores()

    def compute_hotspot_scores(self) -> List[HotspotRecord]:
        """Compute composite normalized hotspot scores across all tracked zones."""
        if not self._zone_stats:
            return []

        cells = list(self._zone_stats.keys())
        visits = np.array([self._zone_stats[c]["visits"] for c in cells], dtype=float)
        runners = np.array([len(self._zone_stats[c]["runners"]) for c in cells], dtype=float)
        takeovers = np.array([self._zone_stats[c]["takeovers"] for c in cells], dtype=float)

        def normalize(arr: np.ndarray) -> np.ndarray:
            a_min = np.min(arr)
            a_max = np.max(arr)
            if a_max == a_min:
                return np.zeros_like(arr)
            return np.round((arr - a_min) / (a_max - a_min), 4)

        norm_v = normalize(visits)
        norm_r = normalize(runners)
        norm_t = normalize(takeovers)

        scores = np.round(
            self.w_takeovers * norm_t
            + self.w_unique_runners * norm_r
            + self.w_visits * norm_v,
            4,
        )
        scores = np.clip(scores, 0.0, 1.0)

        # Rank (dense rank descending)
        ranks = pd.Series(scores).rank(ascending=False, method="dense").astype(int).tolist()

        records: List[HotspotRecord] = []
        for i, cell in enumerate(cells):
            stats = self._zone_stats[cell]
            records.append(HotspotRecord(
                h3_cell=cell,
                total_visits=int(visits[i]),
                unique_runners=int(runners[i]),
                unique_runs=len(stats["runs"]),
                takeovers=int(takeovers[i]),
                norm_takeovers=float(norm_t[i]),
                norm_unique_runners=float(norm_r[i]),
                norm_visits=float(norm_v[i]),
                hotspot_score=float(scores[i]),
                hotspot_rank=int(ranks[i]),
                last_activity_time=stats["last_time"],
            ))

        # Sort descending by score
        records.sort(key=lambda r: (-r.hotspot_score, r.h3_cell))
        return records

    def compute_leaderboard_from_ownership(
        self,
        current_ownership: Dict[str, ZoneOwnershipRecord],
        history_claims: Optional[List[ClaimRecord]] = None,
    ) -> pd.DataFrame:
        """Compute real-time leaderboard with conservation of owned zones.

        Conservation check: sum(zones_owned) == total owned zones.
        """
        if not current_ownership:
            return pd.DataFrame(columns=["runner_id", "zones_owned", "rank", "total_captures", "takeovers"])

        # Count zones owned per runner
        counts: Dict[str, int] = {}
        for rec in current_ownership.values():
            counts[rec.current_owner_id] = counts.get(rec.current_owner_id, 0) + 1

        # Calculate captures and takeovers from history if available
        runner_captures: Dict[str, int] = {}
        runner_takeovers: Dict[str, int] = {}
        if history_claims:
            for c in history_claims:
                if c.is_ownership_change:
                    runner_captures[c.runner_id] = runner_captures.get(c.runner_id, 0) + 1
                    if c.is_takeover:
                        runner_takeovers[c.runner_id] = runner_takeovers.get(c.runner_id, 0) + 1

        rows = []
        for runner_id, owned in counts.items():
            rows.append({
                "runner_id": runner_id,
                "zones_owned": owned,
                "total_captures": runner_captures.get(runner_id, owned),
                "takeovers": runner_takeovers.get(runner_id, 0),
            })

        df = pd.DataFrame(rows)
        df = df.sort_values(by=["zones_owned", "runner_id"], ascending=[False, True]).reset_index(drop=True)
        df["rank"] = df["zones_owned"].rank(ascending=False, method="dense").astype(int)
        return df

    def reset(self) -> None:
        """Reset analytical state."""
        self._zone_stats.clear()
