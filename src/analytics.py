"""Analytics and Leaderboard Generation Engine for Geospatial Big Data.

Computes distributed aggregations across territory conquests, zone activity,
cheating diagnostics, and data quality summaries using Apache PySpark.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

logger = logging.getLogger(__name__)


def generate_current_leaderboard(current_ownership_df: DataFrame) -> DataFrame:
    """Rank runners by total H3 zones currently owned."""
    leaderboard = (
        current_ownership_df.groupBy("current_owner_id")
        .agg(F.count("h3_cell").alias("zones_owned"))
        .withColumnRenamed("current_owner_id", "runner_id")
    )

    rank_window = Window.orderBy(F.col("zones_owned").desc(), F.col("runner_id").asc())
    ranked_leaderboard = leaderboard.withColumn("rank", F.dense_rank().over(rank_window))

    return ranked_leaderboard


def generate_capture_leaderboard(ownership_history_df: DataFrame) -> DataFrame:
    """Rank runners by total successful captures (initial captures + takeovers)."""
    captures_only = ownership_history_df.filter(
        F.col("event_type").isin(["INITIAL_CAPTURE", "TAKEOVER"])
    )

    runner_captures = captures_only.groupBy("runner_id").agg(
        F.count("*").alias("total_captures"),
        F.sum(F.when(F.col("event_type") == "INITIAL_CAPTURE", 1).otherwise(0)).alias("initial_captures"),
        F.sum(F.when(F.col("event_type") == "TAKEOVER", 1).otherwise(0)).alias("takeovers"),
    )

    rank_window = Window.orderBy(F.col("total_captures").desc(), F.col("runner_id").asc())
    ranked_captures = runner_captures.withColumn("rank", F.dense_rank().over(rank_window))

    return ranked_captures


def generate_most_contested_zones(
    ownership_history_df: DataFrame,
    top_n: Optional[int] = None,
) -> DataFrame:
    """Rank H3 cells by number of ownership takeovers."""
    zone_contests = ownership_history_df.groupBy("h3_cell").agg(
        F.sum(F.when(F.col("event_type") == "TAKEOVER", 1).otherwise(0)).alias("takeover_count"),
        F.countDistinct("runner_id").alias("unique_runners"),
        F.count("*").alias("total_claims"),
    )

    rank_window = Window.orderBy(
        F.col("takeover_count").desc(),
        F.col("unique_runners").desc(),
        F.col("total_claims").desc(),
        F.col("h3_cell").asc()
    )

    ranked_zones = zone_contests.withColumn("contest_rank", F.dense_rank().over(rank_window))

    if top_n is not None and top_n > 0:
        return ranked_zones.filter(F.col("contest_rank") <= top_n)
    return ranked_zones


def generate_zone_activity_analysis(ownership_history_df: DataFrame) -> DataFrame:
    """Compute comprehensive visit dynamics and activity timeline per H3 zone."""
    activity = ownership_history_df.groupBy("h3_cell").agg(
        F.count("*").alias("total_visits"),
        F.countDistinct("runner_id").alias("unique_runners"),
        F.countDistinct("run_id").alias("unique_runs"),
        F.min("claim_timestamp").alias("first_visit_time"),
        F.max("claim_timestamp").alias("latest_visit_time"),
    )
    return activity


def generate_cheating_report(
    run_risk_df: DataFrame,
    evaluation_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate summary of detected anomalies, risk categories, and cheating stats."""
    total_runs = run_risk_df.count()

    risk_counts_rows = run_risk_df.groupBy("risk_category").count().collect()
    risk_counts = {r["risk_category"]: r["count"] for r in risk_counts_rows}

    # Reasons breakdown
    reasons_rows = (
        run_risk_df.withColumn("reason", F.explode(F.split("anomaly_reasons", ",")))
        .groupBy("reason")
        .count()
        .collect()
    )
    reasons_counts = {r["reason"]: r["count"] for r in reasons_rows}

    # Anomaly point totals
    metric_aggs = run_risk_df.select(
        F.sum("teleport_points").alias("total_teleport_points"),
        F.sum("driving_points").alias("total_driving_points"),
        F.sum("impossible_speed_points").alias("total_impossible_speed_points"),
        F.sum("abnormal_accel_points").alias("total_abnormal_accel_points"),
        F.sum("noise_points").alias("total_noise_points"),
    ).collect()[0]

    report = {
        "total_runs_analyzed": total_runs,
        "risk_category_counts": risk_counts,
        "risk_category_percentages": {
            k: round(v / total_runs * 100.0, 2) if total_runs > 0 else 0.0
            for k, v in risk_counts.items()
        },
        "anomaly_reason_counts": reasons_counts,
        "anomaly_point_totals": {
            "teleport_points": int(metric_aggs["total_teleport_points"] or 0),
            "driving_points": int(metric_aggs["total_driving_points"] or 0),
            "impossible_speed_points": int(metric_aggs["total_impossible_speed_points"] or 0),
            "abnormal_accel_points": int(metric_aggs["total_abnormal_accel_points"] or 0),
            "noise_points": int(metric_aggs["total_noise_points"] or 0),
        },
        "evaluation_metrics": evaluation_metrics or {},
    }
    return report


def generate_runner_activity_summary(
    cleaned_df: DataFrame,
    eligible_points_df: DataFrame,
    quarantined_df: DataFrame,
) -> Dict[str, Any]:
    """Compute aggregate runner activity summary across all processed points."""
    accepted_points = eligible_points_df.count()
    rejected_points = quarantined_df.count()
    total_valid_cleaned = cleaned_df.count()

    active_runners = eligible_points_df.select("runner_id").distinct().count()
    valid_runs = eligible_points_df.select("run_id").distinct().count()

    # Sum estimated distance across eligible points
    dist_row = eligible_points_df.select(
        F.sum("observed_step_dist_m").alias("total_dist_m")
    ).collect()[0]
    total_dist_km = round((dist_row["total_dist_m"] or 0.0) / 1000.0, 2)

    return {
        "active_runners": active_runners,
        "valid_runs": valid_runs,
        "accepted_gps_points": accepted_points,
        "rejected_gps_points": rejected_points,
        "total_valid_cleaned_points": total_valid_cleaned,
        "total_distance_km": total_dist_km,
    }


def generate_data_quality_summary(
    quality_report: Dict[str, Any],
    eligible_points_df: DataFrame,
    rejected_runs_df: DataFrame,
) -> Dict[str, Any]:
    """Compile comprehensive data quality audit across the entire pipeline."""
    return {
        "raw_records": quality_report.get("total_raw_records", 0),
        "valid_records": quality_report.get("valid_records", 0),
        "quarantined_records": quality_report.get("quarantined_records", 0),
        "eligible_points": eligible_points_df.count(),
        "rejected_runs": rejected_runs_df.count(),
        "quarantine_reasons": quality_report.get("rejection_breakdown", {}),
    }
