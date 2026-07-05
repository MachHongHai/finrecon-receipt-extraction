from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def polygon_area(points: list[list[float]]) -> float:
    area = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        area += point[0] * next_point[1] - next_point[0] * point[1]
    return abs(area) / 2.0


def valid_points(value: Any) -> bool:
    if not (isinstance(value, list) and len(value) >= 4):
        return False
    for point in value:
        if not (isinstance(point, list) and len(point) == 2):
            return False
        if not all(isinstance(coord, (int, float)) for coord in point):
            return False
    return polygon_area(value) >= 1


def validate_split(dataset_dir: Path, split_name: str) -> tuple[dict[str, Any], list[str]]:
    label_path = dataset_dir / f"{split_name}.txt"
    stats = {
        "documents": 0,
        "annotations": 0,
        "missing_images": 0,
        "invalid_json": 0,
        "invalid_points": 0,
        "empty_annotations": 0,
    }
    errors: list[str] = []
    if not label_path.exists():
        errors.append(f"missing label file: {label_path}")
        return stats, errors

    for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        stats["documents"] += 1
        try:
            image_name, payload = line.split("\t", 1)
        except ValueError:
            errors.append(f"{split_name}:{line_number}: expected image_path<TAB>json_annotations")
            continue

        image_path = dataset_dir / image_name
        if not image_path.exists():
            stats["missing_images"] += 1
            errors.append(f"{split_name}:{line_number}: missing image {image_name}")

        try:
            annotations = json.loads(payload)
        except json.JSONDecodeError as exc:
            stats["invalid_json"] += 1
            errors.append(f"{split_name}:{line_number}: invalid json: {exc}")
            continue

        if not annotations:
            stats["empty_annotations"] += 1
            errors.append(f"{split_name}:{line_number}: empty annotations")
            continue

        for index, annotation in enumerate(annotations):
            stats["annotations"] += 1
            if not valid_points(annotation.get("points")):
                stats["invalid_points"] += 1
                if len(errors) < 50:
                    errors.append(f"{split_name}:{line_number}:{index}: invalid points")
            text = annotation.get("transcription")
            if text in ("", None, "###", "*"):
                if len(errors) < 50:
                    errors.append(f"{split_name}:{line_number}:{index}: ignored/empty transcription is not suitable for detector training")

    return stats, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate PaddleOCR text detection dataset exported from MC-OCR.")
    parser.add_argument("--dataset-dir", default="archive/prepared/mcocr2021_text_detection_paddleocr")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir).resolve()
    report = {"dataset_dir": str(dataset_dir), "splits": {}, "errors": []}
    all_errors: list[str] = []
    for split_name in ("train", "val", "test"):
        stats, errors = validate_split(dataset_dir, split_name)
        report["splits"][split_name] = stats
        all_errors.extend(errors)
    report["errors"] = all_errors[:200]

    report_path = Path(args.report) if args.report else dataset_dir / "reports" / "det_validation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if all_errors:
        print(f"ERROR: {len(all_errors)} validation issue(s). See {report_path}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
