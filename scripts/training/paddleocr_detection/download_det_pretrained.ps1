param(
    [string]$Url = "https://paddleocr.bj.bcebos.com/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_det_train.tar",
    [string]$OutputDir = "archive\models\paddleocr\ch_ppocr_mobile_v2.0_det_train"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "..\paddleocr\env.ps1")

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")
$TargetDir = if ([System.IO.Path]::IsPathRooted($OutputDir)) {
    $OutputDir
} else {
    Join-Path $RepoRoot $OutputDir
}
$ArchivePath = Join-Path (Split-Path -Parent $TargetDir) "ch_ppocr_mobile_v2.0_det_train.tar"
$BestParams = Join-Path $TargetDir "best_accuracy.pdparams"

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $TargetDir) | Out-Null
if (Test-Path -LiteralPath $BestParams) {
    Write-Host "Pretrained DB detector already exists: $TargetDir"
    exit 0
}

Write-Host "Downloading PaddleOCR DB detector pretrained weights..."
Write-Host $Url
Invoke-WebRequest -Uri $Url -OutFile $ArchivePath
tar -xf $ArchivePath -C (Split-Path -Parent $TargetDir)

if (-not (Test-Path -LiteralPath $BestParams)) {
    throw "Downloaded archive did not produce expected checkpoint: $BestParams"
}

Write-Host "Saved pretrained DB detector: $TargetDir"
