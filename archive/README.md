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
    mcocr2021_text_recognition_paddleocr/ # PaddleOCR OCR recognition export, ignored
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
  models/                               # optional future exported models, ignored
```

## Active Dataset

The active KIE/SER dataset is:

```text
archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser
```

The active OCR recognition fine-tune dataset is:

```text
archive/prepared/mcocr2021_text_recognition_paddleocr
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
```

Recreate OCR recognition training data from MC-OCR text crops:

```powershell
python scripts\datasets\export_mcocr_text_recognition_dataset.py --clear --copy-mode hardlink
python scripts\datasets\validate_paddleocr_rec_dataset.py --dataset-dir archive\prepared\mcocr2021_text_recognition_paddleocr
```

## Train/Eval

```powershell
.\scripts\training\paddleocr\gpu_check.ps1
.\scripts\training\paddleocr\train_gpu.ps1
.\scripts\training\paddleocr\eval_ser.ps1 -Split test -UseGpu
.\scripts\training\paddleocr\download_rec_pretrained.ps1
.\scripts\training\paddleocr\recognition_train_gpu.ps1
.\scripts\training\paddleocr\recognition_eval.ps1 -UseGpu
```

## Sharing Dataset Or Model

Do not push large dataset/model artifacts through normal Git. Use one of:

- Hugging Face Dataset/Model Hub
- Google Drive/OneDrive
- GitHub Releases
- Git LFS only if versioning large files is truly needed
