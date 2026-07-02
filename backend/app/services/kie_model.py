from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any

from app.utils import parse_amount, parse_date


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
PADDLEOCR_ROOT = REPO_ROOT / "external" / "PaddleOCR"
DEFAULT_CONFIG_PATH = REPO_ROOT / "archive" / "prepared" / "finrecon_receipt_4field_clean" / "paddleocr_ser" / "ser_vi_layoutxlm_finrecon_4field.yml"
DEFAULT_CHECKPOINT_DIR = (
    REPO_ROOT
    / "archive"
    / "prepared"
    / "finrecon_receipt_4field_clean"
    / "paddleocr_ser"
    / "output"
    / "ser_vi_layoutxlm_finrecon_4field"
    / "best_accuracy"
)
DEFAULT_PADDLE_PYTHON = REPO_ROOT / ".venvs" / "paddleocr-gpu" / "Scripts" / "python.exe"
DEFAULT_WORK_DIR = BACKEND_DIR / "data" / "kie_inference"
INFER_SCRIPT = PADDLEOCR_ROOT / "tools" / "infer_kie_token_ser.py"
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
FIELD_LABELS = {"SELLER", "ADDRESS", "TIMESTAMP", "TOTAL_COST"}


class KieModelError(RuntimeError):
    pass


def is_model_supported_file(file_name: str | None) -> bool:
    return Path(file_name or "").suffix.lower() in SUPPORTED_IMAGE_SUFFIXES


def _path_from_env(name: str, default: Path) -> Path:
    return Path(os.getenv(name, str(default))).resolve()


def _validate_runtime() -> tuple[Path, Path, Path]:
    python_path = _path_from_env("PADDLEOCR_PYTHON", DEFAULT_PADDLE_PYTHON)
    config_path = _path_from_env("PADDLEOCR_SER_CONFIG", DEFAULT_CONFIG_PATH)
    checkpoint_dir = _path_from_env("PADDLEOCR_SER_CHECKPOINT", DEFAULT_CHECKPOINT_DIR)

    missing = [
        str(path)
        for path in (python_path, config_path, checkpoint_dir, INFER_SCRIPT, PADDLEOCR_ROOT)
        if not path.exists()
    ]
    if missing:
        raise KieModelError("Thiếu runtime/model PaddleOCR: " + "; ".join(missing))
    return python_path, config_path, checkpoint_dir


def _runtime_env() -> dict[str, str]:
    cache_dir = _path_from_env("FINRECON_PADDLE_CACHE", REPO_ROOT / ".cache")
    temp_dir = cache_dir / "tmp"
    cache_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PPNLP_HOME": str(cache_dir / "paddlenlp"),
            "PADDLE_HOME": str(cache_dir / "paddle"),
            "HF_HOME": str(cache_dir / "huggingface"),
            "XDG_CACHE_HOME": str(cache_dir),
            "PIP_CACHE_DIR": str(cache_dir / "pip"),
            "TEMP": str(temp_dir),
            "TMP": str(temp_dir),
        }
    )
    return env


def _run_inference(image_path: Path, use_gpu: bool = True, timeout_seconds: int = 180) -> tuple[list[dict[str, Any]], str]:
    python_path, config_path, checkpoint_dir = _validate_runtime()
    work_dir = _path_from_env("PADDLEOCR_KIE_WORK_DIR", DEFAULT_WORK_DIR)
    output_dir = work_dir / uuid.uuid4().hex
    output_dir.mkdir(parents=True, exist_ok=True)

    args = [
        str(python_path),
        str(INFER_SCRIPT),
        "-c",
        str(config_path),
        "-o",
        f"Global.use_gpu={'True' if use_gpu else 'False'}",
        f"Global.infer_img={image_path}",
        f"Global.save_res_path={output_dir}",
        f"Architecture.Backbone.checkpoints={checkpoint_dir}",
    ]
    completed = subprocess.run(
        args,
        cwd=str(PADDLEOCR_ROOT),
        env=_runtime_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
    )
    log_text = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    if completed.returncode != 0:
        raise KieModelError(f"PaddleOCR inference lỗi code {completed.returncode}:\n{log_text[-4000:]}")

    result_path = output_dir / "infer_results.txt"
    if not result_path.exists():
        raise KieModelError(f"PaddleOCR không sinh infer_results.txt.\n{log_text[-4000:]}")

    first_line = result_path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    try:
        _, payload = first_line.split("\t", 1)
        ocr_info = json.loads(payload).get("ocr_info", [])
    except Exception as exc:
        raise KieModelError(f"Không đọc được output PaddleOCR: {exc}") from exc
    return ocr_info, str(output_dir)


def _normalize_label(value: Any) -> str:
    label = str(value or "OTHER").upper().replace("B-", "").replace("I-", "")
    return label if label in FIELD_LABELS else "OTHER"


def _token_text(token: dict[str, Any]) -> str:
    return str(token.get("transcription") or token.get("text") or "").strip()


def _bbox_top(token: dict[str, Any]) -> float:
    points = token.get("points") or []
    bbox = token.get("bbox") or []
    if points:
        try:
            return min(float(point[1]) for point in points)
        except Exception:
            return 0.0
    if len(bbox) >= 2:
        try:
            return float(bbox[1])
        except Exception:
            return 0.0
    return 0.0


def _bbox_left(token: dict[str, Any]) -> float:
    points = token.get("points") or []
    bbox = token.get("bbox") or []
    if points:
        try:
            return min(float(point[0]) for point in points)
        except Exception:
            return 0.0
    if bbox:
        try:
            return float(bbox[0])
        except Exception:
            return 0.0
    return 0.0


def _join_label_text(tokens: list[dict[str, Any]], label: str) -> str | None:
    texts = [
        _token_text(token)
        for token in sorted(tokens, key=lambda item: (_bbox_top(item), _bbox_left(item)))
        if _normalize_label(token.get("pred")) == label and _token_text(token)
    ]
    if not texts:
        return None
    return re.sub(r"\s+", " ", " ".join(texts)).strip()


def _extract_date(text: str | None) -> str | None:
    if not text:
        return None
    exact = parse_date(text)
    if exact:
        return exact
    match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", text)
    if not match:
        return None
    value = match.group(1)
    parts = re.split(r"[/-]", value)
    if len(parts[-1]) == 2:
        value = f"{parts[0]}/{parts[1]}/20{parts[2]}"
    return parse_date(value)


def _extract_amount(text: str | None) -> float | None:
    if not text:
        return None
    amounts: list[float] = []
    for match in re.finditer(r"(?<!\d)(\d[\d\s.,]{2,})(?!\d)", text):
        amount = parse_amount(match.group(1))
        if amount is not None:
            amounts.append(amount)
    if amounts:
        return max(amounts)
    return parse_amount(text)


def model_tokens_to_payload(tokens: list[dict[str, Any]]) -> dict[str, Any]:
    seller_text = _join_label_text(tokens, "SELLER")
    address_text = _join_label_text(tokens, "ADDRESS")
    timestamp_text = _join_label_text(tokens, "TIMESTAMP")
    total_text = _join_label_text(tokens, "TOTAL_COST")
    labelled_lines = []
    for token in sorted(tokens, key=lambda item: (_bbox_top(item), _bbox_left(item))):
        text = _token_text(token)
        if not text:
            continue
        labelled_lines.append(f"[{_normalize_label(token.get('pred'))}] {text}")

    return {
        "invoice_number": None,
        "vendor_name": seller_text,
        "vendor_address": address_text,
        "invoice_date": _extract_date(timestamp_text),
        "total_amount": _extract_amount(total_text),
        "currency": "VND",
        "source_type": "paddleocr_ser_model_only",
        "ocr_confidence": None,
        "raw_text": "\n".join(labelled_lines),
        "model_fields": {
            "seller": seller_text,
            "address": address_text,
            "timestamp": timestamp_text,
            "total_cost": total_text,
        },
        "model_tokens": [
            {
                "text": _token_text(token),
                "label": _normalize_label(token.get("pred")),
                "points": token.get("points"),
                "bbox": token.get("bbox"),
            }
            for token in tokens
            if _token_text(token)
        ],
    }


def extract_receipt_fields_model_only(image_path: Path, *, use_gpu: bool = True) -> dict[str, Any]:
    tokens, output_dir = _run_inference(image_path.resolve(), use_gpu=use_gpu)
    payload = model_tokens_to_payload(tokens)
    payload["model_output_dir"] = output_dir
    return payload
