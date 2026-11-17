# Day 1 Execution Results & Verification Report

**Project:** Real-Time Territory Control and Hotspot Analysis Using Geospatial Big Data  
**Date of Execution:** 2026-10-26  
**Host Machine:** Windows 11 (64-bit), 16 GB RAM, Java JDK 23 (build 23.0.2+7-58), Python 3.11.5 (Anaconda 64-bit isolated in `.venv`)

---

## 1. Verified Dependency & Runtime Versions

| Package / Tool | Expected Version Constraint | Actual Installed Version | Status |
|---|---|---|---|
| **Python** | 3.11 (64-bit) | 3.11.5 (AMD64) | PASSED |
| **Java JDK** | 17+ (64-bit) | 23.0.2+7-58 (Oracle HotSpot 64-Bit Server VM) | PASSED |
| **Apache PySpark** | >=4.2.0, <4.3.0 | 4.2.0 | PASSED |
| **Uber H3** | >=4.0.0, <5.0.0 | 4.5.0 | PASSED |
| **Pandas** | >=2.0.0 | 3.1.0 | PASSED |
| **NumPy** | >=1.24.0, <3.0.0 | 2.4.6 | PASSED |
| **PyArrow** | >=18.0.0 | 26.0.0 | PASSED |
| **PyYAML** | >=6.0 | 6.0.3 | PASSED |
| **Pytest** | >=8.0.0 | 9.1.1 | PASSED |
| **Streamlit** | >=1.35.0 | 1.66.1 | PASSED |
| **Plotly** | >=5.20.0 | 7.1.0 | PASSED |
| **Folium** | >=0.16.0 | 0.20.0 | PASSED |
| **Streamlit-Folium** | >=0.20.0 | 0.27.4 | PASSED |

---

## 2. Dataset Generation Counts & Ground Truth Distributions

### 2.1 Demo Dataset: 1,000 GPS Points (Seed 42)
- **Command Executed:**
  ```powershell
  .\.venv\Scripts\python.exe -m src.data_generator --records 1000 --runners 25 --seed 42 --output data/raw/gps_demo.csv
  ```
- **Generated File Size:** `113.21 KB` (115,926 bytes)
- **Metadata Output:** `data/raw/runs_metadata_gps_demo.csv` and `data/raw/runs_metadata.csv`
- **Total Points:** `1,000` (Exact)
- **Total Runs:** `25` (Minimum points per run: 3, observed range: 20 to 60)
- **Total Unique Runners:** `25`
- **Scenario Breakdown:**

| Scenario Type | Target Run % | Actual Runs | Actual Run % | Actual Points | Points % | Mean Speed (km/h) |
|---|---|---|---|---|---|---|
| `normal_run` | 55% | 9 | 36.0% | 375 | 37.5% | 8.29 km/h |
| `fast_run` | 10% | 5 | 20.0% | 149 | 14.9% | 15.66 km/h |
| `walking` | 10% | 3 | 12.0% | 154 | 15.4% | 4.50 km/h |
| `driving` | 10% | 4 | 16.0% | 218 | 21.8% | 54.93 km/h |
| `gps_spoofing` | 10% | 2 | 8.0% | 40 | 4.0% | Teleport Anomaly |
| `gps_noise` | 5% | 2 | 8.0% | 64 | 6.4% | Jitter Anomaly |
| **Total** | **100%** | **25** | **100%** | **1,000** | **100%** | — |

*Note: In the small 25-run demo, all 6 scenario categories are guaranteed representation.*

---

### 2.2 Scalability Dataset: 100,000 GPS Points (Seed 42)
- **Command Executed:**
  ```powershell
  .\.venv\Scripts\python.exe -m src.data_generator --records 100000 --runners 250 --seed 42 --output data/raw/gps_100k.csv
  ```
- **Generated File Size:** `11,489.06 KB` (11.76 MB)
- **Metadata Output:** `data/raw/runs_metadata_gps_100k.csv`
- **Total Points:** `100,000` (Exact)
- **Total Runs:** `1,250`
- **Total Unique Runners:** `250`
- **Scenario Breakdown:**

| Scenario Type | Target Run % | Actual Runs | Actual Run % | Actual Points | Points % |
|---|---|---|---|---|---|
| `normal_run` | 55% | 685 | 54.8% | 54,767 | 54.8% |
| `fast_run` | 10% | 126 | 10.1% | 9,967 | 10.0% |
| `walking` | 10% | 123 | 9.8% | 9,844 | 9.8% |
| `driving` | 10% | 139 | 11.1% | 11,394 | 11.4% |
| `gps_spoofing` | 10% | 107 | 8.6% | 8,497 | 8.5% |
| `gps_noise` | 5% | 70 | 5.6% | 5,531 | 5.5% |
| **Total** | **100%** | **1,250** | **100%** | **100,000** | **100%** |

- **Anomalies Detected by Streaming Validator:**
  - Spoofing Jumps: `214` impossible teleportations detected outside study radius.
  - Noise Spikes: `253` isolated multipath reflection spikes detected.

---

## 3. Streaming Data Validation Results

### 3.1 Demo Validation (1,000 Records)
- **Command:** `.\.venv\Scripts\python.exe -m src.validation --input data/raw/gps_demo.csv --expected-records 1000 --report data/reports/day1_validation.json`
- **Report File:** `data/reports/day1_validation.json`
- **Errors Encountered:** `0`
- **Warnings Encountered:** `0`
- **Integrity Checks:**
  - [x] Schema & Column Ordering: Matched exact 12 columns.
  - [x] ISO 8601 UTC Timestamps: Parseable with `Z` suffix.
  - [x] Temporal Monotonicity: Strictly increasing timestamps per run ($\Delta t \ge 3\text{ s}$).
  - [x] Distance Consistency: Cumulative physical distance is non-decreasing.
  - [x] Metadata Consistency: Matches `runs_metadata_gps_demo.csv`.

### 3.2 100K Dataset Validation (100,000 Records)
- **Command:** `.\.venv\Scripts\python.exe -m src.validation --input data/raw/gps_100k.csv --expected-records 100000 --report data/reports/day1_validation_100k.json`
- **Report File:** `data/reports/day1_validation_100k.json`
- **Errors Encountered:** `0`
- **Warnings Encountered:** `0`
- **Status:** **PASSED**

---

## 4. Pytest Automated Test Results

- **Command:** `.\.venv\Scripts\python.exe -m pytest tests -v`
- **Test Summary:** `19 passed, 0 failed in 46.08s`

```
tests/test_generator.py::test_generator_exact_point_count PASSED         [  5%]
tests/test_generator.py::test_generator_reproducibility PASSED           [ 10%]
tests/test_generator.py::test_generator_different_seeds PASSED           [ 15%]
tests/test_generator.py::test_all_six_scenarios_present PASSED           [ 21%]
tests/test_generator.py::test_per_run_strictly_increasing_timestamps PASSED [ 26%]
tests/test_generator.py::test_cumulative_distance_nondecreasing PASSED   [ 31%]
tests/test_generator.py::test_metadata_consistency PASSED                [ 36%]
tests/test_generator.py::test_streaming_validator_passes_valid_dataset PASSED [ 42%]
tests/test_generator.py::test_validator_rejects_corrupted_data PASSED    [ 47%]
tests/test_geo_utils.py::test_haversine_zero_distance PASSED             [ 52%]
tests/test_geo_utils.py::test_haversine_symmetry PASSED                  [ 57%]
tests/test_geo_utils.py::test_haversine_known_meridian_distance PASSED   [ 63%]
tests/test_geo_utils.py::test_destination_point_zero_distance PASSED     [ 68%]
tests/test_geo_utils.py::test_destination_point_due_north PASSED         [ 73%]
tests/test_geo_utils.py::test_calculate_bearing PASSED                   [ 78%]
tests/test_geo_utils.py::test_h3_cell_generation_and_validation PASSED   [ 84%]
tests/test_geo_utils.py::test_h3_smoke_test PASSED                       [ 89%]
tests/test_spark.py::test_spark_session_creation_and_teardown PASSED     [ 94%]
tests/test_spark.py::test_spark_smoke_test_execution PASSED              [100%]
```

---

## 5. PySpark Smoke Test Verification

- **Command:** `.\.venv\Scripts\python.exe -m src.spark_session`
- **Spark Version:** `4.2.0`
- **Cluster Master:** `local[2]`
- **Driver Memory:** `2g`
- **Shuffle Partitions:** `4`
- **Results:**
  - DataFrame Created: 10 rows
  - Count Computed: `10`
  - Aggregation Computed:
    - `avg_speed_kmh`: `19.33`
    - `max_speed_kmh`: `62.3`
    - `min_speed_kmh`: `4.1`
  - Parquet Written: `data/parquet/smoke_test/`
  - Parquet Read: 10 rows successfully read back
  - Verified Aggregation on Read: `19.33 km/h`
  - Spark Session Cleanly Stopped: Yes
  - Status: **PASSED**

---

## 6. Setup Issues Discovered & Applied Fixes

### Issue 1: Disk Space on Drive C: During Pip Wheel Caching
- **Symptom:** Pip threw `[Errno 28] No space left on device` because Drive C: had < 200 MB free.
- **Root Cause:** Pip caches and extracts 450 MB PySpark wheels into `%TEMP%` and `%LOCALAPPDATA%\pip\cache` on C:.
- **Fix Applied:** Purged legacy pip cache, redirected `$env:TEMP`, `$env:TMP`, and `--cache-dir` to `D:\pip_cache` and `D:\tmp` on Drive D: (100 GB free).

### Issue 2: PySpark Worker Python Version Mismatch
- **Symptom:** Spark worker threw `AttributeError: module 'importlib.resources' has no attribute 'files'`.
- **Root Cause:** When `PYSPARK_PYTHON` was unset, Spark defaulted to Python 3.8 installed globally on the Windows PATH instead of the isolated Python 3.11 in `.venv`.
- **Fix Applied:** Added automatic `os.environ["PYSPARK_PYTHON"] = sys.executable` and `os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable` directly in `src/spark_session.py` and PowerShell scripts.

### Issue 3: Windows Native File System & Winutils Check
- **Symptom:** `UnsatisfiedLinkError: org.apache.hadoop.io.nativeio.NativeIO$Windows.access0`.
- **Root Cause:** Hadoop 3.5 requires `winutils.exe` and `hadoop.dll` on Windows to check file permissions when executing `df.write.parquet()`.
- **Fix Applied:** Configured `RawLocalFileSystem` and placed standard 64-bit `winutils.exe` and `hadoop.dll` under `d:\BDA\hadoop\bin`. Automated detection was added to `src/spark_session.py` to auto-configure `HADOOP_HOME` and `PATH` automatically across all execution contexts.

---

## 7. Day 2 Readiness Confirmation

The Day 1 foundation is completely verified and operational:
1. Reusable, reproducible GPS generator supports 1K, 100K, 500K, and 1M records.
2. Ground-truth fraud scenarios (driving, spoofing, noise) are reliably injected for Day 2 detection.
3. H3 v4 API integration and Haversine distance functions are tested and validated.
4. PySpark 4.2 cluster initialization and Parquet Lakehouse I/O roundtrip are verified on Windows 11.
