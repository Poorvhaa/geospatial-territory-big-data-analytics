"""Incremental Territory Ownership Engine (Day 4).

Updates hexagonal territory ownership incrementally per micro-batch without
rescanning historical datasets. Enforces deterministic tie-breaking, re-entry
segmentation, and exact Day 2 transition classification rules.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from src.realtime.replay_state import ClaimRecord, ZoneOwnershipRecord

logger = logging.getLogger(__name__)


class IncrementalOwnershipEngine:
    """Stateful, incremental territory ownership processor."""

    def __init__(self, initial_ownership: Optional[Dict[str, ZoneOwnershipRecord]] = None) -> None:
        # Key: h3_cell -> ZoneOwnershipRecord
        self._current_ownership: Dict[str, ZoneOwnershipRecord] = {}
        # Key: h3_cell -> Set of unique runner_ids seen
        self._cell_runners: Dict[str, Set[str]] = {}
        # Set of seen claim_ids to guarantee idempotency
        self._seen_claims: Set[str] = set()

        if initial_ownership:
            for cell, record in initial_ownership.items():
                self._current_ownership[cell] = record
                self._cell_runners.setdefault(cell, set()).add(record.current_owner_id)
                if record.previous_owner_id:
                    self._cell_runners[cell].add(record.previous_owner_id)

    @property
    def current_ownership(self) -> Dict[str, ZoneOwnershipRecord]:
        return self._current_ownership

    @property
    def total_owned_zones(self) -> int:
        return len(self._current_ownership)

    def is_claim_seen(self, claim_id: str) -> bool:
        return claim_id in self._seen_claims

    def process_claims_batch(
        self,
        claims: List[ClaimRecord],
        batch_id: int = 0,
    ) -> Tuple[List[ClaimRecord], List[ZoneOwnershipRecord], List[Dict[str, Any]]]:
        """Incrementally apply a batch of confirmed territory claims.

        Claims with identical timestamps are deterministically sorted by:
        (claim_timestamp_epoch, run_id, runner_id, claim_id) matching Day 2.

        Args:
            claims: Confirmed claim events.
            batch_id: Micro-batch sequence identifier.

        Returns:
            Tuple of:
                processed_claims: Enriched claims with transition classification.
                updated_zones: Changed ZoneOwnershipRecords.
                feed_events: Event feed log items for UI notifications.
        """
        if not claims:
            return [], [], []

        # Deterministic sorting
        sorted_claims = sorted(
            claims,
            key=lambda c: (c.claim_timestamp_epoch, c.run_id, c.runner_id, c.claim_id),
        )

        processed_claims: List[ClaimRecord] = []
        updated_zones_dict: Dict[str, ZoneOwnershipRecord] = {}
        feed_events: List[Dict[str, Any]] = []

        for claim in sorted_claims:
            # Idempotency check: skip already committed claims
            if claim.claim_id in self._seen_claims:
                continue
            self._seen_claims.add(claim.claim_id)

            cell = claim.h3_cell
            runner = claim.runner_id
            timestamp = claim.claim_timestamp
            epoch = claim.claim_timestamp_epoch
            run_id = claim.run_id

            existing = self._current_ownership.get(cell)
            unique_runners = self._cell_runners.setdefault(cell, set())
            unique_runners.add(runner)

            if existing is None:
                # 1. INITIAL CAPTURE: Cell has never been claimed before
                claim.event_type = "INITIAL_CAPTURE"
                claim.is_takeover = False
                claim.is_ownership_change = True
                claim.prev_runner_id = None
                claim.batch_id = batch_id

                zone_rec = ZoneOwnershipRecord(
                    h3_cell=cell,
                    current_owner_id=runner,
                    previous_owner_id=None,
                    acquired_in_run=run_id,
                    acquired_at=timestamp,
                    acquired_epoch=epoch,
                    latest_claim_id=claim.claim_id,
                    total_zone_claims=1,
                    total_zone_takeovers=0,
                    total_zone_revisits=0,
                    unique_zone_runners=len(unique_runners),
                    updated_at=timestamp,
                )
                self._current_ownership[cell] = zone_rec
                updated_zones_dict[cell] = zone_rec

                feed_events.append({
                    "event_timestamp": timestamp,
                    "event_type": "INITIAL_CAPTURE",
                    "runner_id": runner,
                    "h3_cell": cell,
                    "message": f"Runner {runner} captured new territory {cell[:9]}...",
                })

            elif existing.current_owner_id != runner:
                # 2. TAKEOVER: Cell held by a different runner
                prev_owner = existing.current_owner_id
                claim.event_type = "TAKEOVER"
                claim.is_takeover = True
                claim.is_ownership_change = True
                claim.prev_runner_id = prev_owner
                claim.batch_id = batch_id

                zone_rec = ZoneOwnershipRecord(
                    h3_cell=cell,
                    current_owner_id=runner,
                    previous_owner_id=prev_owner,
                    acquired_in_run=run_id,
                    acquired_at=timestamp,
                    acquired_epoch=epoch,
                    latest_claim_id=claim.claim_id,
                    total_zone_claims=existing.total_zone_claims + 1,
                    total_zone_takeovers=existing.total_zone_takeovers + 1,
                    total_zone_revisits=existing.total_zone_revisits,
                    unique_zone_runners=len(unique_runners),
                    updated_at=timestamp,
                )
                self._current_ownership[cell] = zone_rec
                updated_zones_dict[cell] = zone_rec

                feed_events.append({
                    "event_timestamp": timestamp,
                    "event_type": "TAKEOVER",
                    "runner_id": runner,
                    "h3_cell": cell,
                    "message": f"Runner {runner} conquered zone {cell[:9]}... from {prev_owner}!",
                })

            else:
                # 3. SAME_OWNER_REVISIT: Current owner visits their own zone again
                claim.event_type = "SAME_OWNER_REVISIT"
                claim.is_takeover = False
                claim.is_ownership_change = False
                claim.prev_runner_id = existing.current_owner_id
                claim.batch_id = batch_id

                # Update stats on zone record (total claims and revisits)
                existing.total_zone_claims += 1
                existing.total_zone_revisits += 1
                existing.latest_claim_id = claim.claim_id
                existing.unique_zone_runners = len(unique_runners)
                existing.updated_at = timestamp
                updated_zones_dict[cell] = existing

            processed_claims.append(claim)

        return processed_claims, list(updated_zones_dict.values()), feed_events

    def reset(self) -> None:
        """Clear all in-memory ownership caches."""
        self._current_ownership.clear()
        self._cell_runners.clear()
        self._seen_claims.clear()
