"""PySpark Data Cleaning Module for Geospatial GPS Big Data.

Performs distributed data quality validation, null/duplicate/anomaly filtering,
quarantine segregation with rejection reasons, and Spark Window-based Haversine
distance, speed, and acceleration calculations.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    StringType,
)

logger = logging.getLogger(__name__)

EARTH_RADIUS_M = 6371000.0


def compute_haversine_distance_col(
    lat1_col: str,
    lon1_col: str,
    lat2_col: str,
    lon2_col: str,
) -> F.Column:
    """Return a PySpark Column expression computing Haversine distance in meters.

    Executes entirely in native Spark SQL (JVM) without Python UDF overhead.
    """
    phi1 = F.radians(F.col(lat1_col))
    phi2 = F.radians(F.col(lat2_col))
    delta_phi = F.radians(F.col(lat2_col) - F.col(lat1_col))
    delta_lambda = F.radians(F.col(lon2_col) - F.col(lon1_col))

    # a = sin^2(delta_phi/2) + cos(phi1) * cos(phi2) * sin^2(delta_lambda/2)
    a = (
        F.pow(F.sin(delta_phi / 2.0), 2)
        + F.cos(phi1) * F.cos(phi2) * F.pow(F.sin(delta_lambda / 2.0), 2)
    )

    # Clip a to [0.0, 1.0] to safeguard against numerical rounding errors in floating point
    clipped_a = F.when(a > 1.0, 1.0).when(a < 0.0, 0.0).otherwise(a)
    c = 2.0 * F.atan2(F.sqrt(clipped_a), F.sqrt(1.0 - clipped_a))

    return F.when(
        F.col(lat1_col).isNull() | F.col(lat2_col).isNull(),
        F.lit(0.0)
    ).otherwise(F.lit(EARTH_RADIUS_M) * c)


def flag_structural_errors(df: DataFrame) -> DataFrame:
    """Identify null, NaN, out-of-bounds, and duplicate records with rejection reasons."""
    # Check null required columns
    is_null_core = (
        F.col("run_id").isNull()
        | F.col("runner_id").isNull()
        | F.col("timestamp").isNull()
        | F.col("latitude").isNull()
        | F.col("longitude").isNull()
    )

    # Check NaN / non-finite coordinates
    is_nan_coord = (
        F.isnan(F.col("latitude"))
        | F.isnan(F.col("longitude"))
    )

    # Check valid coordinate ranges [-90, 90] and [-180, 180]
    is_invalid_coord = (
        (F.col("latitude") < -90.0)
        | (F.col("latitude") > 90.0)
        | (F.col("longitude") < -180.0)
        | (F.col("longitude") > 180.0)
    )

    # Check duplicate records: multiple rows with identical (run_id, timestamp)
    dup_window = Window.partitionBy("run_id", "timestamp").orderBy("run_id")
    df_with_dup = df.withColumn("_row_num_dup", F.row_number().over(dup_window))
    is_duplicate = F.col("_row_num_dup") > 1

    # Assign rejection reason hierarchically
    flagged = df_with_dup.withColumn(
        "rejection_reason",
        F.when(is_null_core, F.lit("NULL_REQUIRED_FIELD"))
        .when(is_nan_coord, F.lit("NON_FINITE_COORDINATE"))
        .when(is_invalid_coord, F.lit("OUT_OF_BOUNDS_COORDINATE"))
        .when(is_duplicate, F.lit("DUPLICATE_TIMESTAMP_IN_RUN"))
        .otherwise(F.lit(None).cast(StringType()))
    ).drop("_row_num_dup")

    return flagged


def clean_gps_data(
    df: DataFrame,
    min_time_diff_s: float = 0.0,
    max_time_diff_s: float = 3600.0,
) -> Tuple[DataFrame, DataFrame, Dict[str, Any]]:
    """Clean raw GPS dataset and calculate movement dynamics (distance, speed, acceleration).

    Args:
        df: Ingested PySpark DataFrame with parsed timestamps.
        min_time_diff_s: Minimum acceptable time delta between consecutive points (default 0.0s).
        max_time_diff_s: Maximum acceptable time delta between consecutive points (default 3600.0s).

    Returns:
        Tuple of:
            cleaned_df: Valid DataFrame enriched with distance, speed, and acceleration.
            quarantined_df: DataFrame containing rejected records and reasons.
            quality_report: Summary dictionary of cleaning metrics.
    """
    total_raw = df.count()

    # Step 1: Structural error identification
    flagged_df = flag_structural_errors(df)

    quarantined_stage1 = flagged_df.filter(F.col("rejection_reason").isNotNull())
    candidates_stage1 = flagged_df.filter(F.col("rejection_reason").isNull()).drop("rejection_reason")

    # Step 2: Time-sequence and Window operations
    # Order points strictly by run_id and timestamp
    run_window = Window.partitionBy("run_id").orderBy("timestamp_epoch")

    with_lag = (
        candidates_stage1
        .withColumn("prev_lat", F.lag("latitude", 1).over(run_window))
        .withColumn("prev_lon", F.lag("longitude", 1).over(run_window))
        .withColumn("prev_ts_epoch", F.lag("timestamp_epoch", 1).over(run_window))
        .withColumn(
            "time_diff_s",
            F.when(F.col("prev_ts_epoch").isNull(), F.lit(0.0)).otherwise(
                F.col("timestamp_epoch") - F.col("prev_ts_epoch")
            )
        )
    )

    # Validate temporal sequence: consecutive points within a run must have time_diff_s > 0 (except first point where prev is null)
    has_temporal_fault = (
        F.col("prev_ts_epoch").isNotNull()
        & (
            (F.col("time_diff_s") <= min_time_diff_s)
            | (F.col("time_diff_s") > max_time_diff_s)
        )
    )

    stage2_flagged = with_lag.withColumn(
        "rejection_reason",
        F.when(
            F.col("prev_ts_epoch").isNotNull() & (F.col("time_diff_s") <= min_time_diff_s),
            F.lit("NON_INCREASING_TIMESTAMP")
        ).when(
            F.col("prev_ts_epoch").isNotNull() & (F.col("time_diff_s") > max_time_diff_s),
            F.lit("EXCESSIVE_TIME_GAP")
        ).otherwise(F.lit(None).cast(StringType()))
    )

    quarantined_stage2 = stage2_flagged.filter(F.col("rejection_reason").isNotNull()).select(
        *[c for c in quarantined_stage1.columns if c in stage2_flagged.columns]
    )

    # Union all quarantined records
    quarantined_df = quarantined_stage1.unionByName(quarantined_stage2, allowMissingColumns=True)

    # Valid candidates for movement calculation
    valid_points = stage2_flagged.filter(F.col("rejection_reason").isNull()).drop("rejection_reason")

    # Re-evaluate lag on strictly clean sequence to guarantee continuous kinematic metrics
    clean_window = Window.partitionBy("run_id").orderBy("timestamp_epoch")

    with_clean_lags = (
        valid_points
        .withColumn("prev_lat", F.lag("latitude", 1).over(clean_window))
        .withColumn("prev_lon", F.lag("longitude", 1).over(clean_window))
        .withColumn("prev_ts_epoch", F.lag("timestamp_epoch", 1).over(clean_window))
        .withColumn(
            "time_diff_s",
            F.when(F.col("prev_ts_epoch").isNull(), F.lit(0.0)).otherwise(
                F.col("timestamp_epoch") - F.col("prev_ts_epoch")
            )
        )
    )

    # Step 3: Compute observed distance using Haversine formula
    with_distance = with_clean_lags.withColumn(
        "observed_step_dist_m",
        F.when(F.col("prev_lat").isNull(), F.lit(0.0)).otherwise(
            compute_haversine_distance_col("prev_lat", "prev_lon", "latitude", "longitude")
        )
    )

    # Compute observed cumulative distance
    cum_window = Window.partitionBy("run_id").orderBy("timestamp_epoch").rowsBetween(
        Window.unboundedPreceding, Window.currentRow
    )
    with_cum_dist = with_distance.withColumn(
        "observed_cum_dist_m",
        F.sum("observed_step_dist_m").over(cum_window)
    )

    # Step 4: Compute speed (m/s and km/h)
    with_speed = (
        with_cum_dist
        .withColumn(
            "speed_mps",
            F.when(
                (F.col("time_diff_s") > 0.0) & (F.col("prev_ts_epoch").isNotNull()),
                F.col("observed_step_dist_m") / F.col("time_diff_s")
            ).otherwise(F.lit(0.0))
        )
        .withColumn(
            "speed_kmh",
            F.col("speed_mps") * 3.6
        )
    )

    # Step 5: Compute acceleration (m/s^2)
    with_speed_lag = with_speed.withColumn(
        "prev_speed_mps",
        F.lag("speed_mps", 1).over(clean_window)
    )

    cleaned_df = with_speed_lag.withColumn(
        "acceleration_mps2",
        F.when(
            (F.col("time_diff_s") > 0.0) & (F.col("prev_speed_mps").isNotNull()),
            (F.col("speed_mps") - F.col("prev_speed_mps")) / F.col("time_diff_s")
        ).otherwise(F.lit(0.0))
    )

    # Drop temporary calculation columns that are no longer needed
    cleaned_df = cleaned_df.drop("prev_ts_epoch", "prev_speed_mps")

    # Generate cleaning summary report
    valid_count = cleaned_df.count()
    quarantined_count = quarantined_df.count()

    reasons_breakdown = {}
    if quarantined_count > 0:
        reasons_rows = quarantined_df.groupBy("rejection_reason").count().collect()
        reasons_breakdown = {r["rejection_reason"]: r["count"] for r in reasons_rows}

    quality_report = {
        "total_raw_records": total_raw,
        "valid_records": valid_count,
        "quarantined_records": quarantined_count,
        "rejection_breakdown": reasons_breakdown,
        "valid_rate_percent": round((valid_count / total_raw * 100.0), 2) if total_raw > 0 else 0.0,
    }

    logger.info(
        f"Data Cleaning Completed: {valid_count} valid ({quality_report['valid_rate_percent']}%), "
        f"{quarantined_count} quarantined"
    )

    return cleaned_df, quarantined_df, quality_report
