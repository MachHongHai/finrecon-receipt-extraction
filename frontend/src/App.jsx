import React, { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Camera,
  CheckCircle2,
  Loader2,
  RefreshCw,
  ScanLine,
  Settings2,
  Trash2,
  Upload,
} from "lucide-react";

const API_BASE =
  import.meta.env.VITE_API_URL ||
  `${window.location.protocol}//${window.location.hostname || "127.0.0.1"}:8000`;

const FIELD_ORDER = ["SELLER", "ADDRESS", "TIMESTAMP", "TOTAL_COST"];

const FIELD_META = {
  SELLER: { title: "SELLER", subtitle: "Tên đơn vị bán hàng" },
  ADDRESS: { title: "ADDRESS", subtitle: "Địa chỉ đơn vị bán hàng" },
  TIMESTAMP: { title: "TIMESTAMP", subtitle: "Thời điểm phát sinh giao dịch" },
  TOTAL_COST: { title: "TOTAL_COST", subtitle: "Tổng giá trị thanh toán" },
};

const FALLBACK_OPTIONS = {
  default_ocr_engine: "paddleocr_trained",
  default_kie_engine: "kie_trained",
  ocr_engines: [
    {
      value: "paddleocr_original",
      label: "PaddleOCR baseline",
      description: "Pipeline OCR mặc định của PaddleOCR package.",
      available: true,
    },
    {
      value: "paddleocr_pretrained",
      label: "PP-OCRv4 pretrained",
      description: "Text detection/recognition pretrained chính thức của PaddleOCR.",
      available: true,
    },
    {
      value: "paddleocr_trained",
      label: "MC-OCR fine-tuned recognizer",
      description: "Text recognizer đã fine-tune trên dữ liệu MC-OCR 2021.",
      available: true,
    },
  ],
  kie_engines: [
    {
      value: "kie_pretrained",
      label: "LayoutXLM pretrained baseline",
      description: "Backbone pretrained, chưa nạp checkpoint phân loại 4 field.",
      available: true,
    },
    {
      value: "kie_trained",
      label: "LayoutXLM-SER fine-tuned",
      description: "Checkpoint SER đã fine-tune cho SELLER, ADDRESS, TIMESTAMP, TOTAL_COST.",
      available: true,
    },
  ],
};

function fieldTone(label) {
  return {
    SELLER: "border-emerald-200 bg-emerald-50 text-emerald-900",
    ADDRESS: "border-cyan-200 bg-cyan-50 text-cyan-950",
    TIMESTAMP: "border-amber-200 bg-amber-50 text-amber-950",
    TOTAL_COST: "border-rose-200 bg-rose-50 text-rose-950",
  }[label] || "border-slate-200 bg-slate-50 text-slate-900";
}

function EngineSelector({ title, description, options, value, onChange }) {
  return (
    <div>
      <div className="mb-1 text-xs font-black uppercase tracking-wider text-zinc-500">{title}</div>
      <p className="mb-2 text-xs leading-relaxed text-zinc-500">{description}</p>
      <div className="grid gap-2">
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              disabled={!option.available}
              onClick={() => onChange(option.value)}
              title={option.reason || option.description}
              className={[
                "rounded-lg border px-3 py-2 text-left transition",
                selected
                  ? "border-emerald-400 bg-emerald-500/15 text-white"
                  : "border-zinc-800 bg-zinc-950 text-zinc-300 hover:border-zinc-600",
                !option.available ? "cursor-not-allowed opacity-45" : "",
              ].join(" ")}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-bold">{option.label}</span>
                {selected && <CheckCircle2 size={16} className="shrink-0 text-emerald-300" />}
              </div>
              <div className="mt-1 text-xs leading-relaxed text-zinc-500">
                {option.available ? option.description : option.reason}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function App() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [localPreview, setLocalPreview] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [options, setOptions] = useState(FALLBACK_OPTIONS);
  const [ocrEngine, setOcrEngine] = useState(FALLBACK_OPTIONS.default_ocr_engine);
  const [kieEngine, setKieEngine] = useState(FALLBACK_OPTIONS.default_kie_engine);

  useEffect(() => {
    let cancelled = false;
    async function loadOptions() {
      try {
        const response = await fetch(`${API_BASE}/api/model-options`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Không tải được cấu hình inference.");
        if (cancelled) return;
        setOptions(data);
        setOcrEngine(data.default_ocr_engine || FALLBACK_OPTIONS.default_ocr_engine);
        setKieEngine(data.default_kie_engine || FALLBACK_OPTIONS.default_kie_engine);
      } catch (error) {
        if (!cancelled) {
          setNotice(`Lỗi tải cấu hình inference: ${error.message}`);
        }
      }
    }
    loadOptions();
    return () => {
      cancelled = true;
    };
  }, []);

  const previewUrl = useMemo(() => {
    if (result?.preview_url) return `${API_BASE}${result.preview_url}`;
    return localPreview;
  }, [result, localPreview]);

  const selectedOcrOption = options.ocr_engines.find((item) => item.value === ocrEngine);
  const selectedKieOption = options.kie_engines.find((item) => item.value === kieEngine);
  const canRunInference = selectedFile && selectedOcrOption?.available && selectedKieOption?.available;

  function selectFile(event) {
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
    setResult(null);
    setNotice("");
    if (localPreview) URL.revokeObjectURL(localPreview);
    setLocalPreview(file ? URL.createObjectURL(file) : "");
  }

  async function runInference() {
    if (!selectedFile) {
      setNotice("Chọn một ảnh hóa đơn trước khi chạy inference.");
      return;
    }
    if (!selectedOcrOption?.available || !selectedKieOption?.available) {
      setNotice("Pipeline đang chọn chưa sẵn sàng. Hãy chọn cấu hình khác hoặc kiểm tra model trong backend.");
      return;
    }

    const form = new FormData();
    form.append("file", selectedFile);
    form.append("ocr_engine", ocrEngine);
    form.append("kie_engine", kieEngine);
    setBusy(true);
    setNotice("");
    try {
      const response = await fetch(`${API_BASE}/api/scan-image`, {
        method: "POST",
        body: form,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Không chạy được inference.");
      setResult(data);
      setNotice(`Inference hoàn tất với ${data.ocr_engine_label} + ${data.kie_engine_label}.`);
    } catch (error) {
      setNotice(`Lỗi: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function clearResults() {
    setBusy(true);
    try {
      await fetch(`${API_BASE}/api/scan-results`, { method: "DELETE" });
      setSelectedFile(null);
      setResult(null);
      if (localPreview) URL.revokeObjectURL(localPreview);
      setLocalPreview("");
      setNotice("Đã xóa ảnh upload và output inference tạm.");
    } catch (error) {
      setNotice(`Lỗi: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  const fields = FIELD_ORDER.map((label) => {
    const found = result?.fields?.find((field) => field.label === label);
    return { label, value: found?.display_value || found?.value || "", rawValue: found?.raw_value || "" };
  });

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <section className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-5 py-6">
        <header className="flex flex-col gap-4 border-b border-zinc-800 pb-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-bold uppercase tracking-wider text-emerald-300">
              <ScanLine size={14} />
              OCR + KIE inference workbench
            </div>
            <h1 className="text-2xl font-black tracking-tight text-white">FinRecon Receipt Field Extraction</h1>
            <p className="mt-1 max-w-2xl text-sm text-zinc-400">
              Workbench kiểm thử pipeline OCR và Sequence Entity Recognition cho hóa đơn bán lẻ Việt Nam.
            </p>
          </div>

          <button
            type="button"
            onClick={clearResults}
            disabled={busy}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm font-semibold text-zinc-200 transition hover:bg-zinc-800 disabled:opacity-50"
          >
            <Trash2 size={16} />
            Xóa output tạm
          </button>
        </header>

        <div className="grid flex-1 grid-cols-1 gap-5 py-5 lg:grid-cols-[440px_1fr]">
          <aside className="flex flex-col gap-4">
            <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
              <div className="mb-4 flex items-center gap-2 text-sm font-bold text-white">
                <Camera size={18} className="text-emerald-300" />
                Input receipt image
              </div>

              <label className="flex min-h-[220px] cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-zinc-700 bg-zinc-950 p-4 text-center transition hover:border-emerald-500/70">
                {previewUrl ? (
                  <img src={previewUrl} alt="Receipt input" className="max-h-[320px] w-full object-contain" />
                ) : (
                  <>
                    <Upload className="mb-3 text-zinc-500" size={32} />
                    <span className="text-sm font-semibold text-zinc-300">Chọn ảnh hóa đơn</span>
                    <span className="mt-1 text-xs text-zinc-500">JPG, PNG, BMP, WEBP</span>
                  </>
                )}
                <input
                  type="file"
                  accept=".png,.jpg,.jpeg,.bmp,.webp"
                  className="hidden"
                  onChange={selectFile}
                />
              </label>

              {selectedFile && (
                <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-400">
                  {selectedFile.name}
                </div>
              )}
            </div>

            <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
              <div className="mb-4 flex items-center gap-2 text-sm font-bold text-white">
                <Settings2 size={17} className="text-zinc-400" />
                Inference pipeline
              </div>

              <div className="grid gap-4">
                <EngineSelector
                  title="OCR stage"
                  description="Text detection và text recognition từ ảnh hóa đơn."
                  options={options.ocr_engines}
                  value={ocrEngine}
                  onChange={setOcrEngine}
                />
                <EngineSelector
                  title="KIE/SER stage"
                  description="Token classification để gán nhãn trường thông tin nghiệp vụ."
                  options={options.kie_engines}
                  value={kieEngine}
                  onChange={setKieEngine}
                />
              </div>

              <button
                type="button"
                onClick={runInference}
                disabled={busy || !canRunInference}
                className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-3 text-sm font-bold text-zinc-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy ? <Loader2 className="animate-spin" size={18} /> : <ScanLine size={18} />}
                Run inference
              </button>

              {notice && (
                <div className="mt-3 flex gap-2 rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-300">
                  {notice.startsWith("Lỗi") ? (
                    <AlertCircle className="mt-0.5 shrink-0 text-rose-400" size={16} />
                  ) : (
                    <CheckCircle2 className="mt-0.5 shrink-0 text-emerald-400" size={16} />
                  )}
                  <span>{notice}</span>
                </div>
              )}
            </div>

            <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-bold text-white">
                <RefreshCw size={16} className="text-zinc-400" />
                Evaluation mode
              </div>
              <p className="text-xs leading-relaxed text-zinc-400">
                Không dùng fallback hoặc rule-based extraction. Raw SER labels và OCR tokens được giữ nguyên để phân tích lỗi model.
              </p>
            </div>
          </aside>

          <section className="flex min-h-0 flex-col gap-4">
            {result && (
              <div className="rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-3 text-xs text-zinc-400">
                Pipeline đã chạy:{" "}
                <span className="font-bold text-emerald-300">{result.ocr_engine_label}</span>
                <span className="mx-2 text-zinc-600">+</span>
                <span className="font-bold text-emerald-300">{result.kie_engine_label}</span>
              </div>
            )}

            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {fields.map((field) => {
                const meta = FIELD_META[field.label];
                return (
                  <div key={field.label} className={`rounded-xl border p-4 ${fieldTone(field.label)}`}>
                    <div className="text-xs font-black uppercase tracking-widest opacity-70">{meta.title}</div>
                    <div className="mt-1 text-xs font-semibold opacity-60">{meta.subtitle}</div>
                    <div className="mt-3 min-h-[56px] text-lg font-extrabold leading-snug">
                      {field.value || <span className="text-sm font-semibold opacity-45">Chưa có kết quả</span>}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-2">
              <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                <h2 className="mb-3 text-sm font-bold text-white">Raw SER output</h2>
                <pre className="max-h-[520px] overflow-auto rounded-lg border border-zinc-800 bg-black/40 p-3 text-xs leading-relaxed text-zinc-300">
                  {result?.raw_text || "Chưa có output. Upload ảnh, chọn pipeline và chạy inference."}
                </pre>
              </div>

              <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                <h2 className="mb-3 text-sm font-bold text-white">OCR tokens</h2>
                <div className="max-h-[520px] overflow-auto rounded-lg border border-zinc-800">
                  <table className="w-full border-collapse text-left text-xs">
                    <thead className="sticky top-0 bg-zinc-900 text-zinc-500">
                      <tr>
                        <th className="border-b border-zinc-800 px-3 py-2">SER label</th>
                        <th className="border-b border-zinc-800 px-3 py-2">Recognized text</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(result?.tokens || []).map((token, index) => (
                        <tr key={`${token.label}-${index}`} className="border-b border-zinc-800/70">
                          <td className="px-3 py-2 font-bold text-emerald-300">{token.label}</td>
                          <td className="px-3 py-2 text-zinc-300">{token.text}</td>
                        </tr>
                      ))}
                      {!result?.tokens?.length && (
                        <tr>
                          <td colSpan="2" className="px-3 py-8 text-center text-zinc-500">
                            Chưa có token.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}

export default App;
