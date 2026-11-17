"""Streaming CSV Data Validator for Day 1 Geospatial Analytics.

Performs schema, integrity, temporal, spatial, and anomaly verification
on generated GPS tracks with bounded memory usage, writing results to JSON.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.data_generator import CSV_COLUMNS, METADATA_COLUMNS, SCENARIO_PROPORTIONS
from src.geo_utils import haversine_distance_m
from src.utils import get_project_root, parse_iso_z


class StreamingValidator:
    """Memory-efficient streaming validator for GPS CSV datasets."""

    def __init__(
        self,
        csv_path: Path | str,
        metadata_path: Optional[Path | str] = None,
        expected_records: Optional[int] = None,
    ) -> None:
        self.csv_path = Path(csv_path)
        self.metadata_path = Path(metadata_path) if metadata_path else None
        self.expected_records = expected_records

        # Validation issues
        self.errors: List[str] = []
        self.warnings: List[str] = []

        # Tracking state
        self.total_points = 0
        self.seen_runs: Dict[str, Dict[str, Any]] = {}
        self.runners: Set[str] = set()
        self.scenarios_seen: Set[str] = set()
        self.scenario_point_counts: Dict[str, int] = {s: 0 for s in SCENARIO_PROPORTIONS}
        self.scenario_run_counts: Dict[str, int] = {s: 0 for s in SCENARIO_PROPORTIONS}

        # Observed speeds by scenario
        self.scenario_speeds: Dict[str, List[float]] = {s: [] for s in SCENARIO_PROPORTIONS}

        # Anomaly tracking
        self.spoofing_jumps_detected = 0
        self.noise_spikes_detected = 0

        # Temporal boundaries
        self.min_time: Optional[datetime] = None
        self.max_time: Optional[datetime] = None

        # Previous point per run for continuity checks
        self.last_point_by_run: Dict[str, Dict[str, Any]] = {}

    def validate_schema(self, header: List[str]) -> bool:
        """Validate header columns and order."""
        if header != CSV_COLUMNS:
            self.errors.append(
                f"Schema mismatch. Expected {CSV_COLUMNS}, but found {header}"
            )
            return False
        return True

    def validate_metadata_consistency(self) -> None:
        """Verify that observed runs match the metadata file if provided."""
        if not self.metadata_path or not self.metadata_path.exists():
            return

        with open(self.metadata_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            meta_runs = {r["run_id"]: r for r in reader}

        for run_id, meta in meta_runs.items():
            if run_id not in self.seen_runs:
                self.errors.append(f"Metadata references run {run_id} which does not exist in CSV")
                continue

            observed = self.seen_runs[run_id]
            if observed["point_count"] != int(meta["point_count"]):
                self.errors.append(
                    f"Run {run_id} point count mismatch: metadata={meta['point_count']}, observed={observed['point_count']}"
                )
            if observed["runner_id"] != meta["runner_id"]:
                self.errors.append(
                    f"Run {run_id} runner mismatch: metadata={meta['runner_id']}, observed={observed['runner_id']}"
                )
            if observed["scenario_type"] != meta["scenario_type"]:
                self.errors.append(
                    f"Run {run_id} scenario mismatch: metadata={meta['scenario_type']}, observed={observed['scenario_type']}"
                )

    def process_file(self) -> bool:
        """Stream through the CSV file and execute all validations."""
        if not self.csv_path.exists():
            self.errors.append(f"File not found: {self.csv_path}")
            return False

        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                self.errors.append("CSV file is completely empty.")
                return False

            if not self.validate_schema(header):
                return False

            dict_reader = csv.DictReader(f, fieldnames=header)

            for line_no, row in enumerate(dict_reader, start=2):
                self.total_points += 1
                self._validate_row(row, line_no)

        # Dataset-level validations
        if self.expected_records is not None and self.total_points != self.expected_records:
            self.errors.append(
                f"Record count mismatch: expected {self.expected_records}, got {self.total_points}"
            )

        # Verify all 6 scenarios are represented
        missing_scenarios = set(SCENARIO_PROPORTIONS.keys()) - self.scenarios_seen
        if missing_scenarios:
            self.errors.append(
                f"Missing required scenario categories: {sorted(list(missing_scenarios))}"
            )

        # Verify runs have at least 3 points
        for run_id, info in self.seen_runs.items():
            if info["point_count"] < 3:
                self.errors.append(
                    f"Run {run_id} has only {info['point_count']} points (minimum required: 3)"
                )

        # Verify metadata consistency
        self.validate_metadata_consistency()

        # Check anomalies were detected
        if "gps_spoofing" in self.scenarios_seen and self.spoofing_jumps_detected == 0:
            self.warnings.append("No large GPS spoofing coordinate jumps were detected.")

        if "gps_noise" in self.scenarios_seen and self.noise_spikes_detected == 0:
            self.warnings.append("No isolated GPS noise anomalies were detected.")

        return len(self.errors) == 0

    def _validate_row(self, row: Dict[str, str], line_no: int) -> None:
        """Validate a single CSV row in stream."""
        # 1. Missing values
        for col in CSV_COLUMNS:
            val = row.get(col)
            if val is None or val.strip() == "":
                self.errors.append(f"Line {line_no}: Column '{col}' is missing or empty.")
                return

        run_id = row["run_id"]
        runner_id = row["runner_id"]
        ts_str = row["timestamp"]
        scenario = row["scenario_type"]
        self.runners.add(runner_id)
        self.scenarios_seen.add(scenario)
        self.scenario_point_counts[scenario] = self.scenario_point_counts.get(scenario, 0) + 1

        # 2. Parse numbers and coordinate bounds
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            hr = int(row["heart_rate"])
            cadence = int(row["cadence"])
            elev = float(row["elevation_m"])
            dist = float(row["distance_m"])
        except ValueError as e:
            self.errors.append(f"Line {line_no}: Numeric parsing failure: {e}")
            return

        for name, val in [("lat", lat), ("lon", lon), ("elev", elev), ("dist", dist)]:
            if not math.isfinite(val):
                self.errors.append(f"Line {line_no}: Non-finite numeric value in {name}: {val}")

        if not (-90.0 <= lat <= 90.0):
            self.errors.append(f"Line {line_no}: Latitude out of bounds [-90, 90]: {lat}")
        if not (-180.0 <= lon <= 180.0):
            self.errors.append(f"Line {line_no}: Longitude out of bounds [-180, 180]: {lon}")
        if hr <= 0 or hr > 250:
            self.errors.append(f"Line {line_no}: Heart rate out of plausible range: {hr}")
        if cadence < 0 or cadence > 260:
            self.errors.append(f"Line {line_no}: Cadence out of plausible range: {cadence}")

        # 3. Timestamp parsing & UTC check
        try:
            if not ts_str.endswith("Z"):
                self.errors.append(f"Line {line_no}: Timestamp missing 'Z' UTC suffix: {ts_str}")
                return
            ts = parse_iso_z(ts_str)
        except Exception as e:
            self.errors.append(f"Line {line_no}: Invalid ISO 8601 timestamp '{ts_str}': {e}")
            return

        if self.min_time is None or ts < self.min_time:
            self.min_time = ts
        if self.max_time is None or ts > self.max_time:
            self.max_time = ts

        # 4. Per-run sequential tracking
        if run_id not in self.seen_runs:
            self.seen_runs[run_id] = {
                "runner_id": runner_id,
                "scenario_type": scenario,
                "point_count": 1,
                "start_time": ts_str,
                "end_time": ts_str,
                "timestamps": {ts_str},
            }
            self.scenario_run_counts[scenario] = self.scenario_run_counts.get(scenario, 0) + 1
            self.last_point_by_run[run_id] = {
                "ts": ts,
                "lat": lat,
                "lon": lon,
                "dist": dist,
            }
        else:
            run_info = self.seen_runs[run_id]
            run_info["point_count"] += 1
            run_info["end_time"] = ts_str

            # Check unique run_id + timestamp
            if ts_str in run_info["timestamps"]:
                self.errors.append(f"Line {line_no}: Duplicate timestamp {ts_str} in run {run_id}")
            run_info["timestamps"].add(ts_str)

            # Continuity and ordering checks
            last_pt = self.last_point_by_run[run_id]
            prev_ts = last_pt["ts"]
            prev_lat = last_pt["lat"]
            prev_lon = last_pt["lon"]
            prev_dist = last_pt["dist"]

            # Strictly increasing timestamp
            delta_s = (ts - prev_ts).total_seconds()
            if delta_s <= 0:
                self.errors.append(
                    f"Line {line_no}: Non-increasing timestamp in run {run_id}: {prev_ts} -> {ts}"
                )

            # Cumulative distance consistency
            if dist < prev_dist:
                self.errors.append(
                    f"Line {line_no}: Decreasing cumulative distance in run {run_id}: {prev_dist} -> {dist}"
                )

            # Spatial distance and speed
            coord_dist_m = haversine_distance_m(prev_lat, prev_lon, lat, lon)
            if delta_s > 0:
                speed_kmh = (coord_dist_m / delta_s) * 3.6
                if len(self.scenario_speeds[scenario]) < 10000:
                    self.scenario_speeds[scenario].append(speed_kmh)

                # Anomaly detection checks
                if scenario == "gps_spoofing" and coord_dist_m > 5000.0:
                    self.spoofing_jumps_detected += 1
                elif scenario == "gps_noise" and 60.0 < coord_dist_m < 1500.0 and speed_kmh > 40.0:
                    self.noise_spikes_detected += 1

                # Normal run spatial continuity check
                if scenario == "normal_run" and speed_kmh > 35.0:
                    self.errors.append(
                        f"Line {line_no}: Unrealistic normal run speed: {speed_kmh:.1f} km/h "
                        f"(coord_dist={coord_dist_m:.1f}m, dt={delta_s}s)"
                    )

            # Update last point
            self.last_point_by_run[run_id] = {
                "ts": ts,
                "lat": lat,
                "lon": lon,
                "dist": dist,
            }

    def generate_report(self, spark_test_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Compile validation findings into a detailed summary report."""
        speed_summaries = {}
        for sc, speeds in self.scenario_speeds.items():
            if speeds:
                speed_summaries[sc] = {
                    "count": len(speeds),
                    "min_kmh": round(min(speeds), 2),
                    "mean_kmh": round(sum(speeds) / len(speeds), 2),
                    "max_kmh": round(max(speeds), 2),
                }

        file_size = self.csv_path.stat().st_size if self.csv_path.exists() else 0

        report = {
            "validation_timestamp": datetime.utcnow().isoformat() + "Z",
            "file_validated": str(self.csv_path),
            "file_size_bytes": file_size,
            "file_size_kb": round(file_size / 1024, 2),
            "is_valid": len(self.errors) == 0,
            "errors": self.errors[:50],  # Cap at 50 errors
            "total_errors": len(self.errors),
            "warnings": self.warnings,
            "metrics": {
                "total_gps_points": self.total_points,
                "total_runs": len(self.seen_runs),
                "total_runners": len(self.runners),
                "date_range": {
                    "start": self.min_time.isoformat() + "Z" if self.min_time else None,
                    "end": self.max_time.isoformat() + "Z" if self.max_time else None,
                },
                "scenario_distribution_points": self.scenario_point_counts,
                "scenario_distribution_runs": self.scenario_run_counts,
                "anomalies_detected": {
                    "spoofing_jumps": self.spoofing_jumps_detected,
                    "noise_spikes": self.noise_spikes_detected,
                },
                "observed_speeds": speed_summaries,
            },
            "spark_test": spark_test_result,
        }
        return report


def main() -> None:
    """CLI entrypoint for data validation."""
    parser = argparse.ArgumentParser(description="Validate Day 1 GPS CSV tracks.")
    parser.add_argument(
        "--input",
        type=str,
        default="data/raw/gps_demo.csv",
        help="Path to CSV dataset to validate.",
    )
    parser.add_argument(
        "--metadata",
        type=str,
        default=None,
        help="Optional path to runs metadata CSV.",
    )
    parser.add_argument(
        "--expected-records",
        type=int,
        default=None,
        help="Expected row count.",
    )
    parser.add_argument(
        "--report",
        type=str,
        default="data/reports/day1_validation.json",
        help="Path to write validation JSON report.",
    )

    args = parser.parse_args()

    # Determine metadata path if not provided
    input_path = Path(args.input)
    if args.metadata is None:
        candidate_meta = input_path.parent / f"runs_metadata_{input_path.stem}.csv"
        if candidate_meta.exists():
            meta_path = candidate_meta
        else:
            meta_path = input_path.parent / "runs_metadata.csv"
    else:
        meta_path = Path(args.metadata)

    validator = StreamingValidator(
        csv_path=input_path,
        metadata_path=meta_path if meta_path.exists() else None,
        expected_records=args.expected_records,
    )

    success = validator.process_file()
    report = validator.generate_report()

    # Save report
    report_file = Path(args.report)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as rf:
        json.dump(report, rf, indent=2)

    print("=" * 60)
    print("  DATA VALIDATION SUMMARY")
    print("=" * 60)
    print(f"File:           {args.input}")
    print(f"Status:         {'PASSED' if success else 'FAILED'}")
    print(f"Points Checked: {validator.total_points:,}")
    print(f"Runs Checked:   {len(validator.seen_runs)}")
    print(f"Total Errors:   {len(validator.errors)}")
    print(f"Total Warnings: {len(validator.warnings)}")
    print(f"Report Written: {report_file}")
    print("=" * 60)

    if not success:
        print("Validation Errors encountered:")
        for err in validator.errors[:10]:
            print(f"  - {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
