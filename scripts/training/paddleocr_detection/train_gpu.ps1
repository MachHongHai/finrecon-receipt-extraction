param(
    [string]$ConfigPath = "archive\prepared\mcocr2021_text_detection_paddleocr\det_mv3_db_mcocr2021.yml",
    [string]$RunName = "",
    [switch]$NoResume,
    [string]$CheckpointName = "latest"
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
$OutputDir = Join-Path $DatasetDir "output\det_db_mv3_mcocr2021_receipts_v2"
$ResumeCheckpoint = Join-Path $OutputDir $CheckpointName
$PretrainedParams = Join-Path $RepoRoot "archive\models\paddleocr\ch_ppocr_mobile_v2.0_det_train\best_accuracy.pdparams"

foreach ($path in @($Python, $TrainScript, $Config, $Validator, $Tracker)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing required file: $path"
    }
}
if (-not (Test-Path -LiteralPath $PretrainedParams)) {
    throw "Missing PaddleOCR DB detector pretrained checkpoint. Run: .\scripts\training\paddleocr_detection\download_det_pretrained.ps1"
}

New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
& $Python $Validator --dataset-dir $DatasetDir --report $ValidationReport
if ($LASTEXITCODE -ne 0) {
    throw "PaddleOCR detection dataset validation failed. See: $ValidationReport"
}

$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$Overrides = @("Global.use_gpu=True")
if (-not $NoResume -and (Test-Path -LiteralPath ($ResumeCheckpoint + ".pdparams"))) {
    Write-Host "Resuming detection training from: $ResumeCheckpoint"
    $Overrides += "Global.checkpoints=$ResumeCheckpoint"
} else {
    Write-Host "Starting detection fine-tune from config pretrained_model."
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
