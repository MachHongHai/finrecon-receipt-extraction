from __future__ import annotations

import json
import os
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

import jwt
import pandas as pd
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.database import UPLOAD_DIR, get_db, init_db
from app.models import (
    AIReport,
    AuditLog,
    BankTransaction,
    Invoice,
    InvoiceBatch,
    InvoiceItem,
    ProcessingJob,
    ReconciliationException,
    ReconciliationMatch,
    ReconciliationRule,
    PaymentBatch,
    UploadedFile,
    User,
    Vendor,
)
from app.schemas import ExceptionUpdatePayload, InvoicePayload, LoginPayload, ResolvePayload, ReviewInvoicePayload, RulePayload
from app.seed import verify_password
from app.services.reconciliation import calculate_match_score, classify_match, is_reconciliation_candidate, match_reason
from app.services.reporting import build_reconciliation_report
from app.services.validation import validate_bank_transaction, validate_invoice, validation_status
from app.utils import (
    dedupe_invoice_items,
    decode_bytes,
    extract_invoice_fields,
    extract_invoice_items,
    parse_amount,
    parse_date,
    parse_tabular_file_bytes,
    parse_vietnam_einvoice_xml,
)


app = FastAPI(title="FinRecon Receipt AI API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

JWT_SECRET = os.getenv("JWT_SECRET", "finrecon-local-secret")
JWT_ALGORITHM = "HS256"
VALIDATION_EXCEPTION_TYPES = {
    "missing_required_field",
    "date_mismatch",
    "vendor_mismatch",
    "vendor_not_found",
    "vendor_bank_mismatch",
    "invalid_tax_code",
    "vat_total_mismatch",
    "unusual_amount",
    "duplicate_invoice",
    "low_ocr_confidence",
    "low_confidence_fallback_extraction",
    "amount_mismatch",
}
VALID_APPROVAL_STATUSES = {"draft", "needs_review", "approved", "rejected", "paid", "reconciled", "exception"}


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def _serialize(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def as_dict(obj: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    data = {column.name: _serialize(getattr(obj, column.name)) for column in obj.__table__.columns}
    if hasattr(obj, "__tablename__") and obj.__tablename__ == "invoices":
        if getattr(obj, "source_file_path", None):
            data["preview_url"] = preview_url(obj.source_file_path)
        if hasattr(obj, "items") and obj.items is not None:
            data["items"] = dedupe_invoice_items([
                {col.name: _serialize(getattr(item, col.name)) for col in item.__table__.columns}
                for item in obj.items
            ], invoice_total=obj.total_amount)
    if extra:
        data.update(extra)
    return data


def public_user(user: User) -> dict[str, Any]:
    data = as_dict(user)
    data.pop("password_hash", None)
    return data


def get_current_user(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> User:
    user = db.scalar(select(User).order_by(User.id).limit(1))
    if user is None:
        user = User(email="admin@finrecon.local", full_name="Admin", role="admin", is_active=True)
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Bạn không có quyền thực hiện thao tác này")
        return user

    return dependency


def rule_dict(rule: ReconciliationRule | None) -> dict[str, Any]:
    if rule is None:
        return {
            "auto_match_threshold": 85,
            "manual_review_threshold": 60,
            "date_tolerance_days": 30,
            "amount_tolerance_vnd": 500000,
            "low_ocr_confidence_threshold": 80,
            "vat_tolerance": 1,
        }
    return as_dict(rule)


def get_rule(db: Session) -> ReconciliationRule:
    rule = db.scalar(select(ReconciliationRule).order_by(ReconciliationRule.id).limit(1))
    if rule is None:
        rule = ReconciliationRule()
        db.add(rule)
        db.flush()
    return rule


def audit(db: Session, action: str, entity_type: str | None = None, entity_id: int | None = None, details: Any = None) -> None:
    db.add(
        AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=json.dumps(details or {}, ensure_ascii=False),
        )
    )


def to_date(value: Any) -> date | None:
    parsed = parse_date(value)
    return date.fromisoformat(parsed) if parsed else None


def normalize_invoice_payload(payload: dict[str, Any]) -> dict[str, Any]:
    invoice_number = payload.get("invoice_number") or None
    if not invoice_number:
        import random
        from datetime import datetime
        invoice_number = f"REC-{datetime.utcnow().strftime('%m%d')}-{random.randint(1000, 9999)}"

    return {
        "invoice_id": payload.get("invoice_id") or payload.get("invoice_code") or None,
        "invoice_number": invoice_number,
        "invoice_series": payload.get("invoice_series") or None,
        "invoice_template_code": payload.get("invoice_template_code") or None,
        "vendor_id": payload.get("vendor_id") or None,
        "vendor_name": payload.get("vendor_name") or None,
        "vendor_tax_code": payload.get("vendor_tax_code") or None,
        "vendor_bank_account": payload.get("vendor_bank_account") or None,
        "vendor_address": payload.get("vendor_address") or None,
        "vendor_phone": payload.get("vendor_phone") or None,
        "buyer_name": payload.get("buyer_name") or None,
        "buyer_tax_code": payload.get("buyer_tax_code") or None,
        "invoice_date": to_date(payload.get("invoice_date")),
        "due_date": to_date(payload.get("due_date")),
        "subtotal": parse_amount(payload.get("subtotal")),
        "vat_rate": parse_amount(payload.get("vat_rate")),
        "vat_amount": parse_amount(payload.get("vat_amount")),
        "total_amount": parse_amount(payload.get("total_amount")),
        "currency": (payload.get("currency") or "VND").upper(),
        "source_type": payload.get("source_type") or None,
        "attachment_file": payload.get("attachment_file") or None,
        "expected_case": payload.get("expected_case") or None,
        "ocr_confidence": parse_amount(payload.get("ocr_confidence")),
    }


def invoice_for_engine(invoice: Invoice) -> dict[str, Any]:
    data = as_dict(invoice)
    data["invoice_date"] = data.get("invoice_date")
    return data


def transaction_for_engine(transaction: BankTransaction) -> dict[str, Any]:
    return as_dict(transaction)


def save_upload(file_name: str, content: bytes) -> Path:
    safe_name = Path(file_name or "upload.bin").name
    target = UPLOAD_DIR / f"{uuid.uuid4().hex}_{safe_name}"
    target.write_bytes(content)
    return target


def remove_uploaded_file_from_disk(file_path: str | None) -> None:
    if not file_path:
        return
    try:
        target = Path(file_path).resolve()
        upload_root = UPLOAD_DIR.resolve()
        if target.is_file() and upload_root in target.parents:
            target.unlink()
    except Exception:
        pass


def delete_uploaded_files(db: Session, files: list[UploadedFile]) -> int:
    deleted = 0
    for uploaded in files:
        remove_uploaded_file_from_disk(uploaded.file_path)
        db.delete(uploaded)
        deleted += 1
    return deleted


def easyocr_results_to_lines(results: list[Any]) -> str:
    rows: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, (list, tuple)) or len(result) < 2:
            continue
        box = result[0]
        text = str(result[1] or "").strip()
        confidence = float(result[2]) if len(result) > 2 and result[2] is not None else 0
        if not text or confidence < 0.18:
            continue
        try:
            xs = [point[0] for point in box]
            ys = [point[1] for point in box]
        except Exception:
            continue
        x_mid = sum(xs) / len(xs)
        y_mid = sum(ys) / len(ys)
        height = max(ys) - min(ys)
        matched = False
        for row in rows:
            tolerance = max(8, min(18, (row["height"] + height) / 2))
            if abs(row["y"] - y_mid) <= tolerance:
                row["items"].append((x_mid, text))
                row["y"] = (row["y"] + y_mid) / 2
                row["height"] = max(row["height"], height)
                matched = True
                break
        if not matched:
            rows.append({"y": y_mid, "height": height, "items": [(x_mid, text)]})

    lines = []
    for row in sorted(rows, key=lambda item: item["y"]):
        parts = [text for _, text in sorted(row["items"], key=lambda item: item[0])]
        line = " | ".join(parts)
        if line and line not in lines:
            lines.append(line)
    return "\n".join(lines)


def preprocess_ocr_image(img: Any) -> list[Any]:
    import cv2

    variants = [img]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    upscaled = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    denoised = cv2.fastNlMeansDenoising(upscaled, None, 12, 7, 21)
    threshold = cv2.adaptiveThreshold(
        denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        11,
    )
    variants.append(cv2.cvtColor(threshold, cv2.COLOR_GRAY2BGR))
    return variants


def read_extractable_text(file_name: str, content: bytes) -> str:
    suffix = Path(file_name or "").suffix.lower()
    if suffix in {".txt", ".csv", ".json", ".md"}:
        from app.utils import decode_bytes
        return decode_bytes(content)
    
    text_blocks = []
    
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(content))
            text_blocks.append("\n".join(page.extract_text() or "" for page in reader.pages))
        except Exception:
            pass
            
    if suffix in {".pdf", ".png", ".jpg", ".jpeg"}:
        try:
            import easyocr
            import fitz
            import numpy as np
            import cv2
            
            # Lazy initialize reader to avoid loading model on startup
            if not hasattr(read_extractable_text, "reader"):
                read_extractable_text.reader = easyocr.Reader(['vi', 'en'], gpu=False)
            reader = read_extractable_text.reader

            images = []
            if suffix == ".pdf":
                doc = fitz.open(stream=content, filetype="pdf")
                for page in doc:
                    pix = page.get_pixmap(dpi=150)
                    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                    if pix.n == 4:
                        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
                    elif pix.n == 1:
                        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                    images.append(img)
            else:
                img = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    images.append(img)
                    
            for img in images:
                for variant in preprocess_ocr_image(img):
                    results = reader.readtext(variant, detail=1, paragraph=False, decoder="beamsearch", text_threshold=0.45, low_text=0.25)
                    structured_text = easyocr_results_to_lines(results)
                    if structured_text:
                        text_blocks.append(structured_text)
                
        except Exception as e:
            print(f"OCR Error: {e}")
            pass
            
    return "\n".join(text_blocks)


def preview_url(file_path: str | None) -> str | None:
    if not file_path:
        return None
    return f"/uploads/{Path(file_path).name}"


def create_batch(db: Session, batch_type: str, total_files: int) -> InvoiceBatch:
    batch = InvoiceBatch(
        batch_code=f"{batch_type.upper()}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
        batch_type=batch_type,
        total_files=total_files,
        status="processing",
    )
    db.add(batch)
    db.flush()
    audit(db, "batch_created", "invoice_batch", batch.id, {"batch_type": batch_type, "total_files": total_files})
    return batch


def create_uploaded_file(db: Session, file_name: str, file_path: Path, category: str, batch_id: int | None = None) -> UploadedFile:
    uploaded = UploadedFile(
        batch_id=batch_id,
        file_name=Path(file_name or "upload.bin").name,
        file_path=str(file_path),
        file_type=Path(file_name or "").suffix.lower().lstrip("."),
        file_category=category,
    )
    db.add(uploaded)
    db.flush()
    audit(db, "file_uploaded", "uploaded_file", uploaded.id, {"category": category, "batch_id": batch_id})
    return uploaded


def create_processing_job(db: Session, job_type: str, file_id: int | None = None, batch_id: int | None = None) -> ProcessingJob:
    job = ProcessingJob(file_id=file_id, batch_id=batch_id, job_type=job_type, status="pending")
    db.add(job)
    db.flush()
    audit(db, "processing_job_created", "processing_job", job.id, {"job_type": job_type, "batch_id": batch_id})
    return job


def update_job(job: ProcessingJob, status: str, error_message: str | None = None) -> None:
    job.status = status
    job.error_message = error_message
    if status == "processing":
        job.started_at = datetime.utcnow()
    if status in {"completed", "failed"}:
        job.finished_at = datetime.utcnow()


def finish_batch(db: Session, batch: InvoiceBatch) -> None:
    jobs = db.scalars(select(ProcessingJob).where(ProcessingJob.batch_id == batch.id)).all()
    batch.completed_jobs = sum(1 for job in jobs if job.status == "completed")
    batch.failed_jobs = sum(1 for job in jobs if job.status == "failed")
    if batch.failed_jobs:
        batch.status = "completed_with_errors" if batch.completed_jobs else "failed"
    elif batch.completed_jobs == batch.total_files:
        batch.status = "completed"
    else:
        batch.status = "processing"


def create_invoice_record(
    db: Session,
    payload: dict[str, Any],
    raw_text: str | None = None,
    source_path: str | None = None,
    source_name: str | None = None,
    uploaded_file_id: int | None = None,
    processing_job_id: int | None = None,
    batch_id: int | None = None,
) -> Invoice:
    normalized = normalize_invoice_payload(payload)
    invoice = Invoice(
        **normalized,
        batch_id=batch_id,
        uploaded_file_id=uploaded_file_id,
        processing_job_id=processing_job_id,
        source_file_name=source_name,
        source_file_path=source_path,
        raw_text=raw_text,
    )
    db.add(invoice)
    db.flush()

    payload_items = payload.get("line_items")
    if isinstance(payload_items, list) and payload_items:
        try:
            for item_data in dedupe_invoice_items(payload_items, invoice_total=invoice.total_amount):
                description = item_data.get("description") or item_data.get("name")
                quantity = parse_amount(item_data.get("quantity"))
                unit_price = parse_amount(item_data.get("unit_price"))
                amount = parse_amount(item_data.get("amount"))
                db.add(
                    InvoiceItem(
                        invoice_id=invoice.id,
                        description=description,
                        quantity=quantity,
                        unit_price=unit_price,
                        amount=amount,
                    )
                )
            db.flush()
        except Exception as e:
            print(f"Error saving fallback invoice items: {e}")
    elif raw_text:
        try:
            items_data = dedupe_invoice_items(extract_invoice_items(raw_text), invoice_total=invoice.total_amount)
            for item_data in items_data:
                db.add(
                    InvoiceItem(
                        invoice_id=invoice.id,
                        description=item_data.get("description"),
                        quantity=item_data.get("quantity"),
                        unit_price=item_data.get("unit_price"),
                        amount=item_data.get("amount")
                    )
                )
            db.flush()
        except Exception as e:
            print(f"Error extracting/saving invoice items: {e}")

    audit(db, "invoice_created", "invoice", invoice.id, {"source": source_name or "manual", "batch_id": batch_id})
    return invoice


def duplicate_invoice_counts(db: Session) -> dict[str, int]:
    invoices = db.scalars(select(Invoice)).all()
    return Counter(
        f"{(invoice.invoice_number or '').lower()}::{(invoice.invoice_series or '').lower()}"
        for invoice in invoices
        if invoice.invoice_number
    )


def duplicate_transaction_counts(db: Session) -> dict[str, int]:
    transactions = db.scalars(select(BankTransaction)).all()
    return Counter((transaction.transaction_id or "").lower() for transaction in transactions if transaction.transaction_id)


def clear_validation_exceptions(db: Session) -> None:
    db.execute(delete(ReconciliationException).where(ReconciliationException.exception_type.in_(VALIDATION_EXCEPTION_TYPES)))


def run_invoice_validation(db: Session, clear_existing: bool = True) -> dict[str, int]:
    if clear_existing:
        clear_validation_exceptions(db)
    vendors = [as_dict(vendor) for vendor in db.scalars(select(Vendor)).all()]
    vendors_by_id = {vendor.vendor_id: vendor for vendor in db.scalars(select(Vendor)).all() if vendor.vendor_id}
    vendors_by_tax = {vendor.tax_code: vendor for vendor in db.scalars(select(Vendor)).all() if vendor.tax_code}
    counts = duplicate_invoice_counts(db)
    rules = rule_dict(get_rule(db))
    invoices = db.scalars(select(Invoice).order_by(Invoice.id)).all()
    vendor_amounts: dict[str, list[float]] = defaultdict(list)
    for invoice in invoices:
        if invoice.vendor_id and invoice.total_amount:
            vendor_amounts[invoice.vendor_id].append(float(invoice.total_amount))
    with_issues = 0
    for invoice in invoices:
        key = f"{(invoice.invoice_number or '').lower()}::{(invoice.invoice_series or '').lower()}"
        issues = validate_invoice(invoice_for_engine(invoice), vendors, counts.get(key, 1), rules)
        vendor = vendors_by_id.get(invoice.vendor_id or "") or vendors_by_tax.get(invoice.vendor_tax_code or "")
        if vendor is None:
            issues.append({"type": "vendor_not_found", "severity": "high", "message": "Vendor does not match vendor master."})
        else:
            if vendor.status != "active":
                issues.append({"type": "vendor_not_found", "severity": "high", "message": "Vendor is inactive."})
            if invoice.vendor_tax_code and vendor.tax_code and invoice.vendor_tax_code != vendor.tax_code:
                issues.append({"type": "invalid_tax_code", "severity": "high", "message": "Receipt vendor tax code does not match vendor master."})
            if invoice.vendor_bank_account and vendor.bank_account and invoice.vendor_bank_account != vendor.bank_account:
                issues.append({"type": "vendor_bank_mismatch", "severity": "high", "message": "Receipt bank account does not match vendor master."})
        if invoice.subtotal is not None and invoice.vat_amount is not None and invoice.total_amount is not None:
            diff = abs((float(invoice.subtotal) + float(invoice.vat_amount)) - float(invoice.total_amount))
            if diff > float(rules.get("vat_tolerance", 1)):
                issues.append({"type": "vat_total_mismatch", "severity": "high", "message": f"Subtotal plus tax differs from total by {diff:,.0f}."})
        amounts = vendor_amounts.get(invoice.vendor_id or "", [])
        normal_amounts = [amount for amount in amounts if amount > 0 and amount != float(invoice.total_amount or 0)]
        if invoice.expected_case == "unusual_amount" or (
            normal_amounts and invoice.total_amount and float(invoice.total_amount) > (sum(normal_amounts) / len(normal_amounts)) * 6
        ):
            issues.append({"type": "unusual_amount", "severity": "medium", "message": "Receipt amount is unusually high for this vendor."})
        status = validation_status(issues)
        invoice.validation_status = status
        if status == "valid":
            invoice.status = "validated" if invoice.status in {"uploaded", "imported", "parsed", "needs_review", "pending"} else invoice.status
        elif status == "invalid" and any(issue["severity"] == "high" for issue in issues):
            invoice.status = "rejected" if invoice.status not in {"approved_for_payment", "payment_scheduled", "paid", "reconciled"} else "exception"
        else:
            if invoice.status not in {"approved_for_payment", "payment_scheduled", "paid", "reconciled"}:
                invoice.status = "needs_review"
        for issue in issues:
            db.add(
                ReconciliationException(
                    invoice_id=invoice.id,
                    exception_type=issue["type"],
                    severity=issue["severity"],
                    message=issue["message"],
                )
            )
        if issues:
            with_issues += 1
    return {"validated": len(invoices), "with_issues": with_issues}


def run_bank_transaction_validation(db: Session, clear_existing: bool = True) -> dict[str, int]:
    if clear_existing:
        clear_validation_exceptions(db)
    counts = duplicate_transaction_counts(db)
    transactions = db.scalars(select(BankTransaction).order_by(BankTransaction.id)).all()
    with_issues = 0
    for transaction in transactions:
        key = (transaction.transaction_id or "").lower()
        issues = validate_bank_transaction(transaction_for_engine(transaction), counts.get(key, 1))
        transaction.validation_status = validation_status(issues)
        for issue in issues:
            db.add(
                ReconciliationException(
                    bank_transaction_id=transaction.id,
                    exception_type=issue["type"],
                    severity=issue["severity"],
                    message=issue["message"],
                )
            )
        if issues:
            with_issues += 1
    return {"validated": len(transactions), "with_issues": with_issues}


def run_all_validation(db: Session) -> dict[str, Any]:
    clear_validation_exceptions(db)
    return {
        "invoices": run_invoice_validation(db, clear_existing=False),
        "bank_transactions": run_bank_transaction_validation(db, clear_existing=False),
    }


def joined_match_dict(match: ReconciliationMatch, invoice: Invoice | None, transaction: BankTransaction | None) -> dict[str, Any]:
    return as_dict(
        match,
        {
            "invoice_number": invoice.invoice_number if invoice else None,
            "vendor_name": invoice.vendor_name if invoice else None,
            "invoice_amount": invoice.total_amount if invoice else None,
            "transaction_id": transaction.transaction_id if transaction else None,
            "transaction_description": transaction.description if transaction else None,
            "transaction_amount": transaction.amount if transaction else None,
            "transaction_date": _serialize(transaction.transaction_date) if transaction else None,
        },
    )


def fetch_reconciliation_results(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(ReconciliationMatch, Invoice, BankTransaction)
        .outerjoin(Invoice, Invoice.id == ReconciliationMatch.invoice_id)
        .outerjoin(BankTransaction, BankTransaction.id == ReconciliationMatch.bank_transaction_id)
        .order_by(ReconciliationMatch.match_score.desc().nullslast(), ReconciliationMatch.created_at.desc())
        .all()
    )
    return [joined_match_dict(match, invoice, transaction) for match, invoice, transaction in rows]


def joined_exception_dict(item: ReconciliationException, invoice: Invoice | None, transaction: BankTransaction | None) -> dict[str, Any]:
    return as_dict(
        item,
        {
            "invoice_number": invoice.invoice_number if invoice else None,
            "vendor_name": invoice.vendor_name if invoice else None,
            "invoice_amount": invoice.total_amount if invoice else None,
            "transaction_id": transaction.transaction_id if transaction else None,
            "transaction_description": transaction.description if transaction else None,
            "transaction_amount": transaction.amount if transaction else None,
        },
    )


def fetch_exceptions(db: Session) -> list[dict[str, Any]]:
    severity_order = {"critical": 1, "high": 2, "medium": 3, "low": 4}
    rows = (
        db.query(ReconciliationException, Invoice, BankTransaction)
        .outerjoin(Invoice, Invoice.id == ReconciliationException.invoice_id)
        .outerjoin(BankTransaction, BankTransaction.id == ReconciliationException.bank_transaction_id)
        .all()
    )
    items = [joined_exception_dict(item, invoice, transaction) for item, invoice, transaction in rows]
    return sorted(items, key=lambda item: (severity_order.get(item.get("severity"), 9), item.get("created_at") or ""), reverse=False)


def build_overview(db: Session) -> dict[str, Any]:
    invoices = db.scalars(select(Invoice)).all()
    transactions = db.scalars(select(BankTransaction)).all()
    matches = fetch_reconciliation_results(db)
    exceptions = fetch_exceptions(db)
    matched_count = sum(1 for item in matches if item.get("match_status") in {"matched", "reconciled"})
    partially_matched_count = sum(1 for item in matches if item.get("match_status") in {"partially_matched", "needs_review"})
    amount_mismatch_count = sum(1 for item in matches if item.get("match_status") == "amount_mismatch")
    unmatched_invoice_count = sum(1 for item in exceptions if item.get("exception_type") in {"unmatched_invoice", "unmatched_approved_invoice"})
    unmatched_transaction_count = sum(1 for item in exceptions if item.get("exception_type") in {"unmatched_transaction", "unmatched_bank_transaction"})
    duplicate_count = sum(1 for item in exceptions if item.get("exception_type") == "duplicate_invoice")
    open_exceptions = sum(1 for item in exceptions if item.get("status") in {None, "open", "in_review"} and not item.get("resolved"))
    total_invoice_value = sum(float(invoice.total_amount or 0) for invoice in invoices)
    matched_invoice_ids = {item.get("invoice_id") for item in matches if item.get("match_status") in {"matched", "reconciled"}}
    matched_value = sum(float(invoice.total_amount or 0) for invoice in invoices if invoice.id in matched_invoice_ids)
    unmatched_value = sum(float(item.get("invoice_amount") or 0) for item in exceptions if item.get("exception_type") in {"unmatched_invoice", "unmatched_approved_invoice"})
    scored_matches = [float(item["match_score"]) for item in matches if item.get("match_score") is not None]
    ocr_values = [float(invoice.ocr_confidence) for invoice in invoices if invoice.ocr_confidence is not None]
    severity_counts = Counter(item.get("severity") for item in exceptions)
    vendor_exception_counts = Counter(item.get("vendor_name") or "Không rõ vendor" for item in exceptions if item.get("invoice_id"))
    delays = [
        item.get("date_diff")
        for item in matches
        if item.get("match_status") in {"matched", "reconciled"} and item.get("date_diff") is not None
    ]
    amount_mismatch_by_vendor: dict[str, float] = defaultdict(float)
    for item in exceptions:
        if item.get("exception_type") == "amount_mismatch":
            amount_mismatch_by_vendor[item.get("vendor_name") or "Không rõ vendor"] += float(item.get("invoice_amount") or 0)
    total_invoices = len(invoices)
    match_rate = round((matched_count / total_invoices) * 100, 1) if total_invoices else 0
    return {
        "total_invoices": total_invoices,
        "total_bank_transactions": len(transactions),
        "total_transactions": len(transactions),
        "total_invoice_value": round(total_invoice_value, 2),
        "matched_value": round(matched_value, 2),
        "unmatched_value": round(max(total_invoice_value - matched_value, 0), 2),
        "matched_count": matched_count,
        "partially_matched_count": partially_matched_count,
        "amount_mismatch_count": amount_mismatch_count,
        "unmatched_invoice_count": unmatched_invoice_count,
        "unmatched_transaction_count": unmatched_transaction_count,
        "duplicate_invoice_count": duplicate_count,
        "open_exceptions": open_exceptions,
        "matched_rate": match_rate,
        "match_rate": match_rate,
        "total_unmatched_value": round(unmatched_value, 2),
        "average_match_score": round(sum(scored_matches) / len(scored_matches), 1) if scored_matches else 0,
        "average_ocr_confidence": round(sum(ocr_values) / len(ocr_values), 1) if ocr_values else 0,
        "average_payment_delay_days": round(sum(delays) / len(delays), 1) if delays else 0,
        "exception_count_by_severity": dict(severity_counts),
        "top_vendor_exceptions": [{"vendor_name": name, "count": count} for name, count in vendor_exception_counts.most_common(5)],
        "amount_mismatch_by_vendor": [
            {"vendor_name": name, "amount": round(amount, 2)} for name, amount in amount_mismatch_by_vendor.items()
        ],
        "currency": "VND",
        "ocr_average_confidence": round(sum(ocr_values) / len(ocr_values), 1) if ocr_values else 0,
    }


def create_invoice_from_upload(db: Session, file: UploadFile, content: bytes, batch: InvoiceBatch | None = None, form_payload: dict[str, Any] | None = None) -> Invoice:
    saved_path = save_upload(file.filename or "invoice", content)
    uploaded = create_uploaded_file(db, file.filename or "invoice", saved_path, "invoice", batch.id if batch else None)
    job = create_processing_job(db, "invoice_ocr_extraction", uploaded.id, batch.id if batch else None)
    update_job(job, "processing")
    is_xml = (file.filename or "").lower().endswith(".xml")
    if is_xml:
        raw_text = decode_bytes(content)
        extracted = parse_vietnam_einvoice_xml(content)
    else:
        raw_text = read_extractable_text(file.filename or "", content)
        extracted = extract_invoice_fields(raw_text, file.filename or "")
    payload = {**extracted, **{key: value for key, value in (form_payload or {}).items() if value not in {None, ""}}}
    try:
        invoice = create_invoice_record(
            db,
            payload,
            raw_text=raw_text,
            source_path=str(saved_path),
            source_name=file.filename,
            uploaded_file_id=uploaded.id,
            processing_job_id=job.id,
            batch_id=batch.id if batch else None,
        )
        update_job(job, "completed")
        return invoice
    except Exception as exc:
        update_job(job, "failed", str(exc))
        raise




def import_invoice_rows(db: Session, rows: list[dict[str, Any]], source_type: str, batch: InvoiceBatch | None = None) -> dict[str, Any]:
    imported = 0
    errors: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=2):
        payload = {**row, "source_type": row.get("source_type") or source_type}
        if not payload.get("invoice_id"):
            errors.append({"row": str(index), "message": "invoice_id is required"})
            continue
        invoice = create_invoice_record(db, payload, batch_id=batch.id if batch else None)
        invoice.status = payload.get("invoice_status") or "imported"
        imported += 1
    validation = run_all_validation(db)
    return {"imported": imported, "errors": errors, "validation": validation}


def linked_invoice_by_business_id(db: Session, invoice_id: str) -> Invoice | None:
    return db.scalar(select(Invoice).where(Invoice.invoice_id == invoice_id).order_by(Invoice.id.desc()).limit(1))


def create_payment_record(db: Session, row: dict[str, Any], batch_id: int | None = None) -> PaymentBatch:
    invoice = linked_invoice_by_business_id(db, row.get("invoice_id") or "")
    approved_at = row.get("approved_at")
    approved_dt = None
    if approved_at:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                approved_dt = datetime.strptime(str(approved_at), fmt)
                break
            except ValueError:
                continue
    payment = PaymentBatch(
        batch_id=batch_id,
        payment_id=row.get("payment_id"),
        invoice_id=row.get("invoice_id"),
        invoice_db_id=invoice.id if invoice else None,
        vendor_id=row.get("vendor_id"),
        scheduled_payment_date=to_date(row.get("scheduled_payment_date")),
        approved_amount=parse_amount(row.get("approved_amount")) or 0,
        currency=(row.get("currency") or "VND").upper(),
        approval_status=(row.get("approval_status") or "draft").lower(),
        approved_by=row.get("approved_by"),
        approved_at=approved_dt,
        payment_method=row.get("payment_method"),
        notes=row.get("notes"),
    )
    db.add(payment)
    db.flush()
    if invoice and payment.approval_status == "approved" and invoice.status == "validated":
        invoice.status = "approved_for_payment"
    return payment


def calculate_payment_match_score(invoice: Invoice, payment: PaymentBatch, transaction: BankTransaction) -> dict[str, Any]:
    score = 0.0
    approved_amount = abs(float(payment.approved_amount or invoice.total_amount or 0))
    paid_amount = abs(float(transaction.amount or 0))
    amount_diff = abs(approved_amount - paid_amount)
    if amount_diff == 0:
        score += 40
    elif amount_diff <= 5000:
        score += 30
    elif amount_diff <= 50000:
        score += 20
    elif amount_diff <= 200000:
        score += 10

    date_diff = None
    base_date = payment.scheduled_payment_date or invoice.due_date or invoice.invoice_date
    if base_date and transaction.transaction_date:
        date_diff = abs((transaction.transaction_date - base_date).days)
        if date_diff <= 3:
            score += 20
        elif date_diff <= 7:
            score += 12
        elif date_diff <= 14:
            score += 5

    from app.services.validation import fuzzy_similarity

    vendor_text = invoice.vendor_name or payment.vendor_id or ""
    counterparty_text = f"{transaction.counterparty_name or ''} {transaction.description or ''}"
    vendor_score = fuzzy_similarity(vendor_text, counterparty_text)
    score += vendor_score * 0.2

    reference_text = f"{transaction.description or ''} {transaction.reference_code or ''}"
    normalized_reference = reference_text.lower()
    if (invoice.invoice_id and invoice.invoice_id.lower() in normalized_reference) or (
        invoice.invoice_number and invoice.invoice_number.lower() in normalized_reference
    ):
        score += 10
    if invoice.vendor_bank_account and transaction.counterparty_account and invoice.vendor_bank_account == transaction.counterparty_account:
        score += 10

    return {
        "score": round(min(score, 100), 2),
        "amount_diff": round(amount_diff, 2),
        "date_diff": date_diff,
        "vendor_score": round(vendor_score, 2),
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(payload: LoginPayload, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.scalar(select(User).where(User.email == payload.email, User.is_active.is_(True)))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")
    token = jwt.encode(
        {"sub": str(user.id), "email": user.email, "role": user.role, "exp": datetime.utcnow() + timedelta(hours=12)},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    return {"access_token": token, "token_type": "bearer", "user": public_user(user)}


@app.get("/api/auth/me")
def auth_me(db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.scalar(select(User).order_by(User.id).limit(1))
    return public_user(user) if user else {}


@app.post("/api/vendors/import")
async def import_vendors(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    content = await file.read()
    rows = parse_tabular_file_bytes(file.filename or "vendor_master.csv", content)
    batch = create_batch(db, "vendor", 1)
    saved_path = save_upload(file.filename or "vendor_master", content)
    uploaded = create_uploaded_file(db, file.filename or "vendor_master", saved_path, "vendor_master", batch.id)
    job = create_processing_job(db, "vendor_master_import", uploaded.id, batch.id)
    update_job(job, "processing")
    existing_tax_codes = {value for value in db.scalars(select(Vendor.tax_code)).all() if value}
    existing_accounts = {value for value in db.scalars(select(Vendor.bank_account)).all() if value}
    imported = 0
    skipped = 0
    errors: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=2):
        name = row.get("vendor_name") or row.get("name")
        vendor_id = row.get("vendor_id") or row.get("id")
        tax_code = row.get("tax_code") or row.get("tax")
        bank_account = row.get("bank_account") or row.get("account")
        status = (row.get("status") or "active").lower()
        row_errors: list[str] = []
        if not vendor_id:
            row_errors.append("vendor_id is required")
        if not name:
            row_errors.append("vendor_name is required")
        if tax_code and tax_code in existing_tax_codes:
            row_errors.append("tax_code already exists")
        if bank_account and bank_account in existing_accounts:
            row_errors.append("bank_account already exists")
        if status not in {"active", "inactive"}:
            row_errors.append("status must be active or inactive")
        if row_errors:
            skipped += 1
            errors.append({"row": str(index), "message": "; ".join(row_errors)})
            continue
        db.add(
            Vendor(
                vendor_id=vendor_id,
                vendor_name=name,
                tax_code=tax_code,
                bank_account=bank_account,
                bank_name=row.get("bank_name"),
                bank_account_holder=row.get("bank_account_holder") or row.get("account_holder") or row.get("account_name"),
                address=row.get("address"),
                email=row.get("email"),
                phone=row.get("phone"),
                category=row.get("category"),
                status=status,
            )
        )
        if tax_code:
            existing_tax_codes.add(tax_code)
        if bank_account:
            existing_accounts.add(bank_account)
        imported += 1
    update_job(job, "completed")
    finish_batch(db, batch)
    audit(db, "vendors_imported", "vendor", uploaded.id, {"count": imported, "skipped": skipped})
    return {"batch_id": batch.id, "imported": imported, "skipped": skipped, "errors": errors}


@app.get("/api/vendors")
def list_vendors(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [as_dict(vendor) for vendor in db.scalars(select(Vendor).order_by(Vendor.vendor_name)).all()]


@app.delete("/api/vendors")
def clear_all_vendors(db: Session = Depends(get_db)) -> dict[str, Any]:
    db.execute(delete(Vendor))
    audit(db, "vendors_cleared", "vendor", None)
    return {"cleared": True}


@app.delete("/api/vendors/{vendor_id}")
def delete_vendor(vendor_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    vendor = db.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor not found")
    db.delete(vendor)
    audit(db, "vendor_deleted", "vendor", vendor_id)
    return {"deleted": vendor_id}


@app.post("/api/bank-transactions/import")
async def import_bank_transactions(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    content = await file.read()
    rows = parse_tabular_file_bytes(file.filename or "bank_statement.csv", content)
    batch = create_batch(db, "bank", 1)
    saved_path = save_upload(file.filename or "bank_statement", content)
    uploaded = create_uploaded_file(db, file.filename or "bank_statement", saved_path, "bank_statement", batch.id)
    job = create_processing_job(db, "bank_statement_import", uploaded.id, batch.id)
    update_job(job, "processing")
    existing_ids = {(value or "").lower() for value in db.scalars(select(BankTransaction.transaction_id)).all() if value}
    imported = 0
    skipped = 0
    errors: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=2):
        amount = parse_amount(row.get("amount"))
        transaction_date = to_date(row.get("transaction_date") or row.get("date"))
        value_date = to_date(row.get("value_date"))
        transaction_id = row.get("transaction_id") or row.get("id")
        direction = (row.get("direction") or "outflow").lower()
        row_errors: list[str] = []
        if not transaction_id:
            row_errors.append("transaction_id is required")
        elif transaction_id.lower() in existing_ids:
            row_errors.append("transaction_id already exists")
        if amount is None or amount == 0:
            row_errors.append("amount must be non-zero")
        if not transaction_date:
            row_errors.append("transaction_date is required or invalid")
        if direction not in {"inflow", "outflow"}:
            row_errors.append("direction must be inflow or outflow")
        if row_errors:
            skipped += 1
            errors.append({"row": str(index), "message": "; ".join(row_errors)})
            continue
        db.add(
            BankTransaction(
                batch_id=batch.id,
                transaction_id=transaction_id,
                transaction_date=transaction_date,
                value_date=value_date,
                account_number=row.get("account_number"),
                description=row.get("description") or row.get("memo") or row.get("content"),
                amount=amount,
                direction=direction,
                currency=(row.get("currency") or "VND").upper(),
                balance_after=parse_amount(row.get("balance_after")),
                counterparty_name=row.get("counterparty_name"),
                counterparty_account=row.get("counterparty_account"),
                bank_account=row.get("bank_account") or row.get("account"),
                reference_code=row.get("reference_code") or row.get("reference"),
                expected_case=row.get("expected_case"),
            )
        )
        existing_ids.add(transaction_id.lower())
        imported += 1
    db.flush()
    validation = run_bank_transaction_validation(db)
    update_job(job, "completed")
    finish_batch(db, batch)
    audit(db, "bank_transactions_imported", "bank_transaction", uploaded.id, {"count": imported, "skipped": skipped})
    return {"batch_id": batch.id, "imported": imported, "skipped": skipped, "errors": errors, "validation": validation}


@app.get("/api/bank-transactions")
def list_bank_transactions(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [as_dict(item) for item in db.scalars(select(BankTransaction).order_by(BankTransaction.transaction_date.desc(), BankTransaction.id.desc())).all()]


@app.delete("/api/bank-transactions")
def clear_all_bank_transactions(db: Session = Depends(get_db)) -> dict[str, Any]:
    db.execute(delete(ReconciliationMatch))
    db.execute(delete(ReconciliationException))
    db.execute(delete(BankTransaction))
    db.execute(delete(UploadedFile).where(UploadedFile.file_category == "bank_statement"))
    audit(db, "bank_transactions_cleared", "bank_transaction", None)
    return {"cleared": True}


@app.post("/api/payment-batches/import")
async def import_payment_batches(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    content = await file.read()
    rows = parse_tabular_file_bytes(file.filename or "payment_batch.csv", content)
    batch = create_batch(db, "payment_batch", 1)
    saved_path = save_upload(file.filename or "payment_batch", content)
    uploaded = create_uploaded_file(db, file.filename or "payment_batch", saved_path, "payment_batch", batch.id)
    job = create_processing_job(db, "payment_batch_import", uploaded.id, batch.id)
    update_job(job, "processing")
    existing_ids = {(value or "").lower() for value in db.scalars(select(PaymentBatch.payment_id)).all() if value}
    imported = 0
    skipped = 0
    errors: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=2):
        payment_id = row.get("payment_id")
        invoice = linked_invoice_by_business_id(db, row.get("invoice_id") or "")
        approval_status = (row.get("approval_status") or "draft").lower()
        row_errors: list[str] = []
        if not payment_id:
            row_errors.append("payment_id is required")
        elif payment_id.lower() in existing_ids:
            row_errors.append("payment_id already exists")
        if invoice is None:
            row_errors.append("invoice_id/receipt_id must exist")
        elif row.get("vendor_id") and invoice.vendor_id and row.get("vendor_id") != invoice.vendor_id:
            row_errors.append("vendor_id must match receipt vendor")
        if approval_status not in VALID_APPROVAL_STATUSES:
            row_errors.append("approval_status is invalid")
        amount = parse_amount(row.get("approved_amount"))
        if invoice and amount is not None and invoice.total_amount and amount != invoice.total_amount and not row.get("notes"):
            row_errors.append("approved_amount differs from receipt total and notes is empty")
        if approval_status == "approved" and invoice and invoice.status not in {"validated", "approved_for_payment", "payment_scheduled", "paid", "reconciled"}:
            row_errors.append("only validated receipts can be approved")
        if row_errors:
            skipped += 1
            errors.append({"row": str(index), "message": "; ".join(row_errors)})
            continue
        create_payment_record(db, row, batch.id)
        existing_ids.add(payment_id.lower())
        imported += 1
    update_job(job, "completed")
    finish_batch(db, batch)
    audit(db, "payment_batch_imported", "payment_batch", uploaded.id, {"imported": imported, "skipped": skipped})
    return {"batch_id": batch.id, "imported": imported, "skipped": skipped, "errors": errors}


@app.get("/api/payment-batches")
def list_payment_batches(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [as_dict(item) for item in db.scalars(select(PaymentBatch).order_by(PaymentBatch.created_at.desc(), PaymentBatch.id.desc())).all()]


@app.delete("/api/payment-batches")
def clear_all_payment_batches(db: Session = Depends(get_db)) -> dict[str, Any]:
    db.execute(delete(ReconciliationMatch))
    db.execute(delete(ReconciliationException))
    db.execute(delete(PaymentBatch))
    db.execute(delete(UploadedFile).where(UploadedFile.file_category == "payment_batch"))
    audit(db, "payment_batches_cleared", "payment_batch", None)
    return {"cleared": True}


@app.post("/api/payment-batches/generate-from-approved-invoices")
def generate_payment_batch_from_approved(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "accountant"))) -> dict[str, Any]:
    invoices = db.scalars(select(Invoice).where(Invoice.status == "approved_for_payment").order_by(Invoice.id)).all()
    existing_invoice_ids = {value for value in db.scalars(select(PaymentBatch.invoice_id)).all()}
    batch = create_batch(db, "payment_batch", len(invoices))
    created = 0
    for invoice in invoices:
        business_id = invoice.invoice_id or f"INV-DB-{invoice.id}"
        if business_id in existing_invoice_ids:
            continue
        payment_id = f"PAY-{datetime.utcnow().strftime('%Y%m%d')}-{invoice.id:04d}"
        payment = PaymentBatch(
            batch_id=batch.id,
            payment_id=payment_id,
            invoice_id=business_id,
            invoice_db_id=invoice.id,
            vendor_id=invoice.vendor_id,
            scheduled_payment_date=invoice.due_date or date.today(),
            approved_amount=float(invoice.total_amount or 0),
            currency=invoice.currency,
            approval_status="approved",
            approved_by=user.email,
            approved_at=datetime.utcnow(),
            payment_method="bank_transfer",
            notes="Generated from approved receipt",
        )
        db.add(payment)
        invoice.status = "payment_scheduled"
        created += 1
    batch.total_files = created
    batch.completed_jobs = created
    batch.status = "completed"
    audit(db, "payment_batch_generated", "payment_batch", batch.id, {"created": created})
    return {"batch_id": batch.id, "created": created}


@app.post("/api/invoices/manual")
def create_manual_invoice(payload: InvoicePayload, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = create_invoice_record(db, payload.model_dump())
    run_all_validation(db)
    return as_dict(invoice)


@app.post("/api/invoices/upload")
async def upload_invoice(
    file: UploadFile = File(...),
    invoice_number: str | None = Form(None),
    vendor_name: str | None = Form(None),
    vendor_tax_code: str | None = Form(None),
    invoice_date: str | None = Form(None),
    due_date: str | None = Form(None),
    subtotal: str | None = Form(None),
    vat_amount: str | None = Form(None),
    total_amount: str | None = Form(None),
    currency: str | None = Form("VND"),
    ocr_confidence: str | None = Form(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    batch = create_batch(db, "invoice", 1)
    content = await file.read()
    invoice = create_invoice_from_upload(
        db,
        file,
        content,
        batch,
        {
            "invoice_number": invoice_number,
            "vendor_name": vendor_name,
            "vendor_tax_code": vendor_tax_code,
            "invoice_date": invoice_date,
            "due_date": due_date,
            "subtotal": subtotal,
            "vat_amount": vat_amount,
            "total_amount": total_amount,
            "currency": currency,
            "ocr_confidence": ocr_confidence,
        },
    )
    finish_batch(db, batch)
    run_all_validation(db)
    return as_dict(invoice, {"preview_url": preview_url(invoice.source_file_path)})


@app.post("/api/batches/invoices/upload")
async def upload_invoice_batch(files: list[UploadFile] = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    batch = create_batch(db, "invoice", len(files))
    created: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for file in files:
        content = await file.read()
        try:
            invoice = create_invoice_from_upload(db, file, content, batch)
            created.append(as_dict(invoice))
        except Exception as exc:
            errors.append({"file": file.filename or "receipt", "message": str(exc)})
    finish_batch(db, batch)
    run_all_validation(db)
    return {"batch_id": batch.id, "created": len(created), "errors": errors, "invoices": created}


@app.post("/api/invoices/import-register")
async def import_invoice_register(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    content = await file.read()
    rows = parse_tabular_file_bytes(file.filename or "invoice_register.csv", content)
    batch = create_batch(db, "invoice_register", 1)
    saved_path = save_upload(file.filename or "invoice_register", content)
    uploaded = create_uploaded_file(db, file.filename or "invoice_register", saved_path, "invoice_register", batch.id)
    job = create_processing_job(db, "invoice_register_import", uploaded.id, batch.id)
    update_job(job, "processing")
    source_type = "xlsx_register" if (file.filename or "").lower().endswith((".xlsx", ".xls")) else "csv_register"
    result = import_invoice_rows(db, rows, source_type, batch)
    update_job(job, "completed")
    finish_batch(db, batch)
    audit(db, "invoice_register_imported", "invoice", uploaded.id, result)
    return {"batch_id": batch.id, **result}


@app.post("/api/invoices/import-xml")
async def import_invoice_xml(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    content = await file.read()
    batch = create_batch(db, "einvoice_xml", 1)
    invoice = create_invoice_from_upload(db, file, content, batch)
    finish_batch(db, batch)
    run_all_validation(db)
    audit(db, "einvoice_xml_imported", "invoice", invoice.id, {"file": file.filename})
    return as_dict(invoice, {"preview_url": preview_url(invoice.source_file_path), "batch_id": batch.id})




@app.post("/api/invoices/upload-attachment")
async def upload_invoice_attachment(
    file: UploadFile = File(...),
    invoice_id: str | None = Form(None),
    use_fallback_extraction: bool = Form(False),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    content = await file.read()
    saved_path = save_upload(file.filename or "attachment", content)
    uploaded = create_uploaded_file(db, file.filename or "attachment", saved_path, "invoice_attachment")
    invoice = linked_invoice_by_business_id(db, invoice_id or Path(file.filename or "").stem)
    if invoice:
        invoice.attachment_file = file.filename
        invoice.source_file_name = file.filename
        invoice.source_file_path = str(saved_path)
        invoice.uploaded_file_id = uploaded.id
        if use_fallback_extraction:
            if (file.filename or "").lower().endswith(".xml"):
                raw_text = decode_bytes(content)
                payload = parse_vietnam_einvoice_xml(content)
            else:
                raw_text = read_extractable_text(file.filename or "", content)
                payload = extract_invoice_fields(raw_text, file.filename or "")
                payload["source_type"] = "ocr"
            payload["attachment_file"] = file.filename
            before = as_dict(invoice)
            for key, value in normalize_invoice_payload(payload).items():
                if value not in {None, ""}:
                    setattr(invoice, key, value)
            invoice.raw_text = raw_text
            invoice.status = "needs_review"
            invoice.updated_at = datetime.utcnow()
            db.execute(delete(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id))
            payload_items = payload.get("line_items")
            items_data = payload_items if isinstance(payload_items, list) and payload_items else extract_invoice_items(raw_text)
            items_data = dedupe_invoice_items(items_data, invoice_total=invoice.total_amount)
            for item_data in items_data:
                description = item_data.get("description") or item_data.get("name")
                quantity = parse_amount(item_data.get("quantity"))
                unit_price = parse_amount(item_data.get("unit_price"))
                amount = parse_amount(item_data.get("amount"))
                db.add(
                    InvoiceItem(
                        invoice_id=invoice.id,
                        description=description,
                        quantity=quantity,
                        unit_price=unit_price,
                        amount=amount,
                    )
                )
            run_all_validation(db)
            audit(db, "invoice_attachment_reprocessed", "invoice", invoice.id, {"file": file.filename, "before": before, "after": as_dict(invoice)})
            return as_dict(invoice, {"preview_url": preview_url(invoice.source_file_path), "uploaded_file_id": uploaded.id})
        audit(db, "invoice_attachment_uploaded", "invoice", invoice.id, {"file": file.filename})
        return as_dict(invoice, {"preview_url": preview_url(invoice.source_file_path), "uploaded_file_id": uploaded.id})
    if not use_fallback_extraction:
        return {"uploaded_file_id": uploaded.id, "preview_url": preview_url(str(saved_path)), "message": "Attachment uploaded without receipt extraction."}
    if (file.filename or "").lower().endswith(".xml"):
        raw_text = decode_bytes(content)
        payload = parse_vietnam_einvoice_xml(content)
    else:
        raw_text = read_extractable_text(file.filename or "", content)
        payload = extract_invoice_fields(raw_text, file.filename or "")
        payload["source_type"] = "ocr"
    payload["attachment_file"] = file.filename
    invoice = create_invoice_record(db, payload, raw_text=raw_text, source_path=str(saved_path), source_name=file.filename, uploaded_file_id=uploaded.id)
    invoice.status = "needs_review"
    run_all_validation(db)
    return as_dict(invoice, {"preview_url": preview_url(invoice.source_file_path)})


@app.get("/api/invoices")
def list_invoices(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [as_dict(invoice, {"preview_url": preview_url(invoice.source_file_path)}) for invoice in db.scalars(select(Invoice).order_by(Invoice.created_at.desc(), Invoice.id.desc())).all()]


@app.get("/api/invoices/{invoice_id}")
def get_invoice(invoice_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return as_dict(invoice, {"preview_url": preview_url(invoice.source_file_path)})


@app.put("/api/invoices/{invoice_id}")
def update_invoice(invoice_id: int, payload: InvoicePayload, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    before = as_dict(invoice)
    for key, value in normalize_invoice_payload(payload.model_dump()).items():
        setattr(invoice, key, value)
    invoice.updated_at = datetime.utcnow()
    run_all_validation(db)
    audit(db, "invoice_updated", "invoice", invoice_id, {"before": before, "after": as_dict(invoice)})
    return as_dict(invoice)


@app.delete("/api/invoices")
def clear_all_invoices(db: Session = Depends(get_db)) -> dict[str, Any]:
    invoices = db.scalars(select(Invoice)).all()
    invoice_ids = [invoice.id for invoice in invoices]
    batch_ids = [
        value
        for value in db.scalars(
            select(InvoiceBatch.id).where(InvoiceBatch.batch_type.in_(["invoice", "invoice_register", "einvoice_xml"]))
        ).all()
        if value is not None
    ]
    upload_conditions = [UploadedFile.file_category.in_(["invoice", "invoice_attachment", "invoice_register"])]
    if batch_ids:
        upload_conditions.append(UploadedFile.batch_id.in_(batch_ids))
    upload_files = db.scalars(select(UploadedFile).where(or_(*upload_conditions))).all()
    uploaded_file_ids = [file.id for file in upload_files]

    db.execute(delete(ReconciliationMatch))
    db.execute(delete(ReconciliationException))
    if invoice_ids:
        db.execute(delete(PaymentBatch).where(PaymentBatch.invoice_db_id.in_(invoice_ids)))
        db.execute(delete(Invoice).where(Invoice.id.in_(invoice_ids)))
    db.execute(delete(InvoiceItem))
    if uploaded_file_ids:
        db.execute(delete(ProcessingJob).where(ProcessingJob.file_id.in_(uploaded_file_ids)))
    if batch_ids:
        db.execute(delete(ProcessingJob).where(ProcessingJob.batch_id.in_(batch_ids)))
    deleted_files = delete_uploaded_files(db, upload_files)
    if batch_ids:
        db.execute(delete(InvoiceBatch).where(InvoiceBatch.id.in_(batch_ids)))
    audit(db, "invoices_cleared", "invoice", None, {"invoices": len(invoice_ids), "uploaded_files": deleted_files})
    return {"cleared": True, "deleted_invoices": len(invoice_ids), "deleted_uploaded_files": deleted_files}


@app.delete("/api/invoices/{invoice_id}")
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    upload_ids = [value for value in [invoice.uploaded_file_id] if value is not None]
    files = db.scalars(select(UploadedFile).where(UploadedFile.id.in_(upload_ids))).all() if upload_ids else []
    db.execute(delete(ReconciliationMatch).where(ReconciliationMatch.invoice_id == invoice_id))
    db.execute(delete(ReconciliationException).where(ReconciliationException.invoice_id == invoice_id))
    db.execute(delete(PaymentBatch).where(PaymentBatch.invoice_db_id == invoice_id))
    db.execute(delete(InvoiceItem).where(InvoiceItem.invoice_id == invoice_id))
    db.delete(invoice)
    if upload_ids:
        db.execute(delete(ProcessingJob).where(ProcessingJob.file_id.in_(upload_ids)))
    deleted_files = delete_uploaded_files(db, files)
    audit(db, "invoice_deleted", "invoice", invoice_id, {"uploaded_files": deleted_files})
    return {"deleted": invoice_id, "deleted_uploaded_files": deleted_files}


@app.get("/api/invoices/{invoice_id}/review")
def get_invoice_review(invoice_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return as_dict(invoice, {"preview_url": preview_url(invoice.source_file_path)})


@app.put("/api/invoices/{invoice_id}/review")
def review_invoice(invoice_id: int, payload: ReviewInvoicePayload, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    before = as_dict(invoice)
    for key, value in normalize_invoice_payload(payload.model_dump()).items():
        setattr(invoice, key, value)
    invoice.status = payload.status or "reviewed"
    if invoice.validation_status == "valid" or invoice.status == "reviewed":
        invoice.status = "ready_for_reconciliation"
    invoice.updated_at = datetime.utcnow()
    run_all_validation(db)
    audit(db, "invoice_reviewed", "invoice", invoice_id, {"before": before, "after": as_dict(invoice)})
    return as_dict(invoice)


def find_invoice(db: Session, invoice_key: str) -> Invoice | None:
    if invoice_key.isdigit():
        found = db.get(Invoice, int(invoice_key))
        if found:
            return found
    return linked_invoice_by_business_id(db, invoice_key)


@app.post("/api/invoices/{invoice_id}/validate")
def validate_one_invoice(invoice_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = find_invoice(db, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    result = run_all_validation(db)
    audit(db, "invoice_validated", "invoice", invoice.id, result)
    return as_dict(invoice, {"validation": result})


@app.post("/api/invoices/{invoice_id}/approve")
def approve_invoice(invoice_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "accountant", "reviewer"))) -> dict[str, Any]:
    invoice = find_invoice(db, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    run_all_validation(db)
    if invoice.validation_status != "valid" and invoice.status != "validated":
        raise HTTPException(status_code=400, detail="Chỉ phiếu nhập đã hợp lệ mới được duyệt thanh toán")
    invoice.status = "approved_for_payment"
    audit(db, "invoice_approved_for_payment", "invoice", invoice.id, {"approved_by": user.email})
    return as_dict(invoice)


@app.post("/api/invoices/{invoice_id}/reject")
def reject_invoice(invoice_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "accountant", "reviewer"))) -> dict[str, Any]:
    invoice = find_invoice(db, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    invoice.status = "rejected"
    audit(db, "invoice_rejected", "invoice", invoice.id, {"rejected_by": user.email})
    return as_dict(invoice)


@app.get("/api/batches")
def list_batches(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [as_dict(batch) for batch in db.scalars(select(InvoiceBatch).order_by(InvoiceBatch.created_at.desc(), InvoiceBatch.id.desc())).all()]


@app.get("/api/batches/{batch_id}")
def get_batch(batch_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    batch = db.get(InvoiceBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    jobs = [as_dict(job) for job in db.scalars(select(ProcessingJob).where(ProcessingJob.batch_id == batch_id).order_by(ProcessingJob.id)).all()]
    files = [as_dict(item) for item in db.scalars(select(UploadedFile).where(UploadedFile.batch_id == batch_id).order_by(UploadedFile.id)).all()]
    invoices = [as_dict(item) for item in db.scalars(select(Invoice).where(Invoice.batch_id == batch_id).order_by(Invoice.id)).all()]
    return as_dict(batch, {"jobs": jobs, "files": files, "invoices": invoices})


@app.get("/api/jobs")
def list_jobs(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [as_dict(job) for job in db.scalars(select(ProcessingJob).order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())).all()]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return as_dict(job)


@app.post("/api/validation/run")
def run_validation(db: Session = Depends(get_db)) -> dict[str, Any]:
    result = run_all_validation(db)
    audit(db, "validation_run", "validation", None, result)
    return result


@app.post("/api/reconciliation/run")
def run_reconciliation(db: Session = Depends(get_db)) -> dict[str, Any]:
    db.execute(delete(ReconciliationMatch))
    db.execute(delete(ReconciliationException))
    validation_result = run_all_validation(db)
    rules = rule_dict(get_rule(db))
    payments = db.scalars(
        select(PaymentBatch)
        .where(PaymentBatch.approval_status.in_(["approved", "paid", "reconciled"]))
        .order_by(PaymentBatch.scheduled_payment_date, PaymentBatch.id)
    ).all()
    transactions = db.scalars(
        select(BankTransaction)
        .where(func.lower(func.coalesce(BankTransaction.direction, "outflow")) == "outflow")
        .order_by(BankTransaction.transaction_date, BankTransaction.id)
    ).all()
    used_transactions: set[int] = set()
    used_payments: set[int] = set()
    created_matches = 0
    created_exceptions = 0
    eligible_statuses = {"approved_for_payment", "payment_scheduled", "paid", "reconciled"}
    
    unpaid_payments = []
    for payment in payments:
        invoice = db.get(Invoice, payment.invoice_db_id) if payment.invoice_db_id else linked_invoice_by_business_id(db, payment.invoice_id)
        if invoice and invoice.status in eligible_statuses:
            unpaid_payments.append((payment, invoice))

    from app.services.validation import fuzzy_similarity

    for transaction in transactions:
        if transaction.id in used_transactions: continue
        
        tx_desc = f"{transaction.counterparty_name or ''} {transaction.description or ''}"
        tx_amount = abs(float(transaction.amount or 0))
        
        scored_payments = []
        for p, i in unpaid_payments:
            if p.id in used_payments: continue
            vendor_text = i.vendor_name or p.vendor_id or ""
            v_score = fuzzy_similarity(vendor_text, tx_desc)
            if v_score >= float(rules["manual_review_threshold"]):
                scored_payments.append((v_score, p, i))
                
        if not scored_payments:
            continue
            
        scored_payments.sort(key=lambda x: (-x[0], x[2].invoice_date or x[1].scheduled_payment_date))
        
        group_to_match = []
        current_sum = 0.0
        best_score_in_group = 0.0
        
        for score, p, i in scored_payments:
            amt = abs(float(p.approved_amount or i.total_amount or 0))
            if current_sum + amt <= tx_amount + float(rules["amount_tolerance_vnd"]):
                group_to_match.append((p, i, score))
                current_sum += amt
                best_score_in_group = max(best_score_in_group, score)
                
        amount_diff = abs(current_sum - tx_amount)
        if group_to_match and amount_diff <= float(rules["amount_tolerance_vnd"]):
            status = "reconciled" if best_score_in_group >= float(rules["auto_match_threshold"]) and amount_diff == 0 else "needs_review"
            
            for p, i, score in group_to_match:
                i.status = "reconciled" if status == "reconciled" else "exception"
                p.approval_status = "reconciled" if status == "reconciled" else "exception"
                match = ReconciliationMatch(
                    invoice_id=i.id,
                    bank_transaction_id=transaction.id,
                    match_score=score,
                    match_status=status,
                    amount_diff=amount_diff,
                    date_diff=0,
                    reason=f"1-to-N match, group diff {amount_diff:,.0f}",
                )
                db.add(match)
                used_payments.add(p.id)
                created_matches += 1
                if status != "reconciled":
                    db.add(ReconciliationException(
                        invoice_id=i.id, bank_transaction_id=transaction.id, 
                        exception_type="amount_mismatch" if amount_diff > 0 else "vendor_mismatch", 
                        severity="medium", 
                        message=f"Group match needs review. Group diff: {amount_diff:,.0f}"
                    ))
                    created_exceptions += 1
                    
            used_transactions.add(transaction.id)

    for p, i in unpaid_payments:
        if p.id not in used_payments:
            i.status = "exception"
            p.approval_status = "exception"
            db.add(ReconciliationException(invoice_id=i.id, exception_type="unmatched_approved_invoice", severity="medium", message="Approved receipt payment has no matching bank transaction."))
            created_exceptions += 1

    for transaction in transactions:
        if transaction.id not in used_transactions:
            db.add(ReconciliationException(bank_transaction_id=transaction.id, exception_type="unmatched_bank_transaction", severity="high", message="Bank transaction was not matched to any approved payment."))
            created_exceptions += 1
    audit(db, "reconciliation_run", "reconciliation", None, {"matches": created_matches, "exceptions": created_exceptions, "validation": validation_result, "rules": rules})
    return {"matches": created_matches, "exceptions": created_exceptions, "validation": validation_result}


@app.get("/api/reconciliation/results")
def reconciliation_results(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return fetch_reconciliation_results(db)


@app.get("/api/reconciliation/candidates")
def reconciliation_candidates(invoice_id: int = Query(...), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    rules = rule_dict(get_rule(db))
    invoice_data = invoice_for_engine(invoice)
    candidates: list[dict[str, Any]] = []
    for transaction in db.scalars(select(BankTransaction).order_by(BankTransaction.transaction_date, BankTransaction.id)).all():
        transaction_data = transaction_for_engine(transaction)
        if is_reconciliation_candidate(invoice_data, transaction_data, rules):
            metrics = calculate_match_score(invoice_data, transaction_data, rules)
            candidates.append(as_dict(transaction, {"candidate_score": metrics["score"], "amount_diff": metrics["amount_diff"], "date_diff": metrics["date_diff"], "reason": match_reason(invoice_data, transaction_data, metrics)}))
    return sorted(candidates, key=lambda item: item["candidate_score"], reverse=True)


@app.get("/api/reconciliation/exceptions")
def reconciliation_exceptions(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return fetch_exceptions(db)


@app.get("/api/exceptions")
def list_exceptions(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return fetch_exceptions(db)


@app.post("/api/reconciliation/{match_id}/approve")
def approve_match(match_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "reviewer"))) -> dict[str, Any]:
    match = db.get(ReconciliationMatch, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    match.approved = True
    match.match_status = "matched"
    match.reviewed_by = user.id
    audit(db, "match_approved", "reconciliation_match", match_id)
    return {"approved": match_id}


@app.post("/api/reconciliation/{match_id}/reject")
def reject_match(match_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "reviewer"))) -> dict[str, Any]:
    match = db.get(ReconciliationMatch, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    match.approved = False
    match.match_status = "rejected"
    match.reviewed_by = user.id
    db.add(ReconciliationException(invoice_id=match.invoice_id, bank_transaction_id=match.bank_transaction_id, exception_type="manual_rejection", severity="medium", message="User rejected this automated receipt/payment match."))
    audit(db, "match_rejected", "reconciliation_match", match_id)
    return {"rejected": match_id}


@app.put("/api/exceptions/{exception_id}")
def update_exception(exception_id: int, payload: ExceptionUpdatePayload, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "reviewer"))) -> dict[str, Any]:
    item = db.get(ReconciliationException, exception_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Exception not found")
    before = as_dict(item)
    if payload.status is not None:
        item.status = payload.status
    if payload.note is not None:
        item.note = payload.note
    if payload.resolved is not None:
        item.resolved = payload.resolved
        if payload.resolved and item.status == "open":
            item.status = "resolved"
    item.updated_at = datetime.utcnow()
    audit(db, "exception_updated", "reconciliation_exception", exception_id, {"before": before, "after": as_dict(item)})
    return as_dict(item)


@app.post("/api/reconciliation/exceptions/{exception_id}/resolve")
def resolve_exception(exception_id: int, payload: ResolvePayload, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.get(ReconciliationException, exception_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Exception not found")
    item.resolved = payload.resolved
    item.status = "resolved" if payload.resolved else "open"
    audit(db, "exception_resolved", "reconciliation_exception", exception_id, payload.model_dump())
    return {"exception_id": exception_id, "resolved": payload.resolved}


@app.get("/api/rules")
def get_rules(db: Session = Depends(get_db)) -> dict[str, Any]:
    return rule_dict(get_rule(db))


@app.put("/api/rules")
def update_rules(payload: RulePayload, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))) -> dict[str, Any]:
    rule = get_rule(db)
    before = rule_dict(rule)
    for key, value in payload.model_dump().items():
        setattr(rule, key, value)
    audit(db, "rules_updated", "reconciliation_rule", rule.id, {"before": before, "after": payload.model_dump()})
    return rule_dict(rule)


@app.get("/api/dashboard/overview")
def dashboard_overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_overview(db)


@app.get("/api/dashboard/reconciliation-summary")
def dashboard_reconciliation_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_overview(db)


@app.get("/api/dashboard/management-summary")
def dashboard_management_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_overview(db)


@app.get("/api/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_overview(db)


def create_report(db: Session, report_type: str = "daily") -> dict[str, Any]:
    overview = build_overview(db)
    report = build_reconciliation_report(overview, fetch_exceptions(db), fetch_reconciliation_results(db))
    item = AIReport(report_type=report_type, report_content=report)
    db.add(item)
    db.flush()
    audit(db, "report_generated", "ai_report", item.id, {"type": report_type})
    return {"id": item.id, "report_type": report_type, "report": report}


@app.post("/api/reports/generate")
def generate_report(db: Session = Depends(get_db)) -> dict[str, Any]:
    return create_report(db, "daily")


@app.get("/api/reports")
def list_reports(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [as_dict(item) for item in db.scalars(select(AIReport).order_by(AIReport.created_at.desc(), AIReport.id.desc())).all()]


@app.get("/api/reports/daily")
def daily_report(db: Session = Depends(get_db)) -> dict[str, Any]:
    return create_report(db, "daily")


def excel_response(rows: list[dict[str, Any]], filename: str) -> StreamingResponse:
    output = BytesIO()
    pd.DataFrame(rows).to_excel(output, index=False)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/reports/export/reconciliation.xlsx")
def export_reconciliation(db: Session = Depends(get_db)) -> StreamingResponse:
    return excel_response(fetch_reconciliation_results(db), "reconciliation_results.xlsx")


@app.get("/api/reports/export/exceptions.xlsx")
def export_exceptions(db: Session = Depends(get_db)) -> StreamingResponse:
    return excel_response(fetch_exceptions(db), "reconciliation_exceptions.xlsx")


@app.get("/api/audit-logs")
def list_audit_logs(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [as_dict(item) for item in db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(200)).all()]
