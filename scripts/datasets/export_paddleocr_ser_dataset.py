from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any


LABELS = ("OTHER", "SELLER", "ADDRESS", "TIMESTAMP", "TOTAL_COST")
LABEL_TO_ID = {label: index for index, label in enumerate(LABELS)}


def load_image_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:
        return 1, 1


def clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


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


def clamp_points(points: list[list[int]], width: int, height: int) -> list[list[int]]:
    max_x = max(0, width - 1)
    max_y = max(0, height - 1)
    return [[clamp(point[0], 0, max_x), clamp(point[1], 0, max_y)] for point in points]


def bbox_to_points(bbox: list[float], width: int, height: int) -> list[list[int]]:
    if len(bbox) < 4:
        return [[0, 0], [0, 0], [0, 0], [0, 0]]
    x1, y1, x2, y2 = [round(float(value)) for value in bbox[:4]]
    return clamp_points([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], width, height)


def polygon_to_points(polygon: list[float], bbox: list[float], width: int, height: int) -> list[list[int]]:
    if len(polygon) >= 8:
        coords = [round(float(value)) for value in polygon[:8]]
        return clamp_points(
            [[coords[0], coords[1]], [coords[2], coords[3]], [coords[4], coords[5]], [coords[6], coords[7]]],
            width,
            height,
        )
    return bbox_to_points(bbox, width, height)


def normalize_label(label: str | None) -> str:
    normalized = (label or "OTHER").strip().upper()
    return normalized if normalized in LABEL_TO_ID else "OTHER"


def convert_record(record: dict[str, Any], image_path: Path) -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    width, height = load_image_size(image_path)
    for index, box in enumerate(record.get("boxes") or []):
        text = (box.get("text") or "").strip()
        if not text:
            continue
        bbox = box.get("bbox") or [0, 0, 0, 0]
        polygon = box.get("polygon") or []
        label = normalize_label(box.get("label"))
        annotations.append(
            {
                "transcription": text,
                "label": label,
                "points": polygon_to_points(polygon, bbox, width, height),
                "id": index,
                "linking": [],
            }
        )
    return annotations


def safe_copy_image(src: Path, dst: Path, mode: str) -> None:
    if mode == "none" or dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if mode == "hardlink":
        try:
            os.link(src, dst)
            return
        except OSError:
            pass
    shutil.copy2(src, dst)


def write_paddle_split(
    split_name: str,
    ids: list[str],
    records_by_id: dict[str, dict[str, Any]],
    dataset_dir: Path,
    output_dir: Path,
    copy_mode: str,
) -> dict[str, int]:
    image_output_dir = output_dir / "images"
    lines: list[str] = []
    stats = {
        "documents": 0,
        "annotations": 0,
        "empty_documents": 0,
        "missing_records": 0,
        "missing_images": 0,
    }
    for record_id in ids:
        record = records_by_id.get(record_id)
        if record is None:
            stats["missing_records"] += 1
            continue
        image_name = Path(record["image"]).name
        source_image = dataset_dir / record["image"]
        if not source_image.exists():
            stats["missing_images"] += 1
            continue
        annotations = convert_record(record, source_image)
        if not annotations:
            stats["empty_documents"] += 1
            continue
        safe_copy_image(source_image, image_output_dir / image_name, copy_mode)
        lines.append(f"{image_name}\t{json.dumps(annotations, ensure_ascii=False, separators=(',', ':'))}")
        stats["documents"] += 1
        stats["annotations"] += len(annotations)
    (output_dir / f"{split_name}.json").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return stats


def write_class_list(output_dir: Path) -> None:
    (output_dir / "class_list.txt").write_text("\n".join(LABELS) + "\n", encoding="utf-8")


def yaml_path(path: Path) -> str:
    return path.resolve().as_posix()


def write_config(
    output_dir: Path,
    epoch_num: int,
    eval_step: int,
    batch_size: int,
    learning_rate: float,
    warmup_epoch: int,
    clip_norm_global: float,
    print_batch_step: int = 10,
) -> None:
    config_path = output_dir / "ser_vi_layoutxlm_finrecon_4field.yml"
    save_dir = output_dir / "output" / "ser_vi_layoutxlm_finrecon_4field"
    pretrained_dir = output_dir / "pretrained"
    labels_count = len(LABELS)
    paddle_num_classes = labels_count * 2 - 1
    learning_rate_text = f"{learning_rate:.10f}".rstrip("0").rstrip(".")
    config = f"""Global:
  use_gpu: true
  epoch_num: &epoch_num {epoch_num}
  log_smooth_window: 10
  print_batch_step: {print_batch_step}
  save_model_dir: {yaml_path(save_dir)}
  save_epoch_step: {epoch_num}
  eval_batch_step: [0, {eval_step}]
  cal_metric_during_train: false
  pretrained_model:
  checkpoints:
  save_inference_dir:
  use_visualdl: false
  save_optimizer_state: false
  save_latest_model: false
  save_epoch_checkpoints: false
  seed: 2022
  infer_img:
  d2s_train_image_shape: [3, 224, 224]
  save_res_path: {yaml_path(output_dir / "output" / "ser_results.txt")}
  kie_det_model_dir:
  amp_custom_white_list: ['scale', 'concat', 'elementwise_add']

Architecture:
  model_type: kie
  algorithm: &algorithm "LayoutXLM"
  Transform:
  Backbone:
    name: LayoutXLMForSer
    pretrained: true
    checkpoints:
    mode: vi
    num_classes: {paddle_num_classes}

Loss:
  name: VQASerTokenLayoutLMLoss
  num_classes: {paddle_num_classes}
  key: "backbone_out"

Optimizer:
  name: AdamW
  beta1: 0.9
  beta2: 0.999
  clip_norm_global: {clip_norm_global}
  lr:
    name: Linear
    learning_rate: {learning_rate_text}
    epochs: *epoch_num
    warmup_epoch: {warmup_epoch}
  regularizer:
    name: L2
    factor: 0.00000

PostProcess:
  name: VQASerTokenLayoutLMPostProcess
  class_path: &class_path {yaml_path(output_dir / "class_list.txt")}

Metric:
  name: VQASerTokenMetric
  main_indicator: hmean

Train:
  dataset:
    name: SimpleDataSet
    data_dir: {yaml_path(output_dir / "images")}
    label_file_list:
      - {yaml_path(output_dir / "train.json")}
    ratio_list: [1.0]
    transforms:
      - DecodeImage:
          img_mode: RGB
          channel_first: false
      - VQATokenLabelEncode:
          contains_re: false
          algorithm: *algorithm
          class_path: *class_path
          use_textline_bbox_info: &use_textline_bbox_info true
          order_method: &order_method "tb-yx"
      - VQATokenPad:
          max_seq_len: 512
          return_attention_mask: true
      - VQASerTokenChunk:
          max_seq_len: 512
      - Resize:
          size: [224, 224]
      - NormalizeImage:
          scale: 1
          mean: [123.675, 116.28, 103.53]
          std: [58.395, 57.12, 57.375]
          order: hwc
      - ToCHWImage:
      - KeepKeys:
          keep_keys: [input_ids, bbox, attention_mask, token_type_ids, image, labels]
  loader:
    shuffle: true
    drop_last: false
    batch_size_per_card: {batch_size}
    num_workers: 0

Eval:
  dataset:
    name: SimpleDataSet
    data_dir: {yaml_path(output_dir / "images")}
    label_file_list:
      - {yaml_path(output_dir / "val.json")}
    transforms:
      - DecodeImage:
          img_mode: RGB
          channel_first: false
      - VQATokenLabelEncode:
          contains_re: false
          algorithm: *algorithm
          class_path: *class_path
          use_textline_bbox_info: *use_textline_bbox_info
          order_method: *order_method
      - VQATokenPad:
          max_seq_len: 512
          return_attention_mask: true
      - VQASerTokenChunk:
          max_seq_len: 512
      - Resize:
          size: [224, 224]
      - NormalizeImage:
          scale: 1
          mean: [123.675, 116.28, 103.53]
          std: [58.395, 57.12, 57.375]
          order: hwc
      - ToCHWImage:
      - KeepKeys:
          keep_keys: [input_ids, bbox, attention_mask, token_type_ids, image, labels]
  loader:
    shuffle: false
    drop_last: false
    batch_size_per_card: {batch_size}
    num_workers: 0
"""
    config_path.write_text(config, encoding="utf-8", newline="\n")
    pretrained_dir.mkdir(parents=True, exist_ok=True)


def write_training_readme(output_dir: Path, stats: dict[str, dict[str, int]]) -> None:
    lines = [
        "# PaddleOCR SER Dataset - FinRecon Receipt 4 Field",
        "",
        "Dataset nay duoc export cho PaddleOCR KIE/SER voi 5 class:",
        "",
        "- `OTHER`",
        "- `SELLER`",
        "- `ADDRESS`",
        "- `TIMESTAMP`",
        "- `TOTAL_COST`",
        "",
        "## Files",
        "",
        "- `images/`: anh receipt.",
        "- `train.json`, `val.json`, `test.json`: PaddleOCR SER label files, moi dong la `image<TAB>json_annotations`.",
        "- `class_list.txt`: danh sach class, `OTHER` nam dau tien.",
        "- `ser_vi_layoutxlm_finrecon_4field.yml`: config train VI-LayoutXLM SER.",
        "",
        "## Stats",
        "",
    ]
    for split_name, split_stats in stats.items():
        lines.append(
            f"- `{split_name}`: {split_stats['documents']} docs, "
            f"{split_stats['annotations']} annotations, "
            f"{split_stats['empty_documents']} empty skipped, "
            f"{split_stats['missing_images']} missing images"
        )
    lines.extend(
        [
            "",
        "## Cach train",
        "",
        "Nen chay trong mot moi truong rieng cho PaddleOCR, khong cai vao backend venv cua web app.",
        "",
        "Trong repo nay, dung script da cau hinh cache/checkpoint tren o D va validate dataset truoc train:",
        "",
        "```powershell",
        ".\\scripts\\training\\paddleocr\\train_gpu.ps1",
        "```",
        "",
        "Danh gia best checkpoint tren test split:",
        "",
        "```powershell",
        ".\\scripts\\training\\paddleocr\\eval_ser.ps1 -Split test",
        "```",
        "",
        "Config mac dinh dung epoch/learning rate trong file yml da export.",
        "Luu y: LayoutXLM train CPU se rat cham. Nen dung GPU neu muon train that.",
        ]
    )
    (output_dir / "README_TRAINING.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def export(args: argparse.Namespace) -> None:
    dataset_dir = Path(args.dataset_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    if args.clear and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "images").mkdir(parents=True, exist_ok=True)

    records_by_id = load_records(dataset_dir)
    stats: dict[str, dict[str, int]] = {}
    for split_name in ("train", "val", "test"):
        split_ids = load_split_ids(dataset_dir, split_name)
        stats[split_name] = write_paddle_split(
            split_name=split_name,
            ids=split_ids,
            records_by_id=records_by_id,
            dataset_dir=dataset_dir,
            output_dir=output_dir,
            copy_mode=args.copy_mode,
        )
    write_class_list(output_dir)
    write_config(
        output_dir=output_dir,
        epoch_num=args.epoch_num,
        eval_step=args.eval_step,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        warmup_epoch=args.warmup_epoch,
        clip_norm_global=args.clip_norm_global,
        print_batch_step=10,
    )
    write_training_readme(output_dir, stats)
    print(f"Wrote PaddleOCR SER dataset to {output_dir}")
    for split_name, split_stats in stats.items():
        print(split_name, split_stats)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export prepared receipt dataset to PaddleOCR SER format.")
    parser.add_argument(
        "--dataset-dir",
        default="archive/prepared/finrecon_receipt_4field_clean",
        help="Prepared 4-field dataset directory.",
    )
    parser.add_argument(
        "--output-dir",
        default="archive/prepared/finrecon_receipt_4field_clean/paddleocr_ser",
        help="Output PaddleOCR SER dataset directory.",
    )
    parser.add_argument(
        "--copy-mode",
        choices=("copy", "hardlink", "none"),
        default="copy",
        help="How to populate PaddleOCR images directory.",
    )
    parser.add_argument("--clear", action="store_true", help="Clear output directory before export.")
    parser.add_argument("--epoch-num", type=int, default=10, help="Epoch count for generated train config.")
    parser.add_argument("--eval-step", type=int, default=250, help="Evaluation step interval for generated train config.")
    parser.add_argument("--batch-size", type=int, default=2, help="Batch size per GPU card for generated train config.")
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.00002,
        help="AdamW learning rate. Keep conservative for small SER datasets.",
    )
    parser.add_argument("--warmup-epoch", type=int, default=1, help="Linear warmup epochs.")
    parser.add_argument(
        "--clip-norm-global",
        type=float,
        default=1.0,
        help="Global gradient clipping norm passed to PaddleOCR optimizer.",
    )
    export(parser.parse_args())


if __name__ == "__main__":
    main()
