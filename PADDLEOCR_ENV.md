# PaddleOCR Environment

Moi truong PaddleOCR duoc tach rieng khoi backend/frontend.

## Duong dan

- Python env: `.venvs/paddleocr`
- Python GPU env: `.venvs/paddleocr-gpu`
- PaddleOCR source: `external/PaddleOCR`
- Project cache: `.cache/`
- PaddleOCR SER dataset khuyen nghi: `archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser`
- Train config khuyen nghi: `archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser/ser_vi_layoutxlm_finrecon_4field.yml`

## Cache va dung luong

Tat ca script PaddleOCR trong `tools/` deu nap `tools/paddleocr_env.ps1` truoc khi chay. File nay ep cache ve o D trong project:

```text
.cache/paddlenlp
.cache/paddle
.cache/huggingface
.cache/pip
.cache/tmp
```

Bien moi truong duoc set trong script:

```text
PPNLP_HOME=.cache/paddlenlp
PADDLE_HOME=.cache/paddle
HF_HOME=.cache/huggingface
XDG_CACHE_HOME=.cache
PIP_CACHE_DIR=.cache/pip
TEMP=.cache/tmp
TMP=.cache/tmp
```

Model pretrained `vi-layoutxlm-base-uncased` da duoc chuyen tu `C:\Users\ADMIN\.paddlenlp` sang `.cache/paddlenlp`.

Ngoai ra, cac bien User environment sau da duoc set de neu chay lenh Paddle/PaddleNLP thu cong thi cache van ve D:

```text
PPNLP_HOME=D:\Du-an\Invoice Automation & Reconciliation System\.cache\paddlenlp
PADDLE_HOME=D:\Du-an\Invoice Automation & Reconciliation System\.cache\paddle
HF_HOME=D:\Du-an\Invoice Automation & Reconciliation System\.cache\huggingface
```

Neu dang mo terminal cu, hay mo terminal moi de nhan User environment moi. Cac script trong `tools/` thi tu set env nen khong can mo terminal moi.

## Phien ban da kiem tra - CPU env

- Python: 3.10.20
- PaddlePaddle: 2.6.2 CPU
- PaddleNLP: 2.6.1
- OpenCV: 4.6.0
- NumPy: 1.26.4

Kiem tra nhanh:

```powershell
.\.venvs\paddleocr\Scripts\python.exe -c "import paddle, cv2, paddlenlp, numpy; print(paddle.__version__, paddle.device.is_compiled_with_cuda()); print(cv2.__version__, paddlenlp.__version__, numpy.__version__)"
```

Ket qua hien tai la Paddle CPU:

```text
paddle 2.6.2 cuda False
```

## Phien ban da kiem tra - GPU env

- Python: 3.10.20
- PaddlePaddle GPU: 3.2.2, CUDA 12.6 wheel
- PaddleNLP: 2.6.1
- OpenCV: 4.6.0
- NumPy: 1.26.4
- GPU env cai dung PaddlePaddle GPU wheel, nhung can kiem tra lai tai thoi diem train bang `.\tools\paddleocr_gpu_check.ps1`.

Kiem tra nhanh:

```powershell
.\tools\paddleocr_gpu_check.ps1
```

Ket qua mong doi khi GPU dang active:

```text
paddle 3.2.2 cuda True gpu_count 1
device gpu:0
PaddlePaddle works well on 1 GPU.
```

Neu output la `gpu_count 0` va `device cpu`, chua train GPU duoc. Lan kiem tra gan nhat sau khi active GPU da bao `gpu_count 1`, `device gpu:0`, va `PaddlePaddle works well on 1 GPU`. Truoc khi train that, van nen chay lai `.\tools\paddleocr_gpu_check.ps1`, cam sac laptop va dam bao Windows dang cho phep dung NVIDIA GPU.

## Chay train CPU de test pipeline

CPU rat cham, chi nen dung de test pipeline/config.

```powershell
.\tools\paddleocr_train_cpu.ps1
```

Hoac chay truc tiep:

```powershell
.\.venvs\paddleocr\Scripts\python.exe .\external\PaddleOCR\tools\train.py `
  -c ".\archive\prepared\finrecon_receipt_4field\paddleocr_ser\ser_vi_layoutxlm_finrecon_4field.yml" `
  -o Global.use_gpu=False
```

## Chay train GPU

May co NVIDIA RTX 4060 Laptop GPU. Env GPU rieng da duoc tao tai `.venvs/paddleocr-gpu`.

Test GPU:

```powershell
.\tools\paddleocr_gpu_check.ps1
```

Train GPU quick 10 epoch tren dataset clean:

```powershell
.\tools\paddleocr_train_gpu.ps1
```

Tao lai dataset clean va PaddleOCR SER export:

```powershell
python tools\clean_receipt_4field_dataset.py --clear --copy-mode hardlink
python tools\export_paddleocr_ser_dataset.py --dataset-dir archive\prepared\finrecon_receipt_4field_clean --output-dir archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser --copy-mode hardlink --clear --epoch-num 10 --eval-step 500 --batch-size 2
python tools\validate_paddleocr_ser_dataset.py archive\prepared\finrecon_receipt_4field_clean\paddleocr_ser
```

Ghi chu: `boxes_and_transcripts` cua MC-OCR co nhieu transcript rong, ke ca box target field. Pipeline prepare hien dung `mcocr_train_df.csv` lam nguon text chinh thuc cho `SELLER`, `ADDRESS`, `TIMESTAMP`, `TOTAL_COST`: box target rong se duoc recover bang CSV neu bbox overlap tot, annotation CSV con thieu se duoc append vao `boxes`, va box `OTHER` rong bi bo qua. Rule clean khong demote `TOTAL_COST` vi thieu so tien va khong demote `TIMESTAMP` vi thieu ngay/gio.

## Tao lai moi truong

```powershell
uv python install 3.10
uv venv .\.venvs\paddleocr --python 3.10
uv pip install --python .\.venvs\paddleocr\Scripts\python.exe pip setuptools wheel
uv pip install --python .\.venvs\paddleocr\Scripts\python.exe paddlepaddle==2.6.2
uv pip install --python .\.venvs\paddleocr\Scripts\python.exe -r .\external\PaddleOCR\requirements.txt
uv pip install --python .\.venvs\paddleocr\Scripts\python.exe numpy==1.26.4 paddlenlp==2.6.1
```

## Tao lai moi truong GPU

```powershell
uv python install 3.10
uv venv .\.venvs\paddleocr-gpu --python 3.10
uv pip install --python .\.venvs\paddleocr-gpu\Scripts\python.exe pip setuptools wheel
uv pip install --python .\.venvs\paddleocr-gpu\Scripts\python.exe paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
uv pip install --python .\.venvs\paddleocr-gpu\Scripts\python.exe -r .\external\PaddleOCR\requirements.txt paddlenlp==2.6.1
uv pip install --python .\.venvs\paddleocr-gpu\Scripts\python.exe numpy==1.26.4
```

Ghi chu: `paddlenlp==2.8.1` khong dung duoc tren Windows trong lan kiem tra nay vi dependency `tool-helpers` khong co wheel `win_amd64`.
