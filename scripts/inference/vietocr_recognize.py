from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image
from vietocr.tool.config import Cfg
from vietocr.tool.predictor import Predictor


def _load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _recognize_images(
    predictor: Predictor,
    items: list[dict[str, Any]],
) -> list[dict[str, str]]:
    results = []
    for item in items:
        image_path = Path(item["path"])
        text = ""
        if image_path.exists():
            with Image.open(image_path) as image:
                text = str(predictor.predict(image.convert("RGB")) or "").strip()
        results.append({"id": str(item["id"]), "text": text})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run VietOCR recognition for receipt text crops.")
    parser.add_argument("--input-json", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--config", default="vgg_transformer")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--weights", default="")
    args = parser.parse_args()

    payload = _load_payload(args.input_json)
    config = Cfg.load_config_from_name(args.config)
    config["device"] = args.device
    if args.weights:
        config["weights"] = args.weights

    predictor = Predictor(config)
    results = _recognize_images(predictor, payload.get("images", []))
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps({"results": results}, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
