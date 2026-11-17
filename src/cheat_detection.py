"""GPS Cheating and Anomaly Detection Module for Geospatial Big Data.

Implements rule-based kinematic anomaly detection across 5 distinct vectors:
1. Impossible Running Speed
2. GPS Teleportation / Large Jumps
3. Sustained Driving Patterns
4. Abnormal Kinematic Acceleration
5. Isolated GPS Multi-Path Noise Spikes

Computes run-level heuristic fraud risk scores (0.0 to 1.0) and filters run eligibility
for downstream territory conquest. Evaluates performance against synthetic ground truth
without using ground truth in detection heuristics.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    StringType,
)

from src.data_cleaning import compute_haversine_distance_col

logger = logging.getLogger(__name__)

# Default heuristic thresholds (overridable via settings.yaml)
DEFAULT_MAX_RUNNING_SPEED_KMH = 25.0
DEFAULT_TELEPORT_JUMP_M = 300.0
DEFAULT_TELEPORT_SPEED_KMH = 80.0
DEFAULT_DRIVING_SPEED_KMH = 25.0
DEFAULT_DRIVING_MIN_CONSECUTIVE = 3
DEFAULT_DRIVING_MAX_CADENCE = 50
DEFAULT_ABNORMAL_ACCEL_MPS2 = 8.0
DEFAULT_NOISE_SPIKE_DIST_M = 50.0
DEFAULT_NOISE_RETURN_DIST_M = 35.0

DEFAULT_NORMAL_MAX = 0.29
DEFAULT_SUSPICIOUS_MAX = 0.59
DEFAULT_HIGH_RISK_MIN = 0.60


def detect_point_anomalies(
    df: DataFrame,
    config: Optional[Dict[str, Any]] = None,
) -> DataFrame:
    """Detect point-level GPS kinematic anomalies using distributed Spark operations.

    Args:
        df: Cleaned PySpark DataFrame with distance, speed, and acceleration.
        config: Optional dictionary containing detection thresholds.

    Returns:
        DataFrame enriched with boolean anomaly flags and chord distances.
    """
    cfg = config or {}
    max_running_speed = float(cfg.get("max_running_speed_kmh", DEFAULT_MAX_RUNNING_SPEED_KMH))
    teleport_jump_m = float(cfg.get("teleport_jump_m", DEFAULT_TELEPORT_JUMP_M))
    teleport_speed_kmh = float(cfg.get("teleport_speed_kmh", DEFAULT_TELEPORT_SPEED_KMH))
    driving_speed_kmh = float(cfg.get("driving_speed_kmh", DEFAULT_DRIVING_SPEED_KMH))
    driving_consecutive = int(cfg.get("driving_min_consecutive_points", DEFAULT_DRIVING_MIN_CONSECUTIVE))
    driving_max_cadence = int(cfg.get("driving_max_cadence", DEFAULT_DRIVING_MAX_CADENCE))
    abnormal_accel_mps2 = float(cfg.get("abnormal_accel_mps2", DEFAULT_ABNORMAL_ACCEL_MPS2))
    noise_spike_dist_m = float(cfg.get("noise_spike_dist_m", DEFAULT_NOISE_SPIKE_DIST_M))
    noise_return_dist_m = float(cfg.get("noise_return_dist_m", DEFAULT_NOISE_RETURN_DIST_M))

    run_window = Window.partitionBy("run_id").orderBy("timestamp_epoch")

    # Lead coordinates to evaluate isolated GPS noise spikes (point i jumped, point i+1 returned)
    with_leads = (
        df
        .withColumn("next_lat", F.lead("latitude", 1).over(run_window))
        .withColumn("next_lon", F.lead("longitude", 1).over(run_window))
        .withColumn("prev_lat", F.lag("latitude", 1).over(run_window))
        .withColumn("prev_lon", F.lag("longitude", 1).over(run_window))
    )

    # Compute chord distance between point (i-1) and point (i+1)
    with_chords = with_leads.withColumn(
        "next_step_dist_m",
        F.when(F.col("next_lat").isNull(), F.lit(0.0)).otherwise(
            compute_haversine_distance_col("latitude", "longitude", "next_lat", "next_lon")
        )
    ).withColumn(
        "prev_to_next_dist_m",
        F.when(F.col("prev_lat").isNull() | F.col("next_lat").isNull(), F.lit(0.0)).otherwise(
            compute_haversine_distance_col("prev_lat", "prev_lon", "next_lat", "next_lon")
        )
    )

    # 1. Detection: Impossible Running Speed
    is_impossible_speed = F.col("speed_kmh") > max_running_speed

    # 2. Detection: GPS Teleportation (massive step jump or extreme instantaneous speed)
    is_teleportation = (
        (F.col("observed_step_dist_m") >= teleport_jump_m)
        | (F.col("speed_kmh") >= teleport_speed_kmh)
    )

    # 3. Detection: Driving Pattern
    # Individual point vehicle speed indicator
    is_vehicle_speed = (
        (F.col("speed_kmh") >= driving_speed_kmh)
        & (
            F.col("cadence").isNull()
            | (F.col("cadence") <= driving_max_cadence)
        )
    )
    with_vehicle_flag = with_chords.withColumn(
        "_vehicle_candidate",
        F.when(is_vehicle_speed, F.lit(1)).otherwise(F.lit(0))
    )

    # Check for sustained consecutive vehicle speed points (sliding window of size driving_consecutive)
    consec_window = run_window.rowsBetween(-(driving_consecutive - 1), 0)
    with_consec_driving = with_vehicle_flag.withColumn(
        "_driving_streak",
        F.sum("_vehicle_candidate").over(consec_window)
    )
    is_driving_pattern = F.col("_driving_streak") >= driving_consecutive

    # 4. Detection: Abnormal Kinematic Acceleration
    is_abnormal_accel = F.abs(F.col("acceleration_mps2")) >= abnormal_accel_mps2

    # 5. Detection: GPS Noise (isolated jump where runner immediately returns to previous path)
    # At noise point: observed_step_dist_m > 50, next_step_dist_m > 50, but chord prev_to_next_dist_m < 35
    is_gps_noise = (
        F.col("prev_lat").isNotNull()
        & F.col("next_lat").isNotNull()
        & (F.col("observed_step_dist_m") >= noise_spike_dist_m)
        & (F.col("next_step_dist_m") >= noise_spike_dist_m)
        & (F.col("prev_to_next_dist_m") <= noise_return_dist_m)
    )

    # Assign boolean anomaly flags
    # Distinguish GPS noise from teleportation: if point is isolated noise, do not flag as teleportation
    point_anomalies_df = (
        with_consec_driving
        .withColumn("flag_noise", is_gps_noise)
        .withColumn("flag_teleportation", is_teleportation & (~is_gps_noise))
        .withColumn("flag_impossible_speed", is_impossible_speed & (~is_gps_noise))
        .withColumn("flag_driving", is_driving_pattern)
        .withColumn("flag_abnormal_accel", is_abnormal_accel)
        .drop("_vehicle_candidate", "_driving_streak", "prev_lat", "prev_lon", "next_lat", "next_lon")
    )

    return point_anomalies_df


def compute_run_risk_scores(
    point_df: DataFrame,
    config: Optional[Dict[str, Any]] = None,
) -> DataFrame:
    """Aggregate point-level anomaly flags into run-level fraud risk scores and risk categories.

    Note: scenario_type is never used to calculate scores or categories.

    Args:
        point_df: DataFrame with point anomaly flags.
        config: Optional dictionary containing weights and threshold settings.

    Returns:
        DataFrame with one record per run containing fraud_score, risk_category, and anomaly reasons.
    """
    cfg = config or {}
    weights = cfg.get("weights", {})
    w_teleport = float(weights.get("teleport", 0.40))
    w_driving = float(weights.get("driving", 0.35))
    w_speed = float(weights.get("impossible_speed", 0.25))
    w_accel = float(weights.get("abnormal_accel", 0.15))
    w_noise = float(weights.get("noise", 0.10))

    thresholds = cfg.get("risk_thresholds", {})
    normal_max = float(thresholds.get("normal_max", DEFAULT_NORMAL_MAX))
    suspicious_max = float(thresholds.get("suspicious_max", DEFAULT_SUSPICIOUS_MAX))
    high_risk_min = float(thresholds.get("high_risk_min", DEFAULT_HIGH_RISK_MIN))

    # Aggregations per run
    run_aggs = point_df.groupBy("run_id").agg(
        F.first("runner_id").alias("runner_id"),
        F.first("scenario_type").alias("scenario_type"),  # preserved for performance evaluation only
        F.count("*").alias("total_points"),
        F.sum(F.when(F.col("flag_teleportation"), 1).otherwise(0)).alias("teleport_points"),
        F.sum(F.when(F.col("flag_driving"), 1).otherwise(0)).alias("driving_points"),
        F.sum(F.when(F.col("flag_impossible_speed"), 1).otherwise(0)).alias("impossible_speed_points"),
        F.sum(F.when(F.col("flag_abnormal_accel"), 1).otherwise(0)).alias("abnormal_accel_points"),
        F.sum(F.when(F.col("flag_noise"), 1).otherwise(0)).alias("noise_points"),
        F.max("speed_kmh").alias("max_speed_kmh"),
        F.avg("speed_kmh").alias("avg_speed_kmh"),
        F.max("observed_cum_dist_m").alias("total_distance_m"),
    )

    # Heuristic Fraud Score Calculation
    # Normalize proportions and apply weighted indicators
    score_expr = (
        # Teleportation penalty: any confirmed teleportation heavily penalizes the run
        F.when(F.col("teleport_points") > 0, F.lit(w_teleport) + (F.col("teleport_points") / F.col("total_points")) * 0.4).otherwise(0.0)
        # Driving penalty: sustained driving points strongly penalize
        + F.when(F.col("driving_points") > 0, F.lit(w_driving) + (F.col("driving_points") / F.col("total_points")) * 0.5).otherwise(0.0)
        # Impossible speed penalty
        + F.when(F.col("impossible_speed_points") > 0, (F.col("impossible_speed_points") / F.col("total_points")) * F.lit(w_speed) * 2.0).otherwise(0.0)
        # Abnormal acceleration penalty
        + F.when(F.col("abnormal_accel_points") > 0, (F.col("abnormal_accel_points") / F.col("total_points")) * F.lit(w_accel)).otherwise(0.0)
        # Isolated GPS noise penalty (kept very low so isolated noise does NOT classify as cheating)
        + F.when(F.col("noise_points") > 0, (F.col("noise_points") / F.col("total_points")) * F.lit(w_noise)).otherwise(0.0)
    )

    with_score = run_aggs.withColumn(
        "raw_fraud_score",
        score_expr
    ).withColumn(
        "fraud_score",
        F.round(
            F.when(F.col("raw_fraud_score") > 1.0, 1.0)
            .when(F.col("raw_fraud_score") < 0.0, 0.0)
            .otherwise(F.col("raw_fraud_score")),
            4
        )
    ).drop("raw_fraud_score")

    # Risk Category Assignment
    with_category = with_score.withColumn(
        "risk_category",
        F.when(F.col("fraud_score") <= normal_max, F.lit("NORMAL"))
        .when(F.col("fraud_score") <= suspicious_max, F.lit("SUSPICIOUS"))
        .otherwise(F.lit("HIGH_RISK"))
    )

    # Anomaly Reasons summary
    reasons_expr = F.concat_ws(
        ",",
        F.when(F.col("teleport_points") > 0, F.lit("TELEPORTATION")),
        F.when(F.col("driving_points") > 0, F.lit("DRIVING")),
        F.when(F.col("impossible_speed_points") > 0, F.lit("IMPOSSIBLE_SPEED")),
        F.when(F.col("abnormal_accel_points") > 0, F.lit("ABNORMAL_ACCELERATION")),
        F.when(F.col("noise_points") > 0, F.lit("GPS_NOISE")),
    )

    with_reasons = with_category.withColumn(
        "anomaly_reasons",
        F.when(F.length(reasons_expr) > 0, reasons_expr).otherwise(F.lit("CLEAN"))
    )

    return with_reasons


def filter_eligible_points(
    point_df: DataFrame,
    run_risk_df: DataFrame,
) -> Tuple[DataFrame, DataFrame]:
    """Filter GPS points, allowing only runs classified as NORMAL to proceed to territory claiming.

    Args:
        point_df: Point-level DataFrame with anomaly flags.
        run_risk_df: Run-level DataFrame with fraud_score and risk_category.

    Returns:
        Tuple of:
            eligible_points_df: Points belonging to NORMAL runs only.
            rejected_runs_df: Runs classified as SUSPICIOUS or HIGH_RISK.
    """
    eligible_runs = run_risk_df.filter(F.col("risk_category") == "NORMAL").select("run_id")
    rejected_runs = run_risk_df.filter(F.col("risk_category") != "NORMAL")

    eligible_points_df = point_df.join(
        eligible_runs,
        on="run_id",
        how="inner"
    )

    return eligible_points_df, rejected_runs


def evaluate_detection_performance(run_risk_df: DataFrame) -> Dict[str, Any]:
    """Evaluate detection metrics against ground truth scenario_type labels.

    Ground truth definitions:
    - Cheating (Positive): 'driving', 'gps_spoofing'
    - Legitimate (Negative): 'normal_run', 'fast_run', 'walking', 'gps_noise'

    Predicted Positive: risk_category in ('SUSPICIOUS', 'HIGH_RISK')
    Predicted Negative: risk_category == 'NORMAL'

    Returns:
        Dictionary containing confusion matrix, precision, recall, and F1 score.
    """
    eval_df = run_risk_df.withColumn(
        "is_actual_cheater",
        F.col("scenario_type").isin(["driving", "gps_spoofing"])
    ).withColumn(
        "is_predicted_cheater",
        F.col("risk_category").isin(["SUSPICIOUS", "HIGH_RISK"])
    )

    # Confusion matrix aggregation
    cm_row = eval_df.select(
        F.count(F.when(F.col("is_actual_cheater") & F.col("is_predicted_cheater"), 1)).alias("tp"),
        F.count(F.when((~F.col("is_actual_cheater")) & F.col("is_predicted_cheater"), 1)).alias("fp"),
        F.count(F.when((~F.col("is_actual_cheater")) & (~F.col("is_predicted_cheater")), 1)).alias("tn"),
        F.count(F.when(F.col("is_actual_cheater") & (~F.col("is_predicted_cheater")), 1)).alias("fn"),
    ).collect()[0]

    tp = int(cm_row["tp"])
    fp = int(cm_row["fp"])
    tn = int(cm_row["tn"])
    fn = int(cm_row["fn"])

    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
    recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
    f1 = round(2.0 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 0.0

    # Breakdown by scenario type
    scenario_breakdown = {}
    scenarios = eval_df.groupBy("scenario_type", "risk_category").count().collect()
    for row in scenarios:
        s_type = row["scenario_type"]
        cat = row["risk_category"]
        cnt = row["count"]
        if s_type not in scenario_breakdown:
            scenario_breakdown[s_type] = {"NORMAL": 0, "SUSPICIOUS": 0, "HIGH_RISK": 0}
        scenario_breakdown[s_type][cat] = cnt

    return {
        "confusion_matrix": {
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn,
            "false_negatives": fn,
        },
        "metrics": {
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "total_runs_evaluated": tp + fp + tn + fn,
        },
        "scenario_risk_distribution": scenario_breakdown,
    }
