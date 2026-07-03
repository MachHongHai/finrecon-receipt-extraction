param(
    [string]$Url = "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/PP-OCRv4_mobile_rec_pretrained.pdparams",
    [string]$OutputPath = "archive\models\paddleocr\PP-OCRv4_mobile_rec_pretrained\PP-OCRv4_mobile_rec_pretrained.pdparams",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "env.ps1")

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")
$Target = if ([System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath
} else {
    Join-Path $RepoRoot $OutputPath
}

if ((Test-Path -LiteralPath $Target) -and -not $Force) {
    Write-Host "Pretrained model already exists: $Target"
    exit 0
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
$TempPath = "$Target.tmp"
if (Test-Path -LiteralPath $TempPath) {
    Remove-Item -LiteralPath $TempPath -Force
}

Write-Host "Downloading PaddleOCR pretrained recognition model..."
Write-Host "Source: $Url"
Write-Host "Target: $Target"
Invoke-WebRequest -Uri $Url -OutFile $TempPath
Move-Item -LiteralPath $TempPath -Destination $Target -Force

$SizeMb = [math]::Round((Get-Item -LiteralPath $Target).Length / 1MB, 2)
Write-Host "Downloaded: $Target ($SizeMb MB)"
