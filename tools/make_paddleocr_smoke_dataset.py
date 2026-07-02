from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from export_paddleocr_ser_dataset import write_config


def read_lines(path: Path, limit: int) -> list[str]:
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def collect_image_names(lines: list[str]) -> set[str]:
    names: set[str] = set()
    for line in lines:
        image_name, payload = line.split("\t", 1)
        json.loads(payload)
        names.add(image_name)
    return names


def link_or_copy(src: Path, dst: Path, mode: str) -> None:
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if mode == "hardlink":
        try:
            os.link(src, dst)
            return
        except OSError:
            pass
    shutil.copy2(src, dst)


def write_split(source_dir: Path, output_dir: Path, split_name: str, limit: int) -> dict[str, int]:
    lines = read_lines(source_dir / f"{split_name}.json", limit)
    (output_dir / f"{split_name}.json").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    annotation_count = 0
    for line in lines:
        _, payload = line.split("\t", 1)
        annotation_count += len(json.loads(payload))
    return {"documents": len(lines), "annotations": annotation_count}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a tiny PaddleOCR SER smoke dataset.")
    parser.add_argument("--source-dir", default="archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser")
    parser.add_argument("--output-dir", default="archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser_smoke")
    parser.add_argument("--train-docs", type=int, default=4)
    parser.add_argument("--val-docs", type=int, default=2)
    parser.add_argument("--test-docs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--copy-mode", choices=("copy", "hardlink"), default="hardlink")
    args = parser.parse_args()

    source_dir = Path(args.source_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    if args.clear and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "images").mkdir(parents=True, exist_ok=True)
    (output_dir / "reports").mkdir(parents=True, exist_ok=True)

    shutil.copy2(source_dir / "class_list.txt", output_dir / "class_list.txt")
    stats = {
        "train": write_split(source_dir, output_dir, "train", args.train_docs),
        "val": write_split(source_dir, output_dir, "val", args.val_docs),
        "test": write_split(source_dir, output_dir, "test", args.test_docs),
    }

    image_names: set[str] = set()
    for split_name in ("train", "val", "test"):
        image_names.update(collect_image_names((output_dir / f"{split_name}.json").read_text(encoding="utf-8").splitlines()))

    missing_images: list[str] = []
    for image_name in sorted(image_names):
        src = source_dir / "images" / image_name
        if not src.exists():
            missing_images.append(image_name)
            continue
        link_or_copy(src, output_dir / "images" / image_name, args.copy_mode)

    write_config(
        output_dir=output_dir,
        epoch_num=1,
        eval_step=1,
        batch_size=args.batch_size,
        learning_rate=2e-5,
        warmup_epoch=0,
        clip_norm_global=1.0,
        print_batch_step=1,
    )
    report = {
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "stats": stats,
        "images": len(image_names),
        "missing_images": missing_images,
    }
    report_path = output_dir / "reports" / "smoke_dataset_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if missing_images else 0


if __name__ == "__main__":
    raise SystemExit(main())
