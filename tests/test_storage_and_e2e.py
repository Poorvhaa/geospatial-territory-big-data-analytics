"""Unit tests for Parquet storage roundtrip and end-to-end integration (Day 2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pyspark.sql import SparkSession

from src.pipeline import run_pipeline
from src.spark_session import get_spark_session, stop_spark_session
from src.storage import read_parquet, write_parquet


@pytest.fixture(scope="module")
def spark() -> SparkSession:
    session = get_spark_session(app_name="TestStorage")
    yield session
    stop_spark_session(session)


def test_parquet_read_write_roundtrip(spark: SparkSession, tmp_path: Path) -> None:
    data = [
        ("r1", "u1", 41.8781, -87.6298, 10.5),
        ("r2", "u2", 41.8826, -87.6226, 12.0),
    ]
    cols = ["run_id", "runner_id", "latitude", "longitude", "speed_kmh"]
    df = spark.createDataFrame(data, cols)

    target_dir = tmp_path / "parquet_test"
    write_parquet(df, target_dir, mode="overwrite")

    # Read back
    df_read = read_parquet(spark, target_dir)
    assert df_read.count() == 2
    rows = df_read.collect()
    assert rows[0]["runner_id"] in ["u1", "u2"]


def test_pipeline_mini_e2e(tmp_path: Path) -> None:
    # Create small deterministic 10-point CSV dataset
    csv_file = tmp_path / "mini_gps.csv"
    csv_content = (
        "run_id,runner_id,timestamp,latitude,longitude,heart_rate,cadence,elevation_m,distance_m,device_type,activity_type,scenario_type\n"
        "run_001,runner_A,2026-10-26T08:00:00Z,41.8781,-87.6298,140,165,181.0,0.0,Garmin,running,normal_run\n"
        "run_001,runner_A,2026-10-26T08:00:05Z,41.8782,-87.6298,142,165,181.2,11.1,Garmin,running,normal_run\n"
        "run_001,runner_A,2026-10-26T08:00:10Z,41.8783,-87.6298,145,166,181.4,22.2,Garmin,running,normal_run\n"
        "run_002,runner_B,2026-10-26T08:05:00Z,41.8781,-87.6298,150,170,181.0,0.0,Apple,running,fast_run\n"
        "run_002,runner_B,2026-10-26T08:05:05Z,41.8782,-87.6298,152,172,181.2,11.1,Apple,running,fast_run\n"
        "run_002,runner_B,2026-10-26T08:05:10Z,41.8783,-87.6298,155,170,181.4,22.2,Apple,running,fast_run\n"
        "run_003,runner_C,2026-10-26T08:10:00Z,41.8781,-87.6298,80,20,181.0,0.0,Polar,running,driving\n"
        "run_003,runner_C,2026-10-26T08:10:05Z,41.8850,-87.6298,82,15,181.2,767.0,Polar,running,driving\n"
        "run_003,runner_C,2026-10-26T08:10:10Z,41.8920,-87.6298,80,10,181.4,1545.0,Polar,running,driving\n"
        "run_003,runner_C,2026-10-26T08:10:15Z,41.8990,-87.6298,81,12,181.5,2322.0,Polar,running,driving\n"
    )
    csv_file.write_text(csv_content, encoding="utf-8")
    original_mtime = csv_file.stat().st_mtime

    output_dir = tmp_path / "parquet_out"

    res = run_pipeline(
        input_path=csv_file,
        output_parquet_dir=output_dir,
        h3_resolution=9,
        min_consecutive_points=2,
        reports_dir=tmp_path / "reports",
    )

    assert res["is_valid"] is True
    assert len(res["validation_errors"]) == 0

    # Verify original CSV was not modified
    assert csv_file.stat().st_mtime == original_mtime

    # Verify run_003 (driving) was rejected and not awarded territory
    rejected_runs = res["data_quality"]["rejected_runs"]
    assert rejected_runs == 1

    # Verify territory was conquered
    territory = res["territory_conquest"]
    assert territory["total_unique_zones"] >= 1
