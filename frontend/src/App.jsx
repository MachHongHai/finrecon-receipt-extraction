import React, { useMemo, useState } from "react";
import {
  AlertCircle,
  Camera,
  CheckCircle2,
  Loader2,
  RefreshCw,
  ScanLine,
  Trash2,
  Upload,
} from "lucide-react";

const API_BASE =
  import.meta.env.VITE_API_URL ||
  `${window.location.protocol}//${window.location.hostname || "127.0.0.1"}:8000`;

const FIELD_ORDER = ["SELLER", "ADDRESS", "TIMESTAMP", "TOTAL_COST"];

function fieldTone(label) {
  return {
    SELLER: "border-emerald-200 bg-emerald-50 text-emerald-900",
    ADDRESS: "border-cyan-200 bg-cyan-50 text-cyan-950",
    TIMESTAMP: "border-amber-200 bg-amber-50 text-amber-950",
    TOTAL_COST: "border-rose-200 bg-rose-50 text-rose-950",
  }[label] || "border-slate-200 bg-slate-50 text-slate-900";
}

function App() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [localPreview, setLocalPreview] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const previewUrl = useMemo(() => {
    if (result?.preview_url) return `${API_BASE}${result.preview_url}`;
    return localPreview;
  }, [result, localPreview]);

  function selectFile(event) {
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
    setResult(null);
    setNotice("");
    if (localPreview) URL.revokeObjectURL(localPreview);
    setLocalPreview(file ? URL.createObjectURL(file) : "");
  }

  async function scanImage() {
    if (!selectedFile) {
      setNotice("Chọn một ảnh trước khi quét.");
      return;
    }
    const form = new FormData();
    form.append("file", selectedFile);
    setBusy(true);
    setNotice("");
    try {
      const response = await fetch(`${API_BASE}/api/scan-image`, {
        method: "POST",
        body: form,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Không quét được ảnh.");
      setResult(data);
      setNotice("Đã quét xong bằng model PaddleOCR/LayoutXLM.");
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
      setNotice("Đã xóa kết quả scan tạm.");
    } catch (error) {
      setNotice(`Lỗi: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  const fields = FIELD_ORDER.map((label) => {
    const found = result?.fields?.find((field) => field.label === label);
    return { label, value: found?.value || "" };
  });

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <section className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-5 py-6">
        <header className="flex flex-col gap-4 border-b border-zinc-800 pb-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-bold uppercase tracking-wider text-emerald-300">
              <ScanLine size={14} />
              Model-only field extractor
            </div>
            <h1 className="text-2xl font-black tracking-tight text-white">FinRecon Receipt AI</h1>
            <p className="mt-1 max-w-2xl text-sm text-zinc-400">
              Upload ảnh phiếu/hóa đơn bán lẻ để kiểm tra model nhận diện 4 field đã train.
            </p>
          </div>

          <button
            type="button"
            onClick={clearResults}
            disabled={busy}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm font-semibold text-zinc-200 transition hover:bg-zinc-800 disabled:opacity-50"
          >
            <Trash2 size={16} />
            Xóa kết quả tạm
          </button>
        </header>

        <div className="grid flex-1 grid-cols-1 gap-5 py-5 lg:grid-cols-[420px_1fr]">
          <aside className="flex flex-col gap-4">
            <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
              <div className="mb-4 flex items-center gap-2 text-sm font-bold text-white">
                <Camera size={18} className="text-emerald-300" />
                Ảnh đầu vào
              </div>

              <label className="flex min-h-[220px] cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-zinc-700 bg-zinc-950 p-4 text-center transition hover:border-emerald-500/70">
                {previewUrl ? (
                  <img src={previewUrl} alt="Ảnh cần quét" className="max-h-[320px] w-full object-contain" />
                ) : (
                  <>
                    <Upload className="mb-3 text-zinc-500" size={32} />
                    <span className="text-sm font-semibold text-zinc-300">Chọn ảnh để quét</span>
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

              <button
                type="button"
                onClick={scanImage}
                disabled={busy || !selectedFile}
                className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-3 text-sm font-bold text-zinc-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy ? <Loader2 className="animate-spin" size={18} /> : <ScanLine size={18} />}
                Quét bằng model
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
                Chế độ kiểm tra
              </div>
              <p className="text-xs leading-relaxed text-zinc-400">
                Màn hình này chỉ gọi checkpoint PaddleOCR/LayoutXLM đã train. Không dùng fallback, không regex,
                không tự sinh dữ liệu, không hiển thị field ngoài 4 nhãn train.
              </p>
            </div>
          </aside>

          <section className="flex min-h-0 flex-col gap-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {fields.map((field) => (
                <div key={field.label} className={`rounded-xl border p-4 ${fieldTone(field.label)}`}>
                  <div className="text-xs font-black uppercase tracking-widest opacity-70">{field.label}</div>
                  <div className="mt-3 min-h-[56px] text-lg font-extrabold leading-snug">
                    {field.value || <span className="text-sm font-semibold opacity-45">Chưa có kết quả</span>}
                  </div>
                </div>
              ))}
            </div>

            <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-2">
              <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                <h2 className="mb-3 text-sm font-bold text-white">Raw model labels</h2>
                <pre className="max-h-[520px] overflow-auto rounded-lg border border-zinc-800 bg-black/40 p-3 text-xs leading-relaxed text-zinc-300">
                  {result?.raw_text || "Chưa có output. Upload ảnh và bấm quét bằng model."}
                </pre>
              </div>

              <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                <h2 className="mb-3 text-sm font-bold text-white">Tokens</h2>
                <div className="max-h-[520px] overflow-auto rounded-lg border border-zinc-800">
                  <table className="w-full border-collapse text-left text-xs">
                    <thead className="sticky top-0 bg-zinc-900 text-zinc-500">
                      <tr>
                        <th className="border-b border-zinc-800 px-3 py-2">Label</th>
                        <th className="border-b border-zinc-800 px-3 py-2">Text</th>
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
