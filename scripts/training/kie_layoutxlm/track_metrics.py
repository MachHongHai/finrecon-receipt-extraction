from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


KEY_VALUE_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*):\s*([-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)", re.IGNORECASE)
EPOCH_RE = re.compile(r"epoch:\s*\[(\d+)/(\d+)\]", re.IGNORECASE)
STEP_RE = re.compile(r"(?:global_step|step):\s*(\d+)", re.IGNORECASE)


def parse_key_values(text: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for key, value in KEY_VALUE_RE.findall(text):
        try:
            values[key] = float(value)
        except ValueError:
            continue
    return values


def read_log_text(log_path: Path) -> str:
    raw = log_path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    if raw[:200].count(b"\x00") > 20:
        return raw.decode("utf-16-le", errors="replace")
    return raw.decode("utf-8", errors="replace")


def parse_log(log_path: Path, run_name: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(read_log_text(log_path).splitlines(), start=1):
        lower = line.lower()
        event = ""
        if "cur metric" in lower:
            event = "eval"
        elif "best metric" in lower:
            event = "best"
        elif "loss:" in lower and "epoch:" in lower:
            event = "train"
        else:
            continue

        metrics = parse_key_values(line)
        if not metrics:
            continue
        epoch_match = EPOCH_RE.search(line)
        step_match = STEP_RE.search(line)
        record: dict[str, Any] = {
            "run_name": run_name,
            "event": event,
            "line": line_number,
            "epoch": int(epoch_match.group(1)) if epoch_match else None,
            "epoch_total": int(epoch_match.group(2)) if epoch_match else None,
            "step": int(step_match.group(1)) if step_match else None,
            "acc": metrics.get("acc"),
            "norm_edit_dis": metrics.get("norm_edit_dis"),
            "precision": metrics.get("precision"),
            "recall": metrics.get("recall"),
            "f1": metrics.get("hmean"),
            "hmean": metrics.get("hmean"),
            "loss": metrics.get("loss"),
            "lr": metrics.get("lr"),
            "fps": metrics.get("fps"),
            "raw": line.strip(),
        }
        records.append(record)
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "run_name",
        "event",
        "line",
        "epoch",
        "epoch_total",
        "step",
        "acc",
        "norm_edit_dis",
        "precision",
        "recall",
        "f1",
        "hmean",
        "loss",
        "lr",
        "fps",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key) for key in fieldnames})


def build_summary(records: list[dict[str, Any]], run_name: str, log_path: Path) -> dict[str, Any]:
    best_records = [record for record in records if record["event"] == "best"]
    eval_records = [record for record in records if record["event"] == "eval"]
    train_records = [record for record in records if record["event"] == "train"]
    scored_records = best_records or eval_records or train_records
    metric_priority = ("f1", "hmean", "acc", "norm_edit_dis", "loss")
    best_metric_name = next(
        (name for name in metric_priority if any(record.get(name) is not None for record in scored_records)),
        "",
    )

    def score_record(record: dict[str, Any]) -> tuple[float, float, float]:
        metric_value = float(record.get(best_metric_name) or 0) if best_metric_name else 0.0
        norm_edit_dis = float(record.get("norm_edit_dis") or 0)
        loss = float(record.get("loss") or 0)
        loss_score = -loss if loss else 0.0
        return metric_value, norm_edit_dis, loss_score

    best = None
    if best_metric_name:
        best = max(
            (record for record in scored_records if record.get(best_metric_name) is not None),
            key=score_record,
            default=None,
        )
    return {
        "run_name": run_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "log_path": str(log_path),
        "train_points": len(train_records),
        "eval_points": len(eval_records),
        "best_points": len(best_records),
        "best_metric_name": best_metric_name,
        "best": best,
        "last_eval": eval_records[-1] if eval_records else None,
        "last_train": train_records[-1] if train_records else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse PaddleOCR logs into metric JSONL/CSV files.")
    parser.add_argument("--log", required=True, help="PaddleOCR train/eval log file.")
    parser.add_argument("--run-name", default="", help="Stable run label.")
    parser.add_argument("--jsonl", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    log_path = Path(args.log).resolve()
    run_name = args.run_name or log_path.stem
    records = parse_log(log_path, run_name)
    write_jsonl(Path(args.jsonl), records)
    write_csv(Path(args.csv), records)
    summary = build_summary(records, run_name, log_path)
    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
