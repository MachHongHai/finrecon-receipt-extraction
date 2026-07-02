from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


LABELS = ("OTHER", "SELLER", "ADDRESS", "TIMESTAMP", "TOTAL_COST")
LABEL_TO_ID = {label: index for index, label in enumerate(LABELS)}
ID_TO_LABEL = {index: label for label, index in LABEL_TO_ID.items()}
FIELD_BY_LABEL = {
    "SELLER": "seller",
    "ADDRESS": "address",
    "TIMESTAMP": "timestamp",
    "TOTAL_COST": "total_cost",
}


def load_image_size(path: Path, boxes: list[dict[str, Any]]) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:
        max_x = 1.0
        max_y = 1.0
        for box in boxes:
            bbox = box.get("bbox") or []
            if len(bbox) >= 4:
                max_x = max(max_x, float(bbox[2]))
                max_y = max(max_y, float(bbox[3]))
        return int(max_x), int(max_y)


def normalize_bbox(bbox: list[float], width: int, height: int) -> list[int]:
    if len(bbox) < 4:
        return [0, 0, 0, 0]
    width = max(1, width)
    height = max(1, height)
    x1, y1, x2, y2 = [float(value) for value in bbox[:4]]
    values = [
        round(max(0, min(1000, x1 / width * 1000))),
        round(max(0, min(1000, y1 / height * 1000))),
        round(max(0, min(1000, x2 / width * 1000))),
        round(max(0, min(1000, y2 / height * 1000))),
    ]
    return [int(value) for value in values]


def load_records(dataset_dir: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with (dataset_dir / "labels.jsonl").open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            record = json.loads(line)
            records[record["id"]] = record
    return records


def load_split_ids(dataset_dir: Path, split_name: str) -> list[str]:
    path = dataset_dir / "splits" / f"{split_name}.txt"
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def token_sort_key(token: dict[str, Any]) -> tuple[int, int]:
    bbox = token.get("bbox") or [0, 0, 0, 0]
    return int(bbox[1]), int(bbox[0])


def convert_record(record: dict[str, Any], dataset_dir: Path, keep_empty_text: bool) -> tuple[dict[str, Any], Counter]:
    stats = Counter()
    source_boxes = record.get("boxes") or []
    image_path = dataset_dir / record["image"]
    width, height = load_image_size(image_path, source_boxes)
    tokens: list[dict[str, Any]] = []

    for index, source_box in enumerate(source_boxes):
        text = (source_box.get("text") or "").strip()
        if not text and not keep_empty_text:
            stats["empty_text_skipped"] += 1
            continue
        raw_label = (source_box.get("label") or "OTHER").strip().upper()
        label = raw_label if raw_label in LABEL_TO_ID else "OTHER"
        if raw_label != label:
            stats["unknown_label_mapped_to_other"] += 1
        bbox = source_box.get("bbox") or [0, 0, 0, 0]
        tokens.append(
            {
                "id": f"{record['id']}_{index}",
                "text": text,
                "bbox": bbox,
                "bbox_1000": normalize_bbox(bbox, width, height),
                "polygon": source_box.get("polygon") or [],
                "label": label,
                "label_id": LABEL_TO_ID[label],
                "field": FIELD_BY_LABEL.get(label),
            }
        )

    tokens.sort(key=token_sort_key)
    stats["tokens"] += len(tokens)
    stats["documents"] += 1
    return (
        {
            "id": record["id"],
            "image": record["image"],
            "source_image": record.get("source_image"),
            "width": width,
            "height": height,
            "quality": record.get("quality"),
            "target_fields": record.get("fields") or {},
            "normalized_targets": record.get("normalized") or {},
            "tokens": tokens,
        },
        stats,
    )


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_flat_csv(path: Path, split_records: dict[str, list[dict[str, Any]]]) -> None:
    fields = [
        "split",
        "document_id",
        "token_id",
        "text",
        "label",
        "label_id",
        "field",
        "x1",
        "y1",
        "x2",
        "y2",
        "nx1",
        "ny1",
        "nx2",
        "ny2",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for split_name, records in split_records.items():
            for record in records:
                for token in record["tokens"]:
                    bbox = token["bbox"]
                    normalized = token["bbox_1000"]
                    writer.writerow(
                        {
                            "split": split_name,
                            "document_id": record["id"],
                            "token_id": token["id"],
                            "text": token["text"],
                            "label": token["label"],
                            "label_id": token["label_id"],
                            "field": token["field"] or "",
                            "x1": bbox[0],
                            "y1": bbox[1],
                            "x2": bbox[2],
                            "y2": bbox[3],
                            "nx1": normalized[0],
                            "ny1": normalized[1],
                            "nx2": normalized[2],
                            "ny2": normalized[3],
                        }
                    )


def summarize(split_records: dict[str, list[dict[str, Any]]], global_stats: Counter) -> str:
    lines = [
        "# Receipt Token Classification Dataset",
        "",
        "Generated from `labels.jsonl` for document token classification.",
        "",
        "Labels:",
        "",
    ]
    for label, label_id in LABEL_TO_ID.items():
        lines.append(f"- `{label}`: {label_id}")
    lines.extend(["", "## Split Summary", ""])
    total_label_counter = Counter()
    for split_name, records in split_records.items():
        label_counter = Counter()
        token_count = 0
        docs_with_label: dict[str, set[str]] = defaultdict(set)
        for record in records:
            token_count += len(record["tokens"])
            for token in record["tokens"]:
                label_counter[token["label"]] += 1
                total_label_counter[token["label"]] += 1
                docs_with_label[token["label"]].add(record["id"])
        lines.append(f"### `{split_name}`")
        lines.append("")
        lines.append(f"- Documents: {len(records)}")
        lines.append(f"- Tokens: {token_count}")
        for label in LABELS:
            lines.append(f"- `{label}`: {label_counter[label]} tokens, {len(docs_with_label[label])} docs")
        lines.append("")

    lines.extend(["## Total Label Distribution", ""])
    total_tokens = sum(total_label_counter.values()) or 1
    for label in LABELS:
        count = total_label_counter[label]
        lines.append(f"- `{label}`: {count} ({count / total_tokens:.2%})")
    lines.extend(
        [
            "",
            "## Cleaning",
            "",
            f"- Empty text boxes skipped: {global_stats['empty_text_skipped']}",
            f"- Unknown labels mapped to `OTHER`: {global_stats['unknown_label_mapped_to_other']}",
            "",
            "## Files",
            "",
            "- `train.jsonl`, `val.jsonl`, `test.jsonl`: document-level token data.",
            "- `tokens.csv`: flat token table for quick inspection/debugging.",
            "- `label_map.json`: label/id mapping.",
        ]
    )
    return "\n".join(lines) + "\n"


def build(args: argparse.Namespace) -> None:
    dataset_dir = Path(args.dataset_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    records_by_id = load_records(dataset_dir)
    split_records: dict[str, list[dict[str, Any]]] = {}
    global_stats = Counter()

    for split_name in ("train", "val", "test"):
        converted_records: list[dict[str, Any]] = []
        for record_id in load_split_ids(dataset_dir, split_name):
            record = records_by_id.get(record_id)
            if not record:
                global_stats["missing_split_record"] += 1
                continue
            converted, stats = convert_record(record, dataset_dir, args.keep_empty_text)
            global_stats.update(stats)
            converted_records.append(converted)
        split_records[split_name] = converted_records
        write_jsonl(output_dir / f"{split_name}.jsonl", converted_records)

    write_flat_csv(output_dir / "tokens.csv", split_records)
    (output_dir / "label_map.json").write_text(
        json.dumps({"label_to_id": LABEL_TO_ID, "id_to_label": ID_TO_LABEL}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "token_dataset_report.md").write_text(
        summarize(split_records, global_stats),
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote token classification dataset to {output_dir}")
    for split_name, records in split_records.items():
        print(split_name, "documents=", len(records), "tokens=", sum(len(record["tokens"]) for record in records))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build token classification data from prepared receipt labels.")
    parser.add_argument(
        "--dataset-dir",
        default="archive/prepared/finrecon_receipt_4field_clean",
        help="Prepared 4-field dataset directory.",
    )
    parser.add_argument(
        "--output-dir",
        default="archive/prepared/finrecon_receipt_4field_clean/token_classification",
        help="Output token classification directory.",
    )
    parser.add_argument("--keep-empty-text", action="store_true", help="Keep OCR boxes with empty transcript text.")
    build(parser.parse_args())


if __name__ == "__main__":
    main()
