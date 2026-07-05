from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


TRAIN_RE = re.compile(
    r"epoch: \[(?P<epoch>\d+)/(?P<epoch_total>\d+)\], global_step: (?P<global_step>\d+), (?P<body>.*)"
)
METRIC_RE = re.compile(r"cur metric, (?P<body>.*)")
BEST_RE = re.compile(r"best metric, (?P<body>.*)")


def read_log_lines(log_path: Path) -> list[str]:
    data = log_path.read_bytes()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16", errors="replace").splitlines()

    # Windows PowerShell 5 Tee-Object often emits UTF-16LE without a BOM.
    # If the first chunk has many NUL bytes, treat it as UTF-16.
    head = data[:512]
    if head.count(b"\x00") > max(8, len(head) // 8):
        return data.decode("utf-16", errors="replace").splitlines()

    return data.decode("utf-8", errors="replace").splitlines()


def parse_pairs(body: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for part in body.split(", "):
        if ": " not in part:
            continue
        key, value = part.split(": ", 1)
        key = key.strip()
        value = value.strip()
        try:
            if re.fullmatch(r"-?\d+", value):
                result[key] = int(value)
            else:
                result[key] = float(value)
        except ValueError:
            result[key] = value
    return result


def parse_log(log_path: Path, run_name: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    last_epoch: int | None = None
    last_step: int | None = None
    for line in read_log_lines(log_path):
        train_match = TRAIN_RE.search(line)
        if train_match:
            body = parse_pairs(train_match.group("body"))
            last_epoch = int(train_match.group("epoch"))
            last_step = int(train_match.group("global_step"))
            events.append(
                {
                    "run_name": run_name,
                    "event": "train",
                    "epoch": last_epoch,
                    "epoch_total": int(train_match.group("epoch_total")),
                    "global_step": last_step,
                    **body,
                }
            )
            continue

        metric_match = METRIC_RE.search(line)
        if metric_match:
            events.append(
                {
                    "run_name": run_name,
                    "event": "eval",
                    "epoch": last_epoch,
                    "global_step": last_step,
                    **parse_pairs(metric_match.group("body")),
                }
            )
            continue

        best_match = BEST_RE.search(line)
        if best_match:
            events.append(
                {
                    "run_name": run_name,
                    "event": "best",
                    "epoch": last_epoch,
                    "global_step": last_step,
                    **parse_pairs(best_match.group("body")),
                }
            )
    return events


def write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for event in events:
            file.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_csv(path: Path, events: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    for event in events:
        for key in event:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(events)


def summarize(events: list[dict[str, Any]], run_name: str, log_path: Path) -> dict[str, Any]:
    train_events = [event for event in events if event.get("event") == "train"]
    eval_events = [event for event in events if event.get("event") == "eval"]
    best_events = [event for event in events if event.get("event") == "best"]
    best = max(
        (event for event in best_events if isinstance(event.get("hmean"), (int, float))),
        key=lambda item: float(item["hmean"]),
        default=None,
    )
    latest_eval = eval_events[-1] if eval_events else None
    latest_train = train_events[-1] if train_events else None
    return {
        "run_name": run_name,
        "log_path": str(log_path),
        "train_events": len(train_events),
        "eval_events": len(eval_events),
        "latest_train": latest_train,
        "latest_eval": latest_eval,
        "best": best,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse PaddleOCR detection training logs into metric artifacts.")
    parser.add_argument("--log", required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--jsonl", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    log_path = Path(args.log)
    events = parse_log(log_path, args.run_name)
    write_jsonl(Path(args.jsonl), events)
    write_csv(Path(args.csv), events)
    summary = summarize(events, args.run_name, log_path)
    Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
