# Archive Local Data Layout

`archive/` is the local data area for OCR/KIE datasets, training exports, reports, and checkpoints. Most of it is intentionally ignored by Git.

## Do Not Commit Heavy Data

`.gitignore` excludes:

- `archive/source_mcocr/`
- `archive/prepared/`
- `archive/models/`
- image/PDF/spreadsheet files
- `train.json`, `val.json`, `test.json`
- Paddle checkpoint/model files
- JSONL training metrics

Keep only lightweight documentation in Git.

## Current Local Layout

```text
archive/
  README.md
  source_mcocr/                         # raw MC-OCR dataset, read-only, ignored
  prepared/
    finrecon_receipt_4field/            # generated prepared dataset, ignored
    finrecon_receipt_4field_clean/      # generated clean dataset, ignored
      paddleocr_ser/                    # PaddleOCR LayoutXLM/SER export, ignored
        images/
        train.json
        val.json
        test.json
        class_list.txt
        ser_vi_layoutxlm_finrecon_4field.yml
        output/
          ser_vi_layoutxlm_finrecon_4field/
            best_accuracy/              # current best checkpoint
        reports/
          gpu_10epoch_tracked.*         # current kept train/eval logs
    mcocr2021_text_detection_paddleocr/ # PaddleOCR DB detection export, ignored
      images/
      train.txt
      val.txt
      test.txt
      det_mv3_db_mcocr2021.yml
      output/
        det_db_mv3_mcocr2021_receipts_v2/ # detection checkpoints, ignored
      reports/
  models/
    paddleocr/
      ch_ppocr_mobile_v2.0_det_train/     # full DB detector pretrained checkpoint
        best_accuracy.pdparams
```

## Active Dataset

The active KIE/SER dataset is:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser
```

Labels:

```text
OTHER
SELLER
ADDRESS
TIMESTAMP
TOTAL_COST
```

The current best checkpoint is:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/output/ser_vi_layoutxlm_finrecon_4field/best_accuracy
```

The active PaddleOCR detection dataset is:

```text
archive/prepared/mcocr2021_text_detection_paddleocr
```

Current detection export:

```text
documents: 1154
annotations: 47626
train/val/test: 924 / 115 / 115
```

The active detection fine-tune starts from PaddleOCR's full DB detector checkpoint, not a bare MobileNetV3 backbone:

```text
archive/models/paddleocr/ch_ppocr_mobile_v2.0_det_train/best_accuracy
```

Detection training outputs are isolated under:

```text
archive/prepared/mcocr2021_text_detection_paddleocr/output/det_db_mv3_mcocr2021_receipts_v2
```

## Recreate Training Data

Put the raw MC-OCR source under:

```text
archive/source_mcocr/
```

Then run:

```powershell
python scripts\datasets\prepare_receipt_4field_dataset.py --clear --copy-mode hardlink
python scripts\datasets\clean_receipt_4field_dataset.py --clear --copy-mode hardlink
python scripts\datasets\export_paddleocr_ser_dataset.py --dataset-dir archive\prepared\finrecon_receipt_4field_clean --output-dir archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser --copy-mode hardlink --epoch-num 10 --eval-step 250 --batch-size 2 --learning-rate 0.00002 --warmup-epoch 1 --clip-norm-global 1.0
python scripts\datasets\validate_paddleocr_ser_dataset.py --dataset-dir archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser
python scripts\datasets\export_paddleocr_det_dataset.py --clear
python scripts\datasets\validate_paddleocr_det_dataset.py --dataset-dir archive\prepared\mcocr2021_text_detection_paddleocr
```

Future OCR data preparation should be split into:

- PaddleOCR detection fine-tuning data from receipt images and polygons.
- VietOCR recognition fine-tuning data from cropped text-line images and transcripts.

## Train/Eval

```powershell
.\scripts\training\paddleocr\gpu_check.ps1
.\scripts\training\kie_layoutxlm\train_gpu.ps1
.\scripts\training\kie_layoutxlm\eval_ser.ps1 -Split test -UseGpu
.\scripts\training\paddleocr_detection\download_det_pretrained.ps1
.\scripts\training\paddleocr_detection\train_gpu.ps1
.\scripts\training\paddleocr_detection\eval_det.ps1 -Split test -UseGpu
```

## Sharing Dataset Or Model

Do not push large dataset/model artifacts through normal Git. Use one of:

- Hugging Face Dataset/Model Hub
- Google Drive/OneDrive
- GitHub Releases
- Git LFS only if versioning large files is truly needed
