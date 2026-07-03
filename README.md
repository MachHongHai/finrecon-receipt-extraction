# FinRecon Receipt Field Extraction

FinRecon Receipt Field Extraction là một workbench OCR/KIE dùng để kiểm thử khả năng trích xuất trường thông tin từ ảnh hóa đơn bán lẻ Việt Nam. Phiên bản hiện tại tập trung vào một bài toán hẹp nhưng có giá trị nền tảng: đọc ảnh hóa đơn, nhận diện text, phân loại token, và gom kết quả về 4 trường nghiệp vụ chính.

## 1. Tóm Tắt Dự Án

Mục tiêu hiện tại:

```text
Input:  Ảnh hóa đơn/phiếu bán lẻ Việt Nam
Output: SELLER, ADDRESS, TIMESTAMP, TOTAL_COST
```

Hệ thống không dùng fallback rule-based khi kiểm thử model. Raw OCR tokens và raw SER labels luôn được hiển thị để đánh giá trung thực chất lượng model.

Trạng thái scope:

- Đã thu hẹp từ ý tưởng invoice automation/reconciliation lớn thành một module receipt field extraction.
- Tạm bỏ các workflow vendor master, bank statement, XML invoice, dashboard tài chính, sample generator.
- Ưu tiên hiện tại là đánh giá chất lượng OCR và KIE trước khi xây lại workflow nghiệp vụ phía trên.

## 2. Bài Toán

Nhiều hóa đơn bán lẻ Việt Nam có ảnh chụp mờ, chữ nhỏ, layout thay đổi, thiếu chuẩn hóa, và có nhiều nhiễu thị giác. Tool này giúp kiểm thử pipeline:

1. Text detection: phát hiện vùng chữ trên ảnh.
2. Text recognition: nhận diện nội dung chữ.
3. Key Information Extraction: phân loại từng token/dòng text vào field nghiệp vụ.
4. Post-processing nhẹ: rút gọn giá trị hiển thị cho ngày và tổng tiền.

Các field hiện hỗ trợ:

| Label | Ý nghĩa |
| --- | --- |
| `SELLER` | Tên đơn vị bán hàng |
| `ADDRESS` | Địa chỉ đơn vị bán hàng |
| `TIMESTAMP` | Ngày/giờ giao dịch |
| `TOTAL_COST` | Tổng giá trị thanh toán |
| `OTHER` | Token không thuộc 4 field cần lấy |

## 3. Kiến Trúc Tổng Thể

```text
frontend/ React + Vite
    ↓ multipart/form-data
backend/ FastAPI
    ↓ subprocess
external/PaddleOCR
    ↓ OCR tokens
LayoutXLM SER checkpoint
    ↓ labels
field aggregation + display normalization
```

Thành phần chính:

- Frontend: giao diện upload ảnh, chọn pipeline, xem field summary, raw SER output, OCR tokens.
- Backend: API FastAPI, lưu upload tạm, gọi PaddleOCR inference, chuẩn hóa response.
- Model runtime: PaddleOCR + LayoutXLM/SER chạy trong môi trường Python riêng.
- Dataset/training scripts: chuẩn bị dữ liệu MC-OCR, train/eval KIE, train/eval OCR recognition.

## 4. Inference Pipeline

Pipeline được chia thành 2 stage rõ ràng.

### 4.1. OCR Stage

OCR stage chịu trách nhiệm đọc text từ ảnh:

- Text detection: tìm vị trí chữ.
- Text recognition: chuyển ảnh crop thành chuỗi ký tự.

Frontend hiện cho chọn 3 cấu hình:

| Option | API value | Mục đích |
| --- | --- | --- |
| PaddleOCR baseline | `paddleocr_original` | Baseline mặc định từ PaddleOCR package |
| PP-OCRv4 pretrained | `paddleocr_pretrained` | Pipeline OCR pretrained chính thức PP-OCRv4 |
| MC-OCR fine-tuned recognizer | `paddleocr_trained` | Text recognizer đã fine-tune từ MC-OCR 2021 |

### 4.2. KIE/SER Stage

KIE/SER stage nhận OCR tokens và gán nhãn field cho từng token.

Frontend hiện cho chọn 2 cấu hình:

| Option | API value | Mục đích |
| --- | --- | --- |
| LayoutXLM pretrained baseline | `kie_pretrained` | Baseline/debug, chưa học 4 field cụ thể |
| LayoutXLM-SER fine-tuned | `kie_trained` | Checkpoint đã fine-tune cho 4 field hiện tại |

Lưu ý: `kie_pretrained` không được kỳ vọng cho kết quả tốt. Nó tồn tại để so sánh baseline và debug pipeline.

## 5. Backend API

```http
GET    /api/health
GET    /api/model-options
POST   /api/scan-image
DELETE /api/scan-results
```

### `GET /api/model-options`

Trả về danh sách OCR/KIE engines, default option và trạng thái model có sẵn hay không.

### `POST /api/scan-image`

Form fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `file` | image | yes | `.jpg`, `.jpeg`, `.png`, `.bmp`, `.webp` |
| `ocr_engine` | string | no | `paddleocr_original`, `paddleocr_pretrained`, `paddleocr_trained` |
| `kie_engine` | string | no | `kie_pretrained`, `kie_trained` |

Response chính:

```json
{
  "file_name": "receipt.jpg",
  "preview_url": "/uploads/...",
  "ocr_engine_label": "MC-OCR fine-tuned recognizer",
  "kie_engine_label": "LayoutXLM-SER fine-tuned",
  "fields": [
    {
      "label": "SELLER",
      "raw_value": "...",
      "display_value": "..."
    }
  ],
  "raw_text": "[SELLER] ...",
  "tokens": [
    {
      "text": "...",
      "label": "SELLER",
      "points": []
    }
  ]
}
```

## 6. Model Và Metrics Hiện Tại

### 6.1. KIE/SER Model

Default KIE checkpoint:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/output/ser_vi_layoutxlm_finrecon_4field/best_accuracy
```

Training run được giữ lại:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/reports/gpu_10epoch_tracked.*
```

Metrics đã ghi nhận:

| Split | Precision | Recall | F1/Hmean |
| --- | ---: | ---: | ---: |
| Validation | 0.9472259811 | 0.9549795362 | 0.9510869565 |
| Test | 0.9069462647 | 0.9153439153 | 0.9111257406 |

Kết luận hiện tại:

- Checkpoint 10 epoch đang là checkpoint KIE tốt nhất đã giữ.
- Các lần continuation sau đó không cải thiện baseline.
- Chỉ nên retrain LayoutXLM/SER nếu thay đổi dataset, label policy, hoặc có failure pattern rõ ràng ở bước phân loại field.

### 6.2. OCR Recognition Model

Default trained OCR recognizer:

```text
archive/models/paddleocr/mcocr2021_rec_svtr_lcnet_best_inference
```

Exported from:

```text
archive/prepared/mcocr2021_text_recognition_paddleocr/output/rec_svtr_lcnet_mcocr2021/best_accuracy
```

Current status:

| Metric | Value |
| --- | ---: |
| Best epoch | 20 |
| Accuracy | 0.4382812466 |
| Normalized edit distance | 0.8654821225 |

Kết luận hiện tại:

- OCR recognizer fine-tuned hiện vẫn là checkpoint thử nghiệm.
- Model có thể chưa tốt hơn PaddleOCR pretrained trên ảnh hóa đơn thật.
- Các lỗi như nhầm `I/l/1`, `O/0`, `S/5`, mất dấu, chữ mờ thường là lỗi OCR recognition, không phải lỗi KIE/SER.

## 7. Dataset

Raw dataset được giữ ngoài git:

```text
archive/source_mcocr/
```

Prepared KIE dataset:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/
```

Prepared OCR recognition dataset:

```text
archive/prepared/mcocr2021_text_recognition_paddleocr/
```

Label policy:

- Giữ cả value lines và context/keyword lines nếu hữu ích cho KIE.
- Không demote `TOTAL_COST` chỉ vì dòng không có số tiền.
- Không demote `TIMESTAMP` chỉ vì dòng không có ngày/giờ.
- Chỉ loại annotation thật sự không dùng được như empty text hoặc geometry lỗi.

## 8. Cấu Trúc Thư Mục

```text
backend/
  app/
    main.py
    services/kie_model.py
  data/

frontend/
  src/App.jsx

scripts/
  datasets/
  training/paddleocr/

archive/
  source_mcocr/      ignored, raw dataset
  prepared/          ignored, prepared datasets and train outputs
  models/            ignored, exported inference models

external/
  PaddleOCR/         ignored, local PaddleOCR clone/runtime
```

Các thư mục nặng được ignore để repo có thể push GitHub:

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

## 9. Cài Đặt Và Chạy Ứng Dụng

### Backend

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

### Frontend

```powershell
cd "D:\Du-an\Invoice Automation & Reconciliation System\frontend"
npm install
npm run dev
```

Frontend:

```text
http://127.0.0.1:5173
```

## 10. Training Và Evaluation

GPU check:

```powershell
.\scripts\training\paddleocr\gpu_check.ps1
```

Train LayoutXLM/SER:

```powershell
.\scripts\training\paddleocr\train_gpu.ps1
```

Evaluate KIE checkpoint:

```powershell
.\scripts\training\paddleocr\eval_ser.ps1 -Split test -UseGpu
```

Prepare OCR recognition data:

```powershell
python scripts\datasets\export_mcocr_text_recognition_dataset.py --clear --copy-mode hardlink
python scripts\datasets\validate_paddleocr_rec_dataset.py --dataset-dir archive\prepared\mcocr2021_text_recognition_paddleocr
```

Download OCR pretrained weights:

```powershell
.\scripts\training\paddleocr\download_rec_pretrained.ps1
```

Fine-tune OCR recognition:

```powershell
.\scripts\training\paddleocr\recognition_train_gpu.ps1
```

Evaluate OCR recognition:

```powershell
.\scripts\training\paddleocr\recognition_eval.ps1 -UseGpu
```

Smoke train OCR recognition:

```powershell
.\scripts\training\paddleocr\recognition_train_gpu.ps1 -RunName rec_smoke_1epoch -EpochNum 1 -BatchSize 8
```

## 11. Runtime Patch Cho PaddleOCR

`external/PaddleOCR/` bị ignore, nên một số sửa runtime cần được apply lại sau khi clone/cài mới.

```powershell
.\scripts\training\paddleocr\apply_runtime_patches.ps1
```

Script này đảm bảo KIE inference có thể:

- Nhận OCR config động từ backend.
- Dùng `inference.json` khi export model bằng Paddle 3.
- Xử lý output recognition head tương thích với custom character dictionary.

## 12. Kiểm Tra Nhanh

Backend:

```powershell
python -m compileall backend\app
```

Frontend:

```powershell
cd frontend
npm run build
```

API option smoke test:

```powershell
$env:PYTHONPATH='backend'
$env:PYTHONUTF8='1'
backend\.venv\Scripts\python.exe -c "from fastapi.testclient import TestClient; from app.main import app; r=TestClient(app).get('/api/model-options'); print(r.status_code, r.json()['default_ocr_engine'])"
```

## 13. Giới Hạn Hiện Tại

- OCR fine-tuned checkpoint chưa đủ mạnh để xem là production OCR.
- Chưa có benchmark tự động so sánh từng pipeline OCR/KIE trên cùng tập ảnh thật.
- Chưa có annotation review UI để sửa ground truth trực tiếp.
- Chưa có export error report theo field.
- Chưa đóng gói model artifacts nhẹ để chạy portable sau khi clone repo.

## 14. Roadmap Đề Xuất

Ưu tiên tiếp theo:

1. Tạo evaluation set ảnh hóa đơn thật ngoài train set.
2. Chạy benchmark 3 OCR options x 2 KIE options.
3. Track CER/WER cho OCR recognition và F1 theo field cho KIE.
4. Train tiếp OCR recognition với augmentation cho ảnh mờ, JPEG noise, low-resolution.
5. Thêm error analysis page: false positive, false negative, OCR confusion, SER confusion.
6. Sau khi extraction ổn định, mới mở rộng lại workflow doanh nghiệp như payable review hoặc reconciliation.

## 15. Định Nghĩa Thuật Ngữ

- OCR: Optical Character Recognition, gồm text detection và text recognition.
- Text detection: phát hiện bounding boxes chứa chữ.
- Text recognition: đọc nội dung chữ từ từng vùng ảnh.
- KIE: Key Information Extraction, trích xuất thông tin có ý nghĩa nghiệp vụ.
- SER: Sequence Entity Recognition, bài toán gán nhãn token trong document.
- Baseline: cấu hình tham chiếu để so sánh.
- Pretrained: model đã học trước trên tập dữ liệu lớn.
- Fine-tuned: model pretrained được train tiếp trên dataset mục tiêu.
