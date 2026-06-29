$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "paddleocr_env.ps1")

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$Python = Join-Path $RepoRoot ".venvs\paddleocr-gpu\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing PaddleOCR GPU Python env: $Python"
}

& $Python -c "import os, paddle, cv2, paddlenlp, numpy; gpu_count = paddle.device.cuda.device_count() if paddle.device.is_compiled_with_cuda() else 0; print('PPNLP_HOME', os.environ.get('PPNLP_HOME')); print('PADDLE_HOME', os.environ.get('PADDLE_HOME')); print('paddle', paddle.__version__, 'cuda', paddle.device.is_compiled_with_cuda(), 'gpu_count', gpu_count); print('cv2', cv2.__version__); print('paddlenlp', paddlenlp.__version__); print('numpy', numpy.__version__); paddle.set_device('gpu:0' if gpu_count > 0 else 'cpu'); print('device', paddle.device.get_device()); paddle.utils.run_check()"
