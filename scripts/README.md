# Project Scripts

This folder contains development and ML operations scripts. Runtime application code stays in `backend/` and `frontend/`.

## Layout

```text
scripts/
  datasets/             # Build, clean, export, and validate training datasets
  evaluation/           # Offline analysis and baseline evaluation helpers
  training/
    paddleocr/          # PaddleOCR/LayoutXLM environment, train, eval, GPU checks
```

## Common Commands

Check GPU:

```powershell
.\scripts\training\paddleocr\gpu_check.ps1
```

Train the current LayoutXLM/SER config:

```powershell
.\scripts\training\paddleocr\train_gpu.ps1
```

Evaluate the current best checkpoint:

```powershell
.\scripts\training\paddleocr\eval_ser.ps1 -Split test -UseGpu
```

Recreate prepared dataset exports:

```powershell
python scripts\datasets\prepare_receipt_4field_dataset.py --clear --copy-mode hardlink
python scripts\datasets\clean_receipt_4field_dataset.py --clear --copy-mode hardlink
python scripts\datasets\export_paddleocr_ser_dataset.py --dataset-dir archive\prepared\finrecon_receipt_4field_clean --output-dir archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser --copy-mode hardlink --epoch-num 10 --eval-step 250 --batch-size 2 --learning-rate 0.00002 --warmup-epoch 1 --clip-norm-global 1.0
python scripts\datasets\validate_paddleocr_ser_dataset.py --dataset-dir archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser
```
