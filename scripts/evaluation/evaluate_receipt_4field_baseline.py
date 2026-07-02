from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from statistics import mean
from typing import Any


DATE_RE = re.compile(
    r"(?P<day>\d{1,2})[\/\-.](?P<month>\d{1,2})[\/\-.](?P<year>\d{2,4})"
    r"|(?P<year2>\d{4})[\/\-.](?P<month2>\d{1,2})[\/\-.](?P<day2>\d{1,2})"
)
TIME_RE = re.compile(r"\b\d{1,2}\s*:\s*\d{2}(?:\s*:\s*\d{2})?\b")
AMOUNT_RE = re.compile(r"\d{1,3}(?:[.,\s]\d{3})+|\d{4,}")
ADDRESS_HINT_RE = re.compile(
    r"\b(dc|d/c|dia chi|địa chỉ|p\.|q\.|tp\.|tinh|tỉnh|quan|quận|phuong|phường|"
    r"duong|đường|so\s+\d|số\s+\d|khu|cho|chợ)\b",
    re.IGNORECASE,
)
ADDRESS_WORD_RE = re.compile(
    r"\b(duong|đường|pho|phố|phuong|phường|quan|quận|tp|thanh pho|thành phố|"
    r"tinh|tỉnh|khu|cho|chợ|to|tổ)\b",
    re.IGNORECASE,
)
TOTAL_KEYWORD_RE = re.compile(
    r"tong|tổng|thanh\s*toan|thanh\s*toán|phai\s*t\.?toan|phải\s*t\.?toán|"
    r"phai\s*tra|phải\s*trả|cong\s*tien|cộng\s*tiền|total|amount",
    re.IGNORECASE,
)
MONEY_CONTEXT_RE = re.compile(r"\b(vnd|vnđ|d|đ)\b|[,.]\d{3}\b", re.IGNORECASE)
SELLER_BAD_RE = re.compile(
    r"ngay|ngày|tong|tổng|thanh|dia chi|địa chỉ|dc|d/c|sdt|đt|mst|ma so|mã số|"
    r"hoa don|hóa đơn|receipt|invoice|total",
    re.IGNORECASE,
)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def normalize_for_fuzzy(value: str) -> str:
    value = strip_accents(clean_text(value).lower())
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def fuzzy_ratio(a: str, b: str) -> float:
    left = normalize_for_fuzzy(a)
    right = normalize_for_fuzzy(b)
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def normalize_amount(value: str, require_money_context_for_alnum: bool = False) -> int | None:
    text = clean_text(value)
    if require_money_context_for_alnum:
        has_letters = bool(re.search(r"[A-Za-zÀ-ỹ]", text))
        has_context = bool(TOTAL_KEYWORD_RE.search(text) or MONEY_CONTEXT_RE.search(text))
        if has_letters and not has_context:
            return None
    candidates: list[int] = []
    for match in AMOUNT_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if not digits:
            continue
        amount = int(digits)
        if amount >= 1_000:
            candidates.append(amount)
    return max(candidates) if candidates else None


def normalize_timestamp(value: str) -> str | None:
    text = clean_text(value)
    match = DATE_RE.search(text)
    if not match:
        return None
    if match.group("year2"):
        year = int(match.group("year2"))
        month = int(match.group("month2"))
        day = int(match.group("day2"))
    else:
        day = int(match.group("day"))
        month = int(match.group("month"))
        year = int(match.group("year"))
        if year < 100:
            year += 2000
    if not (1 <= day <= 31 and 1 <= month <= 12 and 2000 <= year <= 2099):
        return None
    date_part = f"{year:04d}-{month:02d}-{day:02d}"
    time_match = TIME_RE.search(text)
    if not time_match:
        return date_part
    chunks = re.sub(r"\s+", "", time_match.group(0)).split(":")
    if len(chunks) == 2:
        return f"{date_part} {int(chunks[0]):02d}:{int(chunks[1]):02d}:00"
    return f"{date_part} {int(chunks[0]):02d}:{int(chunks[1]):02d}:{int(chunks[2]):02d}"


def box_center_y(box: dict[str, Any]) -> float:
    bbox = box.get("bbox") or [0, 0, 0, 0]
    return (float(bbox[1]) + float(bbox[3])) / 2


def box_center_x(box: dict[str, Any]) -> float:
    bbox = box.get("bbox") or [0, 0, 0, 0]
    return (float(bbox[0]) + float(bbox[2])) / 2


def box_height(box: dict[str, Any]) -> float:
    bbox = box.get("bbox") or [0, 0, 0, 0]
    return max(0.0, float(bbox[3]) - float(bbox[1]))


def infer_page_height(boxes: list[dict[str, Any]]) -> float:
    max_y = 1.0
    for box in boxes:
        bbox = box.get("bbox") or []
        if len(bbox) >= 4:
            max_y = max(max_y, float(bbox[3]))
    return max_y


def predict_seller(boxes: list[dict[str, Any]], page_height: float) -> str:
    scored: list[tuple[float, str]] = []
    for box in boxes:
        text = clean_text(box.get("text"))
        if len(text) < 3 or SELLER_BAD_RE.search(text):
            continue
        if not re.search(r"[A-Za-zÀ-ỹ]", text):
            continue
        y = box_center_y(box) / page_height
        if y > 0.35:
            continue
        alpha_count = len(re.findall(r"[A-Za-zÀ-ỹ]", text))
        uppercase_bonus = 0.15 if text.upper() == text and alpha_count >= 4 else 0
        score = (1 - y) * 2 + min(alpha_count, 30) / 30 + box_height(box) / page_height + uppercase_bonus
        scored.append((score, text))
    if not scored:
        return ""
    scored.sort(reverse=True)
    return scored[0][1]


def predict_address(boxes: list[dict[str, Any]], page_height: float) -> str:
    scored: list[tuple[float, str]] = []
    for box in boxes:
        text = clean_text(box.get("text"))
        if len(text) < 5:
            continue
        if not re.search(r"[A-Za-zÀ-ỹ]", text):
            continue
        hint = bool(ADDRESS_HINT_RE.search(text) or ADDRESS_WORD_RE.search(text))
        if not hint:
            continue
        y = box_center_y(box) / page_height
        score = 2.0 + min(len(text), 80) / 80 - y * 0.25
        scored.append((score, text))
    if not scored:
        return ""
    scored.sort(reverse=True)
    unique: list[str] = []
    for _score, text in scored:
        if text not in unique:
            unique.append(text)
        if len(unique) >= 2:
            break
    return ", ".join(unique)


def predict_timestamp(boxes: list[dict[str, Any]], page_height: float) -> tuple[str, str | None]:
    scored: list[tuple[float, str, str]] = []
    for box in boxes:
        text = clean_text(box.get("text"))
        normalized = normalize_timestamp(text)
        if not normalized:
            continue
        y = box_center_y(box) / page_height
        time_bonus = 0.5 if TIME_RE.search(text) else 0
        score = 2.0 + time_bonus - abs(y - 0.45) * 0.25
        scored.append((score, text, normalized))
    if not scored:
        return "", None
    scored.sort(reverse=True)
    return scored[0][1], scored[0][2]


def predict_total_cost(boxes: list[dict[str, Any]], page_height: float) -> tuple[str, int | None]:
    keyword_ys = [box_center_y(box) / page_height for box in boxes if TOTAL_KEYWORD_RE.search(clean_text(box.get("text")))]
    scored: list[tuple[float, str, int]] = []
    for box in boxes:
        text = clean_text(box.get("text"))
        amount = normalize_amount(text, require_money_context_for_alnum=True)
        if amount is None:
            continue
        y = box_center_y(box) / page_height
        near_keyword = min((abs(y - ky) for ky in keyword_ys), default=1.0)
        keyword_bonus = 2.0 if TOTAL_KEYWORD_RE.search(text) else max(0.0, 1.5 - near_keyword * 8)
        score = math.log10(amount) + y * 1.5 + keyword_bonus
        scored.append((score, text, amount))
    if not scored:
        return "", None
    scored.sort(reverse=True)
    return scored[0][1], scored[0][2]


def predict_record(record: dict[str, Any]) -> dict[str, Any]:
    boxes = record.get("boxes") or []
    page_height = infer_page_height(boxes)
    timestamp, normalized_timestamp = predict_timestamp(boxes, page_height)
    total_cost, normalized_total_cost = predict_total_cost(boxes, page_height)
    return {
        "id": record["id"],
        "fields": {
            "seller": predict_seller(boxes, page_height),
            "address": predict_address(boxes, page_height),
            "timestamp": timestamp,
            "total_cost": total_cost,
        },
        "normalized": {
            "timestamp": normalized_timestamp,
            "total_cost": normalized_total_cost,
        },
    }


def load_records(dataset_dir: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with (dataset_dir / "labels.jsonl").open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                record = json.loads(line)
                records[record["id"]] = record
    return records


def load_split_ids(dataset_dir: Path, split_name: str) -> list[str]:
    path = dataset_dir / "splits" / f"{split_name}.txt"
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate(records: list[dict[str, Any]], predictions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    seller_scores = []
    address_scores = []
    timestamp_total = timestamp_correct = timestamp_present = 0
    total_cost_total = total_cost_correct = total_cost_present = 0
    for record in records:
        prediction = predictions[record["id"]]
        expected_fields = record["fields"]
        expected_normalized = record["normalized"]
        if expected_fields.get("seller"):
            seller_scores.append(fuzzy_ratio(prediction["fields"].get("seller", ""), expected_fields["seller"]))
        if expected_fields.get("address"):
            address_scores.append(fuzzy_ratio(prediction["fields"].get("address", ""), expected_fields["address"]))
        if expected_normalized.get("timestamp"):
            timestamp_total += 1
            if prediction["normalized"].get("timestamp"):
                timestamp_present += 1
            if prediction["normalized"].get("timestamp") == expected_normalized["timestamp"]:
                timestamp_correct += 1
        if expected_normalized.get("total_cost") is not None:
            total_cost_total += 1
            if prediction["normalized"].get("total_cost") is not None:
                total_cost_present += 1
            if prediction["normalized"].get("total_cost") == expected_normalized["total_cost"]:
                total_cost_correct += 1
    return {
        "records": len(records),
        "seller_fuzzy_avg": mean(seller_scores) if seller_scores else 0,
        "seller_fuzzy_ge_80": sum(score >= 0.80 for score in seller_scores) / len(seller_scores) if seller_scores else 0,
        "address_fuzzy_avg": mean(address_scores) if address_scores else 0,
        "address_fuzzy_ge_70": sum(score >= 0.70 for score in address_scores) / len(address_scores) if address_scores else 0,
        "timestamp_accuracy": timestamp_correct / timestamp_total if timestamp_total else 0,
        "timestamp_presence": timestamp_present / timestamp_total if timestamp_total else 0,
        "total_cost_accuracy": total_cost_correct / total_cost_total if total_cost_total else 0,
        "total_cost_presence": total_cost_present / total_cost_total if total_cost_total else 0,
    }


def write_predictions(path: Path, predictions: dict[str, dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for prediction in predictions.values():
            file.write(json.dumps(prediction, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_report(path: Path, metrics_by_split: dict[str, dict[str, Any]]) -> None:
    lines = [
        "# Receipt 4-Field Baseline Report",
        "",
        "This baseline uses only transcript text and box positions from `labels.jsonl`; it does not use box labels for prediction.",
        "",
        "| Split | Records | Seller avg | Seller >=80 | Address avg | Address >=70 | Timestamp acc | Timestamp present | Total cost acc | Total cost present |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for split_name, metrics in metrics_by_split.items():
        lines.append(
            "| {split} | {records} | {seller_avg:.3f} | {seller80:.3f} | {address_avg:.3f} | "
            "{address70:.3f} | {timestamp_acc:.3f} | {timestamp_present:.3f} | "
            "{amount_acc:.3f} | {amount_present:.3f} |".format(
                split=split_name,
                records=metrics["records"],
                seller_avg=metrics["seller_fuzzy_avg"],
                seller80=metrics["seller_fuzzy_ge_80"],
                address_avg=metrics["address_fuzzy_avg"],
                address70=metrics["address_fuzzy_ge_70"],
                timestamp_acc=metrics["timestamp_accuracy"],
                timestamp_present=metrics["timestamp_presence"],
                amount_acc=metrics["total_cost_accuracy"],
                amount_present=metrics["total_cost_presence"],
            )
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Use this report as a baseline to beat with a trained KIE/field extraction model.",
            "- Seller/address are measured with accent-insensitive fuzzy matching.",
            "- Timestamp and total cost are measured after normalization.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def run(args: argparse.Namespace) -> None:
    dataset_dir = Path(args.dataset_dir).resolve()
    report_dir = dataset_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    records_by_id = load_records(dataset_dir)
    split_names = args.splits.split(",")

    metrics_by_split: dict[str, dict[str, Any]] = {}
    all_predictions: dict[str, dict[str, Any]] = {}
    for split_name in split_names:
        ids = load_split_ids(dataset_dir, split_name)
        records = [records_by_id[item_id] for item_id in ids if item_id in records_by_id]
        predictions = {record["id"]: predict_record(record) for record in records}
        metrics_by_split[split_name] = evaluate(records, predictions)
        all_predictions.update(predictions)

    write_predictions(report_dir / "baseline_predictions.jsonl", all_predictions)
    write_report(report_dir / "baseline_report.md", metrics_by_split)
    print(f"Wrote baseline report: {report_dir / 'baseline_report.md'}")
    for split_name, metrics in metrics_by_split.items():
        print(
            split_name,
            "records=", metrics["records"],
            "seller_avg=", f"{metrics['seller_fuzzy_avg']:.3f}",
            "address_avg=", f"{metrics['address_fuzzy_avg']:.3f}",
            "timestamp_acc=", f"{metrics['timestamp_accuracy']:.3f}",
            "total_cost_acc=", f"{metrics['total_cost_accuracy']:.3f}",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a heuristic baseline for the receipt 4-field dataset.")
    parser.add_argument(
        "--dataset-dir",
        default="archive/prepared/finrecon_receipt_4field",
        help="Prepared dataset directory.",
    )
    parser.add_argument("--splits", default="val,test", help="Comma-separated splits to evaluate.")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
