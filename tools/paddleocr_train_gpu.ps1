param(
    [string]$ConfigPath = "archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser\ser_vi_layoutxlm_finrecon_4field.yml"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "paddleocr_env.ps1")

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$Python = Join-Path $RepoRoot ".venvs\paddleocr-gpu\Scripts\python.exe"
$TrainScript = Join-Path $RepoRoot "external\PaddleOCR\tools\train.py"
$Config = Join-Path $RepoRoot $ConfigPath

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing PaddleOCR GPU Python env: $Python"
}
if (-not (Test-Path -LiteralPath $TrainScript)) {
    throw "Missing PaddleOCR train script: $TrainScript"
}
if (-not (Test-Path -LiteralPath $Config)) {
    throw "Missing PaddleOCR config: $Config"
}

& $Python $TrainScript -c $Config -o Global.use_gpu=True
