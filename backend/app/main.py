from __future__ import annotations

import json
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.database import UPLOAD_DIR, get_connection, init_db, rows_to_dicts
from app.schemas import InvoicePayload, ResolvePayload
from app.services.reconciliation import (
    calculate_match_score,
    classify_match,
    is_reconciliation_candidate,
    match_reason,
)
from app.services.reporting import build_reconciliation_report
from app.services.validation import validate_bank_transaction, validate_invoice, validation_status
from app.utils import decode_bytes, extract_invoice_fields, parse_amount, parse_date, parse_tabular_file_bytes


app = FastAPI(title="FinRecon AI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


VALIDATION_EXCEPTION_TYPES = {
    "missing_required_field",
    "date_mismatch",
    "vendor_mismatch",
    "duplicate_invoice",
    "low_ocr_confidence",
    "amount_mismatch",
}


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def audit(conn, action: str, entity_type: str | None = None, entity_id: int | None = None, details: Any = None) -> None:
    conn.execute(
        """
        INSERT INTO audit_logs (action, entity_type, entity_id, details)
        VALUES (?, ?, ?, ?)
        """,
        (action, entity_type, entity_id, json.dumps(details or {}, ensure_ascii=False)),
    )


def fetch_vendors(conn) -> list[dict[str, Any]]:
    return rows_to_dicts(conn.execute("SELECT * FROM vendors ORDER BY vendor_name").fetchall())


def fetch_invoices(conn) -> list[dict[str, Any]]:
    return rows_to_dicts(conn.execute("SELECT * FROM invoices ORDER BY created_at DESC, id DESC").fetchall())


def duplicate_counts(conn) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT LOWER(invoice_number) AS invoice_number, COUNT(*) AS count
        FROM invoices
        WHERE invoice_number IS NOT NULL AND TRIM(invoice_number) <> ''
        GROUP BY LOWER(invoice_number)
        """
    ).fetchall()
    return {row["invoice_number"]: int(row["count"]) for row in rows}


def insert_validation_exception(conn, invoice: dict[str, Any], issue: dict[str, str]) -> None:
    conn.execute(
        """
        INSERT INTO reconciliation_exceptions
            (invoice_id, exception_type, severity, message)
        VALUES (?, ?, ?, ?)
        """,
        (invoice["id"], issue["type"], issue["severity"], issue["message"]),
    )


def run_invoice_validation(conn) -> dict[str, int]:
    placeholders = ",".join("?" for _ in VALIDATION_EXCEPTION_TYPES)
    conn.execute(
        f"DELETE FROM reconciliation_exceptions WHERE exception_type IN ({placeholders})",
        tuple(VALIDATION_EXCEPTION_TYPES),
    )

    vendors = fetch_vendors(conn)
    counts = duplicate_counts(conn)
    invoices = fetch_invoices(conn)
    invalid_count = 0

    for invoice in invoices:
        key = (invoice.get("invoice_number") or "").lower()
        issues = validate_invoice(invoice, vendors, counts.get(key, 1))
        status = validation_status(issues)
        conn.execute(
            """
            UPDATE invoices
            SET validation_status = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                status,
                "ready" if status == "valid" else status,
                invoice["id"],
            ),
        )
        for issue in issues:
            insert_validation_exception(conn, invoice, issue)
        if issues:
            invalid_count += 1

    return {"validated": len(invoices), "with_issues": invalid_count}


def save_upload(file_name: str, content: bytes) -> Path:
    safe_name = Path(file_name or "upload.bin").name
    target = UPLOAD_DIR / f"{uuid.uuid4().hex}_{safe_name}"
    target.write_bytes(content)
    return target


def read_extractable_text(file_name: str, content: bytes) -> str:
    suffix = Path(file_name or "").suffix.lower()
    if suffix in {".txt", ".csv", ".json", ".md"}:
        return decode_bytes(content)
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return ""
    return ""


def normalize_invoice_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "invoice_number": payload.get("invoice_number") or None,
        "vendor_name": payload.get("vendor_name") or None,
        "vendor_tax_code": payload.get("vendor_tax_code") or None,
        "invoice_date": parse_date(payload.get("invoice_date")),
        "due_date": parse_date(payload.get("due_date")),
        "subtotal": parse_amount(payload.get("subtotal")),
        "vat_amount": parse_amount(payload.get("vat_amount")),
        "total_amount": parse_amount(payload.get("total_amount")),
        "currency": (payload.get("currency") or "VND").upper(),
        "ocr_confidence": parse_amount(payload.get("ocr_confidence")),
    }


def create_invoice(conn, payload: dict[str, Any], raw_text: str | None = None, source_path: str | None = None, source_name: str | None = None) -> dict[str, Any]:
    normalized = normalize_invoice_payload(payload)
    cursor = conn.execute(
        """
        INSERT INTO invoices (
            invoice_number, vendor_name, vendor_tax_code, invoice_date, due_date,
            subtotal, vat_amount, total_amount, currency, ocr_confidence,
            source_file_name, source_file_path, raw_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalized["invoice_number"],
            normalized["vendor_name"],
            normalized["vendor_tax_code"],
            normalized["invoice_date"],
            normalized["due_date"],
            normalized["subtotal"],
            normalized["vat_amount"],
            normalized["total_amount"],
            normalized["currency"],
            normalized["ocr_confidence"],
            source_name,
            source_path,
            raw_text,
        ),
    )
    invoice_id = int(cursor.lastrowid)
    audit(conn, "invoice_created", "invoice", invoice_id, {"source": source_name or "manual"})
    invoice = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    return dict(invoice)


def fetch_reconciliation_results(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            rm.*,
            i.invoice_number,
            i.vendor_name,
            i.total_amount AS invoice_amount,
            bt.transaction_id,
            bt.description AS transaction_description,
            bt.amount AS transaction_amount,
            bt.transaction_date
        FROM reconciliation_matches rm
        LEFT JOIN invoices i ON i.id = rm.invoice_id
        LEFT JOIN bank_transactions bt ON bt.id = rm.bank_transaction_id
        ORDER BY rm.match_score DESC, rm.created_at DESC
        """
    ).fetchall()
    return rows_to_dicts(rows)


def fetch_exceptions(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            re.*,
            i.invoice_number,
            i.vendor_name,
            i.total_amount AS invoice_amount,
            bt.transaction_id,
            bt.description AS transaction_description,
            bt.amount AS transaction_amount
        FROM reconciliation_exceptions re
        LEFT JOIN invoices i ON i.id = re.invoice_id
        LEFT JOIN bank_transactions bt ON bt.id = re.bank_transaction_id
        ORDER BY
            CASE re.severity
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                ELSE 4
            END,
            re.created_at DESC
        """
    ).fetchall()
    return rows_to_dicts(rows)


def build_overview(conn) -> dict[str, Any]:
    invoices = rows_to_dicts(conn.execute("SELECT * FROM invoices").fetchall())
    transactions = rows_to_dicts(conn.execute("SELECT * FROM bank_transactions").fetchall())
    matches = fetch_reconciliation_results(conn)
    exceptions = fetch_exceptions(conn)

    matched_count = sum(1 for item in matches if item["match_status"] == "matched")
    partially_matched_count = sum(1 for item in matches if item["match_status"] == "partially_matched")
    amount_mismatch_count = sum(1 for item in matches if item["match_status"] == "amount_mismatch")
    unmatched_invoice_count = sum(1 for item in exceptions if item["exception_type"] == "unmatched_invoice")
    unmatched_transaction_count = sum(1 for item in exceptions if item["exception_type"] == "unmatched_transaction")
    duplicate_count = sum(1 for item in exceptions if item["exception_type"] == "duplicate_invoice_number")
    open_exceptions = sum(1 for item in exceptions if not item["resolved"])
    unmatched_value = sum(float(item.get("invoice_amount") or 0) for item in exceptions if item["exception_type"] == "unmatched_invoice")
    total_invoices = len(invoices)
    matched_rate = round((matched_count / total_invoices) * 100, 1) if total_invoices else 0

    return {
        "total_invoices": total_invoices,
        "total_transactions": len(transactions),
        "matched_count": matched_count,
        "partially_matched_count": partially_matched_count,
        "amount_mismatch_count": amount_mismatch_count,
        "unmatched_invoice_count": unmatched_invoice_count,
        "unmatched_transaction_count": unmatched_transaction_count,
        "duplicate_invoice_count": duplicate_count,
        "open_exceptions": open_exceptions,
        "matched_rate": matched_rate,
        "total_unmatched_value": round(unmatched_value, 2),
        "currency": "VND",
        "ocr_average_confidence": round(
            sum(float(item["ocr_confidence"]) for item in invoices if item.get("ocr_confidence") is not None)
            / max(1, sum(1 for item in invoices if item.get("ocr_confidence") is not None)),
            1,
        ),
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/vendors/import")
async def import_vendors(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read()
    rows = parse_csv_bytes(content)
    imported = 0
    with get_connection() as conn:
        for row in rows:
            name = row.get("vendor_name") or row.get("name")
            if not name:
                continue
            conn.execute(
                """
                INSERT INTO vendors (vendor_id, vendor_name, tax_code, bank_account, address)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    row.get("vendor_id") or row.get("id"),
                    name,
                    row.get("tax_code") or row.get("tax"),
                    row.get("bank_account") or row.get("account"),
                    row.get("address"),
                ),
            )
            imported += 1
        audit(conn, "vendors_imported", "vendor", None, {"file": file.filename, "count": imported})
    return {"imported": imported}


@app.get("/api/vendors")
def list_vendors() -> list[dict[str, Any]]:
    with get_connection() as conn:
        return fetch_vendors(conn)


@app.delete("/api/vendors/{vendor_id}")
def delete_vendor(vendor_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute("DELETE FROM vendors WHERE id = ?", (vendor_id,))
        audit(conn, "vendor_deleted", "vendor", vendor_id)
    return {"deleted": vendor_id}


@app.post("/api/bank-transactions/import")
async def import_bank_transactions(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read()
    rows = parse_csv_bytes(content)
    imported = 0
    skipped = 0
    with get_connection() as conn:
        for row in rows:
            amount = parse_amount(row.get("amount"))
            transaction_date = parse_date(row.get("transaction_date") or row.get("date"))
            if amount is None or not transaction_date:
                skipped += 1
                continue
            conn.execute(
                """
                INSERT INTO bank_transactions (
                    transaction_id, transaction_date, description, amount,
                    direction, bank_account, reference_code
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("transaction_id") or row.get("id"),
                    transaction_date,
                    row.get("description") or row.get("memo") or row.get("content"),
                    amount,
                    (row.get("direction") or "outflow").lower(),
                    row.get("bank_account") or row.get("account"),
                    row.get("reference_code") or row.get("reference"),
                ),
            )
            imported += 1
        audit(conn, "bank_transactions_imported", "bank_transaction", None, {"file": file.filename, "count": imported})
    return {"imported": imported, "skipped": skipped}


@app.get("/api/bank-transactions")
def list_bank_transactions() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM bank_transactions ORDER BY transaction_date DESC, id DESC").fetchall()
        return rows_to_dicts(rows)


@app.post("/api/invoices/manual")
def create_manual_invoice(payload: InvoicePayload) -> dict[str, Any]:
    with get_connection() as conn:
        invoice = create_invoice(conn, payload.model_dump())
        run_invoice_validation(conn)
        return invoice


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
) -> dict[str, Any]:
    content = await file.read()
    saved_path = save_upload(file.filename or "invoice", content)
    raw_text = read_extractable_text(file.filename or "", content)
    extracted = extract_invoice_fields(raw_text, file.filename or "")
    payload = {
        **extracted,
        "invoice_number": invoice_number or extracted.get("invoice_number"),
        "vendor_name": vendor_name,
        "vendor_tax_code": vendor_tax_code,
        "invoice_date": invoice_date or extracted.get("invoice_date"),
        "due_date": due_date,
        "subtotal": subtotal,
        "vat_amount": vat_amount or extracted.get("vat_amount"),
        "total_amount": total_amount or extracted.get("total_amount"),
        "currency": currency or "VND",
        "ocr_confidence": ocr_confidence,
    }

    with get_connection() as conn:
        invoice = create_invoice(
            conn,
            payload,
            raw_text=raw_text,
            source_path=str(saved_path),
            source_name=file.filename,
        )
        run_invoice_validation(conn)
        return invoice


@app.get("/api/invoices")
def list_invoices() -> list[dict[str, Any]]:
    with get_connection() as conn:
        return fetch_invoices(conn)


@app.put("/api/invoices/{invoice_id}")
def update_invoice(invoice_id: int, payload: InvoicePayload) -> dict[str, Any]:
    normalized = normalize_invoice_payload(payload.model_dump())
    with get_connection() as conn:
        current = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="Invoice not found")
        conn.execute(
            """
            UPDATE invoices
            SET invoice_number = ?, vendor_name = ?, vendor_tax_code = ?, invoice_date = ?,
                due_date = ?, subtotal = ?, vat_amount = ?, total_amount = ?,
                currency = ?, ocr_confidence = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                normalized["invoice_number"],
                normalized["vendor_name"],
                normalized["vendor_tax_code"],
                normalized["invoice_date"],
                normalized["due_date"],
                normalized["subtotal"],
                normalized["vat_amount"],
                normalized["total_amount"],
                normalized["currency"],
                normalized["ocr_confidence"],
                invoice_id,
            ),
        )
        run_invoice_validation(conn)
        audit(conn, "invoice_updated", "invoice", invoice_id)
        invoice = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        return dict(invoice)


@app.delete("/api/invoices/{invoice_id}")
def delete_invoice(invoice_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
        audit(conn, "invoice_deleted", "invoice", invoice_id)
    return {"deleted": invoice_id}


@app.post("/api/validation/run")
def run_validation() -> dict[str, Any]:
    with get_connection() as conn:
        result = run_invoice_validation(conn)
        audit(conn, "validation_run", "invoice", None, result)
        return result


@app.post("/api/reconciliation/run")
def run_reconciliation() -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute("DELETE FROM reconciliation_matches")
        conn.execute("DELETE FROM reconciliation_exceptions")
        validation_result = run_invoice_validation(conn)

        invoices = rows_to_dicts(conn.execute("SELECT * FROM invoices ORDER BY id").fetchall())
        transactions = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM bank_transactions
                WHERE COALESCE(direction, 'outflow') = 'outflow'
                ORDER BY transaction_date, id
                """
            ).fetchall()
        )
        used_transactions: set[int] = set()
        created_matches = 0
        created_exceptions = 0

        for invoice in invoices:
            if not invoice.get("total_amount"):
                continue

            best_transaction = None
            best_metrics = {"score": 0.0, "amount_diff": 0.0, "date_diff": None}
            for transaction in transactions:
                if int(transaction["id"]) in used_transactions:
                    continue
                metrics = calculate_match_score(invoice, transaction)
                if metrics["score"] > best_metrics["score"]:
                    best_metrics = metrics
                    best_transaction = transaction

            if best_transaction and best_metrics["score"] >= 60:
                status = classify_match(best_metrics["score"], best_metrics["amount_diff"])
                conn.execute(
                    """
                    INSERT INTO reconciliation_matches (
                        invoice_id, bank_transaction_id, match_score, match_status,
                        amount_diff, date_diff, reason
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        invoice["id"],
                        best_transaction["id"],
                        best_metrics["score"],
                        status,
                        best_metrics["amount_diff"],
                        best_metrics["date_diff"],
                        match_reason(invoice, best_transaction, best_metrics),
                    ),
                )
                used_transactions.add(int(best_transaction["id"]))
                created_matches += 1

                if status == "amount_mismatch":
                    conn.execute(
                        """
                        INSERT INTO reconciliation_exceptions (
                            invoice_id, bank_transaction_id, exception_type, severity, message
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            invoice["id"],
                            best_transaction["id"],
                            "amount_mismatch",
                            "high",
                            f"Matched transaction amount differs by {best_metrics['amount_diff']:,.0f}.",
                        ),
                    )
                    created_exceptions += 1
                elif status == "partially_matched":
                    conn.execute(
                        """
                        INSERT INTO reconciliation_exceptions (
                            invoice_id, bank_transaction_id, exception_type, severity, message
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            invoice["id"],
                            best_transaction["id"],
                            "partial_match_review",
                            "medium",
                            f"Potential match requires review: {match_reason(invoice, best_transaction, best_metrics)}.",
                        ),
                    )
                    created_exceptions += 1
            else:
                conn.execute(
                    """
                    INSERT INTO reconciliation_exceptions (
                        invoice_id, exception_type, severity, message
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        invoice["id"],
                        "unmatched_invoice",
                        "medium",
                        "No bank transaction reached the review threshold.",
                    ),
                )
                created_exceptions += 1

        for transaction in transactions:
            if int(transaction["id"]) not in used_transactions:
                conn.execute(
                    """
                    INSERT INTO reconciliation_exceptions (
                        bank_transaction_id, exception_type, severity, message
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        transaction["id"],
                        "unmatched_transaction",
                        "medium",
                        "Bank transaction was not matched to any invoice.",
                    ),
                )
                created_exceptions += 1

        audit(
            conn,
            "reconciliation_run",
            "reconciliation",
            None,
            {
                "matches": created_matches,
                "exceptions": created_exceptions,
                "validation": validation_result,
            },
        )
        return {
            "matches": created_matches,
            "exceptions": created_exceptions,
            "validation": validation_result,
        }


@app.get("/api/reconciliation/results")
def reconciliation_results() -> list[dict[str, Any]]:
    with get_connection() as conn:
        return fetch_reconciliation_results(conn)


@app.get("/api/reconciliation/exceptions")
def reconciliation_exceptions() -> list[dict[str, Any]]:
    with get_connection() as conn:
        return fetch_exceptions(conn)


@app.post("/api/reconciliation/{match_id}/approve")
def approve_match(match_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        result = conn.execute(
            "UPDATE reconciliation_matches SET approved = 1, match_status = 'matched' WHERE id = ?",
            (match_id,),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Match not found")
        audit(conn, "match_approved", "reconciliation_match", match_id)
    return {"approved": match_id}


@app.post("/api/reconciliation/{match_id}/reject")
def reject_match(match_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        match = conn.execute("SELECT * FROM reconciliation_matches WHERE id = ?", (match_id,)).fetchone()
        if match is None:
            raise HTTPException(status_code=404, detail="Match not found")
        conn.execute("UPDATE reconciliation_matches SET approved = 0, match_status = 'rejected' WHERE id = ?", (match_id,))
        conn.execute(
            """
            INSERT INTO reconciliation_exceptions (
                invoice_id, bank_transaction_id, exception_type, severity, message
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                match["invoice_id"],
                match["bank_transaction_id"],
                "manual_rejection",
                "medium",
                "User rejected this automated match.",
            ),
        )
        audit(conn, "match_rejected", "reconciliation_match", match_id)
    return {"rejected": match_id}


@app.post("/api/reconciliation/exceptions/{exception_id}/resolve")
def resolve_exception(exception_id: int, payload: ResolvePayload) -> dict[str, Any]:
    with get_connection() as conn:
        result = conn.execute(
            "UPDATE reconciliation_exceptions SET resolved = ? WHERE id = ?",
            (1 if payload.resolved else 0, exception_id),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Exception not found")
        audit(conn, "exception_resolved", "reconciliation_exception", exception_id, payload.model_dump())
    return {"exception_id": exception_id, "resolved": payload.resolved}


@app.get("/api/dashboard/overview")
def dashboard_overview() -> dict[str, Any]:
    with get_connection() as conn:
        return build_overview(conn)


@app.get("/api/reports/daily")
def daily_report() -> dict[str, str]:
    with get_connection() as conn:
        overview = build_overview(conn)
        report = build_reconciliation_report(overview, fetch_exceptions(conn), fetch_reconciliation_results(conn))
        audit(conn, "report_generated", "ai_report", None, {"type": "daily"})
        return {"report": report}


@app.get("/api/audit-logs")
def list_audit_logs() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM audit_logs ORDER BY created_at DESC, id DESC LIMIT 100").fetchall()
        return rows_to_dicts(rows)
