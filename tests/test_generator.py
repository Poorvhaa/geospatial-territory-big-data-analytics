"""Unit tests for the synthetic GPS data generator and streaming validator."""

import csv
from pathlib import Path
import pytest

from src.data_generator import (
    CSV_COLUMNS,
    METADATA_COLUMNS,
    SCENARIO_PROPORTIONS,
    generate_dataset,
)
from src.validation import StreamingValidator


@pytest.fixture
def temp_demo_dataset(tmp_path: Path):
    """Generate a small 1000-row dataset in a temporary directory."""
    csv_file = tmp_path / "test_gps_demo.csv"
    meta_file = tmp_path / "test_runs_metadata.csv"
    summary = generate_dataset(
        records=1000,
        runners=25,
        seed=42,
        output_path=csv_file,
        metadata_path=meta_file,
    )
    return {
        "csv_file": csv_file,
        "meta_file": meta_file,
        "summary": summary,
        "tmp_path": tmp_path,
    }


def test_generator_exact_point_count(temp_demo_dataset):
    """Generator must output exactly the requested number of records."""
    csv_file = temp_demo_dataset["csv_file"]
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    assert header == CSV_COLUMNS
    assert len(rows) == 1000


def test_generator_reproducibility(tmp_path: Path):
    """Two generation runs with seed 42 must yield identical files."""
    f1 = tmp_path / "run1.csv"
    f2 = tmp_path / "run2.csv"

    generate_dataset(records=100, runners=10, seed=42, output_path=f1)
    generate_dataset(records=100, runners=10, seed=42, output_path=f2)

    assert f1.read_text(encoding="utf-8") == f2.read_text(encoding="utf-8")


def test_generator_different_seeds(tmp_path: Path):
    """Different seeds must produce different data points."""
    f1 = tmp_path / "seed42.csv"
    f2 = tmp_path / "seed99.csv"

    generate_dataset(records=100, runners=10, seed=42, output_path=f1)
    generate_dataset(records=100, runners=10, seed=99, output_path=f2)

    assert f1.read_text(encoding="utf-8") != f2.read_text(encoding="utf-8")


def test_all_six_scenarios_present(temp_demo_dataset):
    """All 6 scenario categories must appear in the demo dataset."""
    summary = temp_demo_dataset["summary"]
    scenario_pts = summary["scenario_points"]
    for sc in SCENARIO_PROPORTIONS.keys():
        assert scenario_pts.get(sc, 0) > 0, f"Scenario {sc} was not generated"


def test_per_run_strictly_increasing_timestamps(temp_demo_dataset):
    """Timestamps must strictly increase within each individual run."""
    csv_file = temp_demo_dataset["csv_file"]
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        runs_timestamps = {}
        for r in reader:
            run_id = r["run_id"]
            ts = r["timestamp"]
            if run_id not in runs_timestamps:
                runs_timestamps[run_id] = []
            runs_timestamps[run_id].append(ts)

    for run_id, timestamps in runs_timestamps.items():
        assert len(timestamps) >= 3, f"Run {run_id} has < 3 points"
        # Check strict ordering and uniqueness
        for i in range(len(timestamps) - 1):
            assert timestamps[i] < timestamps[i + 1], (
                f"Run {run_id} timestamp out of order: {timestamps[i]} >= {timestamps[i + 1]}"
            )


def test_cumulative_distance_nondecreasing(temp_demo_dataset):
    """distance_m must be non-decreasing within each run."""
    csv_file = temp_demo_dataset["csv_file"]
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        runs_distances = {}
        for r in reader:
            run_id = r["run_id"]
            dist = float(r["distance_m"])
            if run_id not in runs_distances:
                runs_distances[run_id] = []
            runs_distances[run_id].append(dist)

    for run_id, dists in runs_distances.items():
        assert dists[0] == 0.0 or dists[0] >= 0.0
        for i in range(len(dists) - 1):
            assert dists[i + 1] >= dists[i], (
                f"Run {run_id} distance decreased: {dists[i]} -> {dists[i + 1]}"
            )


def test_metadata_consistency(temp_demo_dataset):
    """Metadata CSV must match the generated data exactly."""
    meta_file = temp_demo_dataset["meta_file"]
    with open(meta_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        meta_rows = list(reader)

    assert len(meta_rows) > 0
    total_meta_points = sum(int(r["point_count"]) for r in meta_rows)
    assert total_meta_points == 1000


def test_streaming_validator_passes_valid_dataset(temp_demo_dataset):
    """Validator must return True with zero errors for valid data."""
    csv_file = temp_demo_dataset["csv_file"]
    meta_file = temp_demo_dataset["meta_file"]

    validator = StreamingValidator(
        csv_path=csv_file,
        metadata_path=meta_file,
        expected_records=1000,
    )
    success = validator.process_file()
    assert success is True
    assert len(validator.errors) == 0


def test_validator_rejects_corrupted_data(tmp_path: Path):
    """Validator must catch schema errors, bad timestamps, or missing values."""
    bad_csv = tmp_path / "corrupted.csv"
    with open(bad_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # Missing column in header
        writer.writerow(["run_id", "runner_id", "timestamp"])
        writer.writerow(["run_0001", "runner_001", "invalid_time"])

    validator = StreamingValidator(csv_path=bad_csv)
    success = validator.process_file()
    assert success is False
    assert len(validator.errors) > 0
