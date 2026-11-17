"""Reusable local PySpark session factory and Windows-friendly smoke test."""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Ensure PySpark workers and driver explicitly use the active Python 3.11 environment
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

# Auto-configure local Windows Hadoop environment if present
_root_dir = Path(__file__).resolve().parent.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))
_hadoop_dir = _root_dir / "hadoop"
if _hadoop_dir.exists():
    os.environ.setdefault("HADOOP_HOME", str(_hadoop_dir))
    _hadoop_bin = str(_hadoop_dir / "bin")
    if _hadoop_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{_hadoop_bin};" + os.environ.get("PATH", "")

from src.utils import get_project_root, load_settings

try:
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    from pyspark.sql.types import DoubleType, IntegerType, StringType, StructField, StructType
except ImportError:
    SparkSession = None  # type: ignore
    F = None  # type: ignore


def get_spark_session(
    app_name: Optional[str] = None,
    master: Optional[str] = None,
    driver_memory: Optional[str] = None,
    shuffle_partitions: Optional[int] = None,
    log_level: Optional[str] = None,
    extra_configs: Optional[Dict[str, str]] = None,
) -> SparkSession:
    """Create or retrieve a Windows-compatible local SparkSession.

    Configured specifically for local Windows 11 execution:
    - Avoids dependency on winutils.exe or Hadoop daemons
    - Configures driver memory, shuffle partitions, and localhost binding
    - Gracefully controls verbosity
    """
    if SparkSession is None:
        raise ImportError(
            "PySpark is not installed in the current environment. "
            "Install pyspark>=4.2.0 or run 'pip install -r requirements.txt'."
        )

    # Load defaults from config/settings.yaml
    try:
        settings = load_settings()
        spark_cfg = settings.get("spark", {})
    except Exception:
        spark_cfg = {}

    app_name = app_name or spark_cfg.get("app_name", "TerritoryControlHotspotAnalysis")
    master = master or spark_cfg.get("master", "local[2]")
    driver_memory = driver_memory or spark_cfg.get("driver_memory", "2g")
    shuffle_partitions = shuffle_partitions or spark_cfg.get("shuffle_partitions", 4)
    log_level = log_level or spark_cfg.get("log_level", "WARN")

    root = get_project_root()
    warehouse_dir = str((root / "data" / "spark-warehouse").resolve())
    temp_dir = str((root / "data" / "spark-temp").resolve())
    os.makedirs(temp_dir, exist_ok=True)
    os.environ["SPARK_LOCAL_DIRS"] = temp_dir

    # Build Spark configuration
    builder = (
        SparkSession.builder.appName(app_name)
        .master(master)
        .config("spark.driver.memory", driver_memory)
        .config("spark.sql.shuffle.partitions", str(shuffle_partitions))
        .config("spark.sql.warehouse.dir", warehouse_dir)
        .config("spark.local.dir", temp_dir)
        .config("spark.driver.host", "localhost")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.pyspark.python", sys.executable)
        .config("spark.pyspark.driver.python", sys.executable)
        .config("spark.ui.enabled", "false")
        .config("spark.ui.showConsoleProgress", "false")
        # Windows-friendly RawLocalFileSystem avoids winutils POSIX permission errors
        .config("spark.hadoop.fs.file.impl", "org.apache.hadoop.fs.RawLocalFileSystem")
        .config("spark.hadoop.mapreduce.fileoutputcommitter.marksuccessfuljobs", "false")
        .config("spark.sql.parquet.outputTimestampType", "TIMESTAMP_MICROS")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.adaptive.enabled", "false")
    )

    if extra_configs:
        for k, v in extra_configs.items():
            builder = builder.config(k, v)

    spark = builder.getOrCreate()

    # Set log level
    try:
        spark.sparkContext.setLogLevel(log_level)
    except Exception:
        pass

    return spark


def stop_spark_session(spark: SparkSession) -> None:
    """Cleanly stop the active SparkSession."""
    if spark is not None:
        try:
            spark.stop()
        except Exception as e:
            print(f"Warning during Spark stop: {e}", file=sys.stderr)


def run_spark_smoke_test(
    parquet_path: Optional[str | Path] = None,
    spark_session: Optional[SparkSession] = None,
) -> Dict[str, Any]:
    """Execute a complete PySpark DataFrame & Parquet roundtrip smoke test.

    Steps:
    1. Start local SparkSession (or use provided session).
    2. Create a 10-row synthetic test DataFrame.
    3. Compute count and numeric aggregations.
    4. Write DataFrame to Parquet storage.
    5. Read Parquet back and verify row count and values.
    6. Stop Spark session cleanly if created locally.

    Returns:
        Summary dict containing test results and diagnostic information.
    """
    root = get_project_root()
    if parquet_path is None:
        parquet_dir = root / "data" / "parquet" / "smoke_test"
    else:
        parquet_dir = Path(parquet_path)

    start_time = time.time()
    spark: Optional[SparkSession] = None
    owns_spark = False
    diagnostics: Dict[str, Any] = {
        "status": "FAILED",
        "rows_written": 0,
        "rows_read": 0,
        "parquet_path": str(parquet_dir),
        "duration_seconds": 0.0,
        "spark_version": None,
        "error": None,
        "windows_troubleshooting": None,
    }

    try:
        if spark_session is not None:
            spark = spark_session
        else:
            spark = get_spark_session(app_name="SparkSmokeTest")
            owns_spark = True
        diagnostics["spark_version"] = spark.version

        # 10-row test dataset
        test_data = [
            (1, "runner_001", 8.5, "normal_run"),
            (2, "runner_002", 14.2, "fast_run"),
            (3, "runner_003", 4.1, "walking"),
            (4, "runner_004", 55.0, "driving"),
            (5, "runner_005", 9.1, "gps_spoofing"),
            (6, "runner_006", 8.8, "gps_noise"),
            (7, "runner_007", 10.5, "normal_run"),
            (8, "runner_008", 16.0, "fast_run"),
            (9, "runner_009", 4.8, "walking"),
            (10, "runner_010", 62.3, "driving"),
        ]

        schema = StructType([
            StructField("point_id", IntegerType(), False),
            StructField("runner_id", StringType(), False),
            StructField("speed_kmh", DoubleType(), False),
            StructField("scenario_type", StringType(), False),
        ])

        df = spark.createDataFrame(test_data, schema)
        initial_count = df.count()
        assert initial_count == 10, f"Expected 10 rows, got {initial_count}"

        agg_row = df.select(
            F.avg("speed_kmh").alias("avg_speed"),
            F.max("speed_kmh").alias("max_speed"),
            F.min("speed_kmh").alias("min_speed"),
        ).collect()[0]

        expected_avg = sum(r[2] for r in test_data) / 10.0
        assert abs(agg_row["avg_speed"] - expected_avg) < 1e-4

        # Clean prior test parquet output if exists
        if parquet_dir.exists():
            shutil.rmtree(parquet_dir, ignore_errors=True)
        parquet_dir.parent.mkdir(parents=True, exist_ok=True)

        # Write Parquet
        df.write.mode("overwrite").parquet(str(parquet_dir.resolve()))
        diagnostics["rows_written"] = initial_count

        # Read Parquet back
        df_read = spark.read.parquet(str(parquet_dir.resolve()))
        read_count = df_read.count()
        diagnostics["rows_read"] = read_count
        assert read_count == 10, f"Expected 10 rows read from Parquet, got {read_count}"

        read_agg = df_read.select(F.avg("speed_kmh").alias("avg_speed")).collect()[0]
        assert abs(read_agg["avg_speed"] - expected_avg) < 1e-4

        diagnostics["status"] = "PASSED"
        diagnostics["aggregates"] = {
            "avg_speed_kmh": round(float(read_agg["avg_speed"]), 2),
            "max_speed_kmh": round(float(agg_row["max_speed"]), 2),
            "min_speed_kmh": round(float(agg_row["min_speed"]), 2),
        }

    except Exception as e:
        diagnostics["status"] = "FAILED"
        diagnostics["error"] = str(e)
        diagnostics["windows_troubleshooting"] = (
            "Windows PySpark Troubleshooting Checklist:\n"
            "1. Verify JAVA_HOME is set and points to JDK 17+ 64-bit.\n"
            "2. Ensure RawLocalFileSystem is configured to avoid winutils.exe dependencies.\n"
            "3. If java.lang.SecurityException or IllegalAccessError occurs, ensure Java 17+ JVM "
            "module flags (--add-opens=java.base/java.lang=ALL-UNNAMED) are enabled in spark.driver.extraJavaOptions.\n"
            "4. Verify Python architecture (64-bit) matches Java architecture (64-bit)."
        )
        raise
    finally:
        if spark is not None and owns_spark:
            stop_spark_session(spark)
        diagnostics["duration_seconds"] = round(time.time() - start_time, 2)

    return diagnostics


if __name__ == "__main__":
    print("Running Spark Smoke Test...")
    try:
        res = run_spark_smoke_test()
        print(f"Result: {res['status']}")
        print(f"Spark Version: {res['spark_version']}")
        print(f"Rows Written/Read: {res['rows_written']}/{res['rows_read']}")
        print(f"Aggregates: {res['aggregates']}")
        print(f"Duration: {res['duration_seconds']}s")
    except Exception as err:
        print(f"Smoke Test Failed: {err}", file=sys.stderr)
        sys.exit(1)
