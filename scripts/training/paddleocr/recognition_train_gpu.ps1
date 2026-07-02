param(
    [string]$ConfigPath = "archive\prepared\mcocr2021_text_recognition_paddleocr\rec_svtr_lcnet_mcocr2021.yml",
    [string]$RunName = "",
    [string]$PretrainedModel = "",
    [int]$EpochNum = 0,
    [int]$BatchSize = 0,
    [double]$LearningRate = 0
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "env.ps1")

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")
$Python = Join-Path $RepoRoot ".venvs\paddleocr-gpu\Scripts\python.exe"
$TrainScript = Join-Path $RepoRoot "external\PaddleOCR\tools\train.py"
$Config = Join-Path $RepoRoot $ConfigPath
$DatasetDir = Split-Path -Parent $Config
$Validator = Join-Path $RepoRoot "scripts\datasets\validate_paddleocr_rec_dataset.py"
$Tracker = Join-Path $RepoRoot "scripts\training\paddleocr\track_metrics.py"
$ValidationReport = Join-Path $DatasetDir "reports\paddleocr_rec_validation.json"
$ReportsDir = Join-Path $DatasetDir "reports"
$ResolvedRunName = if ($RunName) { $RunName } else { "rec_train_" + (Get-Date -Format "yyyyMMdd_HHmmss") }
$LogPath = Join-Path $ReportsDir "$ResolvedRunName.log"
$JsonlPath = Join-Path $ReportsDir "$ResolvedRunName.metrics.jsonl"
$CsvPath = Join-Path $ReportsDir "$ResolvedRunName.metrics.csv"
$SummaryPath = Join-Path $ReportsDir "$ResolvedRunName.summary.json"

foreach ($path in @($Python, $TrainScript, $Config, $Validator, $Tracker)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing required file: $path"
    }
}

New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
& $Python $Validator --dataset-dir $DatasetDir --report $ValidationReport
if ($LASTEXITCODE -ne 0) {
    throw "PaddleOCR recognition dataset validation failed. See: $ValidationReport"
}

$Overrides = @("Global.use_gpu=True")
if ($PretrainedModel) {
    $Pretrained = if ([System.IO.Path]::IsPathRooted($PretrainedModel)) { $PretrainedModel } else { Join-Path $RepoRoot $PretrainedModel }
    $Overrides += "Global.pretrained_model=$Pretrained"
}
if ($EpochNum -gt 0) {
    $Overrides += "Global.epoch_num=$EpochNum"
    $Overrides += "Optimizer.lr.epochs=$EpochNum"
}
if ($BatchSize -gt 0) {
    $Overrides += "Train.loader.batch_size_per_card=$BatchSize"
}
if ($LearningRate -gt 0) {
    $Overrides += "Optimizer.lr.learning_rate=$LearningRate"
}

$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python $TrainScript -c $Config -o $Overrides 2>&1 | Tee-Object -FilePath $LogPath
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
