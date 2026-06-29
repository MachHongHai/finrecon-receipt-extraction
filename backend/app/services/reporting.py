from __future__ import annotations

from collections import Counter
from typing import Any


def build_reconciliation_report(
    overview: dict[str, Any],
    exceptions: list[dict[str, Any]],
    matches: list[dict[str, Any]],
) -> str:
    exception_counts = Counter(item["exception_type"] for item in exceptions)
    high_risk = [
        item for item in exceptions if item["severity"] in {"critical", "high"} and not item.get("resolved")
    ]

    lines = [
        "FinRecon Receipt AI - receipt control and payment reconciliation report",
        "",
        f"Processed purchase receipts: {overview['total_invoices']}",
        f"Imported bank transactions: {overview['total_transactions']}",
        f"Matched rate: {overview['matched_rate']}%",
        f"Open exceptions: {overview['open_exceptions']}",
        f"Unmatched value: {overview['total_unmatched_value']:,.0f} {overview.get('currency', 'VND')}",
        "",
        "Status summary:",
        f"- Matched: {overview['matched_count']}",
        f"- Partially matched: {overview['partially_matched_count']}",
        f"- Amount mismatches: {overview['amount_mismatch_count']}",
        f"- Unpaid or unmatched receipts: {overview['unmatched_invoice_count']}",
        f"- Unmatched transactions: {overview['unmatched_transaction_count']}",
    ]

    if exception_counts:
        lines.extend(["", "Exception mix:"])
        for exception_type, count in exception_counts.most_common():
            lines.append(f"- {exception_type}: {count}")

    if high_risk:
        lines.extend(["", "Priority actions:"])
        for item in high_risk[:5]:
            target = item.get("invoice_number") or item.get("transaction_id") or f"exception #{item['id']}"
            lines.append(f"- Review {target}: {item['message']}")

    if matches:
        best = max(matches, key=lambda item: item.get("match_score") or 0)
        lines.extend(
            [
                "",
                "Best automated match:",
                f"- {best.get('invoice_number') or 'Receipt'} to {best.get('transaction_id') or 'transaction'} with score {best.get('match_score')}",
            ]
        )

    return "\n".join(lines)
