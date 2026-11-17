# ==============================================================================
# TERRITORY INTELLIGENCE - LOCAL APPLICATION LAUNCH SCRIPT (WINDOWS)
# ==============================================================================

param (
    [int]$Port = 8501,
    [switch]$Help = $false
)

$ErrorActionPreference = "Continue"
$RootDir = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $RootDir

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  TERRITORY INTELLIGENCE - GEOSPATIAL BIG DATA ANALYTICS" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Location: $RootDir" -ForegroundColor Gray

if ($Help) {
    Write-Host @"

Usage:
  .\scripts\start_project.ps1 [-Port 8501]

Available Tools & Commands:
  - BI Dashboard:
      .\scripts\start_project.ps1 -Port 8501
  - System Health Check:
      .\scripts\check_project.ps1
  - Run Automated Tests:
      & .\.venv\Scripts\python.exe -m pytest -q
  - Spark Smoke Test:
      & .\.venv\Scripts\python.exe -m src.spark_session
  - Run Big Data Pipeline (if reprocessing is required):
      & .\.venv\Scripts\python.exe -m src.pipeline --input data/raw/gps_100k.csv

"@ -ForegroundColor White
    exit 0
}

# 1. Locate and check Virtual Environment
Write-Host "`n[1/6] Verifying Python Environment..." -ForegroundColor Yellow
$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "ERROR: Python virtual environment not found at $VenvPython" -ForegroundColor Red
    Write-Host "Please use the existing .venv virtual environment." -ForegroundColor Yellow
    exit 1
}
$pyVer = & $VenvPython -c "import sys; print(sys.version.split()[0])"
Write-Host "  Python Executable : $VenvPython" -ForegroundColor Gray
Write-Host "  Python Version    : $pyVer (OK)" -ForegroundColor Green

# 2. Verify Required Modules
Write-Host "`n[2/6] Verifying Required Packages..." -ForegroundColor Yellow
$packages = @("streamlit", "pyspark", "h3", "folium", "streamlit_folium", "plotly", "pyarrow", "pandas", "yaml")
$missing = @()
foreach ($pkg in $packages) {
    & $VenvPython -c "import $pkg" 2>$null
    if ($LASTEXITCODE -ne 0) {
        $missing += $pkg
    }
}
if ($missing.Count -gt 0) {
    Write-Host "ERROR: Missing required packages: $($missing -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "  All required packages verified: $($packages -join ', ') (OK)" -ForegroundColor Green

# 3. Check Dashboard Entry Point
Write-Host "`n[3/6] Verifying Dashboard Entry Point..." -ForegroundColor Yellow
$DashboardApp = Join-Path $RootDir "dashboard\app.py"
if (-not (Test-Path $DashboardApp)) {
    Write-Host "ERROR: Dashboard entrypoint not found at $DashboardApp" -ForegroundColor Red
    exit 1
}
Write-Host "  Dashboard entrypoint found: $DashboardApp (OK)" -ForegroundColor Green

# 4. Check Analytical Datasets
Write-Host "`n[4/6] Checking Analytical Parquet Datasets..." -ForegroundColor Yellow
$reqParquet = @("current_ownership", "ownership_history", "run_anomalies", "leaderboard", "zone_statistics", "contested_zones")
$missingParquet = @()
foreach ($t in $reqParquet) {
    $p = Join-Path $RootDir "data\parquet\$t"
    if (-not (Test-Path $p)) {
        $missingParquet += $t
    }
}
if ($missingParquet.Count -eq 0) {
    Write-Host "  Parquet tables present and ready for sub-second BI loading (OK)" -ForegroundColor Green
} else {
    Write-Host "  WARNING: Missing Parquet datasets: $($missingParquet -join ', ')" -ForegroundColor Yellow
    Write-Host "  Run 'python -m src.pipeline' to compile datasets if needed." -ForegroundColor Gray
}

# 5. Check Port Availability
Write-Host "`n[5/6] Checking Port $Port Availability..." -ForegroundColor Yellow
$existingConn = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($existingConn) {
    $pids = ($existingConn | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
    Write-Host "  NOTE: Port $Port is currently in use by PID(s): $pids" -ForegroundColor Cyan
    Write-Host "  If this is an existing project instance, access it directly at http://localhost:$Port" -ForegroundColor Gray
} else {
    Write-Host "  Port $Port is free and available (OK)" -ForegroundColor Green
}

# 6. Launch Streamlit Dashboard
Write-Host "`n[6/6] Launching Streamlit BI Platform..." -ForegroundColor Yellow
$AppUrl = "http://localhost:$Port"
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  APPLICATION URL: $AppUrl" -ForegroundColor Green
Write-Host "  Press Ctrl+C to terminate the dashboard server." -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

& $VenvPython -m streamlit run "$DashboardApp" --server.port $Port --server.address localhost
