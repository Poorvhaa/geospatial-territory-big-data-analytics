"""Unit tests for PySpark data cleaning and kinematic calculations (Day 2)."""

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
    TimestampType,
)

from src.data_cleaning import clean_gps_data, compute_haversine_distance_col
from src.geo_utils import haversine_distance_m
from src.spark_session import get_spark_session, stop_spark_session


@pytest.fixture(scope="module")
def spark() -> SparkSession:
    session = get_spark_session(app_name="TestCleaning")
    yield session
    stop_spark_session(session)


def test_haversine_column_expression_matches_reference(spark: SparkSession) -> None:
    # Compare PySpark SQL Haversine with pure python reference haversine_distance_m
    test_rows = [
        (41.8781, -87.6298, 41.8826, -87.6226),
        (41.8781, -87.6298, 41.8781, -87.6298),
        (0.0, 0.0, 1.0, 0.0),
    ]
    df = spark.createDataFrame(test_rows, ["lat1", "lon1", "lat2", "lon2"])
    res_df = df.withColumn("dist", compute_haversine_distance_col("lat1", "lon1", "lat2", "lon2"))
    spark_dists = [r["dist"] for r in res_df.collect()]

    for i, (lat1, lon1, lat2, lon2) in enumerate(test_rows):
        ref_dist = haversine_distance_m(lat1, lon1, lat2, lon2)
        assert abs(spark_dists[i] - ref_dist) < 0.1, f"Spark dist {spark_dists[i]} != ref {ref_dist}"


def test_invalid_coordinates_and_duplicates_quarantined(spark: SparkSession) -> None:
    # Test dataset containing:
    # 1 valid point
    # 1 out of bounds lat (100.0)
    # 1 out of bounds lon (200.0)
    # 1 duplicate timestamp
    data = [
        ("run_01", "u1", "2026-10-26T08:00:00Z", 41.8781, -87.6298, 1729929600.0),
        ("run_01", "u1", "2026-10-26T08:00:05Z", 100.0, -87.6298, 1729929605.0),    # invalid lat
        ("run_01", "u1", "2026-10-26T08:00:10Z", 41.8781, 200.0, 1729929610.0),     # invalid lon
        ("run_01", "u1", "2026-10-26T08:00:15Z", 41.8782, -87.6297, 1729929615.0),
        ("run_01", "u1", "2026-10-26T08:00:15Z", 41.8782, -87.6297, 1729929615.0), # duplicate
    ]
    schema = StructType([
        StructField("run_id", StringType(), True),
        StructField("runner_id", StringType(), True),
        StructField("raw_timestamp", StringType(), True),
        StructField("latitude", DoubleType(), True),
        StructField("longitude", DoubleType(), True),
        StructField("timestamp_epoch", DoubleType(), True),
    ])

    df = spark.createDataFrame(data, schema).withColumn(
        "timestamp", F.to_timestamp(F.col("raw_timestamp"))
    )

    cleaned_df, quarantined_df, report = clean_gps_data(df)

    assert quarantined_df.count() == 3
    assert cleaned_df.count() == 2

    # Verify rejection reasons exist
    reasons = [r["rejection_reason"] for r in quarantined_df.collect()]
    assert "OUT_OF_BOUNDS_COORDINATE" in reasons
    assert "DUPLICATE_TIMESTAMP_IN_RUN" in reasons


def test_speed_and_acceleration_kinematics(spark: SparkSession) -> None:
    # 3 sequential points 10 seconds apart moving ~100m north
    # Point 0: 0m, 0s
    # Point 1: ~111m north, 10s -> speed ~11.1 m/s (40 km/h)
    # Point 2: another ~222m north, 10s -> speed ~22.2 m/s (80 km/h) -> acceleration ~ 1.11 m/s^2
    lat0 = 41.8781
    lon0 = -87.6298
    lat1 = lat0 + 0.001  # ~111 meters
    lat2 = lat1 + 0.002  # ~222 meters

    data = [
        ("run_k", "runner_1", "2026-10-26T08:00:00Z", lat0, lon0, 1000.0),
        ("run_k", "runner_1", "2026-10-26T08:00:10Z", lat1, lon0, 1010.0),
        ("run_k", "runner_1", "2026-10-26T08:00:20Z", lat2, lon0, 1020.0),
    ]
    schema = StructType([
        StructField("run_id", StringType(), True),
        StructField("runner_id", StringType(), True),
        StructField("raw_timestamp", StringType(), True),
        StructField("latitude", DoubleType(), True),
        StructField("longitude", DoubleType(), True),
        StructField("timestamp_epoch", DoubleType(), True),
    ])

    df = spark.createDataFrame(data, schema).withColumn(
        "timestamp", F.to_timestamp(F.col("raw_timestamp"))
    )

    cleaned_df, quarantined_df, report = clean_gps_data(df)
    assert cleaned_df.count() == 3

    rows = cleaned_df.orderBy("timestamp_epoch").collect()

    # First point
    assert rows[0]["observed_step_dist_m"] == 0.0
    assert rows[0]["speed_kmh"] == 0.0
    assert rows[0]["acceleration_mps2"] == 0.0

    # Second point
    assert rows[1]["observed_step_dist_m"] > 100.0
    assert rows[1]["speed_kmh"] > 35.0
    assert rows[1]["speed_mps"] > 10.0

    # Third point: accelerated further
    assert rows[2]["observed_step_dist_m"] > 200.0
    assert rows[2]["speed_kmh"] > rows[1]["speed_kmh"]
    assert rows[2]["acceleration_mps2"] > 0.0
