"""Unit tests for H3 indexing and territory conquest engine (Day 2)."""

from __future__ import annotations

import pytest
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    BooleanType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from src.analytics import generate_current_leaderboard
from src.h3_indexing import index_gps_points_to_h3
from src.spark_session import get_spark_session, stop_spark_session
from src.territory_engine import generate_zone_visits, process_territory_ownership


@pytest.fixture(scope="module")
def spark() -> SparkSession:
    session = get_spark_session(app_name="TestTerritory")
    yield session
    stop_spark_session(session)


def test_h3_indexing_and_cell_validation(spark: SparkSession) -> None:
    # Chicago Loop coordinates
    data = [
        ("r1", "u1", 41.8781, -87.6298),
        ("r1", "u1", 41.8826, -87.6226),
    ]
    schema = StructType([
        StructField("run_id", StringType(), False),
        StructField("runner_id", StringType(), False),
        StructField("latitude", DoubleType(), False),
        StructField("longitude", DoubleType(), False),
    ])
    df = spark.createDataFrame(data, schema)
    indexed_df = index_gps_points_to_h3(df, resolution=9)

    rows = indexed_df.collect()
    assert len(rows) == 2
    for r in rows:
        assert r["h3_cell"] is not None
        assert len(r["h3_cell"]) == 15  # standard 15-char H3 index hex string
        assert r["is_valid_h3"] is True


def test_zone_visit_deduplication_and_min_observations(spark: SparkSession) -> None:
    # Run visits: Cell_A (3 points), Cell_B (1 point - not confirmed if min_consec=2), Cell_A (2 points - confirmed re-entry)
    data = [
        ("run_1", "runner_A", 1000.0, "Cell_A", True),
        ("run_1", "runner_A", 1005.0, "Cell_A", True),
        ("run_1", "runner_A", 1010.0, "Cell_A", True),
        ("run_1", "runner_A", 1015.0, "Cell_B", True),  # only 1 point
        ("run_1", "runner_A", 1020.0, "Cell_A", True),  # re-entry
        ("run_1", "runner_A", 1025.0, "Cell_A", True),
    ]
    schema = StructType([
        StructField("run_id", StringType(), False),
        StructField("runner_id", StringType(), False),
        StructField("timestamp_epoch", DoubleType(), False),
        StructField("h3_cell", StringType(), False),
        StructField("is_valid_h3", BooleanType(), False),
    ])
    df = spark.createDataFrame(data, schema).withColumn(
        "timestamp", F.to_timestamp(F.from_unixtime("timestamp_epoch"))
    )

    # With min_consecutive = 2:
    claims_df = generate_zone_visits(df, min_consecutive_points=2)
    claims = claims_df.collect()

    # Cell_A visit 1 confirmed (point 2)
    # Cell_B discarded (< 2 points)
    # Cell_A visit 3 confirmed (re-entry)
    assert len(claims) == 2
    assert claims[0]["h3_cell"] == "Cell_A"
    assert claims[1]["h3_cell"] == "Cell_A"


def test_initial_capture_takeover_and_same_owner_revisit(spark: SparkSession) -> None:
    # Chronological claim timeline on Zone_X:
    # 1. Runner A visits Zone_X at t=100 -> INITIAL_CAPTURE
    # 2. Runner A visits Zone_X at t=200 -> SAME_OWNER_REVISIT (no takeover)
    # 3. Runner B visits Zone_X at t=300 -> TAKEOVER (ownership change)
    # 4. Runner B visits Zone_X at t=400 -> SAME_OWNER_REVISIT (no takeover)
    # 5. Runner A visits Zone_X at t=500 -> TAKEOVER (re-takeover)
    claims_data = [
        ("claim_1", "Zone_X", "runner_A", "run_1", 100.0, 3),
        ("claim_2", "Zone_X", "runner_A", "run_2", 200.0, 3),
        ("claim_3", "Zone_X", "runner_B", "run_3", 300.0, 4),
        ("claim_4", "Zone_X", "runner_B", "run_4", 400.0, 2),
        ("claim_5", "Zone_X", "runner_A", "run_5", 500.0, 5),
    ]
    schema = StructType([
        StructField("claim_id", StringType(), False),
        StructField("h3_cell", StringType(), False),
        StructField("runner_id", StringType(), False),
        StructField("run_id", StringType(), False),
        StructField("claim_timestamp_epoch", DoubleType(), False),
        StructField("points_in_visit", IntegerType(), False),
    ])
    claims_df = spark.createDataFrame(claims_data, schema).withColumn(
        "claim_timestamp", F.to_timestamp(F.from_unixtime("claim_timestamp_epoch"))
    )

    history_df, current_ownership_df, metrics = process_territory_ownership(claims_df)

    history = {r["claim_id"]: r.asDict() for r in history_df.collect()}

    # 1. Claim 1 -> INITIAL_CAPTURE
    assert history["claim_1"]["event_type"] == "INITIAL_CAPTURE"
    assert history["claim_1"]["is_ownership_change"] is True
    assert history["claim_1"]["is_takeover"] is False
    assert history["claim_1"]["is_same_owner_revisit"] is False

    # 2. Claim 2 -> SAME_OWNER_REVISIT
    assert history["claim_2"]["event_type"] == "SAME_OWNER_REVISIT"
    assert history["claim_2"]["is_ownership_change"] is False
    assert history["claim_2"]["is_takeover"] is False
    assert history["claim_2"]["is_same_owner_revisit"] is True

    # 3. Claim 3 -> TAKEOVER (runner_B takes over from runner_A)
    assert history["claim_3"]["event_type"] == "TAKEOVER"
    assert history["claim_3"]["prev_runner_id"] == "runner_A"
    assert history["claim_3"]["is_ownership_change"] is True
    assert history["claim_3"]["is_takeover"] is True

    # 4. Claim 4 -> SAME_OWNER_REVISIT
    assert history["claim_4"]["event_type"] == "SAME_OWNER_REVISIT"
    assert history["claim_4"]["is_takeover"] is False

    # 5. Claim 5 -> TAKEOVER (runner_A re-takes from runner_B)
    assert history["claim_5"]["event_type"] == "TAKEOVER"
    assert history["claim_5"]["prev_runner_id"] == "runner_B"
    assert history["claim_5"]["is_takeover"] is True

    # Current ownership verification
    current_owners = current_ownership_df.collect()
    assert len(current_owners) == 1
    assert current_owners[0]["h3_cell"] == "Zone_X"
    assert current_owners[0]["current_owner_id"] == "runner_A"
    assert current_owners[0]["latest_claim_id"] == "claim_5"

    # Aggregates
    assert metrics["initial_captures"] == 1
    assert metrics["takeovers"] == 2
    assert metrics["same_owner_revisits"] == 2

    # Leaderboard check
    leaderboard = generate_current_leaderboard(current_ownership_df)
    leader_rows = leaderboard.collect()
    assert len(leader_rows) == 1
    assert leader_rows[0]["runner_id"] == "runner_A"
    assert leader_rows[0]["zones_owned"] == 1
