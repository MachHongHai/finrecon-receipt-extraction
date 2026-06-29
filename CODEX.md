# FinRecon Receipt AI - Codex Handoff Context

Last updated: 2026-06-29

## Định hướng hiện tại

FinRecon Receipt AI đang được đổi hướng từ nền tảng hóa đơn doanh nghiệp rộng sang tool quy mô nhỏ cho F&B/SME:

```text
Công cụ đọc phiếu nhập hàng, kiểm soát công nợ vendor, duyệt chi và đối soát thanh toán ngân hàng.
```

Cốt lõi AI sắp train là PaddleOCR/LayoutXLM field extractor cho 4 field trước:

- `seller`
- `address`
- `timestamp`
- `total_cost`

Mục tiêu thực tế: người dùng chụp phiếu nhập, biên nhận, phiếu giao hàng hoặc hóa đơn bán hàng đơn giản; hệ thống OCR/extract 4 field chính, cho người dùng review, chuyển thành khoản công nợ phải trả, duyệt chi, rồi đối soát với sao kê ngân hàng.

## Quyết định kiến trúc

- Public product wording dùng “phiếu nhập”, “receipt”, “công nợ”, “vendor payable”.
- Backend vẫn giữ schema/API cũ như `Invoice`, `invoice_number`, `/api/invoices/*` để tránh migration lớn và giữ app chạy ổn.
- XML hóa đơn điện tử Việt Nam không phải luồng chính, nhưng giữ như nguồn structured phụ cho vendor chính thức.
- Synthetic generator dữ liệu mẫu cũ đã bị gỡ khỏi dự án.
- Dữ liệu OCR/train hiện nằm trong `archive/source_mcocr` và `archive/prepared/`.
- Không ghi cache/checkpoint PaddleOCR sang ổ C; dùng workspace trên ổ D và các script trong `tools/`.

## Workflow UI

Frontend hiện theo luồng 8 bước:

1. Cấu hình quy tắc
2. Danh mục vendor/mối buôn
3. Phiếu nhập hàng
4. Kiểm tra phiếu nhập
5. Bảng kê thanh toán
6. Sao kê ngân hàng
7. Đối soát thanh toán
8. Dashboard

Mục “Dữ liệu mẫu” cũ đã bị loại khỏi navigation.

## Backend hiện có

Các endpoint chính vẫn đang dùng tên `invoices`:

- `POST /api/batches/invoices/upload`
- `POST /api/invoices/upload`
- `POST /api/invoices/import-register`
- `POST /api/invoices/import-xml`
- `POST /api/invoices/upload-attachment`
- `GET /api/invoices`
- `PUT /api/invoices/{invoice_id}`
- `POST /api/invoices/{invoice_id}/approve`
- `POST /api/payment-batches/generate-from-approved-invoices`
- `POST /api/bank-transactions/import`
- `POST /api/reconciliation/run`
- `GET /api/dashboard/management-summary`

Không rename API nội bộ sang `/api/receipts` nếu chưa có migration/compat layer rõ ràng.

## OCR và dataset

Hướng train:

- Dataset gốc: `archive/source_mcocr`
- Dataset prepared 4 field: `archive/prepared/finrecon_receipt_4field`
- Dataset clean khuyến nghị cho KIE: `archive/prepared/finrecon_receipt_4field_clean`
- PaddleOCR SER clean export: `archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser`
- Class list: `OTHER`, `SELLER`, `ADDRESS`, `TIMESTAMP`, `TOTAL_COST`

Config train GPU mặc định hiện trỏ vào dataset clean 10 epoch. Rule clean hiện tại giữ keyword/context như "Tổng cộng", "Thanh toán", "Ngày bán", "Thời gian" nếu annotation có text và geometry hợp lệ; không demote `TOTAL_COST` vì thiếu số tiền và không demote `TIMESTAMP` vì thiếu ngày/giờ. `boxes_and_transcripts` trong MC-OCR có nhiều transcript rỗng, nên prepare script dùng `mcocr_train_df.csv` làm nguồn target text chính thức: recover box target rỗng khi bbox overlap tốt, append CSV target annotation còn thiếu, và bỏ qua box `OTHER` rỗng. Chưa tích hợp model trained vào web app cho tới khi có prediction report đủ tin cậy.

## Cách chạy

Backend:

```powershell
cd "D:\Du-an\Invoice Automation & Reconciliation System\backend"
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Frontend:

```powershell
cd "D:\Du-an\Invoice Automation & Reconciliation System\frontend"
npm run dev
```

Frontend mặc định: `http://127.0.0.1:5173`

Backend docs: `http://127.0.0.1:8000/docs`

## Việc nên làm tiếp

- Hoàn thiện integration model field extractor vào backend OCR service.
- Thêm alias API `/api/receipts/*` nếu muốn đổi public API sạch hơn nhưng vẫn giữ `/api/invoices/*` tương thích.
- Chuẩn hóa bảng công nợ vendor: receipt -> payable -> payment batch -> bank reconciliation.
- Bổ sung màn review OCR tập trung vào 4 field chính trước, line items để sau.
- Thêm báo cáo vendor payable đơn giản cho chủ quán: còn nợ ai, đã trả ai, giao dịch nào chưa khớp.
