# PowerShell Script to Execute Big Data Scaling Benchmarks (Day 4)
param (
    [string[]]$Scales = @("100k", "500k"),
    [string]$OutputDir = "data/reports"
)

$ErrorActionPreference = "Stop"
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  GEOSPATIAL BIG DATA BENCHMARKING SUITE (DAY 4)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Dataset Scales: $($Scales -join ', ')" -ForegroundColor Yellow
Write-Host "Reports Directory: $OutputDir" -ForegroundColor Yellow

# Locate virtual environment python
$VenvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $VenvPython = "python"
}

Write-Host "Using Python: $VenvPython" -ForegroundColor Gray

$ScaleArgs = $Scales -join ' '
& $VenvPython -m src.benchmark --scales $Scales --output-dir $OutputDir

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nBenchmarking completed successfully!" -ForegroundColor Green
    Write-Host "Reports generated:" -ForegroundColor Green
    Write-Host "  - CSV: $OutputDir/benchmark_results.csv" -ForegroundColor White
    Write-Host "  - JSON: $OutputDir/benchmark_results.json" -ForegroundColor White
} else {
    Write-Host "`nBenchmarking encountered errors. Exit code: $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}
