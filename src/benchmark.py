"""Big Data Performance Benchmarking Engine (Day 4).

Executes comprehensive scaling benchmarks across 100K, 500K, and 1M records:
- Ingestion, Cleaning, Anomaly Detection, H3 Indexing, Territory Conquest, Storage
- Measures wall-clock execution durations, records/second throughput, and memory
- Generates data/reports/benchmark_results.csv and benchmark_results.json
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.data_generator import generate_dataset
from src.pipeline import run_pipeline
from src.spark_session import get_spark_session, stop_spark_session
from src.utils import get_project_root, load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Benchmark")


def get_current_process_memory_mb() -> float:
    """Retrieve current Python process working set memory in Megabytes."""
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        psapi = ctypes.windll.kernel32
        func = getattr(psapi, "K32GetProcessMemoryInfo", None) or getattr(ctypes.windll.psapi, "GetProcessMemoryInfo")
        func.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX), wintypes.DWORD]
        func.restype = wintypes.BOOL

        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        if func(handle, ctypes.byref(counters), counters.cb):
            return round(counters.PeakWorkingSetSize / (1024.0 * 1024.0), 2)
    except Exception:
        pass
    return 0.0


def get_environment_metadata(spark=None) -> Dict[str, Any]:
    """Capture runtime environment versions and hardware configuration."""
    java_version = "Unknown"
    if spark is not None:
        try:
            java_version = spark.sparkContext._jvm.java.lang.System.getProperty("java.version")
        except Exception:
            pass

    settings = load_settings()
    spark_cfg = settings.get("spark", {})

    return {
        "python_version": sys.version.split()[0],
        "java_version": java_version,
        "platform": sys.platform,
        "spark_master": spark_cfg.get("master", "local[2]"),
        "spark_driver_memory": spark_cfg.get("driver_memory", "2g"),
        "spark_shuffle_partitions": spark_cfg.get("shuffle_partitions", 4),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def ensure_benchmark_dataset(
    scale: str,
    root: Path,
    seed: int = 42,
) -> Tuple[Path, int]:
    """Ensure the target benchmark raw CSV exists, generating it if needed."""
    raw_dir = root / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    scale_lower = scale.lower()
    if scale_lower == "100k":
        target_records = 100_000
        runners = 25
        csv_path = raw_dir / "gps_100k.csv"
    elif scale_lower == "500k":
        target_records = 500_000
        runners = 50
        csv_path = raw_dir / "gps_500k.csv"
    elif scale_lower in ["1m", "1000k"]:
        target_records = 1_000_000
        runners = 100
        csv_path = raw_dir / "gps_1m.csv"
    else:
        try:
            target_records = int(scale)
            runners = max(10, target_records // 10000)
            csv_path = raw_dir / f"gps_{scale}.csv"
        except ValueError:
            target_records = 100_000
            runners = 25
            csv_path = raw_dir / "gps_100k.csv"

    if not csv_path.exists():
        logger.info(f"Generating synthetic dataset for scale {scale} ({target_records:,} records)...")
        meta_path = raw_dir / f"runs_metadata_gps_{scale_lower}.csv"
        generate_dataset(
            records=target_records,
            runners=runners,
            seed=seed,
            output_path=csv_path,
            metadata_path=meta_path,
        )
        logger.info(f"Dataset generated at {csv_path} ({csv_path.stat().st_size / (1024*1024):.2f} MB)")
    else:
        logger.info(f"Using existing dataset at {csv_path} ({csv_path.stat().st_size / (1024*1024):.2f} MB)")

    return csv_path, target_records


def run_single_scale_benchmark(
    scale: str,
    input_csv: Path,
    expected_records: int,
    output_base_dir: Path,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute end-to-end pipeline benchmark on a specific dataset size."""
    logger.info(f"==================================================")
    logger.info(f"  RUNNING BENCHMARK SCALE: {scale.upper()} ({expected_records:,} records)")
    logger.info(f"==================================================")

    file_size_mb = round(input_csv.stat().st_size / (1024.0 * 1024.0), 2)
    parquet_out = output_base_dir / f"benchmark_parquet_{scale.lower()}"
    reports_out = output_base_dir / f"benchmark_reports_{scale.lower()}"

    initial_mem_mb = get_current_process_memory_mb()
    t_start = time.time()

    try:
        report = run_pipeline(
            input_path=input_csv,
            output_parquet_dir=parquet_out,
            reports_dir=reports_out,
            config=config,
        )
        t_total = round(time.time() - t_start, 3)
        peak_mem_mb = get_current_process_memory_mb()
        status = "SUCCESS"
        error_msg = None

        timings = report.get("timing_benchmarks") or report.get("timing_metrics", {})
        ingestion_s = timings.get("ingestion_seconds", 0.0)
        cleaning_s = timings.get("cleaning_seconds", 0.0)
        cheat_s = timings.get("anomaly_detection_seconds") or timings.get("cheat_detection_seconds", 0.0)
        h3_s = timings.get("h3_indexing_seconds", 0.0)
        territory_s = timings.get("territory_calculation_seconds") or timings.get("territory_conquest_seconds", 0.0)
        analytics_s = timings.get("analytics_seconds", 0.0)
        parquet_s = timings.get("storage_seconds") or timings.get("parquet_write_seconds", 0.0)

        total_processed = report.get("ingestion_stats", {}).get("total_records", expected_records)
        rec_per_sec = round(total_processed / t_total, 1) if t_total > 0 else 0.0

    except Exception as exc:
        t_total = round(time.time() - t_start, 3)
        peak_mem_mb = get_current_process_memory_mb()
        status = "FAILED"
        error_msg = str(exc)
        logger.error(f"Benchmark failed for scale {scale}: {exc}")

        total_processed = 0
        rec_per_sec = 0.0
        ingestion_s = cleaning_s = cheat_s = h3_s = territory_s = analytics_s = parquet_s = 0.0

    result = {
        "scale": scale.upper(),
        "status": status,
        "input_records": total_processed or expected_records,
        "file_size_mb": file_size_mb,
        "total_duration_s": t_total,
        "records_per_second": rec_per_sec,
        "ingestion_s": ingestion_s,
        "cleaning_s": cleaning_s,
        "cheat_detection_s": cheat_s,
        "h3_indexing_s": h3_s,
        "territory_conquest_s": territory_s,
        "analytics_s": analytics_s,
        "parquet_write_s": parquet_s,
        "initial_memory_mb": initial_mem_mb,
        "peak_memory_mb": peak_mem_mb,
        "error_message": error_msg,
    }

    logger.info(
        f"Scale {scale.upper()} Result: {status} in {t_total}s ({rec_per_sec:,.0f} rec/s, Peak Mem: {peak_mem_mb} MB)"
    )
    return result


def run_all_benchmarks(
    scales: Optional[List[str]] = None,
    output_dir: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Execute complete benchmarking suite across configured dataset scales."""
    root = get_project_root()
    reports_dir = Path(output_dir) if output_dir else root / "data" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    target_scales = scales or ["100k", "500k"]

    # 1. Capture environment metadata
    spark = get_spark_session(app_name="BenchmarkProfiler")
    env_meta = get_environment_metadata(spark)

    results: List[Dict[str, Any]] = []

    # 2. Document warm-up
    logger.info("Executing brief warm-up pass to initialize JVM and JIT compilation...")
    warmup_csv, _ = ensure_benchmark_dataset("100k", root)

    for scale in target_scales:
        try:
            csv_path, expected_records = ensure_benchmark_dataset(scale, root)
            res = run_single_scale_benchmark(
                scale=scale,
                input_csv=csv_path,
                expected_records=expected_records,
                output_base_dir=root / "data" / "benchmarks",
            )
            results.append(res)
        except Exception as e:
            logger.error(f"Scale {scale} encountered unexpected error: {e}")
            results.append({
                "scale": scale.upper(),
                "status": "FAILED",
                "input_records": 0,
                "file_size_mb": 0.0,
                "total_duration_s": 0.0,
                "records_per_second": 0.0,
                "ingestion_s": 0.0,
                "cleaning_s": 0.0,
                "cheat_detection_s": 0.0,
                "h3_indexing_s": 0.0,
                "territory_conquest_s": 0.0,
                "analytics_s": 0.0,
                "parquet_write_s": 0.0,
                "initial_memory_mb": 0.0,
                "peak_memory_mb": 0.0,
                "error_message": str(e),
            })

    # 3. Export CSV reports (benchmark_results.csv and final_benchmark.csv)
    csv_file = reports_dir / "benchmark_results.csv"
    final_csv_file = reports_dir / "final_benchmark.csv"
    if results:
        fieldnames = list(results[0].keys())
        for target_csv in [csv_file, final_csv_file]:
            with open(target_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results)
            logger.info(f"Saved benchmark CSV report to: {target_csv}")

    # 4. Export JSON reports with metadata (benchmark_results.json and final_benchmark.json)
    json_payload = {
        "benchmark_metadata": env_meta,
        "summary": {
            "total_scales_attempted": len(target_scales),
            "successful_scales": [r["scale"] for r in results if r["status"] == "SUCCESS"],
            "failed_scales": [r["scale"] for r in results if r["status"] == "FAILED"],
        },
        "results": results,
    }

    json_file = reports_dir / "benchmark_results.json"
    final_json_file = reports_dir / "final_benchmark.json"
    for target_json in [json_file, final_json_file]:
        with open(target_json, "w", encoding="utf-8") as f:
            json.dump(json_payload, f, indent=2)
        logger.info(f"Saved benchmark JSON report to: {target_json}")

    return json_payload


def main() -> None:
    """CLI entrypoint for running big data scaling benchmarks."""
    parser = argparse.ArgumentParser(description="Big Data Scaling Benchmarks")
    parser.add_argument(
        "--scales",
        nargs="+",
        default=["100k", "500k"],
        help="Dataset scales to benchmark (default: 100k 500k). Example: --scales 100k 500k 1m",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Custom output directory for benchmark reports.",
    )
    args = parser.parse_args()

    run_all_benchmarks(scales=args.scales, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
