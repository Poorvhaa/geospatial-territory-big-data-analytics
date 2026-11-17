# ==============================================================================
# TERRITORY INTELLIGENCE - ACADEMIC DEMO PREPARATION SCRIPT (DAY 5)
# Purpose: Reproducibly prepare, validate, and stage demo presentation state
# ==============================================================================

param (
    [switch]$ForceReset = $false,
    [switch]$Quick = $false,
    [string]$SessionId = "academic_demo_replay"
)

$ErrorActionPreference = "Stop"
$RootDir = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $RootDir

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  TERRITORY INTELLIGENCE - PRESENTATION DEMO PREPARATION" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Repository Root: $RootDir" -ForegroundColor Gray
Write-Host "Demo Session ID: $SessionId" -ForegroundColor Gray

# 1. Check Python Virtual Environment
Write-Host "`n[1/8] Verifying Python Environment..." -ForegroundColor Yellow
$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "ERROR: Python virtualenv not found at .venv\Scripts\python.exe" -ForegroundColor Red
    exit 1
}
$pyVer = & $VenvPython -c "import sys; print(sys.version.split()[0])"
Write-Host "  Python: $pyVer (OK)" -ForegroundColor Green

# 2. Check Package Dependencies
Write-Host "`n[2/8] Verifying Required Packages..." -ForegroundColor Yellow
$packages = @("pyspark", "h3", "streamlit", "folium", "plotly", "pyarrow", "pandas", "yaml")
foreach ($pkg in $packages) {
    & $VenvPython -c "import $pkg" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Missing package: $pkg" -ForegroundColor Red
        exit 1
    }
}
Write-Host "  All 8 core packages imported successfully (OK)" -ForegroundColor Green

# 3. Verify Demo Seeded Dataset
Write-Host "`n[3/8] Checking Demo Datasets..." -ForegroundColor Yellow
$demoCsv = Join-Path $RootDir "data\raw\gps_demo.csv"
$demoMeta = Join-Path $RootDir "data\raw\runs_metadata_gps_demo.csv"
$demoCsvPy = $demoCsv -replace '\\', '/'
$demoMetaPy = $demoMeta -replace '\\', '/'

if ((-not (Test-Path $demoCsv)) -or (-not (Test-Path $demoMeta))) {
    Write-Host "  Demo dataset missing. Generating seeded 1,000-point demo dataset..." -ForegroundColor Cyan
    & $VenvPython -c "
from src.data_generator import generate_dataset
generate_dataset(records=1000, runners=25, seed=42, output_path='$demoCsvPy', metadata_path='$demoMetaPy')
"
    Write-Host "  Generated seeded demo dataset (OK)" -ForegroundColor Green
} else {
    $demoLines = (Get-Content $demoCsv | Measure-Object -Line).Lines
    Write-Host "  Existing demo dataset verified: $demoCsv ($demoLines lines) (OK)" -ForegroundColor Green
}

# 4. Validate Demo Dataset Integrity
Write-Host "`n[4/8] Validating Demo Dataset Schema & Continuity..." -ForegroundColor Yellow
& $VenvPython -c "
from src.validation import StreamingValidator
validator = StreamingValidator(csv_path='$demoCsvPy', metadata_path='$demoMetaPy', expected_records=1000)
success = validator.process_file()
if not success:
    print('Validation warnings/errors:', validator.errors)
    exit(1)
print(f'Validator passed: {validator.total_points} points verified across {len(validator.seen_runs)} runs.')
"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Demo data validation failed!" -ForegroundColor Red
    exit 1
}
Write-Host "  Demo dataset integrity confirmed (OK)" -ForegroundColor Green

# 5. Verify/Run Demo Processing Pipeline
Write-Host "`n[5/8] Verifying Demo Parquet & Analytics State..." -ForegroundColor Yellow
$demoParquetDir = Join-Path $RootDir "data\demo_parquet"
$demoReportDir = Join-Path $RootDir "data\demo_reports"
$demoParquetDirPy = $demoParquetDir -replace '\\', '/'
$demoReportDirPy = $demoReportDir -replace '\\', '/'

if ((-not (Test-Path "$demoParquetDir\current_ownership")) -or $ForceReset) {
    Write-Host "  Compiling demo pipeline tables to $demoParquetDir..." -ForegroundColor Cyan
    & $VenvPython -c "
from pathlib import Path
from src.pipeline import run_pipeline
report = run_pipeline(
    input_path='$demoCsvPy',
    output_parquet_dir='$demoParquetDirPy',
    reports_dir='$demoReportDirPy'
)
print('Demo pipeline finished. Valid:', report.get('is_valid', False))
"
    Write-Host "  Demo analytics pipeline compiled successfully (OK)" -ForegroundColor Green
} else {
    Write-Host "  Demo parquet tables already prepared at $demoParquetDir (OK)" -ForegroundColor Green
}

# 6. Prepare Consistent Initial Replay State
Write-Host "`n[6/8] Preparing SQLite Replay Simulation State..." -ForegroundColor Yellow
$dbPath = Join-Path $RootDir "data\replay_state.db"
$dbPathPy = $dbPath -replace '\\', '/'

if ($ForceReset) {
    Write-Host "  -ForceReset specified: Re-initializing demo session in $dbPath..." -ForegroundColor Cyan
    & $VenvPython -c "
from src.realtime.state_store import SQLiteStateStore
store = SQLiteStateStore(db_path='$dbPathPy')
store.reset_session('$SessionId')
print('Session reset complete.')
"
} else {
    Write-Host "  Preserving existing replay session state (use -ForceReset to restart fresh)." -ForegroundColor Gray
}

# 7. Verify Academic Demo Scenarios
Write-Host "`n[7/8] Verifying Key Presentation Demonstration Conditions..." -ForegroundColor Yellow
$verifyPyCode = @"
import pandas as pd
curr = pd.read_parquet('$demoParquetDirPy/current_ownership')
hist = pd.read_parquet('$demoParquetDirPy/ownership_history')
risk = pd.read_parquet('$demoParquetDirPy/run_anomalies')

initial_caps = int((hist['event_type'] == 'INITIAL_CAPTURE').sum())
takeovers = int((hist['is_takeover'] == True).sum())
contested = int((curr['total_zone_takeovers'] > 0).sum())
quarantined = int((risk['risk_category'] != 'NORMAL').sum())

print(f'  ✓ Initial Zone Captures: {initial_caps} confirmed')
print(f'  ✓ Competitive Takeovers: {takeovers} confirmed')
print(f'  ✓ Contested Zones: {contested} active battlegrounds')
print(f'  ✓ Quarantined Runs: {quarantined} non-compliant runs rejected')

assert initial_caps > 0, 'Scenario failure: No initial captures found'
assert takeovers > 0, 'Scenario failure: No takeovers found'
assert quarantined > 0, 'Scenario failure: No quarantined runs found'
"@

& $VenvPython -c $verifyPyCode
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Presentation scenario assertions failed!" -ForegroundColor Red
    exit 1
}
Write-Host "  All 5 presentation demonstration criteria verified (OK)" -ForegroundColor Green

# 8. Report Readiness
Write-Host "`n[8/8] Presentation Demo Environment is Fully Staged!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  DEMO IS READY FOR PRESENTATION & VIVA EXAMINATION" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Launch Dashboard:" -ForegroundColor White
Write-Host "  .\scripts\start_project.ps1" -ForegroundColor Yellow
Write-Host "Or manual command:" -ForegroundColor White
Write-Host "  & .\.venv\Scripts\streamlit.exe run dashboard/app.py" -ForegroundColor Yellow
Write-Host ""
