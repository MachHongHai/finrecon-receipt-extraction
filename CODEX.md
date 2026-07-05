# FinRecon Receipt Field Extraction - Codex Handoff Context

Last updated: 2026-07-03

## Current Direction

The project has been narrowed from a broad invoice automation and bank reconciliation platform into a focused receipt field extraction tool.

Current goal:

```text
Upload a Vietnamese retail receipt image and test whether the trained model can identify four fields:
SELLER, ADDRESS, TIMESTAMP, TOTAL_COST.
```

The active app must be honest about model behavior:

- Let the user choose OCR/KIE runtime options from the UI for comparison.
- Do not fallback to regex-generated data or synthetic metadata.
- Keep raw labels and token table visible for debugging.
- The four summary cards may post-process display values, but raw model output must remain visible.

## Active Product Scope

Current UI:

- Single receipt scanning page.
- Upload one image.
- Preview uploaded image.
- Select OCR engine and KIE engine.
- Run scan.
- Show four field cards:
  - `SELLER`
  - `ADDRESS`
  - `TIMESTAMP`
  - `TOTAL_COST`
- Show raw model labels and OCR/token table.

Current backend:

- `GET /api/health`
- `GET /api/model-options`
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
scripts/training/kie_layoutxlm/train_gpu.ps1
scripts/training/kie_layoutxlm/eval_ser.ps1
scripts/training/kie_layoutxlm/track_metrics.py
scripts/training/paddleocr/apply_runtime_patches.ps1
scripts/training/paddleocr_detection/download_det_pretrained.ps1
scripts/training/paddleocr_detection/train_gpu.ps1
scripts/training/paddleocr_detection/eval_det.ps1
scripts/datasets/prepare_receipt_4field_dataset.py
scripts/datasets/clean_receipt_4field_dataset.py
scripts/datasets/export_paddleocr_ser_dataset.py
scripts/datasets/validate_paddleocr_ser_dataset.py
scripts/datasets/export_paddleocr_det_dataset.py
scripts/datasets/validate_paddleocr_det_dataset.py
scripts/inference/vietocr_recognize.py
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

Current web OCR choices:

```text
paddleocr_original      - PaddleOCR package default OCR.
paddleocr_pretrained    - Official PP-OCRv4 Chinese pretrained OCR, lang=ch.
paddleocr_vi_pretrained - Official PaddleOCR Vietnamese/Latin pretrained OCR, lang=vi.
paddleocr_vietocr       - PaddleOCR detection + VietOCR recognition.
```

Current OCR training direction:

```text
PaddleOCR detection fine-tuning for bbox coverage.
VietOCR recognition fine-tuning for Vietnamese text quality.
```

PaddleOCR detection setup is prepared from MC-OCR 2021:

```text
archive/prepared/mcocr2021_text_detection_paddleocr
documents: 1154
annotations: 47626
train/val/test: 924 / 115 / 115
pretrained: archive/models/paddleocr/MobileNetV3_large_x0_5_pretrained.pdparams
```


Current web KIE choices:

```text
kie_pretrained - LayoutXLM pretrained backbone without the trained 4-field checkpoint.
kie_trained    - Current best LayoutXLM/SER checkpoint for SELLER, ADDRESS, TIMESTAMP, TOTAL_COST.
```

Use `kie_pretrained` only as a baseline/debug option. It has not learned the project labels and its field output is expected to be poor.

If the app misreads characters such as `I/l/1`, `O/0`, or `S/5`, that is mostly an OCR recognition issue, not a LayoutXLM field classification issue.

Likely next model work:

1. Run a real PaddleOCR detection fine-tune from `mcocr2021_text_detection_paddleocr`.
2. Export the best detection checkpoint to inference format.
3. Integrate the trained detector as a selectable detection model in web inference.
4. Prepare VietOCR recognition fine-tuning from text-line crops.
5. Track detection hmean separately from recognition CER/WER and KIE F1.

## Dataset

Raw dataset:

```text
archive/source_mcocr/
```

Prepared/clean KIE dataset:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/
```

Prepared PaddleOCR detection dataset:

```text
archive/prepared/mcocr2021_text_detection_paddleocr/
train: 924 documents, 37827 polygons
val:   115 documents, 4760 polygons
test:  115 documents, 5039 polygons
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
cd "D:\Du-an\finrecon-receipt-extraction\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Frontend:

```powershell
cd "D:\Du-an\finrecon-receipt-extraction\frontend"
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
.\scripts\training\kie_layoutxlm\train_gpu.ps1
```

Evaluate current best checkpoint:

```powershell
.\scripts\training\kie_layoutxlm\eval_ser.ps1 -Split test -UseGpu
```

## Recommended Next Steps

1. Test more real receipt images through the current web app and save failure cases.
2. Build a small error report by field: missed `SELLER`, wrong `ADDRESS`, wrong `TIMESTAMP`, wrong `TOTAL_COST`.
3. Train/fine-tune PaddleOCR text recognition if the main failures are character-level OCR mistakes.
4. Only retrain LayoutXLM if labels/data split change or there is a clear field-classification failure pattern.
5. After extraction quality is acceptable, decide whether to rebuild a small-business workflow around receipt capture, payable review, and optional payment reconciliation.
