from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any


TARGET_LABELS = {"SELLER", "ADDRESS", "TIMESTAMP", "TOTAL_COST"}
ALL_LABELS = {"OTHER", *TARGET_LABELS}
FIELD_BY_LABEL = {
    "SELLER": "seller",
    "ADDRESS": "address",
    "TIMESTAMP": "timestamp",
    "TOTAL_COST": "total_cost",
}
MOJIBAKE_RE = re.compile(r"(?:Ã|Ä|Æ|á»|áº|[\x80-\x9f]|�)")
DATE_RE = re.compile(
    r"\b(?:\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}|\d{4}[\/\-.]\d{1,2}[\/\-.]\d{1,2})\b"
)
TIME_RE = re.compile(r"\b\d{1,2}\s*:\s*\d{2}(?:\s*:\s*\d{2})?\b")
AMOUNT_RE = re.compile(r"\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d{1,2})?|\d{4,}")


def mojibake_score(text: str) -> int:
    return len(MOJIBAKE_RE.findall(text)) if text else 0


def mojibake_bytes(text: str) -> bytes:
    buffer = bytearray()
    for char in text:
        codepoint = ord(char)
        if codepoint <= 255:
            buffer.append(codepoint)
            continue
        try:
            buffer.extend(char.encode("cp1252"))
        except UnicodeEncodeError:
            buffer.extend(char.encode("utf-8"))
    return bytes(buffer)


def repair_once(text: str) -> list[str]:
    candidates = [text]
    for encoding in ("latin1", "cp1252"):
        try:
            candidates.append(text.encode(encoding).decode("utf-8"))
        except UnicodeError:
            pass
    try:
        candidates.append(mojibake_bytes(text).decode("utf-8"))
    except UnicodeError:
        pass
    return candidates


def repair_text(text: str | None) -> tuple[str, bool]:
    if not text:
        return "", False
    candidates = [text]
    frontier = [text]
    for _ in range(2):
        next_frontier: list[str] = []
        for candidate in frontier:
            for repaired in repair_once(candidate):
                if repaired not in candidates:
                    candidates.append(repaired)
                    next_frontier.append(repaired)
        frontier = next_frontier
    best = min(candidates, key=lambda item: (mojibake_score(item), -len(item)))
    return best, best != text and mojibake_score(best) < mojibake_score(text)


def normalize_label(label: str | None) -> str:
    value = (label or "OTHER").strip().upper()
    if value == "TOTAL_TOTAL_COST":
        value = "TOTAL_COST"
    return value if value in ALL_LABELS else "OTHER"


def valid_points(points: Any) -> bool:
    if isinstance(points, list) and len(points) == 4 and all(isinstance(item, list) and len(item) == 2 for item in points):
        return True
    if isinstance(points, list) and len(points) >= 8 and all(isinstance(item, (int, float)) for item in points[:8]):
        return True
    if (
        isinstance(points, list)
        and len(points) == 1
        and isinstance(points[0], list)
        and len(points[0]) >= 8
        and all(isinstance(item, (int, float)) for item in points[0][:8])
    ):
        return True
    return False


def valid_bbox(bbox: Any) -> bool:
    if not (isinstance(bbox, list) and len(bbox) >= 4):
        return False
    try:
        x1, y1, x2, y2 = [float(value) for value in bbox[:4]]
    except (TypeError, ValueError):
        return False
    return (x2 > x1 and y2 > y1) or (x2 > 0 and y2 > 0)


def geometry_ok(item: dict[str, Any]) -> bool:
    return valid_points(item.get("points") or item.get("polygon")) or valid_bbox(item.get("bbox"))


def normalize_amount_candidate(raw: str) -> int | None:
    value = raw.strip()
    if not value:
        return None
    separators = [(index, char) for index, char in enumerate(value) if char in "., "]
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    if "." in value and "," in value:
        last_dot = value.rfind(".")
        last_comma = value.rfind(",")
        decimal_sep = "." if last_dot > last_comma else ","
        decimal_digits = len(re.sub(r"\D", "", value.split(decimal_sep)[-1]))
        if 1 <= decimal_digits <= 2:
            digits = re.sub(r"\D", "", value[: value.rfind(decimal_sep)])
    elif separators:
        last_index, last_sep = separators[-1]
        tail_digits = len(re.sub(r"\D", "", value[last_index + 1 :]))
        if last_sep in ".," and 1 <= tail_digits <= 2 and len(separators) == 1:
            digits = re.sub(r"\D", "", value[:last_index])
    if not digits:
        return None
    amount = int(digits)
    return amount if amount >= 1_000 else None


def normalize_field_value(field_name: str, value: str | None) -> tuple[str, Any | None]:
    text, _ = repair_text(value or "")
    if field_name == "timestamp":
        has_value = bool(DATE_RE.search(text) or TIME_RE.search(text))
        return text, text if has_value else None
    if field_name == "total_cost":
        for match in AMOUNT_RE.finditer(text):
            amount = normalize_amount_candidate(match.group(0))
            if amount is not None:
                return text, amount
        return text, None
    return text, None


def clean_annotation(
    item: dict[str, Any],
    record_id: str,
    group: str,
    index: int,
    stats: Counter[str],
    dropped: list[dict[str, Any]],
) -> dict[str, Any] | None:
    cleaned = dict(item)
    original_text = str(cleaned.get("text") or cleaned.get("transcription") or "")
    text, repaired = repair_text(original_text)
    label = normalize_label(cleaned.get("label"))

    if not text.strip():
        stats[f"{group}_empty_text_skipped"] += 1
        stats[f"empty_text_{label}"] += 1
        dropped.append(
            {
                "record_id": record_id,
                "group": group,
                "index": index,
                "reason": "empty_text",
                "label": label,
                "text": original_text,
                "bbox": cleaned.get("bbox"),
                "polygon": cleaned.get("polygon") or cleaned.get("points"),
            }
        )
        return None

    if not geometry_ok(cleaned):
        stats[f"{group}_invalid_geometry_skipped"] += 1
        stats[f"invalid_geometry_{label}"] += 1
        dropped.append(
            {
                "record_id": record_id,
                "group": group,
                "index": index,
                "reason": "invalid_geometry",
                "label": label,
                "text": text,
                "bbox": cleaned.get("bbox"),
                "polygon": cleaned.get("polygon") or cleaned.get("points"),
            }
        )
        return None

    raw_label = (cleaned.get("label") or "OTHER").strip().upper()
    if raw_label not in ALL_LABELS and raw_label != "TOTAL_TOTAL_COST":
        stats["unknown_label_mapped_to_other"] += 1

    if "text" in cleaned:
        cleaned["text"] = text
    if "transcription" in cleaned:
        cleaned["transcription"] = text
    if repaired:
        stats["text_repaired"] += 1
    cleaned["label"] = label
    cleaned["field"] = FIELD_BY_LABEL.get(label)
    stats[f"{group}_kept"] += 1
    stats[f"kept_{label}"] += 1
    return cleaned


def clean_record(record: dict[str, Any], stats: Counter[str], dropped: list[dict[str, Any]]) -> dict[str, Any]:
    cleaned = dict(record)
    cleaned["fields"] = dict(record.get("fields") or {})
    cleaned["normalized"] = dict(record.get("normalized") or {})

    for field_name in ("seller", "address", "timestamp", "total_cost"):
        text, normalized = normalize_field_value(field_name, cleaned["fields"].get(field_name))
        cleaned["fields"][field_name] = text
        if field_name in {"timestamp", "total_cost"}:
            cleaned["normalized"][field_name] = normalized

    cleaned["field_candidates"] = {
        field_name: [repair_text(str(candidate))[0] for candidate in candidates]
        for field_name, candidates in (record.get("field_candidates") or {}).items()
    }

    for group in ("source_annotations", "boxes"):
        cleaned_items: list[dict[str, Any]] = []
        for index, item in enumerate(record.get(group) or []):
            cleaned_item = clean_annotation(item, str(record.get("id")), group, index, stats, dropped)
            if cleaned_item is not None:
                cleaned_items.append(cleaned_item)
        cleaned[group] = cleaned_items

    present = []
    for field_name, label in FIELD_BY_LABEL.items():
        if any(box.get("label") == field_name for box in cleaned.get("boxes") or []):
            present.append(label)
    cleaned["coverage"] = {
        **(record.get("coverage") or {}),
        "fields_present": sorted(present),
        "has_all_4_fields": len(set(present)) == 4,
        "has_normalized_timestamp": cleaned["normalized"].get("timestamp") is not None,
        "has_normalized_total_cost": cleaned["normalized"].get("total_cost") is not None,
    }
    return cleaned


def count_box_labels(records: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for record in records:
        for box in record.get("boxes") or []:
            label = normalize_label(box.get("label"))
            counts[label] += 1
    return counts


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def copy_image(source: Path, destination: Path, mode: str) -> None:
    if mode == "none":
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    if mode == "hardlink":
        try:
            os.link(source, destination)
            return
        except OSError:
            pass
    shutil.copy2(source, destination)


def write_audit(
    output_dir: Path,
    before_counts: Counter[str],
    after_counts: Counter[str],
    stats: Counter[str],
    dropped: list[dict[str, Any]],
) -> None:
    report_dir = output_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "policy": {
            "keep_context_labels": ["SELLER", "ADDRESS", "TIMESTAMP", "TOTAL_COST"],
            "never_demote_by_missing_amount_or_date": True,
            "skip_empty_text": True,
            "skip_invalid_geometry": True,
            "map_unknown_labels_to_other": True,
        },
        "before_box_label_distribution": dict(before_counts),
        "after_box_label_distribution": dict(after_counts),
        "stats": dict(stats),
        "dropped_annotations": len(dropped),
    }
    (report_dir / "clean_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_jsonl(report_dir / "dropped_annotations.jsonl", dropped)

    lines = [
        "# FinRecon Receipt 4-Field Clean Dataset Audit",
        "",
        "Raw/prepared input is read-only. This script writes a clean training copy.",
        "",
        "## Canonical Cleaning Policy",
        "",
        "- Keep `SELLER`, `ADDRESS`, `TIMESTAMP`, and `TOTAL_COST` whenever text and geometry are usable.",
        "- Do not demote `TOTAL_COST` when the text has no amount; keyword/context lines are useful for KIE.",
        "- Do not demote `TIMESTAMP` when the text has no date/time; keyword/context lines are useful for KIE.",
        "- Skip empty-text annotations instead of relabeling them as `OTHER`.",
        "- Skip invalid-geometry annotations instead of relabeling them as `OTHER`.",
        "- Map unknown labels to `OTHER` only when the annotation has usable text and geometry.",
        "",
        "## Box Label Distribution",
        "",
        "| Label | Before | After | Delta |",
        "|---|---:|---:|---:|",
    ]
    for label in sorted(ALL_LABELS):
        lines.append(f"| `{label}` | {before_counts[label]} | {after_counts[label]} | {after_counts[label] - before_counts[label]} |")
    lines.extend(
        [
            "",
            "## Skip/Repair Stats",
            "",
            f"- Text repaired: {stats['text_repaired']}",
            f"- Empty text skipped: {stats['boxes_empty_text_skipped'] + stats['source_annotations_empty_text_skipped']}",
            f"- Invalid geometry skipped: {stats['boxes_invalid_geometry_skipped'] + stats['source_annotations_invalid_geometry_skipped']}",
            f"- Unknown labels mapped to `OTHER`: {stats['unknown_label_mapped_to_other']}",
            "",
            "## Empty Text Skipped By Original Label",
            "",
        ]
    )
    for label in sorted(ALL_LABELS):
        lines.append(f"- `{label}`: {stats[f'empty_text_{label}']}")
    lines.extend(
        [
            "",
            "Dropped annotation details are stored in `reports/dropped_annotations.jsonl`.",
        ]
    )
    (report_dir / "clean_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def clean_dataset(args: argparse.Namespace) -> None:
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not (input_dir / "labels.jsonl").exists():
        raise FileNotFoundError(f"Missing labels.jsonl in {input_dir}")
    if args.clear and output_dir.exists():
        shutil.rmtree(output_dir)
    (output_dir / "images").mkdir(parents=True, exist_ok=True)
    (output_dir / "splits").mkdir(parents=True, exist_ok=True)

    records = [json.loads(line) for line in (input_dir / "labels.jsonl").read_text(encoding="utf-8").splitlines() if line]
    before_counts = count_box_labels(records)
    stats: Counter[str] = Counter()
    dropped: list[dict[str, Any]] = []
    cleaned_records = [clean_record(record, stats, dropped) for record in records]
    after_counts = count_box_labels(cleaned_records)

    for record in cleaned_records:
        image_path = Path(record["image"])
        copy_image(input_dir / image_path, output_dir / image_path, args.copy_mode)
    for split_path in (input_dir / "splits").glob("*.txt"):
        shutil.copy2(split_path, output_dir / "splits" / split_path.name)

    write_jsonl(output_dir / "labels.jsonl", cleaned_records)
    write_audit(output_dir, before_counts, after_counts, stats, dropped)
    print(f"Wrote clean dataset to {output_dir}")
    print(f"Records: {len(cleaned_records)}")
    print(f"Text repaired: {stats['text_repaired']}")
    print(f"Empty text skipped: {stats['boxes_empty_text_skipped'] + stats['source_annotations_empty_text_skipped']}")
    print(f"Invalid geometry skipped: {stats['boxes_invalid_geometry_skipped'] + stats['source_annotations_invalid_geometry_skipped']}")
    print(f"Audit: {output_dir / 'reports' / 'clean_audit.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the canonical clean FinRecon receipt 4-field dataset.")
    parser.add_argument("--input-dir", default="archive/prepared/finrecon_receipt_4field")
    parser.add_argument("--output-dir", default="archive/prepared/finrecon_receipt_4field_clean")
    parser.add_argument("--copy-mode", choices=("copy", "hardlink", "none"), default="hardlink")
    parser.add_argument("--clear", action="store_true")
    clean_dataset(parser.parse_args())


if __name__ == "__main__":
    main()
