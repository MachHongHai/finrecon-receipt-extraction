from __future__ import annotations

import argparse
import ast
import csv
import json
import os
import random
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SOURCE_SEPARATOR = "|||"
FIELD_MAP = {
    "SELLER": "seller",
    "ADDRESS": "address",
    "TIMESTAMP": "timestamp",
    "TOTAL_COST": "total_cost",
    "TOTAL_TOTAL_COST": "total_cost",
}
TARGET_FIELDS = ("seller", "address", "timestamp", "total_cost")
DATE_RE = re.compile(
    r"(?P<day>\d{1,2})[\/\-.](?P<month>\d{1,2})[\/\-.](?P<year>\d{2,4})"
    r"|(?P<year2>\d{4})[\/\-.](?P<month2>\d{1,2})[\/\-.](?P<day2>\d{1,2})"
)
TIME_RE = re.compile(r"\b\d{1,2}\s*:\s*\d{2}(?:\s*:\s*\d{2})?\b")
AMOUNT_RE = re.compile(r"\d{1,3}(?:[.,\s]\d{3})+|\d{4,}")
TOTAL_KEYWORD_RE = re.compile(
    r"tong|tổng|thanh\s*toan|thanh\s*toán|phai\s*t\.?toan|phải\s*t\.?toán|"
    r"phai\s*tra|phải\s*trả|cong\s*tien|cộng\s*tiền",
    re.IGNORECASE,
)
ADDRESS_HINT_RE = re.compile(
    r"\b(dc|d/c|dia chi|địa chỉ|p\.|q\.|tp\.|tinh|tỉnh|quan|quận|phuong|phường|"
    r"duong|đường|so\s+\d|số\s+\d)\b",
    re.IGNORECASE,
)


def split_source_field(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(SOURCE_SEPARATOR)]


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def normalize_amount(value: str) -> int | None:
    text = clean_text(value)
    candidates: list[int] = []
    for match in AMOUNT_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if not digits:
            continue
        amount = int(digits)
        if amount >= 1_000:
            candidates.append(amount)
    if not candidates:
        return None
    return max(candidates)


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
        raw_year = match.group("year")
        year = int(raw_year)
        if year < 100:
            year += 2000
    if not (1 <= day <= 31 and 1 <= month <= 12 and 2000 <= year <= 2099):
        return None
    date_part = f"{year:04d}-{month:02d}-{day:02d}"
    time_match = TIME_RE.search(text)
    if time_match:
        time_part = re.sub(r"\s+", "", time_match.group(0))
        chunks = time_part.split(":")
        if len(chunks) == 2:
            time_part = f"{int(chunks[0]):02d}:{int(chunks[1]):02d}:00"
        elif len(chunks) == 3:
            time_part = f"{int(chunks[0]):02d}:{int(chunks[1]):02d}:{int(chunks[2]):02d}"
        return f"{date_part} {time_part}"
    return date_part


def parse_polygons(raw_value: str | None) -> list[dict[str, Any]]:
    if not raw_value:
        return []
    try:
        parsed = ast.literal_eval(raw_value)
    except (SyntaxError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def polygon_to_bbox(polygon: list[float]) -> list[float]:
    xs = polygon[0::2]
    ys = polygon[1::2]
    return [min(xs), min(ys), max(xs), max(ys)]


def flatten_polygon(raw_polygon: Any) -> list[float]:
    if not raw_polygon:
        return []
    if isinstance(raw_polygon, list) and raw_polygon and isinstance(raw_polygon[0], list):
        return [float(value) for value in raw_polygon[0]]
    if isinstance(raw_polygon, list):
        return [float(value) for value in raw_polygon]
    return []


def source_bbox_to_xyxy(raw_bbox: Any, polygon: list[float]) -> list[float]:
    if isinstance(raw_bbox, list) and len(raw_bbox) >= 4:
        x, y, width, height = [float(value) for value in raw_bbox[:4]]
        return [x, y, x + width, y + height]
    if len(polygon) >= 8:
        return polygon_to_bbox(polygon)
    return [0.0, 0.0, 0.0, 0.0]


def box_area(bbox: list[float]) -> float:
    if len(bbox) < 4:
        return 0.0
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def source_coverage(source_bbox: list[float], candidate_bbox: list[float]) -> float:
    if len(source_bbox) < 4 or len(candidate_bbox) < 4:
        return 0.0
    x1 = max(source_bbox[0], candidate_bbox[0])
    y1 = max(source_bbox[1], candidate_bbox[1])
    x2 = min(source_bbox[2], candidate_bbox[2])
    y2 = min(source_bbox[3], candidate_bbox[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return intersection / max(1.0, box_area(source_bbox))


def normalized_match_text(value: str | None) -> str:
    return re.sub(r"\W+", "", clean_text(value).casefold())


def parse_kie_line(line: str) -> dict[str, Any] | None:
    try:
        parts = next(csv.reader([line]))
    except csv.Error:
        parts = line.split(",")
    if len(parts) < 11:
        return None
    try:
        coords = [float(part) for part in parts[1:9]]
    except ValueError:
        return None
    label = clean_text(parts[-1]).upper()
    text = clean_text(",".join(parts[9:-1]))
    field = FIELD_MAP.get(label)
    return {
        "text": text,
        "label": label,
        "field": field,
        "polygon": coords,
        "bbox": polygon_to_bbox(coords),
    }


def load_kie_boxes(kie_dir: Path) -> dict[str, list[dict[str, Any]]]:
    boxes_by_id: dict[str, list[dict[str, Any]]] = {}
    if not kie_dir.exists():
        return boxes_by_id
    for path in kie_dir.glob("*.tsv"):
        boxes: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            parsed = parse_kie_line(line)
            if parsed is not None:
                boxes.append(parsed)
        boxes_by_id[path.stem] = boxes
    return boxes_by_id


def choose_seller(candidates: list[str]) -> str:
    cleaned = [clean_text(item) for item in candidates if clean_text(item)]
    if not cleaned:
        return ""
    return max(cleaned, key=lambda item: (len(re.findall(r"[A-Za-zÀ-ỹ]", item)), len(item)))


def choose_address(candidates: list[str]) -> str:
    unique: list[str] = []
    for item in candidates:
        text = clean_text(item)
        if text and text not in unique:
            unique.append(text)
    if not unique:
        return ""
    hinted = [item for item in unique if ADDRESS_HINT_RE.search(item)]
    chosen = hinted if hinted else unique
    return ", ".join(chosen[:3])


def choose_timestamp(candidates: list[str]) -> tuple[str, str | None]:
    valid: list[tuple[str, str]] = []
    fallback: list[str] = []
    for item in candidates:
        text = clean_text(item)
        if not text:
            continue
        normalized = normalize_timestamp(text)
        if normalized:
            valid.append((text, normalized))
        else:
            fallback.append(text)
    if valid:
        valid.sort(key=lambda pair: (len(pair[0]), bool(TIME_RE.search(pair[0]))), reverse=True)
        return valid[0]
    return (fallback[0], None) if fallback else ("", None)


def choose_total_cost(candidates: list[str]) -> tuple[str, int | None]:
    parsed: list[tuple[str, int, int]] = []
    fallback: list[str] = []
    for index, item in enumerate(candidates):
        text = clean_text(item)
        if not text:
            continue
        amount = normalize_amount(text)
        if amount is None:
            fallback.append(text)
            continue
        keyword_bonus = 1 if TOTAL_KEYWORD_RE.search(text) else 0
        parsed.append((text, amount, keyword_bonus * 10_000_000_000 + amount * 10 + index))
    if parsed:
        parsed.sort(key=lambda item: item[2], reverse=True)
        text, amount, _score = parsed[0]
        return text, amount
    return (fallback[0], None) if fallback else ("", None)


def parse_source_annotations(row: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    labels = split_source_field(row.get("anno_labels"))
    texts = split_source_field(row.get("anno_texts"))
    polygons = parse_polygons(row.get("anno_polygons"))
    source_candidates: dict[str, list[str]] = defaultdict(list)
    source_annotations: list[dict[str, Any]] = []
    for index, (label, text) in enumerate(zip(labels, texts)):
        normalized_label = clean_text(label).upper()
        if normalized_label == "TOTAL_TOTAL_COST":
            normalized_label = "TOTAL_COST"
        field = FIELD_MAP.get(normalized_label)
        text = clean_text(text)
        if field:
            source_candidates[field].append(text)
        polygon = []
        bbox = [0.0, 0.0, 0.0, 0.0]
        if index < len(polygons):
            polygon = flatten_polygon(polygons[index].get("segmentation"))
            bbox = source_bbox_to_xyxy(polygons[index].get("bbox"), polygon)
        annotation: dict[str, Any] = {
            "text": text,
            "label": normalized_label,
            "field": field,
            "polygon": polygon,
            "bbox": bbox,
            "source": "mcocr_train_df",
        }
        source_annotations.append(annotation)
    return source_annotations, source_candidates


def source_annotation_to_box(annotation: dict[str, Any]) -> dict[str, Any]:
    return {
        "text": annotation["text"],
        "label": annotation["label"],
        "field": annotation["field"],
        "polygon": annotation.get("polygon") or [],
        "bbox": annotation.get("bbox") or [0.0, 0.0, 0.0, 0.0],
        "source": "mcocr_train_df",
    }


def merge_kie_boxes_with_source(
    boxes: list[dict[str, Any]],
    source_annotations: list[dict[str, Any]],
    stats: Counter[str],
    overlap_threshold: float = 0.55,
) -> list[dict[str, Any]]:
    source_targets = [
        annotation
        for annotation in source_annotations
        if annotation.get("field") in TARGET_FIELDS and clean_text(annotation.get("text"))
    ]
    represented_source_indexes: set[int] = set()
    merged: list[dict[str, Any]] = []

    for box in boxes:
        text = clean_text(box.get("text"))
        label = clean_text(box.get("label")).upper()
        if label == "TOTAL_TOTAL_COST":
            label = "TOTAL_COST"
        box = {**box, "text": text, "label": label, "field": FIELD_MAP.get(label), "source": "boxes_and_transcripts"}

        if text:
            merged.append(box)
            for index, annotation in enumerate(source_targets):
                if index in represented_source_indexes or annotation["label"] != label:
                    continue
                same_text = normalized_match_text(annotation["text"]) == normalized_match_text(text)
                enough_overlap = source_coverage(annotation["bbox"], box["bbox"]) >= overlap_threshold
                if same_text or enough_overlap:
                    represented_source_indexes.add(index)
            continue

        stats[f"raw_empty_{label or 'UNKNOWN'}"] += 1
        if label not in FIELD_MAP:
            stats["raw_empty_other_or_unknown_ignored"] += 1
            continue

        best_index: int | None = None
        best_score = 0.0
        for index, annotation in enumerate(source_targets):
            if index in represented_source_indexes or annotation["label"] != label:
                continue
            score = source_coverage(annotation["bbox"], box["bbox"])
            if score > best_score:
                best_index = index
                best_score = score
        if best_index is not None and best_score >= overlap_threshold:
            annotation = source_targets[best_index]
            recovered = {**box, "text": annotation["text"], "source": "boxes_and_transcripts_recovered_from_csv"}
            merged.append(recovered)
            represented_source_indexes.add(best_index)
            stats[f"recovered_empty_{label}"] += 1
        else:
            stats[f"unrecovered_empty_{label}"] += 1

    for index, annotation in enumerate(source_targets):
        if index in represented_source_indexes:
            continue
        merged.append(source_annotation_to_box(annotation))
        stats[f"appended_source_{annotation['label']}"] += 1

    return merged


def build_record(row: dict[str, str], boxes: list[dict[str, Any]], image_path: Path, stats: Counter[str]) -> dict[str, Any]:
    source_annotations, source_candidates = parse_source_annotations(row)
    merged_boxes = merge_kie_boxes_with_source(boxes, source_annotations, stats)

    seller = choose_seller(source_candidates["seller"])
    address = choose_address(source_candidates["address"])
    timestamp, normalized_timestamp = choose_timestamp(source_candidates["timestamp"])
    total_cost, normalized_total_cost = choose_total_cost(source_candidates["total_cost"])
    fields = {
        "seller": seller,
        "address": address,
        "timestamp": timestamp,
        "total_cost": total_cost,
    }
    normalized = {
        "timestamp": normalized_timestamp,
        "total_cost": normalized_total_cost,
    }
    fields_present = [field for field in TARGET_FIELDS if fields.get(field)]
    return {
        "id": Path(row["img_id"]).stem,
        "image": f"images/{row['img_id']}",
        "source_image": str(image_path.as_posix()),
        "quality": float(row.get("anno_image_quality") or 0),
        "fields": fields,
        "field_candidates": {field: source_candidates.get(field, []) for field in TARGET_FIELDS},
        "normalized": normalized,
        "source_annotations": source_annotations,
        "boxes": merged_boxes,
        "coverage": {
            "fields_present": fields_present,
            "has_all_4_fields": len(fields_present) == 4,
            "has_normalized_timestamp": normalized_timestamp is not None,
            "has_normalized_total_cost": normalized_total_cost is not None,
        },
    }


def safe_copy_image(src: Path, dst: Path, mode: str) -> None:
    if mode == "none":
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    if mode == "hardlink":
        try:
            os.link(src, dst)
            return
        except OSError:
            pass
    shutil.copy2(src, dst)


def split_records(records: list[dict[str, Any]], seed: int) -> dict[str, list[str]]:
    rng = random.Random(seed)
    buckets: dict[str, list[str]] = defaultdict(list)
    for record in records:
        coverage_count = len(record["coverage"]["fields_present"])
        quality_band = "high" if record["quality"] >= 0.7 else "mid" if record["quality"] >= 0.5 else "low"
        buckets[f"{coverage_count}_{quality_band}"].append(record["id"])

    result = {"train": [], "val": [], "test": []}
    for ids in buckets.values():
        rng.shuffle(ids)
        total = len(ids)
        val_count = max(1, round(total * 0.10)) if total >= 10 else 0
        test_count = max(1, round(total * 0.10)) if total >= 10 else 0
        result["val"].extend(ids[:val_count])
        result["test"].extend(ids[val_count : val_count + test_count])
        result["train"].extend(ids[val_count + test_count :])

    for split_ids in result.values():
        split_ids.sort()
    return result


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_splits(output_dir: Path, splits: dict[str, list[str]]) -> None:
    split_dir = output_dir / "splits"
    split_dir.mkdir(parents=True, exist_ok=True)
    for split_name, ids in splits.items():
        (split_dir / f"{split_name}.txt").write_text(
            "\n".join(ids) + ("\n" if ids else ""),
            encoding="utf-8",
        )


def build_audit(
    records: list[dict[str, Any]],
    splits: dict[str, list[str]],
    missing_images: list[str],
    stats: Counter[str],
) -> str:
    field_presence = Counter()
    normalized_presence = Counter()
    quality_values = []
    box_labels = Counter()
    docs_with_box_label = Counter()
    for record in records:
        quality_values.append(record["quality"])
        for field in record["coverage"]["fields_present"]:
            field_presence[field] += 1
        if record["coverage"]["has_normalized_timestamp"]:
            normalized_presence["timestamp"] += 1
        if record["coverage"]["has_normalized_total_cost"]:
            normalized_presence["total_cost"] += 1
        labels_in_doc = set()
        for box in record["boxes"]:
            box_labels[box.get("label") or ""] += 1
            labels_in_doc.add(box.get("label") or "")
        docs_with_box_label.update(labels_in_doc)

    quality_avg = sum(quality_values) / len(quality_values) if quality_values else 0
    all_4 = sum(1 for record in records if record["coverage"]["has_all_4_fields"])
    lines = [
        "# FinRecon Receipt 4-Field Dataset Audit",
        "",
        "Generated dataset for receipt field extraction.",
        "",
        "## Summary",
        "",
        f"- Records: {len(records)}",
        f"- Missing source images skipped: {len(missing_images)}",
        f"- Records with all 4 fields: {all_4}",
        f"- Average image quality: {quality_avg:.3f}",
        "",
        "## Field Coverage",
        "",
    ]
    for field in TARGET_FIELDS:
        lines.append(f"- `{field}`: {field_presence[field]}")
    lines.extend(
        [
            f"- `timestamp` normalized: {normalized_presence['timestamp']}",
            f"- `total_cost` normalized: {normalized_presence['total_cost']}",
            "",
            "## Splits",
            "",
        ]
    )
    for split_name in ("train", "val", "test"):
        lines.append(f"- `{split_name}`: {len(splits[split_name])}")
    lines.extend(["", "## KIE Box Labels", ""])
    for label, count in box_labels.most_common():
        if label:
            lines.append(f"- `{label}`: {count} boxes, {docs_with_box_label[label]} docs")
    lines.extend(
        [
            "",
            "## Source Text Recovery",
            "",
            "- `boxes_and_transcripts` contains many blank transcript cells, including blank target-field boxes.",
            "- `mcocr_train_df.csv` is used as the authoritative source for target-field text.",
            "- Blank `OTHER` boxes are ignored.",
            "- Blank target boxes are filled from CSV when same-label bbox coverage is high enough.",
            "- CSV target annotations not represented by a usable KIE box are appended as target boxes.",
            "",
        ]
    )
    for key, count in stats.most_common():
        lines.append(f"- `{key}`: {count}")
    if missing_images:
        lines.extend(["", "## Missing Images", ""])
        lines.extend(f"- `{item}`" for item in missing_images[:100])
        if len(missing_images) > 100:
            lines.append(f"- ... and {len(missing_images) - 100} more")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Validation labels from `mcocr_val_sample_df.csv` are placeholders, so this dataset creates train/val/test from the labeled train CSV.",
            "- `total_cost` is normalized by selecting a valid money-like value from `TOTAL_COST` labels.",
            "- `timestamp` is normalized only when a date-like pattern is present.",
        ]
    )
    return "\n".join(lines) + "\n"


def prepare_dataset(args: argparse.Namespace) -> None:
    archive_dir = Path(args.archive_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    train_csv = archive_dir / "mcocr_train_df.csv"
    image_dir = archive_dir / "train_images" / "train_images"
    kie_dir = archive_dir / "kie_data" / "kie_data" / "boxes_and_transcripts"

    if not train_csv.exists():
        raise FileNotFoundError(f"Missing train CSV: {train_csv}")
    if not image_dir.exists():
        raise FileNotFoundError(f"Missing train image directory: {image_dir}")
    if args.clear and output_dir.exists():
        shutil.rmtree(output_dir)

    (output_dir / "images").mkdir(parents=True, exist_ok=True)
    (output_dir / "reports").mkdir(parents=True, exist_ok=True)
    boxes_by_id = load_kie_boxes(kie_dir)
    stats: Counter[str] = Counter()

    with train_csv.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    records: list[dict[str, Any]] = []
    missing_images: list[str] = []
    for row in rows:
        image_name = row["img_id"]
        source_image = image_dir / image_name
        if not source_image.exists():
            missing_images.append(image_name)
            continue
        safe_copy_image(source_image, output_dir / "images" / image_name, args.copy_mode)
        record = build_record(
            row=row,
            boxes=boxes_by_id.get(Path(image_name).stem, []),
            image_path=source_image.relative_to(archive_dir),
            stats=stats,
        )
        records.append(record)

    splits = split_records(records, args.seed)
    write_jsonl(output_dir / "labels.jsonl", records)
    write_splits(output_dir, splits)
    audit = build_audit(records, splits, missing_images, stats)
    (output_dir / "reports" / "dataset_audit.md").write_text(audit, encoding="utf-8", newline="\n")

    print(f"Prepared {len(records)} records at {output_dir}")
    print(f"Splits: train={len(splits['train'])}, val={len(splits['val'])}, test={len(splits['test'])}")
    print("Source text recovery:")
    for key, count in stats.most_common():
        print(f"  {key}: {count}")
    print(f"Audit: {output_dir / 'reports' / 'dataset_audit.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare FinRecon receipt 4-field dataset from MCOCR archive.")
    parser.add_argument("--archive-dir", default="archive/source_mcocr", help="Path to original MCOCR archive directory.")
    parser.add_argument(
        "--output-dir",
        default="archive/prepared/finrecon_receipt_4field",
        help="Output dataset directory.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for split generation.")
    parser.add_argument(
        "--copy-mode",
        choices=("copy", "hardlink", "none"),
        default="copy",
        help="How to populate output images directory.",
    )
    parser.add_argument("--clear", action="store_true", help="Clear the output directory before generation.")
    prepare_dataset(parser.parse_args())


if __name__ == "__main__":
    main()
