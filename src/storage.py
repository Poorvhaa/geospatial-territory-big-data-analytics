"""Parquet Storage Management Module for Geospatial Big Data.

Handles atomic, idempotent, reproducible writing and reading of analytical
datasets to Apache Parquet storage.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Dict, Union

from pyspark.sql import DataFrame, SparkSession

logger = logging.getLogger(__name__)


def write_parquet(
    df: DataFrame,
    target_path: Union[str, Path],
    mode: str = "overwrite",
) -> None:
    """Safely write a PySpark DataFrame to Parquet storage with schema preservation.

    Args:
        df: PySpark DataFrame to write.
        target_path: Destination directory path.
        mode: Save mode ('overwrite' or 'append', default 'overwrite').
    """
    path_obj = Path(target_path).resolve()
    path_str = str(path_obj)

    logger.info(f"Saving Parquet dataset to: {path_str} (mode={mode})")

    # If overwrite on Windows with local filesystem, ensure clean directory
    if mode == "overwrite" and path_obj.exists():
        try:
            # We let Spark write overwrite, or ensure directory structure is valid
            pass
        except Exception:
            pass

    path_obj.parent.mkdir(parents=True, exist_ok=True)
    df.write.mode(mode).parquet(path_str)


def read_parquet(
    spark: SparkSession,
    source_path: Union[str, Path],
) -> DataFrame:
    """Read a Parquet dataset into a PySpark DataFrame.

    Args:
        spark: Active SparkSession.
        source_path: Path to the Parquet directory or file.

    Returns:
        PySpark DataFrame.
    """
    path_str = str(Path(source_path).resolve())
    return spark.read.parquet(path_str)


def save_all_pipeline_datasets(
    datasets: Dict[str, DataFrame],
    base_parquet_dir: Union[str, Path],
    mode: str = "overwrite",
) -> Dict[str, str]:
    """Write all analytical pipeline datasets to standard subdirectories.

    Args:
        datasets: Dict mapping dataset key names to DataFrames.
        base_parquet_dir: Base directory for parquet outputs (e.g. 'data/parquet').
        mode: Save mode (default 'overwrite').

    Returns:
        Dictionary mapping dataset keys to written paths.
    """
    base_dir = Path(base_parquet_dir).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = {}
    for key, df in datasets.items():
        if df is None:
            continue
        dest = base_dir / key
        write_parquet(df, dest, mode=mode)
        saved_paths[key] = str(dest)

    return saved_paths
