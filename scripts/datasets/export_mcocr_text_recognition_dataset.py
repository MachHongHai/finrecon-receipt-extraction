from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable


DEFAULT_SOURCE_DIR = Path("archive/source_mcocr")
DEFAULT_OUTPUT_DIR = Path("archive/prepared/mcocr2021_text_recognition_paddleocr")
DEFAULT_IMAGE_SUBDIR = Path("text_recognition_mcocr_data/text_recognition_mcocr_data")


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def link_or_copy(source: Path, destination: Path, mode: str) -> None:
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if mode == "hardlink":
        try:
            os.link(source, destination)
            return
        except OSError:
            pass
    shutil.copy2(source, destination)


def read_source_labels(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        if "\t" not in line:
            raise ValueError(f"Invalid label row without tab at {path}:{line_number}")
        image_name, text = line.split("\t", 1)
        image_name = image_name.strip()
        text = text.strip()
        if image_name and text:
            rows.append((image_name, text))
    return rows


def write_paddleocr_label_file(path: Path, rows: Iterable[tuple[str, str]], image_prefix: str) -> int:
    count = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for image_name, text in rows:
            file.write(f"{image_prefix}/{image_name}\t{text}\n")
            count += 1
    return count


def collect_characters(rows: Iterable[tuple[str, str]], use_space_char: bool) -> list[str]:
    chars: set[str] = set()
    for _, text in rows:
        for char in text:
            if char in {"\n", "\r", "\t"}:
                continue
            if char == " " and use_space_char:
                continue
            chars.add(char)
    return sorted(chars, key=lambda value: (value.casefold(), value))


def write_character_dict(path: Path, characters: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(characters) + "\n", encoding="utf-8", newline="\n")


def write_config(
    output_dir: Path,
    config_path: Path,
    character_dict_path: Path,
    epoch_num: int,
    batch_size: int,
    eval_batch_size: int,
    learning_rate: float,
    max_text_length: int,
    image_width: int,
    image_height: int,
    eval_step: int,
    pretrained_model: str,
) -> None:
    output_root = output_dir.as_posix()
    dict_path = character_dict_path.as_posix()
    save_model_dir = (output_dir / "output" / "rec_svtr_lcnet_mcocr2021").as_posix()
    save_res_path = (output_dir / "output" / "rec_results.txt").as_posix()
    infer_img = (output_dir / "images").as_posix()
    pretrained_value = pretrained_model.replace("\\", "/") if pretrained_model else ""
    config = f"""Global:
  debug: false
  use_gpu: true
  epoch_num: {epoch_num}
  log_smooth_window: 20
  print_batch_step: 10
  save_model_dir: {save_model_dir}
  save_epoch_step: 10
  eval_batch_step: [0, {eval_step}]
  cal_metric_during_train: true
  pretrained_model: {pretrained_value}
  checkpoints:
  save_inference_dir:
  use_visualdl: false
  infer_img: {infer_img}
  character_dict_path: {dict_path}
  max_text_length: &max_text_length {max_text_length}
  infer_mode: false
  use_space_char: true
  distributed: false
  save_res_path: {save_res_path}
  save_optimizer_state: false
  save_latest_model: false
  save_epoch_checkpoints: false

Optimizer:
  name: Adam
  beta1: 0.9
  beta2: 0.999
  lr:
    name: Cosine
    learning_rate: {learning_rate}
    warmup_epoch: 1
  regularizer:
    name: L2
    factor: 0.00003

Architecture:
  model_type: rec
  algorithm: SVTR_LCNet
  Transform:
  Backbone:
    name: PPLCNetV3
    scale: 0.95
  Head:
    name: MultiHead
    head_list:
      - CTCHead:
          Neck:
            name: svtr
            dims: 120
            depth: 2
            hidden_dims: 120
            kernel_size: [1, 3]
            use_guide: True
          Head:
            fc_decay: 0.00001
      - NRTRHead:
          nrtr_dim: 384
          max_text_length: *max_text_length

Loss:
  name: MultiLoss
  loss_config_list:
    - CTCLoss:
    - NRTRLoss:

PostProcess:
  name: CTCLabelDecode

Metric:
  name: RecMetric
  main_indicator: acc

Train:
  dataset:
    name: SimpleDataSet
    data_dir: {output_root}
    label_file_list:
      - {output_root}/train.txt
    transforms:
      - DecodeImage:
          img_mode: BGR
          channel_first: false
      - RecAug:
      - MultiLabelEncode:
          gtc_encode: NRTRLabelEncode
      - RecResizeImg:
          image_shape: [3, {image_height}, {image_width}]
      - KeepKeys:
          keep_keys: [image, label_ctc, label_gtc, length, valid_ratio]
  loader:
    shuffle: true
    batch_size_per_card: {batch_size}
    drop_last: true
    num_workers: 0

Eval:
  dataset:
    name: SimpleDataSet
    data_dir: {output_root}
    label_file_list:
      - {output_root}/val.txt
    transforms:
      - DecodeImage:
          img_mode: BGR
          channel_first: false
      - MultiLabelEncode:
          gtc_encode: NRTRLabelEncode
      - RecResizeImg:
          image_shape: [3, {image_height}, {image_width}]
      - KeepKeys:
          keep_keys: [image, label_ctc, label_gtc, length, valid_ratio]
  loader:
    shuffle: false
    drop_last: false
    batch_size_per_card: {eval_batch_size}
    num_workers: 0
"""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config, encoding="utf-8", newline="\n")


def build_report(
    source_dir: Path,
    output_dir: Path,
    train_rows: list[tuple[str, str]],
    val_rows: list[tuple[str, str]],
    missing_images: list[str],
    characters: list[str],
    max_text_length: int,
) -> dict[str, object]:
    lengths = [len(text) for _, text in [*train_rows, *val_rows]]
    char_counts = Counter(char for _, text in [*train_rows, *val_rows] for char in text)
    confusing_chars = ["0", "O", "o", "1", "I", "l", "L", "5", "S", "8", "B"]
    return {
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "train_rows": len(train_rows),
        "val_rows": len(val_rows),
        "missing_images": len(missing_images),
        "missing_image_examples": missing_images[:20],
        "unique_characters_without_space": len(characters),
        "max_text_length_config": max_text_length,
        "text_length": {
            "min": min(lengths) if lengths else 0,
            "max": max(lengths) if lengths else 0,
            "avg": sum(lengths) / len(lengths) if lengths else 0,
        },
        "confusing_character_counts": {char: char_counts.get(char, 0) for char in confusing_chars},
    }


def export(args: argparse.Namespace) -> dict[str, object]:
    source_dir = Path(args.source_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    image_source_dir = source_dir / args.image_subdir
    train_source = source_dir / "text_recognition_train_data.txt"
    val_source = source_dir / "text_recognition_val_data.txt"

    for required in (image_source_dir, train_source, val_source):
        if not required.exists():
            raise FileNotFoundError(f"Missing MC-OCR recognition source: {required}")

    if args.clear and output_dir.exists():
        shutil.rmtree(output_dir)
    (output_dir / "images").mkdir(parents=True, exist_ok=True)
    (output_dir / "reports").mkdir(parents=True, exist_ok=True)

    train_rows = read_source_labels(train_source)
    val_rows = read_source_labels(val_source)
    all_rows = [*train_rows, *val_rows]

    missing_images: list[str] = []
    for image_name, _ in all_rows:
        source_image = image_source_dir / image_name
        if not source_image.exists():
            missing_images.append(image_name)
            continue
        link_or_copy(source_image, output_dir / "images" / image_name, args.copy_mode)

    if missing_images and not args.allow_missing:
        raise FileNotFoundError(f"Missing {len(missing_images)} source images. First examples: {missing_images[:5]}")

    valid_train_rows = [(name, text) for name, text in train_rows if (image_source_dir / name).exists()]
    valid_val_rows = [(name, text) for name, text in val_rows if (image_source_dir / name).exists()]
    write_paddleocr_label_file(output_dir / "train.txt", valid_train_rows, "images")
    write_paddleocr_label_file(output_dir / "val.txt", valid_val_rows, "images")

    characters = collect_characters([*valid_train_rows, *valid_val_rows], use_space_char=True)
    dict_path = output_dir / "dict" / "mcocr2021_vi_receipt_dict.txt"
    write_character_dict(dict_path, characters)

    max_observed_len = max((len(text) for _, text in [*valid_train_rows, *valid_val_rows]), default=0)
    max_text_length = max(args.max_text_length, max_observed_len)
    config_path = output_dir / "rec_svtr_lcnet_mcocr2021.yml"
    write_config(
        output_dir=output_dir,
        config_path=config_path,
        character_dict_path=dict_path,
        epoch_num=args.epoch_num,
        batch_size=args.batch_size,
        eval_batch_size=args.eval_batch_size,
        learning_rate=args.learning_rate,
        max_text_length=max_text_length,
        image_width=args.image_width,
        image_height=args.image_height,
        eval_step=args.eval_step,
        pretrained_model=args.pretrained_model,
    )

    report = build_report(source_dir, output_dir, valid_train_rows, valid_val_rows, missing_images, characters, max_text_length)
    report_path = output_dir / "reports" / "export_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Export MC-OCR 2021 text recognition crops to PaddleOCR rec format.")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--image-subdir", default=str(DEFAULT_IMAGE_SUBDIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--copy-mode", choices=("copy", "hardlink"), default="hardlink")
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--epoch-num", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--eval-batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=0.0001)
    parser.add_argument("--max-text-length", type=int, default=160)
    parser.add_argument("--image-width", type=int, default=640)
    parser.add_argument("--image-height", type=int, default=48)
    parser.add_argument("--eval-step", type=int, default=250)
    parser.add_argument("--pretrained-model", default="")
    args = parser.parse_args()

    report = export(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
