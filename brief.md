# FinRecon Receipt AI - Current Project Brief

## 1. Project Goal

FinRecon Receipt AI is currently a focused Vietnamese receipt understanding tool.

The immediate goal is:

```text
Upload a receipt image and use a trained PaddleOCR/LayoutXLM model to identify four fields:
SELLER, ADDRESS, TIMESTAMP, TOTAL_COST.
```

This project is no longer focused on a broad invoice automation and bank reconciliation MVP in the active codebase. That larger finance workflow can be revisited later, after the receipt extraction model is reliable.

## 2. Problem Being Solved

Small businesses, especially F&B and retail shops, often keep purchase receipts, sales receipts, delivery slips, and simple invoices as photos. Manual entry is slow and error-prone.

The current tool helps test whether AI can extract the minimum useful receipt facts:

- Who issued/sold the receipt.
- Where the seller is located.
- When the sale happened.
- What the total amount was.

These four fields are enough for a first receipt capture layer. Later, they can feed payable tracking, expense logging, vendor review, or reconciliation workflows.

## 3. Current Trained Fields

The active model predicts:

```text
OTHER
SELLER
ADDRESS
TIMESTAMP
TOTAL_COST
```

The frontend only shows these four business fields:

```text
SELLER
ADDRESS
TIMESTAMP
TOTAL_COST
```

Raw model labels and token output should stay visible for debugging.

## 4. Current Architecture

```text
Receipt image
  -> FastAPI upload endpoint
  -> PaddleOCR detects/recognizes text
  -> LayoutXLM/SER classifies token labels
  -> Backend groups labels into four fields
  -> Frontend displays field cards + raw labels + token table
```

Important distinction:

- PaddleOCR is responsible for reading text from the image.
- LayoutXLM/SER is responsible for deciding which text belongs to each field.

Character mistakes such as `I/l/1` or `O/0` are OCR recognition problems, not field-classification problems.

## 5. Current Backend API

```http
GET    /api/health
POST   /api/scan-image
DELETE /api/scan-results
```

No vendor import, bank statement import, reconciliation, XML import, or report generation endpoints are active in the simplified app.

## 6. Current Frontend

The frontend is a single receipt scanning experience:

- Upload image.
- Preview image.
- Click scan.
- Show four field cards.
- Show raw model labels.
- Show token table.

The UI should not reintroduce the old multi-step reconciliation workflow unless the product direction changes again.

## 7. Dataset

Raw data:

```text
archive/source_mcocr/
```

Prepared KIE/SER dataset:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/
```

The raw MC-OCR dataset must not be overwritten.

Current split sizes:

```text
train: 929 documents, 19775 annotations
val:   112 documents, 2392 annotations
test:  112 documents, 2341 annotations
```

Clean rule policy:

- Keep valid keyword/context annotations.
- Do not demote `TOTAL_COST` just because text has no amount.
- Do not demote `TIMESTAMP` just because text has no date/time.
- Skip only truly invalid annotations such as empty text or invalid geometry.

## 8. Current Best Model

Checkpoint used by the app:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/output/ser_vi_layoutxlm_finrecon_4field/best_accuracy
```

Known metrics:

```text
Validation F1/hmean: 0.9510869565
Test F1/hmean:       0.9111257406
```

This is the best known LayoutXLM/SER checkpoint. Longer continuation training from this checkpoint was tested and did not improve validation performance.

## 9. What Was Removed From Active Scope

Removed or inactive:

- Sample input generator.
- Vendor master import.
- Bank statement import.
- Invoice register import.
- E-invoice XML parsing.
- Payment batch workflow.
- Bank reconciliation engine.
- Dashboard/report workflow.
- PostgreSQL/Alembic schema.
- Multi-step business workflow UI.

These are not deleted as product ideas forever; they are simply not part of the current focused model-testing app.

## 10. Training Direction

Do not assume more LayoutXLM epochs will improve the model. The 10 epoch checkpoint is currently strongest.

Better next training work:

1. Collect real receipt failures from the web app.
2. Categorize errors into OCR text errors vs field-label errors.
3. If OCR text is wrong, fine-tune PaddleOCR text recognition.
4. If field labels are wrong, improve KIE labels/data split and retrain LayoutXLM.
5. Track metrics separately:
   - OCR: CER/WER
   - KIE/SER: precision/recall/F1

OCR recognition fine-tune setup is prepared from MC-OCR 2021:

```text
archive/prepared/mcocr2021_text_recognition_paddleocr
```

It uses the MC-OCR text crop labels:

```text
train: 5285 rows
val:   1300 rows
dictionary: 180 characters
config: rec_svtr_lcnet_mcocr2021.yml
```

Train/eval:

```powershell
.\scripts\training\paddleocr\recognition_train_gpu.ps1
.\scripts\training\paddleocr\recognition_eval.ps1 -UseGpu
```

## 11. Run Commands

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

GPU check:

```powershell
.\scripts\training\paddleocr\gpu_check.ps1
```

Evaluate current best model:

```powershell
.\scripts\training\paddleocr\eval_ser.ps1 -Split test -UseGpu
```

## 12. Future Product Direction

Once receipt extraction quality is strong enough, the product can expand into a practical small-business workflow:

```text
Receipt capture
  -> Human review
  -> Expense/payable record
  -> Vendor history
  -> Payment status
  -> Optional bank reconciliation
```

The next practical milestone is not a full accounting platform. It is a reliable receipt capture and review tool for small businesses.
