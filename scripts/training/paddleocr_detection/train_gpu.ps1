param(
    [string]$ConfigPath = "archive\prepared\mcocr2021_text_detection_paddleocr\det_mv3_db_mcocr2021.yml",
    [string]$RunName = "",
    [switch]$NoResume
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "..\paddleocr\env.ps1")

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")
$Python = Join-Path $RepoRoot ".venvs\paddleocr-gpu\Scripts\python.exe"
$TrainScript = Join-Path $RepoRoot "external\PaddleOCR\tools\train.py"
$Config = if ([System.IO.Path]::IsPathRooted($ConfigPath)) {
    $ConfigPath
} else {
    Join-Path $RepoRoot $ConfigPath
}
$DatasetDir = Split-Path -Parent $Config
$Validator = Join-Path $RepoRoot "scripts\datasets\validate_paddleocr_det_dataset.py"
$Tracker = Join-Path $RepoRoot "scripts\training\paddleocr_detection\track_det_metrics.py"
$ReportsDir = Join-Path $DatasetDir "reports"
$ResolvedRunName = if ($RunName) { $RunName } else { "det_train_" + (Get-Date -Format "yyyyMMdd_HHmmss") }
$ValidationReport = Join-Path $ReportsDir "det_validation_report.json"
$LogPath = Join-Path $ReportsDir "$ResolvedRunName.log"
$JsonlPath = Join-Path $ReportsDir "$ResolvedRunName.metrics.jsonl"
$CsvPath = Join-Path $ReportsDir "$ResolvedRunName.metrics.csv"
$SummaryPath = Join-Path $ReportsDir "$ResolvedRunName.summary.json"
$LatestCheckpoint = Join-Path $DatasetDir "output\det_mv3_db_mcocr2021\latest"

foreach ($path in @($Python, $TrainScript, $Config, $Validator, $Tracker)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing required file: $path"
    }
}

New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
& $Python $Validator --dataset-dir $DatasetDir --report $ValidationReport
if ($LASTEXITCODE -ne 0) {
    throw "PaddleOCR detection dataset validation failed. See: $ValidationReport"
}

$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$Overrides = @("Global.use_gpu=True")
if (-not $NoResume -and (Test-Path -LiteralPath ($LatestCheckpoint + ".pdparams"))) {
    Write-Host "Resuming detection training from: $LatestCheckpoint"
    $Overrides += "Global.checkpoints=$LatestCheckpoint"
} else {
    Write-Host "Starting detection training from config pretrained_model."
}
& $Python $TrainScript -c $Config -o @Overrides 2>&1 | Tee-Object -FilePath $LogPath
$TrainExitCode = $LASTEXITCODE
$ErrorActionPreference = $PreviousErrorActionPreference

& $Python $Tracker --log $LogPath --run-name $ResolvedRunName --jsonl $JsonlPath --csv $CsvPath --summary $SummaryPath
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Detection metric tracking failed. Log is still available at: $LogPath"
}
Write-Host "Detection train log: $LogPath"
Write-Host "Detection metric CSV: $CsvPath"
Write-Host "Detection metric summary: $SummaryPath"
exit $TrainExitCode
