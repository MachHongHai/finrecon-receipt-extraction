param(
    [string]$ConfigPath = "archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser\ser_vi_layoutxlm_finrecon_4field.yml",
    [string]$RunName = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "..\paddleocr\env.ps1")

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")
$Python = Join-Path $RepoRoot ".venvs\paddleocr-gpu\Scripts\python.exe"
$TrainScript = Join-Path $RepoRoot "external\PaddleOCR\tools\train.py"
$Config = Join-Path $RepoRoot $ConfigPath
$DatasetDir = Split-Path -Parent $Config
$Validator = Join-Path $RepoRoot "scripts\datasets\validate_paddleocr_ser_dataset.py"
$Tracker = Join-Path $RepoRoot "scripts\training\kie_layoutxlm\track_metrics.py"
$ValidationReport = Join-Path $DatasetDir "reports\paddleocr_ser_validation.json"
$ReportsDir = Join-Path $DatasetDir "reports"
$ResolvedRunName = if ($RunName) { $RunName } else { "train_" + (Get-Date -Format "yyyyMMdd_HHmmss") }
$LogPath = Join-Path $ReportsDir "$ResolvedRunName.log"
$JsonlPath = Join-Path $ReportsDir "$ResolvedRunName.metrics.jsonl"
$CsvPath = Join-Path $ReportsDir "$ResolvedRunName.metrics.csv"
$SummaryPath = Join-Path $ReportsDir "$ResolvedRunName.summary.json"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing PaddleOCR GPU Python env: $Python"
}
if (-not (Test-Path -LiteralPath $TrainScript)) {
    throw "Missing PaddleOCR train script: $TrainScript"
}
if (-not (Test-Path -LiteralPath $Config)) {
    throw "Missing PaddleOCR config: $Config"
}
if (-not (Test-Path -LiteralPath $Validator)) {
    throw "Missing PaddleOCR SER validator: $Validator"
}
if (-not (Test-Path -LiteralPath $Tracker)) {
    throw "Missing PaddleOCR metric tracker: $Tracker"
}

New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
& $Python $Validator --dataset-dir $DatasetDir --report $ValidationReport
if ($LASTEXITCODE -ne 0) {
    throw "PaddleOCR SER dataset validation failed. See: $ValidationReport"
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
Write-Host "Train log: $LogPath"
Write-Host "Metric CSV: $CsvPath"
Write-Host "Metric summary: $SummaryPath"
exit $TrainExitCode
