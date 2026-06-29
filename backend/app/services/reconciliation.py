from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from app.utils import normalize_text, parse_date


def _days_between(left: str | None, right: str | None) -> int | None:
    left_date = parse_date(left)
    right_date = parse_date(right)
    if not left_date or not right_date:
        return None
    return abs((datetime.fromisoformat(left_date) - datetime.fromisoformat(right_date)).days)


def _text_ratio(left: str, right: str) -> float:
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm in right_norm or right_norm in left_norm:
        return 100.0
    return SequenceMatcher(None, left_norm, right_norm).ratio() * 100


DEFAULT_RULES = {
    "auto_match_threshold": 85,
    "manual_review_threshold": 60,
    "date_tolerance_days": 30,
    "amount_tolerance_vnd": 500000,
}


def calculate_match_score(invoice: dict[str, Any], transaction: dict[str, Any], rules: dict[str, Any] | None = None) -> dict[str, Any]:
    score = 0.0
    total = abs(float(invoice.get("total_amount") or 0))
    amount = abs(float(transaction.get("amount") or 0))
    amount_diff = abs(total - amount)

    if total > 0:
        if amount_diff == 0:
            score += 45
        elif amount_diff <= 5000:
            score += 35
        elif amount_diff <= 50000:
            score += 20
        elif amount_diff <= 200000:
            score += 10

    date_diff = _days_between(invoice.get("invoice_date"), transaction.get("transaction_date"))
    if date_diff is not None:
        if date_diff <= 3:
            score += 25
        elif date_diff <= 7:
            score += 15
        elif date_diff <= 14:
            score += 5

    vendor_score = _text_ratio(invoice.get("vendor_name") or "", transaction.get("description") or "")
    score += vendor_score * 0.2

    invoice_number = normalize_text(invoice.get("invoice_number"))
    description = normalize_text(transaction.get("description"))
    reference = normalize_text(transaction.get("reference_code"))
    if invoice_number and (invoice_number in description or invoice_number in reference):
        score += 10

    return {
        "score": round(min(score, 100.0), 2),
        "amount_diff": round(amount_diff, 2),
        "date_diff": date_diff,
        "vendor_score": round(vendor_score, 2),
    }


def is_reconciliation_candidate(invoice: dict[str, Any], transaction: dict[str, Any], rules: dict[str, Any] | None = None) -> bool:
    rules = {**DEFAULT_RULES, **(rules or {})}
    if (transaction.get("direction") or "outflow").lower() != "outflow":
        return False

    metrics = calculate_match_score(invoice, transaction)
    date_diff = metrics.get("date_diff")
    if date_diff is None or date_diff > int(rules["date_tolerance_days"]):
        return False
    return float(metrics["amount_diff"]) <= float(rules["amount_tolerance_vnd"])


def classify_match(score: float, amount_diff: float, rules: dict[str, Any] | None = None) -> str:
    rules = {**DEFAULT_RULES, **(rules or {})}
    auto_threshold = float(rules["auto_match_threshold"])
    review_threshold = float(rules["manual_review_threshold"])
    if score >= auto_threshold and amount_diff == 0:
        return "matched"
    if score >= auto_threshold and amount_diff > 0:
        return "amount_mismatch"
    if score >= review_threshold:
        return "partially_matched"
    return "unmatched"


def match_reason(invoice: dict[str, Any], transaction: dict[str, Any], metrics: dict[str, Any]) -> str:
    parts = [
        f"score {metrics['score']:.2f}",
        f"amount diff {metrics['amount_diff']:,.0f}",
    ]
    if metrics.get("date_diff") is not None:
        parts.append(f"date diff {metrics['date_diff']} days")
    reference_text = f"{transaction.get('description') or ''} {transaction.get('reference_code') or ''}"
    if invoice.get("invoice_number") and normalize_text(invoice["invoice_number"]) in normalize_text(reference_text):
        parts.append("receipt/reference found in bank description")
    return ", ".join(parts)
