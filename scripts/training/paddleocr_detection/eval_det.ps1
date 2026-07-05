param(
    [string]$ConfigPath = "archive\prepared\mcocr2021_text_detection_paddleocr\det_mv3_db_mcocr2021.yml",
    [ValidateSet("val", "test")]
    [string]$Split = "test",
    [switch]$UseGpu
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "..\paddleocr\env.ps1")

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")
$Python = Join-Path $RepoRoot ".venvs\paddleocr-gpu\Scripts\python.exe"
$EvalScript = Join-Path $RepoRoot "external\PaddleOCR\tools\eval.py"
$Config = if ([System.IO.Path]::IsPathRooted($ConfigPath)) {
    $ConfigPath
} else {
    Join-Path $RepoRoot $ConfigPath
}
$DatasetDir = Split-Path -Parent $Config
$Checkpoint = Join-Path $DatasetDir "output\det_mv3_db_mcocr2021\best_accuracy"
$LabelFile = Join-Path $DatasetDir "$Split.txt"

foreach ($path in @($Python, $EvalScript, $Config, $Checkpoint, $LabelFile)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing required file: $path"
    }
}

$gpuValue = if ($UseGpu) { "True" } else { "False" }
$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python $EvalScript -c $Config -o `
    Global.use_gpu=$gpuValue `
    Global.checkpoints="$Checkpoint" `
    Eval.dataset.label_file_list="[${LabelFile}]"
$EvalExitCode = $LASTEXITCODE
$ErrorActionPreference = $PreviousErrorActionPreference
exit $EvalExitCode
