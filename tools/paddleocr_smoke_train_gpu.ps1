param(
    [string]$SourceDir = "archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser",
    [string]$SmokeDir = "archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser_smoke",
    [int]$TrainDocs = 4,
    [int]$ValDocs = 2,
    [string]$RunName = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "paddleocr_env.ps1")

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$Python = Join-Path $RepoRoot ".venvs\paddleocr-gpu\Scripts\python.exe"
$TrainScript = Join-Path $RepoRoot "external\PaddleOCR\tools\train.py"
$Maker = Join-Path $RepoRoot "tools\make_paddleocr_smoke_dataset.py"
$Validator = Join-Path $RepoRoot "tools\validate_paddleocr_ser_dataset.py"
$Tracker = Join-Path $RepoRoot "tools\track_paddleocr_metrics.py"

$Source = Join-Path $RepoRoot $SourceDir
$Smoke = Join-Path $RepoRoot $SmokeDir
$Config = Join-Path $Smoke "ser_vi_layoutxlm_finrecon_4field.yml"
$ReportsDir = Join-Path $Smoke "reports"
$ResolvedRunName = if ($RunName) { $RunName } else { "smoke_" + (Get-Date -Format "yyyyMMdd_HHmmss") }
$ValidationReport = Join-Path $ReportsDir "paddleocr_ser_smoke_validation.json"
$LogPath = Join-Path $ReportsDir "$ResolvedRunName.log"
$JsonlPath = Join-Path $ReportsDir "$ResolvedRunName.metrics.jsonl"
$CsvPath = Join-Path $ReportsDir "$ResolvedRunName.metrics.csv"
$SummaryPath = Join-Path $ReportsDir "$ResolvedRunName.summary.json"

foreach ($path in @($Python, $TrainScript, $Maker, $Validator, $Tracker)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing required file: $path"
    }
}
if (-not (Test-Path -LiteralPath $Source)) {
    throw "Missing source PaddleOCR SER dataset: $Source"
}

& $Python $Maker --source-dir $Source --output-dir $Smoke --train-docs $TrainDocs --val-docs $ValDocs --test-docs 2 --batch-size 1 --clear --copy-mode hardlink
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create smoke dataset: $Smoke"
}

& $Python $Validator --dataset-dir $Smoke --report $ValidationReport
if ($LASTEXITCODE -ne 0) {
    throw "Smoke dataset validation failed. See: $ValidationReport"
}

$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python $TrainScript -c $Config -o Global.use_gpu=True 2>&1 | Tee-Object -FilePath $LogPath
$TrainExitCode = $LASTEXITCODE
$ErrorActionPreference = $PreviousErrorActionPreference

& $Python $Tracker --log $LogPath --run-name $ResolvedRunName --jsonl $JsonlPath --csv $CsvPath --summary $SummaryPath
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Metric tracking failed. Log is still available at: $LogPath"
}

Write-Host "Smoke log: $LogPath"
Write-Host "Metric CSV: $CsvPath"
Write-Host "Metric summary: $SummaryPath"
exit $TrainExitCode
