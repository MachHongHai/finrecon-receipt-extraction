from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def read_label_file(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        if "\t" not in line:
            raise ValueError(f"Invalid row without tab at {path}:{line_number}")
        image_path, text = line.split("\t", 1)
        rows.append((image_path.strip(), text.strip()))
    return rows


def validate_split(dataset_dir: Path, split_name: str, dictionary: set[str], use_space_char: bool) -> tuple[dict[str, Any], list[str]]:
    label_file = dataset_dir / f"{split_name}.txt"
    errors: list[str] = []
    if not label_file.exists():
        return {"rows": 0, "missing_images": 0, "empty_text": 0, "unknown_chars": 0}, [f"missing label file: {label_file}"]

    rows = read_label_file(label_file)
    missing_images = 0
    empty_text = 0
    unknown_chars: Counter[str] = Counter()
    lengths: list[int] = []

    for index, (relative_image_path, text) in enumerate(rows, start=1):
        image_path = dataset_dir / relative_image_path
        if not image_path.exists():
            missing_images += 1
            if len(errors) < 100:
                errors.append(f"{split_name}:{index} missing image: {relative_image_path}")
        if not text:
            empty_text += 1
            if len(errors) < 100:
                errors.append(f"{split_name}:{index} empty text")
            continue
        lengths.append(len(text))
        for char in text:
            if char == " " and use_space_char:
                continue
            if char not in dictionary:
                unknown_chars[char] += 1

    if unknown_chars:
        examples = ", ".join(f"{repr(char)}={count}" for char, count in unknown_chars.most_common(20))
        errors.append(f"{split_name} unknown chars not in dictionary: {examples}")

    return (
        {
            "rows": len(rows),
            "missing_images": missing_images,
            "empty_text": empty_text,
            "unknown_chars": sum(unknown_chars.values()),
            "text_length": {
                "min": min(lengths) if lengths else 0,
                "max": max(lengths) if lengths else 0,
                "avg": sum(lengths) / len(lengths) if lengths else 0,
            },
        },
        errors,
    )


def main() -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Validate a PaddleOCR text recognition dataset export.")
    parser.add_argument("--dataset-dir", default="archive/prepared/mcocr2021_text_recognition_paddleocr")
    parser.add_argument("--dict-path", default="")
    parser.add_argument("--no-space-char", action="store_true")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir).resolve()
    dict_path = Path(args.dict_path).resolve() if args.dict_path else dataset_dir / "dict" / "mcocr2021_vi_receipt_dict.txt"
    if not dataset_dir.exists():
        print(f"ERROR: missing dataset dir: {dataset_dir}", file=sys.stderr)
        return 1
    if not dict_path.exists():
        print(f"ERROR: missing dictionary file: {dict_path}", file=sys.stderr)
        return 1

    dictionary = set(dict_path.read_text(encoding="utf-8").splitlines())
    report: dict[str, Any] = {
        "dataset_dir": str(dataset_dir),
        "dict_path": str(dict_path),
        "dict_characters": len(dictionary),
        "splits": {},
    }
    errors: list[str] = []
    for split_name in ("train", "val"):
        split_report, split_errors = validate_split(dataset_dir, split_name, dictionary, use_space_char=not args.no_space_char)
        report["splits"][split_name] = split_report
        errors.extend(split_errors)

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
