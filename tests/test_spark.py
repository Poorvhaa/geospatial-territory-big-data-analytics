"""Tests for local PySpark session management, DataFrame operations, and Parquet roundtrip."""

from pathlib import Path
import pytest

from src.spark_session import (
    get_spark_session,
    stop_spark_session,
    run_spark_smoke_test,
)


@pytest.fixture(scope="module")
def spark():
    session = get_spark_session(app_name="TestPySparkSession")
    yield session
    stop_spark_session(session)


@pytest.mark.spark
def test_spark_session_creation_and_teardown(spark):
    """Verify local SparkSession starts and operates cleanly."""
    assert spark is not None
    assert "local" in spark.sparkContext.master.lower()


@pytest.mark.spark
def test_spark_smoke_test_execution(tmp_path: Path, spark):
    """Verify the 10-row DataFrame, aggregation, and Parquet roundtrip."""
    test_parquet_path = tmp_path / "smoke_test_parquet"
    res = run_spark_smoke_test(parquet_path=test_parquet_path, spark_session=spark)

    assert res["status"] == "PASSED"
    assert res["rows_written"] == 10
    assert res["rows_read"] == 10
    assert "avg_speed_kmh" in res["aggregates"]
    assert res["aggregates"]["avg_speed_kmh"] > 0
