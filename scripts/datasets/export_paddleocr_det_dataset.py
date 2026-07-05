from __future__ import annotations

import argparse
import json
import os
import random
import shutil
from pathlib import Path
from typing import Any


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_SOURCE_DIR = Path("archive/source_mcocr")
DEFAULT_OUTPUT_DIR = Path("archive/prepared/mcocr2021_text_detection_paddleocr")
DEFAULT_PRETRAINED_MODEL = Path("archive/models/paddleocr/MobileNetV3_large_x0_5_pretrained.pdparams")


def parse_polygon_line(line: str) -> list[list[float]] | None:
    parts = [part.strip() for part in line.strip().split(",")]
    if len(parts) < 8:
        return None
    try:
        coords = [float(value) for value in parts[:8]]
    except ValueError:
        return None
    points = [[coords[index], coords[index + 1]] for index in range(0, 8, 2)]
    if polygon_area(points) < 1:
        return None
    return points


def polygon_area(points: list[list[float]]) -> float:
    area = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        area += point[0] * next_point[1] - next_point[0] * point[1]
    return abs(area) / 2.0


def find_image(image_dirs: list[Path], stem: str) -> Path | None:
    for image_dir in image_dirs:
        for suffix in IMAGE_SUFFIXES:
            candidate = image_dir / f"{stem}{suffix}"
            if candidate.exists():
                return candidate
    return None


def ensure_link_or_copy(source: Path, target: Path, mode: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return
    if mode == "copy":
        shutil.copy2(source, target)
        return
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def write_label_file(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            annotations = [
                {"transcription": item.get("text") or "text", "points": item["points"]}
                for item in record["annotations"]
            ]
            file.write(f"{record['image_path']}\t{json.dumps(annotations, ensure_ascii=False)}\n")


def yaml_path(path: Path) -> str:
    return path.as_posix()


def write_config(
    output_dir: Path,
    *,
    epoch_num: int,
    batch_size: int,
    eval_step: int,
    learning_rate: float,
    pretrained_model: Path,
) -> None:
    config_path = output_dir / "det_mv3_db_mcocr2021.yml"
    save_dir = output_dir / "output" / "det_mv3_db_mcocr2021"
    pretrained_value = yaml_path(pretrained_model)
    config = f"""Global:
  use_gpu: true
  use_xpu: false
  use_mlu: false
  epoch_num: {epoch_num}
  log_smooth_window: 20
  print_batch_step: 10
  save_model_dir: {yaml_path(save_dir)}
  save_epoch_step: {epoch_num}
  eval_batch_step: [0, {eval_step}]
  cal_metric_during_train: false
  pretrained_model: {pretrained_value}
  checkpoints:
  save_inference_dir:
  use_visualdl: false
  infer_img:
  save_res_path: {yaml_path(output_dir / "output" / "det_results.txt")}
  save_optimizer_state: true
  save_latest_model: true
  save_epoch_checkpoints: false

Architecture:
  model_type: det
  algorithm: DB
  Transform:
  Backbone:
    name: MobileNetV3
    scale: 0.5
    model_name: large
  Neck:
    name: DBFPN
    out_channels: 256
  Head:
    name: DBHead
    k: 50

Loss:
  name: DBLoss
  balance_loss: true
  main_loss_type: DiceLoss
  alpha: 5
  beta: 10
  ohem_ratio: 3

Optimizer:
  name: Adam
  beta1: 0.9
  beta2: 0.999
  lr:
    learning_rate: {learning_rate}
  regularizer:
    name: L2
    factor: 0

PostProcess:
  name: DBPostProcess
  thresh: 0.3
  box_thresh: 0.6
  max_candidates: 1000
  unclip_ratio: 1.5

Metric:
  name: DetMetric
  main_indicator: hmean

Train:
  dataset:
    name: SimpleDataSet
    data_dir: {yaml_path(output_dir)}
    label_file_list:
      - {yaml_path(output_dir / "train.txt")}
    ratio_list: [1.0]
    transforms:
      - DecodeImage:
          img_mode: BGR
          channel_first: false
      - DetLabelEncode:
      - IaaAugment:
          augmenter_args:
            - {{type: Fliplr, args: {{p: 0.5}}}}
            - {{type: Affine, args: {{rotate: [-10, 10]}}}}
            - {{type: Resize, args: {{size: [0.5, 3]}}}}
      - EastRandomCropData:
          size: [640, 640]
          max_tries: 50
          keep_ratio: true
      - MakeBorderMap:
          shrink_ratio: 0.4
          thresh_min: 0.3
          thresh_max: 0.7
      - MakeShrinkMap:
          shrink_ratio: 0.4
          min_text_size: 8
      - NormalizeImage:
          scale: 1./255.
          mean: [0.485, 0.456, 0.406]
          std: [0.229, 0.224, 0.225]
          order: hwc
      - ToCHWImage:
      - KeepKeys:
          keep_keys: ['image', 'threshold_map', 'threshold_mask', 'shrink_map', 'shrink_mask']
  loader:
    shuffle: true
    drop_last: false
    batch_size_per_card: {batch_size}
    num_workers: 0
    use_shared_memory: false

Eval:
  dataset:
    name: SimpleDataSet
    data_dir: {yaml_path(output_dir)}
    label_file_list:
      - {yaml_path(output_dir / "val.txt")}
    transforms:
      - DecodeImage:
          img_mode: BGR
          channel_first: false
      - DetLabelEncode:
      - DetResizeForTest:
          image_shape: [736, 1280]
      - NormalizeImage:
          scale: 1./255.
          mean: [0.485, 0.456, 0.406]
          std: [0.229, 0.224, 0.225]
          order: hwc
      - ToCHWImage:
      - KeepKeys:
          keep_keys: ['image', 'shape', 'polys', 'ignore_tags']
  loader:
    shuffle: false
    drop_last: false
    batch_size_per_card: 1
    num_workers: 0
    use_shared_memory: false
"""
    config_path.write_text(config, encoding="utf-8", newline="\n")


def write_readme(output_dir: Path, report: dict[str, Any]) -> None:
    lines = [
        "# MC-OCR 2021 PaddleOCR Detection Export",
        "",
        "This dataset is generated from `archive/source_mcocr/text_detector/text_detector/txt`.",
        "Raw MC-OCR files are not modified.",
        "",
        "## Summary",
        "",
        f"- Documents: {report['documents']}",
        f"- Annotations: {report['annotations']}",
        f"- Train/Val/Test: {report['splits']['train']} / {report['splits']['val']} / {report['splits']['test']}",
        f"- Missing images skipped: {report['missing_images']}",
        f"- Invalid polygons skipped: {report['invalid_polygons']}",
        "",
        "## Commands",
        "",
        "Download detection pretrained weights:",
        "",
        "```powershell",
        ".\\scripts\\training\\paddleocr_detection\\download_det_pretrained.ps1",
        "```",
        "",
        "Validate:",
        "",
        "```powershell",
        "python scripts\\datasets\\validate_paddleocr_det_dataset.py --dataset-dir archive\\prepared\\mcocr2021_text_detection_paddleocr",
        "```",
        "",
        "Train with resumable latest checkpoint:",
        "",
        "```powershell",
        ".\\scripts\\training\\paddleocr_detection\\train_gpu.ps1",
        "```",
    ]
    (output_dir / "README_TRAINING.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def export(args: argparse.Namespace) -> None:
    source_dir = Path(args.source_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    if args.clear and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    txt_dir = source_dir / "text_detector" / "text_detector" / "txt"
    if not txt_dir.exists():
        txt_dir = source_dir / "dataset" / "text_detector" / "txt"
    image_dirs = [
        source_dir / "train_images" / "train_images",
        source_dir / "kie_data" / "kie_data" / "images",
    ]
    if not txt_dir.exists():
        raise FileNotFoundError(f"Missing MC-OCR detection txt dir: {txt_dir}")

    records: list[dict[str, Any]] = []
    missing_images = 0
    invalid_polygons = 0
    for txt_path in sorted(txt_dir.glob("*.txt")):
        image_path = find_image(image_dirs, txt_path.stem)
        if not image_path:
            missing_images += 1
            continue
        annotations = []
        for line in txt_path.read_text(encoding="utf-8", errors="replace").splitlines():
            points = parse_polygon_line(line)
            if points is None:
                invalid_polygons += 1
                continue
            annotations.append({"text": "text", "points": points})
        if not annotations:
            continue
        target_image = output_dir / "images" / image_path.name
        ensure_link_or_copy(image_path, target_image, args.copy_mode)
        records.append({"image_path": f"images/{image_path.name}", "annotations": annotations})

    rng = random.Random(args.seed)
    rng.shuffle(records)
    if args.max_images and args.max_images > 0:
        records = records[: args.max_images]

    total = len(records)
    val_count = max(1, round(total * args.val_ratio)) if total >= 10 else max(1, total // 5)
    test_count = max(1, round(total * args.test_ratio)) if total >= 10 else max(1, total // 5)
    if args.max_images and total >= 15:
        val_count = max(3, val_count)
        test_count = max(3, test_count)
    if val_count + test_count >= total:
        val_count = max(1, total // 5)
        test_count = max(1, total // 5)
    val_records = records[:val_count]
    test_records = records[val_count : val_count + test_count]
    train_records = records[val_count + test_count :]

    write_label_file(output_dir / "train.txt", train_records)
    write_label_file(output_dir / "val.txt", val_records)
    write_label_file(output_dir / "test.txt", test_records)
    write_config(
        output_dir,
        epoch_num=args.epoch_num,
        batch_size=args.batch_size,
        eval_step=args.eval_step,
        learning_rate=args.learning_rate,
        pretrained_model=Path(args.pretrained_model).resolve(),
    )

    report = {
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "documents": total,
        "annotations": sum(len(record["annotations"]) for record in records),
        "missing_images": missing_images,
        "invalid_polygons": invalid_polygons,
        "splits": {
            "train": len(train_records),
            "val": len(val_records),
            "test": len(test_records),
        },
    }
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "det_export_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    write_readme(output_dir, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Export MC-OCR 2021 text detection data to PaddleOCR DB format.")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--pretrained-model", default=str(DEFAULT_PRETRAINED_MODEL))
    parser.add_argument("--copy-mode", choices=("hardlink", "copy"), default="hardlink")
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--val-ratio", type=float, default=0.10)
    parser.add_argument("--test-ratio", type=float, default=0.10)
    parser.add_argument("--max-images", type=int, default=0)
    parser.add_argument("--epoch-num", type=int, default=50)
    parser.add_argument("--eval-step", type=int, default=250)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=0.0001)
    export(parser.parse_args())


if __name__ == "__main__":
    main()
