# FinRecon Receipt AI - Codex Handoff Context

Last updated: 2026-07-02

## Current Direction

The project has been narrowed from a broad invoice automation and bank reconciliation platform into a focused receipt field extraction tool.

Current goal:

```text
Upload a Vietnamese retail receipt image and test whether the trained model can identify four fields:
SELLER, ADDRESS, TIMESTAMP, TOTAL_COST.
```

The active app must be honest about model behavior:

- Use the trained PaddleOCR/LayoutXLM pipeline only.
- Do not fallback to regex-generated data or synthetic metadata.
- Keep raw labels and token table visible for debugging.
- The four summary cards may post-process display values, but raw model output must remain visible.

## Active Product Scope

Current UI:

- Single receipt scanning page.
- Upload one image.
- Preview uploaded image.
- Run model.
- Show four field cards:
  - `SELLER`
  - `ADDRESS`
  - `TIMESTAMP`
  - `TOTAL_COST`
- Show raw model labels and OCR/token table.

Current backend:

- `GET /api/health`
- `POST /api/scan-image`
- `DELETE /api/scan-results`

Removed or inactive for now:

- Vendor master import.
- Invoice/bank reconciliation workflow.
- Payment approval workflow.
- Dashboard/reporting workflow.
- PostgreSQL/Alembic models.
- XML invoice import.
- Sample input generator.
- Batch/job screens.

## Key Source Files

Backend:

```text
backend/app/main.py
backend/app/services/kie_model.py
backend/app/database.py
backend/requirements.txt
```

Frontend:

```text
frontend/src/App.jsx
frontend/package.json
```

Training/tools:

```text
scripts/training/paddleocr/env.ps1
scripts/training/paddleocr/gpu_check.ps1
scripts/training/paddleocr/train_gpu.ps1
scripts/training/paddleocr/eval_ser.ps1
scripts/training/paddleocr/track_metrics.py
scripts/datasets/prepare_receipt_4field_dataset.py
scripts/datasets/clean_receipt_4field_dataset.py
scripts/datasets/export_paddleocr_ser_dataset.py
scripts/datasets/validate_paddleocr_ser_dataset.py
```

## Model State

The web app uses this checkpoint:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/output/ser_vi_layoutxlm_finrecon_4field/best_accuracy
```

This checkpoint came from the 10 epoch GPU run:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/reports/gpu_10epoch_tracked.*
```

Known metrics:

```text
Validation F1/hmean: 0.9510869565
Validation precision: 0.9472259811
Validation recall:    0.9549795362

Test F1/hmean:        0.9111257406
Test precision:       0.9069462647
Test recall:          0.9153439153
```

Two continuation attempts after the 10 epoch run were deleted because they did not improve the model:

- LR `1e-5`, target 50 epochs: validation F1 dropped to about `0.931`.
- LR `2e-6`, target 30 epochs: validation F1 stayed below baseline, around `0.950` then `0.9486`.

Conclusion:

```text
Do not assume longer LayoutXLM training will improve this dataset.
The current 10 epoch checkpoint remains the best known checkpoint.
```

## OCR vs KIE

The pipeline has two distinct layers:

- PaddleOCR detects/recognizes text from the receipt image.
- LayoutXLM/SER classifies recognized text tokens into `SELLER`, `ADDRESS`, `TIMESTAMP`, `TOTAL_COST`, or `OTHER`.

If the app misreads characters such as `I/l/1`, `O/0`, or `S/5`, that is mostly an OCR recognition issue, not a LayoutXLM field classification issue.

Likely next model work:

1. Fine-tune PaddleOCR text recognition on MC-OCR text crops.
2. Add blur/noise/JPEG/low-resolution augmentation.
3. Track OCR `CER`/`WER` before and after.
4. Keep the current LayoutXLM checkpoint unless a new validation/test run beats it.

## Dataset

Raw dataset:

```text
archive/source_mcocr/
```

Prepared/clean KIE dataset:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/
```

Current label set:

```text
OTHER
SELLER
ADDRESS
TIMESTAMP
TOTAL_COST
```

Current split sizes from validation:

```text
train: 929 documents, 19775 annotations
val:   112 documents, 2392 annotations
test:  112 documents, 2341 annotations
```

Clean rule policy:

- Keep valid `TOTAL_COST` keyword/context lines even if the line itself has no amount.
- Keep valid `TIMESTAMP` keyword/context lines even if the line itself has no date/time.
- Skip only truly unusable annotations such as empty text or invalid geometry.
- Do not overwrite raw MC-OCR data.

## Cache and Disk Policy

Do not write PaddleOCR/PaddleNLP cache to drive C.

Scripts load:

```text
scripts/training/paddleocr/env.ps1
```

This keeps cache inside:

```text
.cache/paddlenlp
.cache/paddle
.cache/huggingface
.cache/pip
.cache/tmp
```

Ignored local-heavy folders:

```text
.venvs/
.cache/
external/PaddleOCR/
archive/source_mcocr/
archive/prepared/
archive/models/
backend/data/
frontend/node_modules/
frontend/dist/
```

## Run App

Backend:

```powershell
cd "D:\Du-an\Invoice Automation & Reconciliation System\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Frontend:

```powershell
cd "D:\Du-an\Invoice Automation & Reconciliation System\frontend"
npm run dev
```

Frontend:

```text
http://127.0.0.1:5173
```

Backend docs:

```text
http://127.0.0.1:8000/docs
```

## Useful Training Commands

GPU check:

```powershell
.\scripts\training\paddleocr\gpu_check.ps1
```

Train current LayoutXLM/SER config:

```powershell
.\scripts\training\paddleocr\train_gpu.ps1
```

Evaluate current best checkpoint:

```powershell
.\scripts\training\paddleocr\eval_ser.ps1 -Split test -UseGpu
```

## Recommended Next Steps

1. Test more real receipt images through the current web app and save failure cases.
2. Build a small error report by field: missed `SELLER`, wrong `ADDRESS`, wrong `TIMESTAMP`, wrong `TOTAL_COST`.
3. Train/fine-tune PaddleOCR text recognition if the main failures are character-level OCR mistakes.
4. Only retrain LayoutXLM if labels/data split change or there is a clear field-classification failure pattern.
5. After extraction quality is acceptable, decide whether to rebuild a small-business workflow around receipt capture, payable review, and optional payment reconciliation.
