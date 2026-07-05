# PaddleOCR Environment

The PaddleOCR/LayoutXLM environment is separate from the backend and frontend environments.

## Paths

```text
Paddle/LayoutXLM env:.venvs/paddleocr-gpu
VietOCR env:         .venvs/vietocr
PaddleOCR source:    external/PaddleOCR
Project cache:       .cache/
SER dataset:         archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser
SER train config:    archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/ser_vi_layoutxlm_finrecon_4field.yml
Best checkpoint:     archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/output/ser_vi_layoutxlm_finrecon_4field/best_accuracy
VietOCR bridge:      scripts/inference/vietocr_recognize.py
```

## Cache Policy

All project scripts load:

```powershell
scripts\training\paddleocr\env.ps1
```

This keeps Paddle/PaddleNLP/HuggingFace/Torch/pip/temp cache inside the project on drive D:

```text
.cache/paddlenlp
.cache/paddle
.cache/huggingface
.cache/torch
.cache/pip
.cache/tmp
```

Environment variables set by the script:

```text
PPNLP_HOME=.cache/paddlenlp
PADDLE_HOME=.cache/paddle
HF_HOME=.cache/huggingface
TORCH_HOME=.cache/torch
XDG_CACHE_HOME=.cache
PIP_CACHE_DIR=.cache/pip
TEMP=.cache/tmp
TMP=.cache/tmp
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
```

Do not run PaddleOCR commands manually without these variables unless you intentionally want cache outside the project.

## Paddle/LayoutXLM GPU Environment

Checked Paddle/LayoutXLM environment:

```text
Python: 3.10.20
PaddlePaddle GPU: 3.2.2, CUDA 12.6 wheel
PaddleNLP: 2.6.1.post
OpenCV: 4.6.0
NumPy: 1.26.4
Torch/VietOCR: intentionally not installed here
```

`paddleocr-gpu` is intentionally kept free of PyTorch/VietOCR to avoid CUDA/cuDNN DLL conflicts. The hybrid OCR option uses PaddleOCR detection in this environment, then calls VietOCR in a separate process through `.venvs/vietocr`.

## VietOCR Environment

VietOCR is isolated in:

```text
.venvs/vietocr
```

Expected packages:

```text
Python: 3.10.20
Torch: CPU build
VietOCR: 0.3.13
```

Check the environment:

```powershell
.\.venvs\vietocr\Scripts\python.exe -c "import torch, vietocr; print(torch.__version__, torch.cuda.is_available()); print('vietocr ok')"
.\.venvs\vietocr\Scripts\python.exe -m pip check
```

The web option `paddleocr_vietocr` uses:

```text
PaddleOCR process: .venvs/paddleocr-gpu
VietOCR process:   .venvs/vietocr
Bridge script:     scripts/inference/vietocr_recognize.py
```

Check GPU before training:

```powershell
.\scripts\training\paddleocr\gpu_check.ps1
```

Expected good output:

```text
paddle 3.2.2 cuda True gpu_count 1
device gpu:0
PaddlePaddle works well on 1 GPU.
```

Also plug in the laptop charger before long training runs.

## Current LayoutXLM/SER Result

The best kept model is the 10 epoch GPU run:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/output/ser_vi_layoutxlm_finrecon_4field/best_accuracy
```

Metrics:

```text
Validation F1/hmean: 0.9510869565
Test F1/hmean:       0.9111257406
```

Kept logs:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/reports/gpu_10epoch_tracked.*
```

Later continuation attempts were removed because they did not improve validation F1.

## Train LayoutXLM/SER

Validate GPU:

```powershell
.\scripts\training\paddleocr\gpu_check.ps1
```

Run the current training config:

```powershell
.\scripts\training\paddleocr\train_gpu.ps1
```

The script validates the PaddleOCR SER dataset first, then writes logs and tracked metrics to:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/reports/
```

Evaluate current best checkpoint:

```powershell
.\scripts\training\paddleocr\eval_ser.ps1 -Split test -UseGpu
```

## OCR Training Direction

The old PaddleOCR text-recognition fine-tuning run has been removed. The next OCR work is split by responsibility:

- PaddleOCR detection fine-tuning uses receipt images and text polygons to improve missing-text-box cases.
- VietOCR recognition fine-tuning uses cropped text-line images to improve Vietnamese transcription, accents, and character confusions.

Keep these experiments separate from LayoutXLM/SER. Detection quality is measured with detection metrics; recognition quality is measured with CER/WER or exact-match accuracy on crops.

## Recreate Prepared Dataset

Raw MC-OCR data should stay read-only under:

```text
archive/source_mcocr/
```

Recreate prepared/clean/exported data:

```powershell
python scripts\datasets\prepare_receipt_4field_dataset.py --clear --copy-mode hardlink
python scripts\datasets\clean_receipt_4field_dataset.py --clear --copy-mode hardlink
python scripts\datasets\export_paddleocr_ser_dataset.py --dataset-dir archive\prepared\finrecon_receipt_4field_clean --output-dir archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser --copy-mode hardlink --epoch-num 10 --eval-step 250 --batch-size 2 --learning-rate 0.00002 --warmup-epoch 1 --clip-norm-global 1.0
python scripts\datasets\validate_paddleocr_ser_dataset.py --dataset-dir archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser
```

## Dataset Notes

Current labels:

```text
OTHER
SELLER
ADDRESS
TIMESTAMP
TOTAL_COST
```

Clean policy:

- Keep keyword/context annotations for `TOTAL_COST` and `TIMESTAMP`.
- Do not demote `TOTAL_COST` just because a line has no amount.
- Do not demote `TIMESTAMP` just because a line has no date/time.
- Skip only truly invalid annotations such as empty text or bad geometry.

## CPU Environment

The CPU env exists mainly for lightweight checks. It is too slow for real LayoutXLM training.

Checked CPU env:

```text
Python: 3.10.20
PaddlePaddle: 2.6.2 CPU
PaddleNLP: 2.6.1
OpenCV: 4.6.0
NumPy: 1.26.4
```

## Recreate GPU Environment

```powershell
uv python install 3.10
uv venv .\.venvs\paddleocr-gpu --python 3.10
uv pip install --python .\.venvs\paddleocr-gpu\Scripts\python.exe pip setuptools wheel
uv pip install --python .\.venvs\paddleocr-gpu\Scripts\python.exe paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
uv pip install --python .\.venvs\paddleocr-gpu\Scripts\python.exe -r .\external\PaddleOCR\requirements.txt paddlenlp==2.6.1
uv pip install --python .\.venvs\paddleocr-gpu\Scripts\python.exe numpy==1.26.4
```

Note: `paddlenlp==2.8.1` was not usable on Windows in this environment because one dependency had no `win_amd64` wheel.

Do not install PyTorch or VietOCR into `.venvs/paddleocr-gpu`.

## Recreate VietOCR Environment

```powershell
uv venv .\.venvs\vietocr --python 3.10
uv pip install --python .\.venvs\vietocr\Scripts\python.exe pip
uv pip install --python .\.venvs\vietocr\Scripts\python.exe torch torchvision --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .\.venvs\vietocr\Scripts\python.exe vietocr
```

Check VietOCR:

```powershell
.\.venvs\vietocr\Scripts\python.exe -c "import torch, vietocr; print(torch.__version__, torch.cuda.is_available()); print('vietocr ok')"
.\.venvs\vietocr\Scripts\python.exe -m pip check
```
