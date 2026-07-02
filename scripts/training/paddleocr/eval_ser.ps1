param(
    [string]$ConfigPath = "archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser\ser_vi_layoutxlm_finrecon_4field.yml",
    [ValidateSet("train", "val", "test")]
    [string]$Split = "test",
    [switch]$UseGpu
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "env.ps1")

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")
$Python = Join-Path $RepoRoot ".venvs\paddleocr-gpu\Scripts\python.exe"
$EvalScript = Join-Path $RepoRoot "external\PaddleOCR\tools\eval.py"
$Config = Join-Path $RepoRoot $ConfigPath
$DatasetDir = Split-Path -Parent $Config
$Checkpoint = Join-Path $DatasetDir "output\ser_vi_layoutxlm_finrecon_4field\best_accuracy"
$LabelFile = Join-Path $DatasetDir "$Split.json"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing PaddleOCR GPU Python env: $Python"
}
if (-not (Test-Path -LiteralPath $EvalScript)) {
    throw "Missing PaddleOCR eval script: $EvalScript"
}
if (-not (Test-Path -LiteralPath $Config)) {
    throw "Missing PaddleOCR config: $Config"
}
if (-not (Test-Path -LiteralPath $Checkpoint)) {
    throw "Missing best checkpoint: $Checkpoint"
}
if (-not (Test-Path -LiteralPath $LabelFile)) {
    throw "Missing split label file: $LabelFile"
}

$gpuValue = if ($UseGpu) { "True" } else { "False" }
$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python $EvalScript -c $Config -o `
    Global.use_gpu=$gpuValue `
    Architecture.Backbone.checkpoints="$Checkpoint" `
    Eval.dataset.label_file_list="[${LabelFile}]"
$EvalExitCode = $LASTEXITCODE
$ErrorActionPreference = $PreviousErrorActionPreference
exit $EvalExitCode
