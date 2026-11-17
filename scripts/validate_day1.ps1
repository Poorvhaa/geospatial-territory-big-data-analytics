<#
.SYNOPSIS
    Day 1 End-to-End Validation Pipeline for Territory Control Project.
.DESCRIPTION
    Executes dataset generation (1K and 100K), streaming data validation,
    Pytest test suite, and local PySpark DataFrame/Parquet smoke test.
#>

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found at $VenvPython. Please run scripts/setup.ps1 first."
    exit 1
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  DAY 1 END-TO-END VALIDATION PIPELINE" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Generate 1,000 Demo Records
Write-Host "`n[Step 1/6] Generating 1,000 GPS Demo Records..." -ForegroundColor Yellow
& $VenvPython -m src.data_generator --records 1000 --runners 25 --seed 42 --output data/raw/gps_demo.csv
if ($LASTEXITCODE -ne 0) {
    Write-Error "Data generator failed for 1,000 records."
    exit 1
}

# 2. Validate 1,000 Demo Records
Write-Host "`n[Step 2/6] Running Streaming Validation on 1,000 Demo Records..." -ForegroundColor Yellow
& $VenvPython -m src.validation --input data/raw/gps_demo.csv --expected-records 1000 --report data/reports/day1_validation.json
if ($LASTEXITCODE -ne 0) {
    Write-Error "Streaming validation failed for 1,000 records."
    exit 1
}

# 3. Run Pytest Suite
Write-Host "`n[Step 3/6] Running Pytest Suite (Unit Tests)..." -ForegroundColor Yellow
& $VenvPython -m pytest tests -v
if ($LASTEXITCODE -ne 0) {
    Write-Error "Pytest test suite failed."
    exit 1
}

# 4. Run PySpark Smoke Test
Write-Host "`n[Step 4/6] Running PySpark DataFrame & Parquet Smoke Test..." -ForegroundColor Yellow
& $VenvPython -m src.spark_session
if ($LASTEXITCODE -ne 0) {
    Write-Error "PySpark smoke test failed."
    exit 1
}

# 5. Generate 100,000 Records
Write-Host "`n[Step 5/6] Generating 100,000 GPS Records (Scalability Ingestion)..." -ForegroundColor Yellow
& $VenvPython -m src.data_generator --records 100000 --runners 250 --seed 42 --output data/raw/gps_100k.csv
if ($LASTEXITCODE -ne 0) {
    Write-Error "Data generator failed for 100,000 records."
    exit 1
}

# 6. Validate 100,000 Records
Write-Host "`n[Step 6/6] Running Streaming Validation on 100,000 Records..." -ForegroundColor Yellow
& $VenvPython -m src.validation --input data/raw/gps_100k.csv --expected-records 100000 --report data/reports/day1_validation_100k.json
if ($LASTEXITCODE -ne 0) {
    Write-Error "Streaming validation failed for 100,000 records."
    exit 1
}

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "  ALL DAY 1 ACCEPTANCE CRITERIA SUCCESSFULLY PASSED!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
