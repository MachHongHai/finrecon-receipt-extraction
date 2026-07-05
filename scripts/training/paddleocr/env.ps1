$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")
$ProjectCache = Join-Path $RepoRoot ".cache"

$env:PPNLP_HOME = Join-Path $ProjectCache "paddlenlp"
$env:PADDLE_HOME = Join-Path $ProjectCache "paddle"
$env:HF_HOME = Join-Path $ProjectCache "huggingface"
$env:TORCH_HOME = Join-Path $ProjectCache "torch"
$env:XDG_CACHE_HOME = $ProjectCache
$env:PIP_CACHE_DIR = Join-Path $ProjectCache "pip"
$env:TEMP = Join-Path $ProjectCache "tmp"
$env:TMP = Join-Path $ProjectCache "tmp"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

foreach ($path in @(
    $env:PPNLP_HOME,
    $env:PADDLE_HOME,
    $env:HF_HOME,
    $env:TORCH_HOME,
    $env:PIP_CACHE_DIR,
    $env:TEMP
)) {
    if (-not (Test-Path -LiteralPath $path)) {
        New-Item -ItemType Directory -Path $path | Out-Null
    }
}
