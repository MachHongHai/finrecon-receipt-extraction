# Archive Dataset Layout

Thu muc nay duoc chia lam 2 vung chinh de tranh lan giua data goc va output do FinRecon sinh ra.

## `source_mcocr/`

Day la dataset goc ban da bo sung vao project. Khong sua truc tiep cac file trong day khi prepare/train.

Noi dung chinh:

- `mcocr_train_df.csv`: annotation chinh cho 4 field `SELLER`, `ADDRESS`, `TIMESTAMP`, `TOTAL_COST`.
- `train_images/train_images/`: anh train goc, khop voi `mcocr_train_df.csv`.
- `kie_data/kie_data/`: box-level OCR/KIE annotation.
- `text_recognition_mcocr_data/`: crop anh cho text recognition.
- `text_detector/`, `dataset/text_detector/`: annotation/phu lieu text detection.
- `preprocessor/`, `rotation_corrector/`, `rotation_corrector_kie/`: du lieu tien xu ly/xoay anh.
- `val_images/`, `mcocr_val_sample_df.csv`, `results.csv`: val sample hien tai chua co ground truth field tot.
- `pre_dict.pkl`, `post_dict.pkl`: du lieu phu tro pipeline cu.

Quy tac: coi `source_mcocr/` la read-only.

## `prepared/`

Day la output do code FinRecon sinh ra de chuan bi train/evaluate.

Hien tai co:

- `prepared/finrecon_receipt_4field/`
  - `images/`: anh da copy tu `source_mcocr/train_images/train_images`.
  - `labels.jsonl`: dataset sach cho 4 field `seller`, `address`, `timestamp`, `total_cost`.
  - `splits/train.txt`, `splits/val.txt`, `splits/test.txt`: split noi bo vi val goc chua co nhan dung.
  - `reports/dataset_audit.md`: thong ke dataset sau khi prepare.
  - `reports/baseline_report.md`: diem baseline heuristic truoc khi train model.
  - `reports/baseline_predictions.jsonl`: prediction baseline tren val/test.
  - `token_classification/`: dataset token-level de train model KIE/token classifier.
    - `train.jsonl`, `val.jsonl`, `test.jsonl`: moi dong la 1 receipt voi danh sach token OCR/KIE.
    - `tokens.csv`: bang phang de inspect nhanh tung token/label.
    - `label_map.json`: mapping `OTHER`, `SELLER`, `ADDRESS`, `TIMESTAMP`, `TOTAL_COST`.
    - `token_dataset_report.md`: thong ke class imbalance va so token theo split.
  - `paddleocr_ser/`: export rieng cho PaddleOCR KIE/SER.
    - `images/`: anh receipt dung cho PaddleOCR.
    - `train.json`, `val.json`, `test.json`: moi dong la `image<TAB>json_annotations`.
    - `class_list.txt`: class list cho PaddleOCR, `OTHER` nam dau tien.
    - `ser_vi_layoutxlm_finrecon_4field.yml`: config train VI-LayoutXLM SER.
    - `README_TRAINING.md`: lenh train va luu y moi truong.

Quy tac: co the xoa/sinh lai `prepared/` bang script, vi day la generated output.

## Scripts lien quan

Chay prepare dataset:

```powershell
.\backend\.venv\Scripts\python.exe .\tools\prepare_receipt_4field_dataset.py --clear --copy-mode copy
```

Chay baseline evaluation:

```powershell
.\backend\.venv\Scripts\python.exe .\tools\evaluate_receipt_4field_baseline.py
```

Build token classification dataset:

```powershell
.\backend\.venv\Scripts\python.exe .\tools\build_receipt_token_dataset.py
```

Export PaddleOCR SER dataset:

```powershell
.\backend\.venv\Scripts\python.exe .\tools\export_paddleocr_ser_dataset.py --clear --copy-mode copy
```

Default path cua script:

- Input goc: `archive/source_mcocr`
- Output prepare: `archive/prepared/finrecon_receipt_4field`
