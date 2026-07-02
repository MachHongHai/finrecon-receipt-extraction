from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


EXPECTED_LABELS = ("OTHER", "SELLER", "ADDRESS", "TIMESTAMP", "TOTAL_COST")
MOJIBAKE_HINT_RE = re.compile(r"(?:Ã.|Ä.|Æ.|á»|áº|Â.|€|™|œ)")


def load_class_list(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def valid_points(points: Any) -> bool:
    if not (isinstance(points, list) and len(points) == 4):
        return False
    for point in points:
        if not (isinstance(point, list) and len(point) == 2):
            return False
        if not all(isinstance(value, (int, float)) for value in point):
            return False
    return True


def validate_split(dataset_dir: Path, split_name: str, labels: set[str]) -> tuple[dict[str, Any], list[str]]:
    label_path = dataset_dir / f"{split_name}.json"
    image_dir = dataset_dir / "images"
    errors: list[str] = []
    counts: Counter[str] = Counter()
    docs = 0
    annotations = 0
    max_annotations = 0
    mojibake_examples: list[str] = []

    if not label_path.exists():
        return {"documents": 0, "annotations": 0, "label_counts": {}}, [f"missing {label_path}"]

    for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            image_name, payload = line.split("\t", 1)
            items = json.loads(payload)
        except Exception as exc:
            errors.append(f"{split_name}:{line_number}: invalid PaddleOCR SER line: {exc}")
            continue

        docs += 1
        image_path = image_dir / image_name
        if not image_path.exists():
            errors.append(f"{split_name}:{line_number}: missing image {image_name}")

        if not isinstance(items, list) or not items:
            errors.append(f"{split_name}:{line_number}: empty annotations")
            continue

        annotations += len(items)
        max_annotations = max(max_annotations, len(items))
        if len(items) > 512:
            errors.append(f"{split_name}:{line_number}: {len(items)} annotations exceeds max_seq_len 512")

        for index, item in enumerate(items):
            label = str(item.get("label") or "OTHER")
            text = str(item.get("transcription") or "")
            counts[label] += 1
            if label not in labels:
                errors.append(f"{split_name}:{line_number}:{index}: unknown label {label}")
            if not text.strip():
                errors.append(f"{split_name}:{line_number}:{index}: empty transcription")
            if not valid_points(item.get("points")):
                errors.append(f"{split_name}:{line_number}:{index}: invalid points")
            if MOJIBAKE_HINT_RE.search(text) and len(mojibake_examples) < 20:
                mojibake_examples.append(text)

    stats = {
        "documents": docs,
        "annotations": annotations,
        "max_annotations_per_doc": max_annotations,
        "label_counts": dict(counts),
        "mojibake_examples": mojibake_examples,
    }
    return stats, errors


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Validate a PaddleOCR SER dataset before training.")
    parser.add_argument("--dataset-dir", default="archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser")
    parser.add_argument("--strict-mojibake", action="store_true")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir).resolve()
    class_list_path = dataset_dir / "class_list.txt"
    if not class_list_path.exists():
        print(f"ERROR: missing class_list.txt in {dataset_dir}", file=sys.stderr)
        return 1

    class_list = load_class_list(class_list_path)
    errors: list[str] = []
    if class_list != list(EXPECTED_LABELS):
        errors.append(f"class_list mismatch: expected {list(EXPECTED_LABELS)}, got {class_list}")

    report: dict[str, Any] = {"dataset_dir": str(dataset_dir), "class_list": class_list, "splits": {}}
    labels = set(class_list)
    for split_name in ("train", "val", "test"):
        stats, split_errors = validate_split(dataset_dir, split_name, labels)
        report["splits"][split_name] = stats
        errors.extend(split_errors)
        if args.strict_mojibake and stats.get("mojibake_examples"):
            errors.append(f"{split_name}: suspect mojibake examples found")

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        print("\nValidation errors:", file=sys.stderr)
        for error in errors[:100]:
            print(f"- {error}", file=sys.stderr)
        if len(errors) > 100:
            print(f"- ... and {len(errors) - 100} more", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
