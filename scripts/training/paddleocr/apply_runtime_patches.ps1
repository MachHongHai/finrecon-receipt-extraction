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
            "rec_algorithm": "rec_algorithm",
            "kie_rec_model_dir": "rec_model_dir",
            "rec_image_shape": "rec_image_shape",
            "rec_char_dict_path": "rec_char_dict_path",
            "max_text_length": "max_text_length",
            "use_space_char": "use_space_char",
            "kie_det_model_dir": "det_model_dir",
        }
        for config_key, paddle_key in optional_ocr_keys.items():
            value = global_config.get(config_key, None)
            if value not in (None, ""):
                ocr_kwargs[paddle_key] = value

        self.ocr_engine = PaddleOCR(**ocr_kwargs)
'@

$inferKieText = Get-Content -LiteralPath $InferKie -Raw
if ($inferKieText -notmatch "optional_ocr_keys") {
    $inferKieText = [regex]::Replace(
        $inferKieText,
        "        self\.ocr_engine = PaddleOCR\([\s\S]*?            use_gpu=global_config\[['""]use_gpu['""]\]\)",
        $ocrKwargsBlock.TrimEnd()
    )
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
