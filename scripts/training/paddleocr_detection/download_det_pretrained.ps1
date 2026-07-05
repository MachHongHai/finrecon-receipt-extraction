param(
    [string]$Url = "https://paddleocr.bj.bcebos.com/pretrained/MobileNetV3_large_x0_5_pretrained.pdparams",
    [string]$OutputPath = "archive\models\paddleocr\MobileNetV3_large_x0_5_pretrained.pdparams"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "..\paddleocr\env.ps1")

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")
$Target = if ([System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath
} else {
    Join-Path $RepoRoot $OutputPath
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
if (Test-Path -LiteralPath $Target) {
    Write-Host "Pretrained detection weights already exist: $Target"
    exit 0
}

Write-Host "Downloading PaddleOCR detection pretrained weights..."
Write-Host $Url
Invoke-WebRequest -Uri $Url -OutFile $Target
Write-Host "Saved: $Target"
