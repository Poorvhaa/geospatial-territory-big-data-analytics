"""Territory Ownership Engine for Geospatial Big Data Analytics.

Implements competitive hexagonal zone conquest logic using distributed PySpark:
- Contiguous zone visit segmentation with re-entry support
- Minimum consecutive observation threshold filtering
- Deterministic chronological tie-breaking
- Window-based ownership transition tracking (INITIAL_CAPTURE, TAKEOVER, SAME_OWNER_REVISIT)
- Current state snapshot generation
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql.types import (
    BooleanType,
    IntegerType,
    StringType,
)

logger = logging.getLogger(__name__)

DEFAULT_MIN_CONSECUTIVE_OBSERVATIONS = 2


def generate_zone_visits(
    eligible_h3_df: DataFrame,
    min_consecutive_points: int = DEFAULT_MIN_CONSECUTIVE_OBSERVATIONS,
) -> DataFrame:
    """Segment consecutive GPS observations into discrete H3 zone visits.

    A new visit begins when a run enters a new H3 cell or re-enters a previously
    visited cell after traversing other cells. Requisite consecutive observations
    are validated before confirming each visit.

    Args:
        eligible_h3_df: DataFrame containing eligible GPS points with 'h3_cell'.
        min_consecutive_points: Minimum consecutive points in a zone to confirm claim (default 2).

    Returns:
        DataFrame of confirmed zone claims with claim_id, h3_cell, runner_id, run_id, and claim_timestamp.
    """
    logger.info(
        f"Generating zone visits (min_consecutive_observations={min_consecutive_points})..."
    )

    # Filter out invalid or null H3 cells
    valid_points = eligible_h3_df.filter(
        F.col("h3_cell").isNotNull()
        & (F.col("is_valid_h3") == True)  # noqa: E712
    )

    # 1. Detect cell transitions within each run
    run_window = Window.partitionBy("run_id").orderBy("timestamp_epoch")

    with_prev_cell = valid_points.withColumn(
        "prev_cell",
        F.lag("h3_cell", 1).over(run_window)
    )

    # Transition occurs if this is the first point or cell differs from previous point
    with_transitions = with_prev_cell.withColumn(
        "is_cell_transition",
        F.when(
            F.col("prev_cell").isNull() | (F.col("h3_cell") != F.col("prev_cell")),
            F.lit(1)
        ).otherwise(F.lit(0))
    )

    # Running sum of transitions generates a unique visit_idx per contiguous cell stay
    with_visit_idx = with_transitions.withColumn(
        "visit_idx",
        F.sum("is_cell_transition").over(
            run_window.rowsBetween(Window.unboundedPreceding, Window.currentRow)
        )
    )

    # 2. Count consecutive points in each contiguous visit
    visit_window = Window.partitionBy("run_id", "visit_idx")

    with_visit_counts = (
        with_visit_idx
        .withColumn("points_in_visit", F.count("*").over(visit_window))
        .withColumn("point_rank_in_visit", F.row_number().over(visit_window.orderBy("timestamp_epoch")))
    )

    # 3. Filter to confirmed visits satisfying the minimum consecutive observations rule
    # And select the confirming point (point_rank == min_consecutive_points) or first point if min == 1
    target_rank = max(1, min_consecutive_points)

    confirmed_visits = with_visit_counts.filter(
        (F.col("points_in_visit") >= min_consecutive_points)
        & (F.col("point_rank_in_visit") == target_rank)
    )

    # 4. Form deterministic claim identifiers and schema
    claims_df = confirmed_visits.select(
        F.concat(
            F.col("run_id"),
            F.lit("_v"),
            F.col("visit_idx"),
            F.lit("_"),
            F.col("h3_cell")
        ).alias("claim_id"),
        F.col("h3_cell"),
        F.col("runner_id"),
        F.col("run_id"),
        F.col("timestamp").alias("claim_timestamp"),
        F.col("timestamp_epoch").alias("claim_timestamp_epoch"),
        F.col("points_in_visit"),
    )

    return claims_df


def process_territory_ownership(
    claims_df: DataFrame,
) -> Tuple[DataFrame, DataFrame, Dict[str, Any]]:
    """Compute chronological territory conquest history and current ownership state.

    Uses deterministic window ordering over each H3 cell across all runs:
    - INITIAL_CAPTURE: First time any runner claims the cell.
    - TAKEOVER: Runner claims a cell previously held by a DIFFERENT runner.
    - SAME_OWNER_REVISIT: Current owner visits the cell again (not a takeover).

    Args:
        claims_df: Confirmed claim events.

    Returns:
        Tuple of:
            ownership_history_df: Complete sequential audit log of all claims with transition types.
            current_ownership_df: Snapshot of the latest owner for each H3 cell.
            ownership_metrics: Summary metrics dictionary.
    """
    logger.info("Computing territory ownership transitions and current state...")

    # Deterministic chronological ordering across all claims per H3 cell
    # Secondary order keys prevent non-deterministic sorting on identical timestamps
    cell_window = Window.partitionBy("h3_cell").orderBy(
        F.col("claim_timestamp_epoch").asc(),
        F.col("run_id").asc(),
        F.col("runner_id").asc(),
        F.col("claim_id").asc()
    )

    with_lags = (
        claims_df
        .withColumn("prev_runner_id", F.lag("runner_id", 1).over(cell_window))
        .withColumn("prev_claim_timestamp", F.lag("claim_timestamp", 1).over(cell_window))
        .withColumn("claim_sequence", F.row_number().over(cell_window))
    )

    # Classify claim transition event types
    ownership_history_df = with_lags.withColumn(
        "event_type",
        F.when(
            F.col("prev_runner_id").isNull(),
            F.lit("INITIAL_CAPTURE")
        ).when(
            F.col("prev_runner_id") != F.col("runner_id"),
            F.lit("TAKEOVER")
        ).otherwise(
            F.lit("SAME_OWNER_REVISIT")
        )
    ).withColumn(
        "is_ownership_change",
        F.col("event_type").isin(["INITIAL_CAPTURE", "TAKEOVER"])
    ).withColumn(
        "is_takeover",
        F.col("event_type") == "TAKEOVER"
    ).withColumn(
        "is_same_owner_revisit",
        F.col("event_type") == "SAME_OWNER_REVISIT"
    )

    # Step 2: Compute current ownership snapshot
    # Latest claim in each cell dictates current ownership
    latest_window = Window.partitionBy("h3_cell").orderBy(
        F.col("claim_timestamp_epoch").desc(),
        F.col("run_id").desc(),
        F.col("runner_id").desc(),
        F.col("claim_id").desc()
    )

    # Compute aggregate stats per zone across entire history
    zone_stats_window = Window.partitionBy("h3_cell")

    history_with_stats = (
        ownership_history_df
        .withColumn("total_zone_claims", F.count("*").over(zone_stats_window))
        .withColumn("total_zone_takeovers", F.sum(F.when(F.col("is_takeover"), 1).otherwise(0)).over(zone_stats_window))
        .withColumn("total_zone_revisits", F.sum(F.when(F.col("is_same_owner_revisit"), 1).otherwise(0)).over(zone_stats_window))
        .withColumn("unique_zone_runners", F.size(F.collect_set("runner_id").over(zone_stats_window)))
        .withColumn("_rank_latest", F.row_number().over(latest_window))
    )

    current_ownership_df = (
        history_with_stats.filter(F.col("_rank_latest") == 1)
        .select(
            F.col("h3_cell"),
            F.col("runner_id").alias("current_owner_id"),
            F.col("run_id").alias("acquired_in_run"),
            F.col("claim_timestamp").alias("acquired_at"),
            F.col("claim_id").alias("latest_claim_id"),
            F.col("prev_runner_id").alias("previous_owner_id"),
            F.col("total_zone_claims"),
            F.col("total_zone_takeovers"),
            F.col("total_zone_revisits"),
            F.col("unique_zone_runners"),
        )
    )

    # Summary metrics
    total_claims = ownership_history_df.count()
    total_zones = current_ownership_df.count()

    event_counts_rows = ownership_history_df.groupBy("event_type").count().collect()
    event_counts = {r["event_type"]: r["count"] for r in event_counts_rows}

    initial_captures = event_counts.get("INITIAL_CAPTURE", 0)
    takeovers = event_counts.get("TAKEOVER", 0)
    revisits = event_counts.get("SAME_OWNER_REVISIT", 0)

    ownership_metrics = {
        "total_claims": total_claims,
        "total_unique_zones": total_zones,
        "initial_captures": initial_captures,
        "takeovers": takeovers,
        "same_owner_revisits": revisits,
        "total_ownership_changes": initial_captures + takeovers,
    }

    logger.info(
        f"Territory Engine: {total_zones} active zones, {initial_captures} initial captures, "
        f"{takeovers} takeovers, {revisits} revisits"
    )

    return ownership_history_df, current_ownership_df, ownership_metrics
