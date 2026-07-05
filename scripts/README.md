# Project Scripts

This folder contains development and ML operations scripts. Runtime application code stays in `backend/` and `frontend/`.

## Layout

```text
scripts/
  datasets/             # Build, clean, export, and validate training datasets
  evaluation/           # Offline analysis and baseline evaluation helpers
  inference/            # Runtime bridge scripts, such as VietOCR crop recognition
  training/
    kie_layoutxlm/      # LayoutXLM/SER train, eval, metric tracking
    paddleocr/          # Shared PaddleOCR env, GPU check, runtime patches
    paddleocr_detection/# PaddleOCR DB detection fine-tuning
```

## Common Commands

Check GPU:

```powershell
.\scripts\training\paddleocr\gpu_check.ps1
```

Train the current LayoutXLM/SER config:

```powershell
.\scripts\training\kie_layoutxlm\train_gpu.ps1
```

Evaluate the current best checkpoint:

```powershell
.\scripts\training\kie_layoutxlm\eval_ser.ps1 -Split test -UseGpu
```

Recreate prepared dataset exports:

```powershell
python scripts\datasets\prepare_receipt_4field_dataset.py --clear --copy-mode hardlink
python scripts\datasets\clean_receipt_4field_dataset.py --clear --copy-mode hardlink
python scripts\datasets\export_paddleocr_ser_dataset.py --dataset-dir archive\prepared\finrecon_receipt_4field_clean --output-dir archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser --copy-mode hardlink --epoch-num 10 --eval-step 250 --batch-size 2 --learning-rate 0.00002 --warmup-epoch 1 --clip-norm-global 1.0
python scripts\datasets\validate_paddleocr_ser_dataset.py --dataset-dir archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser
```

Prepare PaddleOCR text detection fine-tuning data from MC-OCR:

```powershell
python scripts\datasets\export_paddleocr_det_dataset.py --clear
python scripts\datasets\validate_paddleocr_det_dataset.py --dataset-dir archive\prepared\mcocr2021_text_detection_paddleocr
.\scripts\training\paddleocr_detection\download_det_pretrained.ps1
```

Train/evaluate PaddleOCR detection:

```powershell
.\scripts\training\paddleocr_detection\train_gpu.ps1
.\scripts\training\paddleocr_detection\eval_det.ps1 -Split test -UseGpu
```

Apply local PaddleOCR runtime patches needed by the web scanner after refreshing `external/PaddleOCR`:

```powershell
.\scripts\training\paddleocr\apply_runtime_patches.ps1
```

Check the isolated VietOCR runtime used by the hybrid OCR option:

```powershell
.\.venvs\vietocr\Scripts\python.exe -c "import torch, vietocr; print(torch.__version__, torch.cuda.is_available()); print('vietocr ok')"
.\.venvs\vietocr\Scripts\python.exe -m pip check
```

The next OCR training direction is split by responsibility:

- PaddleOCR detection fine-tuning: improve text box detection on Vietnamese receipts.
- VietOCR recognition fine-tuning: improve Vietnamese text transcription inside detected crops.

The previous PaddleOCR text-recognition fine-tuning scripts and artifacts were removed to avoid mixing that experiment with the new detection + VietOCR plan.
