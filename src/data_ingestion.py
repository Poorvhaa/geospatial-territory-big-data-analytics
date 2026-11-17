"""PySpark Data Ingestion Module for Geospatial GPS Big Data.

Handles distributed loading of high-frequency GPS datasets with explicit schemas,
timestamp parsing, schema validation, and partition diagnostics without collecting
data into driver memory.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

logger = logging.getLogger(__name__)

# Standard required column list
REQUIRED_COLUMNS: List[str] = [
    "run_id",
    "runner_id",
    "timestamp",
    "latitude",
    "longitude",
]

ALL_EXPECTED_COLUMNS: List[str] = [
    "run_id",
    "runner_id",
    "timestamp",
    "latitude",
    "longitude",
    "heart_rate",
    "cadence",
    "elevation_m",
    "distance_m",
    "device_type",
    "activity_type",
    "scenario_type",
]

# Explicit Schema for Raw GPS Ingestion
GPS_RAW_SCHEMA: StructType = StructType([
    StructField("run_id", StringType(), nullable=True),
    StructField("runner_id", StringType(), nullable=True),
    StructField("timestamp", StringType(), nullable=True),
    StructField("latitude", DoubleType(), nullable=True),
    StructField("longitude", DoubleType(), nullable=True),
    StructField("heart_rate", IntegerType(), nullable=True),
    StructField("cadence", IntegerType(), nullable=True),
    StructField("elevation_m", DoubleType(), nullable=True),
    StructField("distance_m", DoubleType(), nullable=True),
    StructField("device_type", StringType(), nullable=True),
    StructField("activity_type", StringType(), nullable=True),
    StructField("scenario_type", StringType(), nullable=True),
])


def get_raw_gps_schema() -> StructType:
    """Return the explicit StructType schema for raw GPS data ingestion."""
    return GPS_RAW_SCHEMA


def validate_schema_columns(df: DataFrame) -> Tuple[bool, List[str]]:
    """Validate that all required columns are present in the DataFrame.

    Returns:
        Tuple of (is_valid, missing_columns).
    """
    df_cols = set(df.columns)
    missing = [col for col in REQUIRED_COLUMNS if col not in df_cols]
    return len(missing) == 0, missing


def load_gps_data(
    spark: SparkSession,
    file_path: Union[str, Path],
    schema: Optional[StructType] = None,
    header: bool = True,
    delimiter: str = ",",
) -> DataFrame:
    """Load GPS dataset into PySpark with explicit schema and UTC timestamp parsing.

    Args:
        spark: Active SparkSession.
        file_path: Path to CSV dataset (supports local paths or wildcard patterns).
        schema: Optional custom StructType (defaults to GPS_RAW_SCHEMA).
        header: Whether input file has header row (default True).
        delimiter: CSV column delimiter (default ',').

    Returns:
        PySpark DataFrame with explicit schema and parsed 'timestamp' column as TimestampType.
    """
    file_path_str = str(Path(file_path).resolve())
    target_schema = schema or GPS_RAW_SCHEMA

    logger.info(f"Ingesting GPS data from: {file_path_str}")

    raw_df = (
        spark.read.format("csv")
        .option("header", str(header).lower())
        .option("delimiter", delimiter)
        .option("mode", "PERMISSIVE")
        .schema(target_schema)
        .load(file_path_str)
    )

    is_valid, missing = validate_schema_columns(raw_df)
    if not is_valid:
        raise ValueError(
            f"Input dataset is missing required columns: {missing}. Found: {raw_df.columns}"
        )

    # Preserve raw timestamp string as 'raw_timestamp' and parse 'timestamp' as TimestampType
    # Also parse timestamp to epoch seconds for fast mathematical window operations
    parsed_df = (
        raw_df.withColumn("raw_timestamp", F.col("timestamp"))
        .withColumn(
            "timestamp",
            F.coalesce(
                F.to_timestamp(F.col("timestamp"), "yyyy-MM-dd'T'HH:mm:ss'Z'"),
                F.to_timestamp(F.col("timestamp")),
            ),
        )
        .withColumn("timestamp_epoch", F.col("timestamp").cast("double"))
    )

    return parsed_df


def get_ingestion_statistics(df: DataFrame) -> Dict[str, Any]:
    """Compute ingestion summary metrics without collecting full data to driver.

    Args:
        df: Ingested PySpark DataFrame.

    Returns:
        Dictionary with count, partitions, null checks, and column names.
    """
    total_records = df.count()
    num_partitions = df.rdd.getNumPartitions()
    columns = df.columns

    # Count nulls across essential columns using a single distributed aggregation
    null_aggs = [
        F.count(F.when(F.col(c).isNull(), c)).alias(f"null_{c}")
        for c in REQUIRED_COLUMNS
    ]
    null_counts_row = df.select(null_aggs).collect()[0]
    null_counts = {c: null_counts_row[f"null_{c}"] for c in REQUIRED_COLUMNS}

    stats = {
        "total_records": total_records,
        "num_columns": len(columns),
        "columns": columns,
        "num_partitions": num_partitions,
        "null_counts": null_counts,
    }

    logger.info(
        f"Ingestion Stats: {total_records} records, {len(columns)} cols, {num_partitions} partitions"
    )
    return stats
