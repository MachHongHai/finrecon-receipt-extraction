# FinRecon Receipt AI

FinRecon Receipt AI is currently a focused OCR/KIE demo for Vietnamese retail receipts. The app uploads one receipt image, runs PaddleOCR plus a fine-tuned LayoutXLM SER model, and displays only the four trained fields:

- `SELLER`
- `ADDRESS`
- `TIMESTAMP`
- `TOTAL_COST`

The current product direction is intentionally narrow: prove that the model can read receipt images and classify receipt text into the right business fields. The older invoice automation, bank reconciliation, vendor master, XML, sample generator, and dashboard workflows have been removed from the active app for now.

## Current App Scope

Included now:

- React frontend with a single receipt scanning screen.
- FastAPI backend with a model-only scan endpoint.
- PaddleOCR/LayoutXLM inference through a separate PaddleOCR GPU environment.
- No fallback extraction when testing model intelligence.
- Raw token/model labels kept for debugging.
- Display values normalized for the four cards:
  - `TIMESTAMP` shows the date value when possible.
  - `TOTAL_COST` shows the amount value when possible.

Not included in the active app:

- Vendor import.
- Bank statement import.
- Invoice/payment reconciliation.
- PostgreSQL workflow.
- Sample input generator UI.
- AI financial report generation.

Those can be rebuilt later after the receipt extraction model is reliable.

## Active Backend API

```http
GET    /api/health
POST   /api/scan-image
DELETE /api/scan-results
```

`POST /api/scan-image` accepts an image file and returns:

- grouped field rows for `SELLER`, `ADDRESS`, `TIMESTAMP`, `TOTAL_COST`
- raw model labels
- OCR/token table
- uploaded image preview URL

## Run Backend

```powershell
cd "D:\Du-an\Invoice Automation & Reconciliation System\backend"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
npm run dev
```

Backend docs:

```text
http://127.0.0.1:8000/docs
```

## Run Frontend

```powershell
cd "D:\Du-an\Invoice Automation & Reconciliation System\frontend"
npm install
npm run dev
```

Frontend:

```text
http://127.0.0.1:5173
```

## Model In Use

The web app currently uses the best checkpoint from the 10 epoch LayoutXLM/SER run:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/output/ser_vi_layoutxlm_finrecon_4field/best_accuracy
```

Latest kept metrics:

```text
Validation F1/hmean: 0.9510869565
Test F1/hmean:       0.9111257406
```

Training artifacts kept for that run:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/reports/gpu_10epoch_tracked.*
```

Two later continuation experiments were deleted because they did not improve the baseline.

## Dataset

The project uses MC-OCR 2021 data stored locally under ignored folders:

```text
archive/source_mcocr/
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/
```

The active KIE/SER labels are:

```text
OTHER
SELLER
ADDRESS
TIMESTAMP
TOTAL_COST
```

The clean dataset intentionally keeps keyword/context lines for `TOTAL_COST` and `TIMESTAMP`; it does not demote lines just because a line lacks a number or date.

## Useful Commands

Check GPU:

```powershell
.\scripts\training\paddleocr\gpu_check.ps1
```

Train the current LayoutXLM/SER config:

```powershell
.\scripts\training\paddleocr\train_gpu.ps1
```

Evaluate best checkpoint on test split:

```powershell
.\scripts\training\paddleocr\eval_ser.ps1 -Split test -UseGpu
```

Prepare OCR recognition fine-tuning data from MC-OCR 2021:

```powershell
python scripts\datasets\export_mcocr_text_recognition_dataset.py --clear --copy-mode hardlink
python scripts\datasets\validate_paddleocr_rec_dataset.py --dataset-dir archive\prepared\mcocr2021_text_recognition_paddleocr
```

Fine-tune/evaluate PaddleOCR text recognition:

```powershell
.\scripts\training\paddleocr\recognition_train_gpu.ps1
.\scripts\training\paddleocr\recognition_eval.ps1 -UseGpu
```

Smoke train OCR recognition for one epoch:

```powershell
.\scripts\training\paddleocr\recognition_train_gpu.ps1 -RunName rec_smoke_1epoch -EpochNum 1 -BatchSize 8
```

Validate backend/frontend quickly:

```powershell
cd backend
.\.venv\Scripts\python.exe -m compileall app

cd ..\frontend
npm run build
```
