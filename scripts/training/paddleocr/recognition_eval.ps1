param(
    [string]$ConfigPath = "archive\prepared\mcocr2021_text_recognition_paddleocr\rec_svtr_lcnet_mcocr2021.yml",
    [string]$CheckpointPath = "",
    [switch]$UseGpu
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "env.ps1")

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")
$Python = Join-Path $RepoRoot ".venvs\paddleocr-gpu\Scripts\python.exe"
$EvalScript = Join-Path $RepoRoot "external\PaddleOCR\tools\eval.py"
$Config = Join-Path $RepoRoot $ConfigPath
$DatasetDir = Split-Path -Parent $Config
$Checkpoint = if ($CheckpointPath) {
    if ([System.IO.Path]::IsPathRooted($CheckpointPath)) { $CheckpointPath } else { Join-Path $RepoRoot $CheckpointPath }
} else {
    Join-Path $DatasetDir "output\rec_svtr_lcnet_mcocr2021\best_accuracy"
}

foreach ($path in @($Python, $EvalScript, $Config)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing required file: $path"
    }
}
if (-not (Test-Path -LiteralPath ($Checkpoint + ".pdparams"))) {
    throw "Missing checkpoint params: $Checkpoint.pdparams"
}

$gpuValue = if ($UseGpu) { "True" } else { "False" }
$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python $EvalScript -c $Config -o `
    Global.use_gpu=$gpuValue `
    Global.checkpoints="$Checkpoint"
$EvalExitCode = $LASTEXITCODE
$ErrorActionPreference = $PreviousErrorActionPreference
exit $EvalExitCode
