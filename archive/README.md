# Archive Local Data Layout

`archive/` la khu vuc du lieu local cho OCR/KIE training. Thu muc nay khong nen day len GitHub, ngoai file README nhe nay.

## Khong commit

`.gitignore` da bo qua cac thu muc/file nang sau:

- `archive/source_mcocr/`: dataset MC-OCR goc.
- `archive/prepared/`: dataset da prepare/export, co the sinh lai.
- `archive/models/`: model/checkpoint/export artifact neu co.
- Anh, PDF, CSV/TSV/XLSX, JSONL, `train.json`, `val.json`, `test.json`, checkpoint Paddle.

Neu can chia se dataset/model, dung mot trong cac cach sau thay vi Git thuong:

- Hugging Face Dataset/Model Hub.
- Google Drive/OneDrive link.
- GitHub Release artifact.
- Git LFS chi khi that su can version file nặng trong repo.

## Cau truc local de xuat

```text
archive/
  README.md
  source_mcocr/                         # raw dataset, read-only, ignored
  prepared/
    finrecon_receipt_4field/            # generated prepared dataset, ignored
    finrecon_receipt_4field_clean/      # generated clean dataset, ignored
      paddleocr_ser/                    # PaddleOCR SER export, ignored
  models/
    paddleocr_ser_4field/               # trained checkpoints/inference exports, ignored
```

## Cach tai tao dataset train

Dat dataset goc vao:

```text
archive/source_mcocr/
```

Sau do chay:

```powershell
python tools\prepare_receipt_4field_dataset.py --clear --copy-mode hardlink
python tools\clean_receipt_4field_dataset.py --clear --copy-mode hardlink
python tools\export_paddleocr_ser_dataset.py --dataset-dir archive\prepared\finrecon_receipt_4field_clean --output-dir archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser --copy-mode hardlink --epoch-num 6 --eval-step 250 --batch-size 2 --learning-rate 0.00002 --warmup-epoch 1 --clip-norm-global 1.0
python tools\validate_paddleocr_ser_dataset.py --dataset-dir archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser
```

## Train/eval

```powershell
.\tools\paddleocr_gpu_check.ps1
.\tools\paddleocr_train_gpu.ps1
.\tools\paddleocr_eval_ser.ps1 -Split test -UseGpu
```
