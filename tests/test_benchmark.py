"""Unit tests for Performance Benchmarking Suite (Day 4)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from src.benchmark import (
    ensure_benchmark_dataset,
    get_current_process_memory_mb,
    get_environment_metadata,
    run_single_scale_benchmark,
)
from src.spark_session import get_spark_session, stop_spark_session


@pytest.fixture(scope="module")
def spark():
    session = get_spark_session(app_name="TestBenchmarkSession")
    yield session
    stop_spark_session(session)


def test_environment_metadata_capture(spark) -> None:
    meta = get_environment_metadata(spark)
    assert "python_version" in meta
    assert "java_version" in meta
    assert "spark_master" in meta
    assert "timestamp" in meta


def test_process_memory_reporting() -> None:
    mem = get_current_process_memory_mb()
    # Memory should be non-negative float
    assert isinstance(mem, float)
    assert mem >= 0.0


def test_single_scale_benchmark_execution(tmp_path: Path, spark) -> None:
    # Create small deterministic 10-row CSV
    csv_file = tmp_path / "mini_bench.csv"
    data = [
        "run_id,runner_id,timestamp,latitude,longitude,heart_rate,cadence,elevation_m,distance_m,device_type,activity_type,scenario_type\n",
        "r1,u1,2026-10-26T08:00:00Z,41.8781,-87.6298,140,165,181.0,0.0,Garmin,running,normal_run\n",
        "r1,u1,2026-10-26T08:00:05Z,41.8782,-87.6298,142,165,181.2,11.1,Garmin,running,normal_run\n",
        "r1,u1,2026-10-26T08:00:10Z,41.8783,-87.6298,145,166,181.4,22.2,Garmin,running,normal_run\n",
    ]
    with open(csv_file, "w", encoding="utf-8") as f:
        f.writelines(data)

    res = run_single_scale_benchmark(
        scale="mini",
        input_csv=csv_file,
        expected_records=3,
        output_base_dir=tmp_path / "bench_out",
    )

    assert res["status"] == "SUCCESS"
    assert res["scale"] == "MINI"
    assert res["input_records"] == 3
    assert res["total_duration_s"] > 0.0
    assert "ingestion_s" in res
    assert "records_per_second" in res
