# ==============================================================================
# TERRITORY INTELLIGENCE - ENVIRONMENT & SYSTEM HEALTH AUDIT SCRIPT
# ==============================================================================

$ErrorActionPreference = "Continue"
$RootDir = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $RootDir

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  TERRITORY INTELLIGENCE - SYSTEM HEALTH & READINESS AUDIT" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Root Directory: $RootDir" -ForegroundColor Gray
Write-Host "Timestamp     : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray

# 1. Python Environment Check
Write-Host "`n[1/7] Python Status:" -ForegroundColor Yellow
$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $pyInfo = & $VenvPython -c "import sys; print(f'Version: {sys.version.split()[0]} | Executable: {sys.executable}')"
    Write-Host "  [OK] $pyInfo" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] .venv\Scripts\python.exe not found at $VenvPython" -ForegroundColor Red
}

# 2. Java Environment Check
Write-Host "`n[2/7] Java Status:" -ForegroundColor Yellow
$javaHome = $env:JAVA_HOME
Write-Host "  JAVA_HOME: $javaHome" -ForegroundColor Gray
try {
    $javaVer = (java -version 2>&1 | Select-Object -First 1)
    Write-Host "  [OK] $javaVer" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] 'java' command not accessible in PATH directly: $_" -ForegroundColor Yellow
}

# 3. Spark & Core Packages Status
Write-Host "`n[3/7] PySpark & Core Packages Status:" -ForegroundColor Yellow
$pyCode = @"
import sys
packages = ['pyspark', 'h3', 'streamlit', 'pandas', 'plotly', 'folium', 'streamlit_folium', 'pyarrow']
for p in packages:
    try:
        mod = __import__(p)
        ver = getattr(mod, '__version__', 'available')
        print(f'  [OK] {p}: {ver}')
    except Exception as e:
        print(f'  [FAIL] {p}: {e}')
"@
& $VenvPython -c $pyCode

# 4. Required Files Check
Write-Host "`n[4/7] Required Project Files Status:" -ForegroundColor Yellow
$reqFiles = @(
    "config\settings.yaml",
    "dashboard\app.py",
    "dashboard\components\tables.py",
    "dashboard\components\maps.py",
    "src\pipeline.py",
    "src\spark_session.py",
    "src\cheat_detection.py",
    "src\territory_engine.py",
    "pytest.ini"
)
foreach ($f in $reqFiles) {
    $p = Join-Path $RootDir $f
    if (Test-Path $p) {
        Write-Host "  [OK] $f" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] Missing file: $f" -ForegroundColor Red
    }
}

# 5. Dataset Status
Write-Host "`n[5/7] Dataset Status:" -ForegroundColor Yellow
Write-Host "  Raw Datasets:" -ForegroundColor Gray
$rawFiles = @("gps_100k.csv", "gps_500k.csv", "gps_1m.csv", "gps_demo.csv")
foreach ($rf in $rawFiles) {
    $rp = Join-Path $RootDir "data\raw\$rf"
    if (Test-Path $rp) {
        $sizeMB = [math]::Round(((Get-Item $rp).Length / 1MB), 2)
        Write-Host "    [OK] data/raw/$rf ($sizeMB MB)" -ForegroundColor Green
    } else {
        Write-Host "    [WARN] data/raw/$rf (not found)" -ForegroundColor Yellow
    }
}

Write-Host "  Analytical Parquet Tables:" -ForegroundColor Gray
$pqTables = @(
    "current_ownership",
    "ownership_history",
    "zone_statistics",
    "contested_zones",
    "leaderboard",
    "run_anomalies",
    "claim_events",
    "eligible_points",
    "cleaned_points"
)
foreach ($pt in $pqTables) {
    $pp = Join-Path $RootDir "data\parquet\$pt"
    if (Test-Path $pp) {
        Write-Host "    [OK] data/parquet/$pt" -ForegroundColor Green
    } else {
        Write-Host "    [FAIL] Missing parquet table: data/parquet/$pt" -ForegroundColor Red
    }
}

# 6. Dashboard Readiness
Write-Host "`n[6/7] Dashboard Readiness:" -ForegroundColor Yellow
$DashboardApp = Join-Path $RootDir "dashboard\app.py"
if (Test-Path $DashboardApp) {
    Write-Host "  [OK] Entrypoint present: dashboard/app.py" -ForegroundColor Green
    $portCheck = Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue
    if ($portCheck) {
        $pids = ($portCheck | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
        Write-Host "  [ACTIVE] Port 8501 is actively listening (PID: $pids) -> http://localhost:8501" -ForegroundColor Cyan
    } else {
        Write-Host "  [READY] Port 8501 is available. Launch with: .\scripts\start_project.ps1" -ForegroundColor Green
    }
} else {
    Write-Host "  [FAIL] dashboard/app.py missing" -ForegroundColor Red
}

# 7. Automated Tests Status
Write-Host "`n[7/7] Automated Tests Availability:" -ForegroundColor Yellow
$testsDir = Join-Path $RootDir "tests"
if (Test-Path $testsDir) {
    $testFiles = Get-ChildItem -Path $testsDir -Filter "test_*.py"
    Write-Host "  [OK] Found $($testFiles.Count) test suites in tests/" -ForegroundColor Green
    Write-Host "  Run all tests using: & .\.venv\Scripts\python.exe -m pytest -q" -ForegroundColor Gray
} else {
    Write-Host "  [FAIL] tests/ directory missing" -ForegroundColor Red
}

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "  SYSTEM AUDIT COMPLETE" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
