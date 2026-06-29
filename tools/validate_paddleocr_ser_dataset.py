from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED_LABELS = {"OTHER", "SELLER", "ADDRESS", "TIMESTAMP", "TOTAL_COST"}


def is_paddle_points(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(point, list) and len(point) == 2 for point in value)
        and all(isinstance(coord, (int, float)) for point in value for coord in point)
    )


def validate_split(root: Path, split: str) -> dict[str, object]:
    rows = 0
    annotations = 0
    missing_images = 0
    bad_labels = 0
    bad_points = 0
    labels: dict[str, int] = {}
    split_path = root / f"{split}.json"

    if not split_path.exists():
        return {
            "rows": 0,
            "annotations": 0,
            "missing_images": 0,
            "bad_labels": 0,
            "bad_points": 0,
            "labels": {},
            "error": f"Missing split file: {split_path}",
        }

    for line in split_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows += 1
        image_name, payload = line.split("\t", 1)
        data = json.loads(payload)

        if not (root / "images" / image_name).exists():
            missing_images += 1

        for item in data:
            annotations += 1
            label = item.get("label")
            labels[str(label)] = labels.get(str(label), 0) + 1
            if label not in EXPECTED_LABELS:
                bad_labels += 1
            if not is_paddle_points(item.get("points")):
                bad_points += 1

    return {
        "rows": rows,
        "annotations": annotations,
        "missing_images": missing_images,
        "bad_labels": bad_labels,
        "bad_points": bad_points,
        "labels": labels,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a PaddleOCR SER export dataset.")
    parser.add_argument(
        "dataset_dir",
        type=Path,
        help="Path to the PaddleOCR SER directory containing train/val/test json files.",
    )
    args = parser.parse_args()

    root = args.dataset_dir.resolve()
    report = {split: validate_split(root, split) for split in ["train", "val", "test"]}
    print(json.dumps(report, ensure_ascii=False, indent=2))

    has_errors = any(
        split_report.get("missing_images", 0)
        or split_report.get("bad_labels", 0)
        or split_report.get("bad_points", 0)
        or split_report.get("error")
        for split_report in report.values()
    )
    if has_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
