# FinRecon Receipt AI

AI receipt capture, vendor payable control, and payment reconciliation for small F&B businesses.

The product focus is small restaurant/vendor paperwork: photographed purchase receipts, delivery notes, simple sales invoices, payment batches, and bank statements. The trained field extractor targets four receipt fields first: `seller`, `address`, `timestamp`, and `total_cost`.

## What is included

- Vendor master CSV import
- Bank statement CSV/Excel import
- Purchase receipt register CSV/Excel import
- E-invoice XML import as a secondary structured source
- Receipt PDF/image attachments with optional OCR fallback
- Payment approval and payment batch workflow
- Single and batch receipt upload with local file storage
- Processing jobs and batch tracking
- OCR extraction with fallback parsing for uploaded receipt files
- OCR review form and audit logging
- Manual receipt creation
- Receipt validation rules
- Configurable rule-based reconciliation scoring
- Reconciliation workspace with approve/reject actions
- Exception workflow with status and notes
- Management dashboard summary
- AI-style reconciliation report generated from computed results
- Excel export for reconciliation results and exceptions
- PostgreSQL-ready Docker Compose for local development

## Run backend and frontend separately

Backend:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
npm run dev
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open:

- Frontend: http://127.0.0.1:5173
- Backend API docs: http://127.0.0.1:8000/docs

When running backend this way, the app uses local SQLite by default so you can test quickly without Docker. Set `DATABASE_URL` if you want the separate backend dev server to connect to PostgreSQL.

## Run with Docker

```powershell
docker compose up --build
```

Docker Compose starts `postgres`, `backend`, and `frontend`. The backend uses:

```text
postgresql://finrecon:finrecon@postgres:5432/finrecon
```

Demo users are seeded automatically. Password for all demo users is `demo123`:

- `admin@finrecon.local`
- `accountant@finrecon.local`
- `reviewer@finrecon.local`
- `manager@finrecon.local`

## CSV formats

Vendor master columns (`.csv`, `.xlsx`, or `.xls`):

```csv
vendor_id,vendor_name,tax_code,bank_account,address
```

Bank statement columns (`.csv`, `.xlsx`, or `.xls`):

```csv
transaction_id,transaction_date,value_date,account_number,description,amount,direction,currency,balance_after,counterparty_name,counterparty_account,reference_code,expected_case
```

Dates should use `YYYY-MM-DD` or `DD/MM/YYYY`. Amounts can include separators such as `6,050,000`.

Purchase receipt register columns. These keep legacy column names such as `invoice_id` for API/database compatibility, but they represent receipt IDs in the current product:

```csv
invoice_id,invoice_number,invoice_series,invoice_template_code,invoice_date,due_date,vendor_id,vendor_name,vendor_tax_code,vendor_bank_account,buyer_name,buyer_tax_code,subtotal,vat_rate,vat_amount,total_amount,currency,invoice_status,source_type,attachment_file,expected_case
```

Payment batch columns:

```csv
payment_id,invoice_id,vendor_id,scheduled_payment_date,approved_amount,currency,approval_status,approved_by,approved_at,payment_method,notes
```

## Training and archived datasets

Legacy synthetic inputs have been removed. OCR/field-extractor work now uses the dataset archive under `archive/source_mcocr` and prepared training outputs under `archive/prepared/`. The recommended clean PaddleOCR/LayoutXLM training dataset is `archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser`.

The clean rule keeps keyword/context annotations for `TOTAL_COST` and `TIMESTAMP` instead of demoting lines such as "Tong cong", "Thanh toan", "Ngay ban", or "Thoi gian" just because the line itself has no amount/date value. Empty-text or invalid-geometry annotations are skipped from training instead of being relabeled as `OTHER`.

MC-OCR's `boxes_and_transcripts` files contain blank transcript cells for some target-field boxes. The prepare step uses `mcocr_train_df.csv` as the authoritative source for target-field text, recovers blank target boxes when bbox overlap is high, appends missing CSV target annotations, and ignores blank `OTHER` boxes.

## Reconciliation scoring

The backend computes match candidates with:

- 45% amount similarity
- 25% date proximity
- 20% vendor similarity
- 10% receipt/reference similarity

The report endpoint only explains backend-computed results. It does not calculate financial totals with an LLM.

## Main MVP endpoints

Note: public endpoint paths still use `/api/invoices/*` internally for compatibility with the existing database schema. In the product UI and docs, these records are purchase receipts/phiếu nhập.

- `POST /api/vendors/import`
- `GET /api/vendors`
- `POST /api/invoices/upload`
- `POST /api/batches/invoices/upload`
- `POST /api/invoices/import-register`
- `POST /api/invoices/import-xml`
- `POST /api/invoices/upload-attachment`
- `GET /api/batches`
- `GET /api/jobs`
- `GET /api/invoices`
- `GET /api/invoices/{invoice_id}`
- `PUT /api/invoices/{invoice_id}`
- `GET /api/invoices/{invoice_id}/review`
- `PUT /api/invoices/{invoice_id}/review`
- `POST /api/invoices/{invoice_id}/validate`
- `POST /api/invoices/{invoice_id}/approve`
- `POST /api/invoices/{invoice_id}/reject`
- `POST /api/payment-batches/import`
- `GET /api/payment-batches`
- `POST /api/payment-batches/generate-from-approved-invoices`
- `POST /api/bank-transactions/import`
- `GET /api/bank-transactions`
- `POST /api/reconciliation/run`
- `GET /api/reconciliation/results`
- `GET /api/reconciliation/candidates`
- `GET /api/reconciliation/exceptions`
- `GET /api/exceptions`
- `PUT /api/exceptions/{exception_id}`
- `GET /api/rules`
- `PUT /api/rules`
- `GET /api/audit-logs`
- `GET /api/dashboard/reconciliation-summary`
- `GET /api/dashboard/management-summary`
- `POST /api/reports/generate`
- `GET /api/reports`
- `GET /api/reports/export/reconciliation.xlsx`
- `GET /api/reports/export/exceptions.xlsx`
