# PaddleOCR Environment

The PaddleOCR/LayoutXLM environment is separate from the backend and frontend environments.

## Paths

```text
Python CPU env:      .venvs/paddleocr
Python GPU env:      .venvs/paddleocr-gpu
PaddleOCR source:    external/PaddleOCR
Project cache:       .cache/
SER dataset:         archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser
SER train config:    archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/ser_vi_layoutxlm_finrecon_4field.yml
Best checkpoint:     archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/output/ser_vi_layoutxlm_finrecon_4field/best_accuracy
OCR rec dataset:     archive/prepared/mcocr2021_text_recognition_paddleocr
OCR rec config:      archive/prepared/mcocr2021_text_recognition_paddleocr/rec_svtr_lcnet_mcocr2021.yml
Web OCR rec model:   archive/models/paddleocr/mcocr2021_rec_svtr_lcnet_best_inference
```

## Cache Policy

All project scripts load:

```powershell
scripts\training\paddleocr\env.ps1
```

This keeps Paddle/PaddleNLP/HuggingFace/pip/temp cache inside the project on drive D:

```text
.cache/paddlenlp
.cache/paddle
.cache/huggingface
.cache/pip
.cache/tmp
```

Environment variables set by the script:

```text
PPNLP_HOME=.cache/paddlenlp
PADDLE_HOME=.cache/paddle
HF_HOME=.cache/huggingface
XDG_CACHE_HOME=.cache
PIP_CACHE_DIR=.cache/pip
TEMP=.cache/tmp
TMP=.cache/tmp
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
```

Do not run PaddleOCR commands manually without these variables unless you intentionally want cache outside the project.

## GPU Environment

Checked environment:

```text
Python: 3.10.20
PaddlePaddle GPU: 3.2.2, CUDA 12.6 wheel
PaddleNLP: 2.6.1.post
OpenCV: 4.6.0
NumPy: 1.26.4
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

## Fine-Tune PaddleOCR Text Recognition

This is separate from LayoutXLM/SER. Use this when the web app reads the right field region but OCR confuses characters such as `I/l/1`, `O/0`, `S/5`, accents, or blurry text.

Prepare MC-OCR 2021 recognition crops:

```powershell
python scripts\datasets\export_mcocr_text_recognition_dataset.py --clear --copy-mode hardlink
python scripts\datasets\validate_paddleocr_rec_dataset.py --dataset-dir archive\prepared\mcocr2021_text_recognition_paddleocr
```

Current export summary:

```text
train rows: 5285
val rows: 1300
missing images: 0
dictionary characters: 180
max text length: 139 observed, 160 configured
```

Download the default PP-OCRv4 mobile recognition pretrained weights:

```powershell
.\scripts\training\paddleocr\download_rec_pretrained.ps1
```

Train recognition model from pretrained weights:

```powershell
.\scripts\training\paddleocr\recognition_train_gpu.ps1
```

Smoke train one epoch before a longer run:

```powershell
.\scripts\training\paddleocr\recognition_train_gpu.ps1 -RunName rec_smoke_1epoch -EpochNum 1 -BatchSize 8
```

The default pretrained file is:

```text
archive\models\paddleocr\PP-OCRv4_mobile_rec_pretrained\PP-OCRv4_mobile_rec_pretrained.pdparams
```

To use a different compatible PaddleOCR recognition checkpoint, pass it explicitly:

```powershell
.\scripts\training\paddleocr\recognition_train_gpu.ps1 -PretrainedModel "archive\models\paddleocr\your_rec_pretrained\best_accuracy"
```

Evaluate recognition checkpoint:

```powershell
.\scripts\training\paddleocr\recognition_eval.ps1 -UseGpu
```

Tracked recognition metrics are `acc` and `norm_edit_dis`. For OCR recognition, these matter more than the KIE metrics `precision`, `recall`, and `hmean`.

## Web OCR Recognition Integration

The web scan pipeline currently uses this exported recognition inference model:

```text
archive/models/paddleocr/mcocr2021_rec_svtr_lcnet_best_inference
```

It was exported from the training checkpoint:

```text
archive/prepared/mcocr2021_text_recognition_paddleocr/output/rec_svtr_lcnet_mcocr2021/best_accuracy
```

Important export detail: use `Global.checkpoints`, not `Global.pretrained_model`, when exporting a trained checkpoint. `pretrained_model` can leave the original PP-OCR head in place.

```powershell
.\.venvs\paddleocr-gpu\Scripts\python.exe external\PaddleOCR\tools\export_model.py `
  -c archive\prepared\mcocr2021_text_recognition_paddleocr\rec_svtr_lcnet_mcocr2021.yml `
  -o Global.use_gpu=False `
     Global.checkpoints="D:/Du-an/Invoice Automation & Reconciliation System/archive/prepared/mcocr2021_text_recognition_paddleocr/output/rec_svtr_lcnet_mcocr2021/best_accuracy" `
     Global.pretrained_model= `
     Global.save_inference_dir="D:/Du-an/Invoice Automation & Reconciliation System/archive/models/paddleocr/mcocr2021_rec_svtr_lcnet_best_inference"
```

Current integrated checkpoint:

```text
best_epoch: 20
acc: 0.4382812466
norm_edit_dis: 0.8654821225
```

This is an honest test checkpoint, not a finished OCR model. It may produce noisy full-receipt recognition until training is continued and evaluated.

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
