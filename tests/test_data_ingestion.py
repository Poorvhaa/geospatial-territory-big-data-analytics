"""Unit tests for PySpark data ingestion module (Day 2)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from pyspark.sql import SparkSession

from src.data_ingestion import (
    GPS_RAW_SCHEMA,
    get_ingestion_statistics,
    load_gps_data,
    validate_schema_columns,
)
from src.spark_session import get_spark_session, stop_spark_session


@pytest.fixture(scope="module")
def spark() -> SparkSession:
    session = get_spark_session(app_name="TestIngestion")
    yield session
    stop_spark_session(session)


def test_schema_columns_validation(spark: SparkSession) -> None:
    # Valid dataframe with all columns
    valid_cols = ["run_id", "runner_id", "timestamp", "latitude", "longitude"]
    df_valid = spark.createDataFrame([("r1", "u1", "2026-10-26T08:00:00Z", 41.8781, -87.6298)], valid_cols)
    is_valid, missing = validate_schema_columns(df_valid)
    assert is_valid is True
    assert len(missing) == 0

    # Incomplete dataframe
    incomplete_cols = ["run_id", "runner_id"]
    df_incomplete = spark.createDataFrame([("r1", "u1")], incomplete_cols)
    is_valid, missing = validate_schema_columns(df_incomplete)
    assert is_valid is False
    assert "timestamp" in missing
    assert "latitude" in missing


def test_load_gps_data_and_timestamp_parsing(spark: SparkSession, tmp_path: Path) -> None:
    csv_file = tmp_path / "test_sample.csv"
    csv_content = (
        "run_id,runner_id,timestamp,latitude,longitude,heart_rate,cadence,elevation_m,distance_m,device_type,activity_type,scenario_type\n"
        "run_001,runner_A,2026-10-26T08:00:00Z,41.8781,-87.6298,140,165,181.0,0.0,Garmin,running,normal_run\n"
        "run_001,runner_A,2026-10-26T08:00:05Z,41.8782,-87.6297,142,166,181.2,12.5,Garmin,running,normal_run\n"
    )
    csv_file.write_text(csv_content, encoding="utf-8")

    df = load_gps_data(spark, csv_file)
    assert df.count() == 2

    # Check that timestamp is parsed as TimestampType and timestamp_epoch is double
    dtypes = dict(df.dtypes)
    assert dtypes["timestamp"] == "timestamp"
    assert dtypes["timestamp_epoch"] == "double"
    assert "raw_timestamp" in dtypes

    stats = get_ingestion_statistics(df)
    assert stats["total_records"] == 2
    assert stats["null_counts"]["run_id"] == 0
