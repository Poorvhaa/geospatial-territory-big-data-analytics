"""Uber H3 Geospatial Indexing Module for Geospatial Big Data.

Projects eligible GPS latitude/longitude coordinates onto discrete hexagonal spatial
indices using Uber H3 v4.x within distributed PySpark workflows, without collecting
datasets to driver memory.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

import h3
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType, StringType

logger = logging.getLogger(__name__)

DEFAULT_H3_RESOLUTION = 9


# PySpark UDF for H3 v4.x latlng_to_cell
@F.udf(returnType=StringType())
def latlng_to_h3_udf(lat: Optional[float], lon: Optional[float], resolution: int = DEFAULT_H3_RESOLUTION) -> Optional[str]:
    """Convert (latitude, longitude) coordinate to Uber H3 v4 hexagonal cell string."""
    if lat is None or lon is None:
        return None
    try:
        return h3.latlng_to_cell(float(lat), float(lon), int(resolution))
    except Exception:
        return None


# PySpark UDF for H3 cell validation
@F.udf(returnType=BooleanType())
def is_valid_h3_udf(cell: Optional[str]) -> bool:
    """Validate whether an H3 cell index string is valid."""
    if cell is None:
        return False
    try:
        return bool(h3.is_valid_cell(str(cell)))
    except Exception:
        return False


def index_gps_points_to_h3(
    df: DataFrame,
    resolution: int = DEFAULT_H3_RESOLUTION,
) -> DataFrame:
    """Assign Uber H3 index to every GPS point in a distributed PySpark DataFrame.

    Args:
        df: Input DataFrame containing 'latitude' and 'longitude'.
        resolution: H3 grid resolution (0 to 15, default 9).

    Returns:
        DataFrame enriched with 'h3_cell' column and 'is_valid_h3' boolean column.
    """
    logger.info(f"Computing Uber H3 hexagonal spatial index at resolution {resolution}...")

    # Project to H3 cell using Spark UDF
    indexed_df = (
        df.withColumn(
            "h3_cell",
            latlng_to_h3_udf(F.col("latitude"), F.col("longitude"), F.lit(resolution))
        )
        .withColumn(
            "is_valid_h3",
            is_valid_h3_udf(F.col("h3_cell"))
        )
    )

    return indexed_df


def save_h3_indexed_points(
    df: DataFrame,
    output_dir: Union[str, Path],
    mode: str = "overwrite",
) -> None:
    """Save H3 indexed GPS points to Parquet format.

    Args:
        df: Indexed DataFrame.
        output_dir: Target output directory.
        mode: Save mode ('overwrite' or 'append').
    """
    output_path = str(Path(output_dir).resolve())
    logger.info(f"Writing H3 indexed points to Parquet at: {output_path}")

    # Standard select of core columns for the h3_points parquet dataset
    core_cols = [
        "run_id",
        "runner_id",
        "timestamp",
        "timestamp_epoch",
        "latitude",
        "longitude",
        "h3_cell",
        "speed_kmh",
        "observed_step_dist_m",
    ]
    available_cols = [c for c in core_cols if c in df.columns]

    (
        df.select(*available_cols)
        .write.mode(mode)
        .parquet(output_path)
    )
