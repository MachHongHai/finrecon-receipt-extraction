from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import DEFAULT_DATA_DIR, UPLOAD_DIR, ensure_storage
from app.services.kie_model import (
    KieModelError,
    extract_receipt_fields_model_only,
    is_model_supported_file,
)


app = FastAPI(title="FinRecon Receipt Field Extractor API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ensure_storage()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


def _save_upload(file_name: str | None, content: bytes) -> Path:
    safe_name = Path(file_name or "receipt.jpg").name
    target = UPLOAD_DIR / f"{uuid.uuid4().hex}_{safe_name}"
    target.write_bytes(content)
    return target


def _preview_url(path: Path) -> str:
    return f"/uploads/{path.name}"


def _field_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    model_fields = payload.get("model_fields") or {}
    return [
        {"label": "SELLER", "value": model_fields.get("SELLER")},
        {"label": "ADDRESS", "value": model_fields.get("ADDRESS")},
        {"label": "TIMESTAMP", "value": model_fields.get("TIMESTAMP")},
        {"label": "TOTAL_COST", "value": model_fields.get("TOTAL_COST")},
    ]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "model_only"}


@app.post("/api/scan-image")
async def scan_image(file: UploadFile = File(...)) -> dict[str, Any]:
    if not is_model_supported_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail="Chỉ hỗ trợ ảnh .jpg, .jpeg, .png, .bmp, .webp. Không dùng fallback.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File ảnh rỗng.")

    saved_path = _save_upload(file.filename, content)
    try:
        payload = extract_receipt_fields_model_only(saved_path)
    except KieModelError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "file_name": Path(file.filename or saved_path.name).name,
        "preview_url": _preview_url(saved_path),
        "mode": "paddleocr_layoutxlm_model_only",
        "fields": _field_rows(payload),
        "raw_text": payload.get("raw_text") or "",
        "tokens": payload.get("model_tokens") or [],
        "model_output_dir": payload.get("model_output_dir"),
    }


@app.delete("/api/scan-results")
def clear_scan_results() -> dict[str, Any]:
    deleted_uploads = 0
    for item in UPLOAD_DIR.glob("*"):
        if item.is_file():
            item.unlink()
            deleted_uploads += 1

    inference_dir = DEFAULT_DATA_DIR / "kie_inference"
    if inference_dir.exists():
        shutil.rmtree(inference_dir)
    inference_dir.mkdir(parents=True, exist_ok=True)

    return {"cleared": True, "deleted_uploads": deleted_uploads}
