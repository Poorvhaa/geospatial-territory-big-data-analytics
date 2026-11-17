"""Unit tests for GPS cheat detection, fraud scoring, and eligibility filtering (Day 2)."""

from __future__ import annotations

import pytest
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

from src.cheat_detection import (
    compute_run_risk_scores,
    detect_point_anomalies,
    evaluate_detection_performance,
    filter_eligible_points,
)
from src.spark_session import get_spark_session, stop_spark_session


@pytest.fixture(scope="module")
def spark() -> SparkSession:
    session = get_spark_session(app_name="TestCheating")
    yield session
    stop_spark_session(session)


def create_point_df(spark: SparkSession, rows: list) -> any:
    schema = StructType([
        StructField("run_id", StringType(), False),
        StructField("runner_id", StringType(), False),
        StructField("timestamp_epoch", DoubleType(), False),
        StructField("latitude", DoubleType(), False),
        StructField("longitude", DoubleType(), False),
        StructField("speed_kmh", DoubleType(), False),
        StructField("acceleration_mps2", DoubleType(), False),
        StructField("observed_step_dist_m", DoubleType(), False),
        StructField("observed_cum_dist_m", DoubleType(), False),
        StructField("cadence", IntegerType(), True),
        StructField("scenario_type", StringType(), True),
    ])
    return spark.createDataFrame(rows, schema)


def test_normal_runner_and_fast_runner_accepted(spark: SparkSession) -> None:
    # Normal runner (speed ~8-10 km/h, cadence ~160)
    normal_rows = [
        ("run_norm", "runner_A", 1000.0, 41.8781, -87.6298, 8.5, 0.2, 11.8, 11.8, 160, "normal_run"),
        ("run_norm", "runner_A", 1005.0, 41.8782, -87.6298, 9.0, 0.1, 12.5, 24.3, 162, "normal_run"),
        ("run_norm", "runner_A", 1010.0, 41.8783, -87.6298, 8.8, -0.1, 12.2, 36.5, 160, "normal_run"),
        ("run_norm", "runner_A", 1015.0, 41.8784, -87.6298, 9.2, 0.2, 12.8, 49.3, 164, "normal_run"),
    ]
    # Fast runner (speed ~16-19 km/h, cadence ~180 - legitimate runner below 25 km/h limit)
    fast_rows = [
        ("run_fast", "runner_B", 1000.0, 41.8781, -87.6298, 17.5, 0.3, 24.3, 24.3, 180, "fast_run"),
        ("run_fast", "runner_B", 1005.0, 41.8783, -87.6298, 18.0, 0.1, 25.0, 49.3, 182, "fast_run"),
        ("run_fast", "runner_B", 1010.0, 41.8785, -87.6298, 18.2, 0.1, 25.3, 74.6, 182, "fast_run"),
        ("run_fast", "runner_B", 1015.0, 41.8787, -87.6298, 17.9, -0.1, 24.9, 99.5, 180, "fast_run"),
    ]

    df = create_point_df(spark, normal_rows + fast_rows)
    anomalies_df = detect_point_anomalies(df)
    risk_df = compute_run_risk_scores(anomalies_df)

    risks = {r["run_id"]: r.asDict() for r in risk_df.collect()}

    # Both must be classified as NORMAL
    assert risks["run_norm"]["risk_category"] == "NORMAL"
    assert risks["run_norm"]["fraud_score"] <= 0.29
    assert risks["run_fast"]["risk_category"] == "NORMAL"
    assert risks["run_fast"]["fraud_score"] <= 0.29


def test_teleportation_and_driving_detection(spark: SparkSession) -> None:
    # Teleportation: 600m jump in 5s
    teleport_rows = [
        ("run_tp", "runner_C", 1000.0, 41.8781, -87.6298, 9.0, 0.0, 12.5, 12.5, 160, "gps_spoofing"),
        ("run_tp", "runner_C", 1005.0, 41.8850, -87.6298, 430.0, 25.0, 765.0, 777.5, 160, "gps_spoofing"),
        ("run_tp", "runner_C", 1010.0, 41.8851, -87.6298, 9.2, -24.0, 12.8, 790.3, 160, "gps_spoofing"),
    ]
    # Driving: 5 consecutive points at 50 km/h with low cadence
    driving_rows = [
        ("run_drive", "runner_D", 1000.0, 41.8781, -87.6298, 50.0, 0.0, 69.4, 69.4, 20, "driving"),
        ("run_drive", "runner_D", 1005.0, 41.8787, -87.6298, 52.0, 0.1, 72.2, 141.6, 20, "driving"),
        ("run_drive", "runner_D", 1010.0, 41.8793, -87.6298, 48.0, -0.2, 66.7, 208.3, 15, "driving"),
        ("run_drive", "runner_D", 1015.0, 41.8800, -87.6298, 51.0, 0.2, 70.8, 279.1, 10, "driving"),
    ]

    df = create_point_df(spark, teleport_rows + driving_rows)
    anomalies_df = detect_point_anomalies(df)
    risk_df = compute_run_risk_scores(anomalies_df)

    risks = {r["run_id"]: r.asDict() for r in risk_df.collect()}

    # Teleportation run must be HIGH_RISK or SUSPICIOUS (not NORMAL)
    assert risks["run_tp"]["risk_category"] in ["HIGH_RISK", "SUSPICIOUS"]
    assert risks["run_tp"]["teleport_points"] >= 1
    assert "TELEPORTATION" in risks["run_tp"]["anomaly_reasons"]

    # Driving run must be HIGH_RISK (score >= 0.60)
    assert risks["run_drive"]["risk_category"] == "HIGH_RISK"
    assert risks["run_drive"]["driving_points"] >= 1
    assert "DRIVING" in risks["run_drive"]["anomaly_reasons"]


def test_gps_noise_isolated_spike_does_not_label_fraud(spark: SparkSession) -> None:
    # 5 points: pt 2 jumps by 80m and pt 3 returns back to the normal route
    lat_base = 41.8781
    lon_base = -87.6298
    noise_rows = [
        ("run_noise", "runner_E", 1000.0, lat_base, lon_base, 8.5, 0.0, 11.8, 11.8, 160, "gps_noise"),
        ("run_noise", "runner_E", 1005.0, lat_base + 0.0001, lon_base, 8.8, 0.1, 11.1, 22.9, 160, "gps_noise"),
        # Spike point: offset lat by +0.0008 (~88m)
        ("run_noise", "runner_E", 1010.0, lat_base + 0.0009, lon_base, 65.0, 12.0, 88.0, 110.9, 160, "gps_noise"),
        # Return point: back on track lat_base + 0.0003 (~33m from pt 1)
        ("run_noise", "runner_E", 1015.0, lat_base + 0.0003, lon_base, 8.5, -12.0, 67.0, 177.9, 160, "gps_noise"),
        ("run_noise", "runner_E", 1020.0, lat_base + 0.0004, lon_base, 8.7, 0.0, 11.1, 189.0, 160, "gps_noise"),
    ]

    df = create_point_df(spark, noise_rows)
    anomalies_df = detect_point_anomalies(df)
    risk_df = compute_run_risk_scores(anomalies_df)

    risk_row = risk_df.collect()[0]
    # Isolated noise point detected as noise, not fraud
    assert risk_row["noise_points"] >= 1
    # Fraud score must be low (isolated noise doesn't imply fraud)
    assert risk_row["risk_category"] == "NORMAL"
    assert risk_row["fraud_score"] <= 0.29


def test_fraud_score_range_and_suspicious_exclusion(spark: SparkSession) -> None:
    rows = [
        ("run_clean", "u1", 1000.0, 41.8781, -87.6298, 8.0, 0.0, 11.0, 11.0, 160, "normal_run"),
        ("run_bad", "u2", 1000.0, 41.8781, -87.6298, 90.0, 15.0, 600.0, 600.0, 0, "driving"),
    ]
    df = create_point_df(spark, rows)
    anomalies_df = detect_point_anomalies(df)
    risk_df = compute_run_risk_scores(anomalies_df)

    for r in risk_df.collect():
        score = r["fraud_score"]
        assert 0.0 <= score <= 1.0, f"Score {score} out of [0, 1] bounds"

    eligible_pts, rejected_runs = filter_eligible_points(anomalies_df, risk_df)

    eligible_run_ids = [r["run_id"] for r in eligible_pts.select("run_id").distinct().collect()]
    rejected_run_ids = [r["run_id"] for r in rejected_runs.select("run_id").collect()]

    assert "run_clean" in eligible_run_ids
    assert "run_bad" not in eligible_run_ids
    assert "run_bad" in rejected_run_ids
