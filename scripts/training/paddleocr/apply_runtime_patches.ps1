param(
    [string]$PaddleOcrRoot = "external\PaddleOCR"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")
$Root = if ([System.IO.Path]::IsPathRooted($PaddleOcrRoot)) {
    Resolve-Path -LiteralPath $PaddleOcrRoot
} else {
    Resolve-Path -LiteralPath (Join-Path $RepoRoot $PaddleOcrRoot)
}

$InferKie = Join-Path $Root "tools\infer_kie_token_ser.py"
$Utility = Join-Path $Root "tools\infer\utility.py"
$PredictRec = Join-Path $Root "tools\infer\predict_rec.py"

foreach ($path in @($InferKie, $Utility, $PredictRec)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing PaddleOCR runtime file: $path"
    }
}

$ocrKwargsBlock = @'
        ocr_kwargs = {
            "use_angle_cls": False,
            "show_log": False,
            "use_gpu": global_config["use_gpu"],
        }
        optional_ocr_keys = {
            "ocr_lang": "lang",
            "ocr_version": "ocr_version",
            "kie_det_model_dir": "det_model_dir",
        }
        for config_key, paddle_key in optional_ocr_keys.items():
            value = global_config.get(config_key, None)
            if value not in (None, ""):
                ocr_kwargs[paddle_key] = value

        self.ocr_engine = PaddleOCR(**ocr_kwargs)
'@

$inferKieText = Get-Content -LiteralPath $InferKie -Raw
if ($inferKieText -notmatch "import subprocess") {
    $inferKieText = $inferKieText -replace "import sys\r?\n", "import sys`r`nimport subprocess`r`nimport uuid`r`n"
    Set-Content -LiteralPath $InferKie -Value $inferKieText -Encoding UTF8
}

$inferKieText = Get-Content -LiteralPath $InferKie -Raw
if ($inferKieText -notmatch "optional_ocr_keys") {
    $inferKieText = [regex]::Replace(
        $inferKieText,
        "        self\.ocr_engine = PaddleOCR\([\s\S]*?            use_gpu=global_config\[['""]use_gpu['""]\]\)",
        $ocrKwargsBlock.TrimEnd()
    )
    Set-Content -LiteralPath $InferKie -Value $inferKieText -Encoding UTF8
}

$inferKieText = Get-Content -LiteralPath $InferKie -Raw
if ($inferKieText -notmatch "PaddleDetectionVietOCREngine") {
    $inferKieText = $inferKieText -replace `
        "from ppocr\.utils\.visual import draw_ser_results\r?\n", `
        "from ppocr.utils.visual import draw_ser_results`r`nfrom tools.infer.utility import get_rotate_crop_image`r`nfrom tools.infer.predict_system import sorted_boxes`r`n"

    $vietOcrAdapterBlock = @'

class PaddleDetectionVietOCREngine(object):
    def __init__(self, paddle_ocr, global_config):
        self.paddle_ocr = paddle_ocr
        self.vietocr_python = global_config.get("vietocr_python", "")
        self.vietocr_script = global_config.get("vietocr_script", "")
        self.vietocr_config = global_config.get("vietocr_config", "vgg_transformer")
        self.vietocr_device = global_config.get("vietocr_device", "cpu")
        self.vietocr_weights = global_config.get("vietocr_weights", "")
        self.vietocr_timeout = int(global_config.get("vietocr_timeout", 180))
        self.work_root = global_config.get("save_res_path", ".")

        if not self.vietocr_python or not os.path.exists(self.vietocr_python):
            raise RuntimeError("VietOCR python runtime is missing: {}".format(self.vietocr_python))
        if not self.vietocr_script or not os.path.exists(self.vietocr_script):
            raise RuntimeError("VietOCR inference script is missing: {}".format(self.vietocr_script))

    def _decode_image(self, image):
        if isinstance(image, bytes):
            data = np.frombuffer(image, np.uint8)
            return cv2.imdecode(data, cv2.IMREAD_COLOR)
        return image

    def _recognize_crop(self, image, box):
        points = np.array(box).astype("float32")
        crop = get_rotate_crop_image(image, points)
        if crop is None or crop.size == 0:
            return None
        return crop

    def _recognize_crops(self, crops):
        if not crops:
            return {}

        batch_dir = os.path.join(self.work_root, "vietocr_crops", uuid.uuid4().hex)
        os.makedirs(batch_dir, exist_ok=True)
        images = []
        for idx, crop in enumerate(crops):
            crop_path = os.path.join(batch_dir, "{:04d}.png".format(idx))
            cv2.imwrite(crop_path, crop)
            images.append({"id": str(idx), "path": crop_path})

        input_json = os.path.join(batch_dir, "input.json")
        output_json = os.path.join(batch_dir, "output.json")
        with open(input_json, "w", encoding="utf-8") as f:
            json.dump({"images": images}, f, ensure_ascii=False)

        args = [
            self.vietocr_python,
            self.vietocr_script,
            "--input-json",
            input_json,
            "--output-json",
            output_json,
            "--config",
            self.vietocr_config,
            "--device",
            self.vietocr_device,
        ]
        if self.vietocr_weights:
            args.extend(["--weights", self.vietocr_weights])

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.vietocr_timeout,
            env=env,
        )
        if completed.returncode != 0:
            log_text = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
            raise RuntimeError("VietOCR recognition failed:\n{}".format(log_text[-4000:]))
        if not os.path.exists(output_json):
            raise RuntimeError("VietOCR did not create output JSON: {}".format(output_json))

        with open(output_json, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return {item["id"]: item.get("text", "") for item in payload.get("results", [])}

    def ocr(self, image, cls=False):
        decoded = self._decode_image(image)
        if decoded is None:
            return [[]]
        detected, _ = self.paddle_ocr.text_detector(decoded)
        if detected is None or len(detected) == 0:
            return [[]]
        detected = sorted_boxes(detected)
        results = []
        result_boxes = []
        crops = []
        for box in detected:
            box = box.tolist() if hasattr(box, "tolist") else box
            crop = self._recognize_crop(decoded, box)
            if crop is None:
                continue
            result_boxes.append(box)
            crops.append(crop)

        texts = self._recognize_crops(crops)
        for idx, box in enumerate(result_boxes):
            text = texts.get(str(idx), "")
            if text:
                results.append([box, (text, 1.0)])
        return [results]

'@

    $inferKieText = $inferKieText -replace "class SerPredictor\(object\):", ($vietOcrAdapterBlock + "class SerPredictor(object):")
    $inferKieText = $inferKieText -replace `
        "        self\.ocr_engine = PaddleOCR\(\*\*ocr_kwargs\)", `
        "        paddle_ocr_engine = PaddleOCR(**ocr_kwargs)`r`n        if global_config.get(""ocr_recognizer"", """") == ""vietocr"":`r`n            self.ocr_engine = PaddleDetectionVietOCREngine(paddle_ocr_engine,`r`n                                                           global_config)`r`n        else:`r`n            self.ocr_engine = paddle_ocr_engine"
    Set-Content -LiteralPath $InferKie -Value $inferKieText -Encoding UTF8
}

$utilityText = Get-Content -LiteralPath $Utility -Raw
if ($utilityText -notmatch "inference\.json") {
    $utilityText = $utilityText -replace `
        "file_names = \['model', 'inference'\]\r?\n\s+for file_name in file_names:\r?\n\s+model_file_path = '\{\}/\{\}\.pdmodel'\.format\(model_dir, file_name\)\r?\n\s+params_file_path = '\{\}/\{\}\.pdiparams'\.format\(model_dir, file_name\)\r?\n\s+if os\.path\.exists\(model_file_path\) and os\.path\.exists\(\r?\n\s+params_file_path\):\r?\n\s+break", `
        "model_file_path = None`r`n        params_file_path = None`r`n        model_files = [`r`n            ('model.pdmodel', 'model.pdiparams'),`r`n            ('inference.pdmodel', 'inference.pdiparams'),`r`n            ('inference.json', 'inference.pdiparams'),`r`n        ]`r`n        for model_name, params_name in model_files:`r`n            candidate_model_path = os.path.join(model_dir, model_name)`r`n            candidate_params_path = os.path.join(model_dir, params_name)`r`n            if os.path.exists(candidate_model_path) and os.path.exists(`r`n                    candidate_params_path):`r`n                model_file_path = candidate_model_path`r`n                params_file_path = candidate_params_path`r`n                break"
    $utilityText = $utilityText -replace "if not os\.path\.exists\(model_file_path\):", "if model_file_path is None:"
    $utilityText = $utilityText -replace "not find model\.pdmodel or inference\.pdmodel in", "not find model.pdmodel, inference.pdmodel, or inference.json in"
    $utilityText = $utilityText -replace "if not os\.path\.exists\(params_file_path\):", "if params_file_path is None:"
    Set-Content -LiteralPath $Utility -Value $utilityText -Encoding UTF8
}

$predictRecText = Get-Content -LiteralPath $PredictRec -Raw
if ($predictRecText -notmatch "matching_preds") {
    $predictRecText = $predictRecText -replace `
        "if self\.postprocess_params\['name'\] == 'CTCLabelDecode':\r?\n\s+rec_result = self\.postprocess_op\(", `
        "if self.postprocess_params['name'] == 'CTCLabelDecode':`r`n                character_count = len(getattr(self.postprocess_op, ""character"", []))`r`n                if isinstance(preds, (list, tuple)):`r`n                    matching_preds = [`r`n                        pred for pred in preds`r`n                        if hasattr(pred, ""shape"") and len(pred.shape) == 3`r`n                        and pred.shape[-1] == character_count`r`n                    ]`r`n                    preds = matching_preds[0] if matching_preds else preds[0]`r`n                if (`r`n                    character_count`r`n                    and hasattr(preds, ""shape"")`r`n                    and len(preds.shape) == 3`r`n                    and preds.shape[-1] > character_count`r`n                ):`r`n                    preds = preds[:, :, :character_count]`r`n                rec_result = self.postprocess_op("
    Set-Content -LiteralPath $PredictRec -Value $predictRecText -Encoding UTF8
}

Write-Host "PaddleOCR runtime patches applied: $Root"
