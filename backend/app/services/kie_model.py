from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
PADDLEOCR_ROOT = REPO_ROOT / "external" / "PaddleOCR"
DEFAULT_CONFIG_PATH = (
    REPO_ROOT
    / "archive"
    / "prepared"
    / "finrecon_receipt_4field_clean"
    / "paddleocr_ser"
    / "ser_vi_layoutxlm_finrecon_4field.yml"
)
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
DEFAULT_REC_MODEL_DIR = (
    REPO_ROOT
    / "archive"
    / "models"
    / "paddleocr"
    / "mcocr2021_rec_svtr_lcnet_best_inference"
)
DEFAULT_REC_CHAR_DICT = (
    REPO_ROOT
    / "archive"
    / "prepared"
    / "mcocr2021_text_recognition_paddleocr"
    / "dict"
    / "mcocr2021_vi_receipt_dict.txt"
)
DEFAULT_PADDLE_PYTHON = REPO_ROOT / ".venvs" / "paddleocr-gpu" / "Scripts" / "python.exe"
DEFAULT_WORK_DIR = BACKEND_DIR / "data" / "kie_inference"
INFER_SCRIPT = PADDLEOCR_ROOT / "tools" / "infer_kie_token_ser.py"
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
FIELD_LABELS = {"SELLER", "ADDRESS", "TIMESTAMP", "TOTAL_COST"}

# Keep these option keys explicit. "pretrained" means the official Chinese
# PP-OCRv4 pipeline. Vietnamese/Latin is a separate option so benchmarking is
# not ambiguous.
OCR_ENGINE_PROFILES: dict[str, dict[str, Any]] = {
    "paddleocr_original": {
        "label": "PaddleOCR package default",
        "description": "PaddleOCR default configuration. This is only a package baseline.",
        "requires_trained_recognizer": False,
        "overrides": {},
    },
    "paddleocr_pretrained": {
        "label": "PP-OCRv4 Chinese pretrained",
        "description": "Official PP-OCRv4 pretrained OCR with lang=ch. Useful baseline, weak for Vietnamese diacritics.",
        "requires_trained_recognizer": False,
        "overrides": {
            "Global.ocr_version": "PP-OCRv4",
            "Global.ocr_lang": "ch",
        },
    },
    "paddleocr_vi_pretrained": {
        "label": "PP-OCRv4 Vietnamese/Latin pretrained",
        "description": "Official PaddleOCR pretrained OCR with lang=vi, mapped to the Latin recognizer for Vietnamese diacritics.",
        "requires_trained_recognizer": False,
        "overrides": {
            "Global.ocr_version": "PP-OCRv4",
            "Global.ocr_lang": "vi",
        },
    },
    "paddleocr_trained": {
        "label": "MC-OCR fine-tuned recognizer",
        "description": "Project OCR recognizer fine-tuned from MC-OCR 2021 and exported to inference format.",
        "requires_trained_recognizer": True,
        "overrides": {
            "Global.rec_algorithm": "SVTR_LCNet",
            "Global.rec_image_shape": "3,48,640",
            "Global.max_text_length": "160",
            "Global.use_space_char": "True",
        },
    },
}
KIE_ENGINE_PROFILES: dict[str, dict[str, Any]] = {
    "kie_pretrained": {
        "label": "LayoutXLM pretrained baseline",
        "description": "Pretrained LayoutXLM backbone without the project 4-field SER checkpoint.",
        "requires_trained_checkpoint": False,
    },
    "kie_trained": {
        "label": "LayoutXLM-SER fine-tuned",
        "description": "Project SER checkpoint fine-tuned for SELLER, ADDRESS, TIMESTAMP, and TOTAL_COST.",
        "requires_trained_checkpoint": True,
    },
}
DEFAULT_OCR_ENGINE = "paddleocr_vi_pretrained"
DEFAULT_KIE_ENGINE = "kie_trained"


class KieModelError(RuntimeError):
    pass


def is_model_supported_file(file_name: str | None) -> bool:
    return Path(file_name or "").suffix.lower() in SUPPORTED_IMAGE_SUFFIXES


def _path_from_env(name: str, default: Path) -> Path:
    return Path(os.getenv(name, str(default))).resolve()


def _runtime_paths() -> tuple[Path, Path, Path, Path, Path]:
    return (
        _path_from_env("PADDLEOCR_PYTHON", DEFAULT_PADDLE_PYTHON),
        _path_from_env("PADDLEOCR_SER_CONFIG", DEFAULT_CONFIG_PATH),
        _path_from_env("PADDLEOCR_SER_CHECKPOINT", DEFAULT_CHECKPOINT_DIR),
        _path_from_env("PADDLEOCR_REC_MODEL_DIR", DEFAULT_REC_MODEL_DIR),
        _path_from_env("PADDLEOCR_REC_CHAR_DICT", DEFAULT_REC_CHAR_DICT),
    )


def _validate_choice(value: str | None, choices: dict[str, dict[str, Any]], default: str, kind: str) -> str:
    key = value or default
    if key not in choices:
        valid = ", ".join(choices)
        raise KieModelError(f"{kind} is invalid: {key}. Valid values: {valid}")
    return key


def _validate_runtime(ocr_engine: str, kie_engine: str) -> tuple[Path, Path, Path | None, Path | None, Path | None]:
    python_path, config_path, checkpoint_dir, rec_model_dir, rec_char_dict = _runtime_paths()
    missing = [
        str(path)
        for path in (python_path, config_path, INFER_SCRIPT, PADDLEOCR_ROOT)
        if not path.exists()
    ]
    if KIE_ENGINE_PROFILES[kie_engine]["requires_trained_checkpoint"] and not checkpoint_dir.exists():
        missing.append(str(checkpoint_dir))
    if OCR_ENGINE_PROFILES[ocr_engine]["requires_trained_recognizer"]:
        for path in (rec_model_dir, rec_char_dict):
            if not path.exists():
                missing.append(str(path))
    if missing:
        raise KieModelError("Missing PaddleOCR runtime/model: " + "; ".join(missing))
    return (
        python_path,
        config_path,
        checkpoint_dir if KIE_ENGINE_PROFILES[kie_engine]["requires_trained_checkpoint"] else None,
        rec_model_dir if OCR_ENGINE_PROFILES[ocr_engine]["requires_trained_recognizer"] else None,
        rec_char_dict if OCR_ENGINE_PROFILES[ocr_engine]["requires_trained_recognizer"] else None,
    )


def _option_payload(key: str, profile: dict[str, Any], available: bool, reason: str | None) -> dict[str, Any]:
    return {
        "value": key,
        "label": profile["label"],
        "description": profile["description"],
        "available": available,
        "reason": reason,
    }


def get_model_runtime_options() -> dict[str, Any]:
    python_path, config_path, checkpoint_dir, rec_model_dir, rec_char_dict = _runtime_paths()
    base_missing = [path for path in (python_path, config_path, INFER_SCRIPT, PADDLEOCR_ROOT) if not path.exists()]

    ocr_options = []
    for key, profile in OCR_ENGINE_PROFILES.items():
        missing = list(base_missing)
        if profile["requires_trained_recognizer"]:
            missing.extend(path for path in (rec_model_dir, rec_char_dict) if not path.exists())
        reason = "Missing: " + "; ".join(str(path) for path in missing) if missing else None
        ocr_options.append(_option_payload(key, profile, not missing, reason))

    kie_options = []
    for key, profile in KIE_ENGINE_PROFILES.items():
        missing = list(base_missing)
        if profile["requires_trained_checkpoint"] and not checkpoint_dir.exists():
            missing.append(checkpoint_dir)
        reason = "Missing: " + "; ".join(str(path) for path in missing) if missing else None
        kie_options.append(_option_payload(key, profile, not missing, reason))

    return {
        "default_ocr_engine": DEFAULT_OCR_ENGINE,
        "default_kie_engine": DEFAULT_KIE_ENGINE,
        "ocr_engines": ocr_options,
        "kie_engines": kie_options,
    }


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
            "HOME": str(cache_dir),
            "USERPROFILE": str(cache_dir),
            "TEMP": str(temp_dir),
            "TMP": str(temp_dir),
        }
    )
    return env


def _run_inference(
    image_path: Path,
    *,
    ocr_engine: str,
    kie_engine: str,
    use_gpu: bool = True,
    timeout_seconds: int = 180,
) -> tuple[list[dict[str, Any]], str]:
    ocr_engine = _validate_choice(ocr_engine, OCR_ENGINE_PROFILES, DEFAULT_OCR_ENGINE, "OCR engine")
    kie_engine = _validate_choice(kie_engine, KIE_ENGINE_PROFILES, DEFAULT_KIE_ENGINE, "KIE engine")
    python_path, config_path, checkpoint_dir, rec_model_dir, rec_char_dict = _validate_runtime(ocr_engine, kie_engine)

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
    ]
    if checkpoint_dir:
        args.append(f"Architecture.Backbone.checkpoints={checkpoint_dir}")
    else:
        args.append("Architecture.Backbone.checkpoints=")

    for name, value in OCR_ENGINE_PROFILES[ocr_engine].get("overrides", {}).items():
        args.append(f"{name}={value}")
    if rec_model_dir and rec_char_dict:
        args.extend(
            [
                f"Global.kie_rec_model_dir={rec_model_dir}",
                f"Global.rec_char_dict_path={rec_char_dict}",
            ]
        )

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
        raise KieModelError(f"PaddleOCR inference failed with code {completed.returncode}:\n{log_text[-4000:]}")

    result_path = output_dir / "infer_results.txt"
    if not result_path.exists():
        raise KieModelError(f"PaddleOCR did not create infer_results.txt.\n{log_text[-4000:]}")

    first_line = result_path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    try:
        _, payload = first_line.split("\t", 1)
        ocr_info = json.loads(payload).get("ocr_info", [])
    except Exception as exc:
        raise KieModelError(f"Could not parse PaddleOCR output: {exc}") from exc
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


def model_tokens_to_payload(tokens: list[dict[str, Any]]) -> dict[str, Any]:
    labelled_lines = []
    for token in sorted(tokens, key=lambda item: (_bbox_top(item), _bbox_left(item))):
        text = _token_text(token)
        if text:
            labelled_lines.append(f"[{_normalize_label(token.get('pred'))}] {text}")

    return {
        "raw_text": "\n".join(labelled_lines),
        "model_fields": {
            "SELLER": _join_label_text(tokens, "SELLER"),
            "ADDRESS": _join_label_text(tokens, "ADDRESS"),
            "TIMESTAMP": _join_label_text(tokens, "TIMESTAMP"),
            "TOTAL_COST": _join_label_text(tokens, "TOTAL_COST"),
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


def extract_receipt_fields_model_only(
    image_path: Path,
    *,
    ocr_engine: str = DEFAULT_OCR_ENGINE,
    kie_engine: str = DEFAULT_KIE_ENGINE,
    use_gpu: bool = True,
) -> dict[str, Any]:
    ocr_engine = _validate_choice(ocr_engine, OCR_ENGINE_PROFILES, DEFAULT_OCR_ENGINE, "OCR engine")
    kie_engine = _validate_choice(kie_engine, KIE_ENGINE_PROFILES, DEFAULT_KIE_ENGINE, "KIE engine")
    tokens, output_dir = _run_inference(
        image_path.resolve(),
        ocr_engine=ocr_engine,
        kie_engine=kie_engine,
        use_gpu=use_gpu,
    )
    payload = model_tokens_to_payload(tokens)
    payload["model_output_dir"] = output_dir
    payload["ocr_engine"] = ocr_engine
    payload["kie_engine"] = kie_engine
    payload["ocr_engine_label"] = OCR_ENGINE_PROFILES[ocr_engine]["label"]
    payload["kie_engine_label"] = KIE_ENGINE_PROFILES[kie_engine]["label"]
    return payload
