import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Banknote,
  CheckCircle2,
  ClipboardCheck,
  FileSpreadsheet,
  FileText,
  History,
  RefreshCw,
  Settings2,
  Upload,
  WandSparkles,
  Sun,
  Moon,
  Trash2,
  Activity,
  FileCheck,
  CreditCard,
  AlertCircle,
  Loader2,
  ChevronRight,
} from "lucide-react";

const API_BASE =
  import.meta.env.VITE_API_URL ||
  `${window.location.protocol}//${window.location.hostname || "127.0.0.1"}:8000`;

const defaultRules = {
  auto_match_threshold: 85,
  manual_review_threshold: 60,
  date_tolerance_days: 30,
  amount_tolerance_vnd: 500000,
  low_ocr_confidence_threshold: 80,
  vat_tolerance: 1,
};

const statusLabels = {
  pending: "Đang chờ",
  processing: "Đang xử lý",
  completed: "Hoàn tất",
  completed_with_errors: "Có lỗi",
  failed: "Thất bại",
  valid: "Hợp lệ",
  invalid: "Không hợp lệ",
  validated: "Đã kiểm soát",
  imported: "Đã import",
  parsed: "Đã parse",
  needs_review: "Cần kiểm tra",
  reviewed: "Đã review",
  rejected: "Từ chối",
  approved_for_payment: "Đã duyệt thanh toán",
  payment_scheduled: "Đã lên lịch trả",
  paid: "Đã thanh toán",
  reconciled: "Đã đối soát",
  matched: "Đã khớp",
  partially_matched: "Cần review",
  amount_mismatch: "Lệch tiền",
  unmatched_invoice: "Phiếu chưa thanh toán",
  unmatched_approved_invoice: "Phiếu chưa trả",
  unmatched_transaction: "Giao dịch chưa khớp",
  unmatched_bank_transaction: "CK chưa khớp",
  duplicate_invoice: "Trùng phiếu nhập",
  low_ocr_confidence: "Độ tin cậy thấp",
  low_confidence_fallback_extraction: "Trích xuất yếu",
  amount_mismatch_exception: "Lệch số tiền",
  inflow: "Tiền vào",
  outflow: "Tiền ra",
};

const steps = [
  {
    id: "rules",
    number: 1,
    label: "Cấu hình quy tắc",
    short: "Quy tắc",
    icon: Settings2,
  },
  {
    id: "vendors",
    number: 2,
    label: "Danh mục mối buôn",
    short: "Mối buôn",
    icon: FileSpreadsheet,
  },
  {
    id: "invoice-source",
    number: 3,
    label: "Phiếu nhập hàng",
    short: "Nhập hàng",
    icon: Upload,
  },
  {
    id: "prepayment",
    number: 4,
    label: "Kiểm tra phiếu nhập",
    short: "Kiểm tra",
    icon: ClipboardCheck,
  },
  {
    id: "payment",
    number: 5,
    label: "Bảng kê thanh toán",
    short: "Bảng kê",
    icon: Banknote,
  },
  {
    id: "bank",
    number: 6,
    label: "Sao kê ngân hàng",
    short: "Sao kê",
    icon: FileSpreadsheet,
  },
  {
    id: "reconcile",
    number: 7,
    label: "Đối soát thanh toán",
    short: "Đối soát",
    icon: AlertTriangle,
  },
  {
    id: "dashboard",
    number: 8,
    label: "Bảng điều khiển",
    short: "Báo cáo",
    icon: WandSparkles,
  },
];

function formatMoney(value, currency = "VND") {
  if (value === null || value === undefined || value === "") return "-";
  try {
    const num = Number(value);
    if (isNaN(num)) return value;
    if (currency === "VND") {
      return num.toLocaleString("vi-VN") + " ₫";
    }
    return num.toLocaleString("en-US", { style: "currency", currency });
  } catch (e) {
    return value;
  }
}

function formatQuantity(value) {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return value;
  return Number.isInteger(num) ? String(num) : num.toLocaleString("vi-VN", { maximumFractionDigits: 2 });
}

function StatusPill({ value }) {
  const label = statusLabels[value] || value || "-";
  let classes = "inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold ";

  if (["matched", "valid", "completed", "resolved", "validated", "approved", "approved_for_payment", "paid", "reconciled"].includes(value)) {
    classes += "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400 border border-emerald-200/40 dark:border-emerald-800/30";
  } else if (["needs_review", "partially_matched", "in_review", "open", "warning", "medium", "unmatched_invoice", "unmatched_approved_invoice"].includes(value)) {
    classes += "bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400 border border-amber-200/40 dark:border-amber-800/30";
  } else if (["failed", "invalid", "rejected", "critical", "high", "amount_mismatch", "unmatched_transaction", "unmatched_bank_transaction"].includes(value)) {
    classes += "bg-rose-50 text-rose-700 dark:bg-rose-950/30 dark:text-rose-400 border border-rose-200/40 dark:border-rose-800/30";
  } else {
    classes += "bg-slate-50 text-slate-600 dark:bg-zinc-800/50 dark:text-zinc-400 border border-slate-200/40 dark:border-zinc-700/30";
  }

  return <span className={classes}>{label}</span>;
}

function Metric({ icon: Icon, label, value, tone = "default" }) {
  let toneClasses = "premium-card p-4 flex items-center gap-3.5 ";
  let iconClasses = "p-2.5 rounded-lg ";

  if (tone === "good") {
    toneClasses += "bg-emerald-50/20 dark:bg-emerald-950/10 border-emerald-100/70 dark:border-emerald-900/20";
    iconClasses += "bg-emerald-100/70 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400";
  } else if (tone === "warn") {
    toneClasses += "bg-amber-50/20 dark:bg-amber-950/10 border-amber-100/70 dark:border-amber-900/20";
    iconClasses += "bg-amber-100/70 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400";
  } else if (tone === "danger") {
    toneClasses += "bg-rose-50/20 dark:bg-rose-950/10 border-rose-100/70 dark:border-rose-900/20";
    iconClasses += "bg-rose-100/70 text-rose-600 dark:bg-rose-900/30 dark:text-rose-400";
  } else {
    toneClasses += "bg-white dark:bg-zinc-900 border-slate-100 dark:border-zinc-800/60";
    iconClasses += "bg-slate-100 text-slate-500 dark:bg-zinc-800 dark:text-zinc-400";
  }

  return (
    <div className={toneClasses}>
      <div className={iconClasses}>
        <Icon size={18} />
      </div>
      <div>
        <p className="text-[10px] font-bold text-slate-400 dark:text-zinc-500 uppercase tracking-wider">{label}</p>
        <h4 className="text-base font-extrabold text-slate-800 dark:text-zinc-100 mt-0.5">{value}</h4>
      </div>
    </div>
  );
}

function DataTable({ columns, rows, empty = "Chưa có dữ liệu", pageSize = 12 }) {
  const [currentPage, setCurrentPage] = useState(1);

  useEffect(() => {
    setCurrentPage(1);
  }, [rows.length]);

  const totalPages = Math.ceil(rows.length / pageSize) || 1;

  const paginatedRows = useMemo(() => {
    const startIndex = (currentPage - 1) * pageSize;
    return rows.slice(startIndex, startIndex + pageSize);
  }, [rows, currentPage, pageSize]);

  return (
    <div className="table-container fade-in">
      <div className="table-wrap border border-slate-100 dark:border-zinc-800/80 rounded-xl overflow-x-auto shadow-xs">
        <table className="modern-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key}>{column.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedRows.length === 0 ? (
              <tr>
                <td className="empty-row" colSpan={columns.length}>
                  {empty}
                </td>
              </tr>
            ) : (
              paginatedRows.map((row, index) => (
                <tr key={row.id || `${row.invoice_id || row.transaction_id || row.payment_id || "row"}-${index}`}>
                  {columns.map((column) => (
                    <td key={column.key}>
                      {column.render ? column.render(row) : row[column.key] !== null && row[column.key] !== undefined ? String(row[column.key]) : "-"}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {rows.length > pageSize && (
        <div className="pagination mt-2 flex justify-between items-center">
          <button
            type="button"
            className="pag-btn text-xs px-3 py-1.5"
            onClick={() => setCurrentPage((prev) => Math.max(prev - 1, 1))}
            disabled={currentPage === 1}
          >
            Trước
          </button>
          <span className="pag-info text-xs">
            Trang <strong>{currentPage}</strong> / {totalPages}
          </span>
          <button
            type="button"
            className="pag-btn text-xs px-3 py-1.5"
            onClick={() => setCurrentPage((prev) => Math.min(prev + 1, totalPages))}
            disabled={currentPage === totalPages}
          >
            Sau
          </button>
        </div>
      )}
    </div>
  );
}

function Field({ label, name, value, onChange, type = "text" }) {
  return (
    <div className="flex flex-col gap-1 w-full">
      <span className="text-[10px] font-bold text-slate-400 dark:text-zinc-500 uppercase tracking-wider">{label}</span>
      <input
        className="input-field py-2 text-xs"
        type={type}
        name={name}
        value={value ?? ""}
        onChange={onChange}
      />
    </div>
  );
}

function UploadCard({ icon: Icon, title, helper, inputRef, accept, multiple, onSubmit, primary, selectedFiles, onSelectFiles, busy }) {
  const [localFiles, setLocalFiles] = useState(null);
  const filesToPreview = selectedFiles !== undefined ? selectedFiles : localFiles;
  const [previews, setPreviews] = useState([]);

  useEffect(() => {
    if (filesToPreview && filesToPreview.length > 0) {
      const newPreviews = Array.from(filesToPreview).map((file) => {
        if (file.type.startsWith("image/")) {
          return { name: file.name, url: URL.createObjectURL(file), type: "image" };
        }
        return { name: file.name, type: "other" };
      });
      setPreviews(newPreviews);
      return () => newPreviews.forEach((p) => p.url && URL.revokeObjectURL(p.url));
    } else {
      setPreviews([]);
    }
  }, [filesToPreview]);

  const handleFileChange = (e) => {
    if (onSelectFiles) {
      onSelectFiles(e.target.files);
    } else {
      setLocalFiles(e.target.files);
    }
  };

  return (
    <div className={`premium-card p-4 flex flex-col items-center text-center gap-2.5 transition-all duration-300 relative overflow-hidden group ${primary ? "border-emerald-500/20 bg-emerald-500/[0.01] dark:bg-emerald-500/[0.005]" : ""}`}>
      <div className={`p-2.5 rounded-full ${primary ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-400" : "bg-slate-100 text-slate-500 dark:bg-zinc-800 dark:text-zinc-400"} group-hover:scale-105 transition-transform duration-300`}>
        <Icon size={20} />
      </div>
      <div>
        <h4 className="font-bold text-slate-800 dark:text-zinc-100 text-xs">{title}</h4>
        <p className="text-[10px] text-slate-400 dark:text-zinc-500 mt-0.5 max-w-[200px] leading-relaxed">{helper}</p>
      </div>

      {previews.length > 0 && (
        <div className="flex flex-wrap justify-center gap-1.5 mt-1 w-full max-h-[90px] overflow-y-auto p-1 border border-dashed border-slate-100 dark:border-zinc-800 rounded-lg bg-slate-50/50 dark:bg-zinc-900/30">
          {previews.map((p, i) => (
            <div key={i} className="flex flex-col items-center p-1 bg-white dark:bg-zinc-800/80 border border-slate-100 dark:border-zinc-700/50 rounded-md w-[60px] shrink-0">
              {p.type === "image" ? (
                <img src={p.url} alt={p.name} className="w-8 h-8 object-cover rounded-sm border border-slate-100 dark:border-zinc-700" />
              ) : (
                <span className="text-lg h-8 flex items-center justify-center">📄</span>
              )}
              <span className="text-[8px] text-slate-400 dark:text-zinc-500 truncate w-full mt-0.5 px-0.5 text-center" title={p.name}>{p.name}</span>
            </div>
          ))}
        </div>
      )}

      <div className="w-full mt-1 flex flex-col gap-1.5">
        <label className="btn-secondary w-full py-1 cursor-pointer text-[11px] flex items-center justify-center gap-1">
          <span>Chọn tệp</span>
          <input
            ref={inputRef}
            type="file"
            accept={accept}
            multiple={multiple}
            onChange={handleFileChange}
            className="hidden"
          />
        </label>
        {filesToPreview && filesToPreview.length > 0 && (
          <button
            type="button"
            onClick={onSubmit}
            disabled={busy}
            className="btn-primary w-full py-1 text-[11px] flex items-center justify-center gap-1 shadow-sm"
          >
            {busy ? <Loader2 className="animate-spin" size={12} /> : <Upload size={12} />}
            <span>Tải lên ({filesToPreview.length})</span>
          </button>
        )}
      </div>
    </div>
  );
}

function QuickEditModal({ invoice, isOpen, onClose, onSave, busy }) {
  const [totalAmount, setTotalAmount] = useState("");
  const [vendorName, setVendorName] = useState("");
  const [vendorAddress, setVendorAddress] = useState("");
  const [vendorPhone, setVendorPhone] = useState("");
  const [invoiceDate, setInvoiceDate] = useState("");
  const [buyerName, setBuyerName] = useState("");

  useEffect(() => {
    if (invoice) {
      setTotalAmount(invoice.total_amount || "");
      setVendorName(invoice.vendor_name || "");
      setVendorAddress(invoice.vendor_address || "");
      setVendorPhone(invoice.vendor_phone || "");
      setInvoiceDate(invoice.invoice_date || "");
      setBuyerName(invoice.buyer_name || "");
    }
  }, [invoice]);

  if (!isOpen || !invoice) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 dark:bg-black/60 backdrop-blur-sm fade-in">
      <div className="bg-white dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 rounded-2xl p-5 w-full max-w-4xl shadow-xl slide-up flex flex-col max-h-[90vh]">
        <div className="flex justify-between items-center pb-2.5 border-b border-slate-100 dark:border-zinc-800/80">
          <h3 className="text-sm font-bold text-slate-800 dark:text-zinc-100 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            Chi tiết phiếu nhập hàng (OCR)
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-zinc-200 text-sm">✕</button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-5 py-4 overflow-y-auto min-h-0 flex-1">
          {/* LEFT COLUMN: METADATA & EDIT FIELDS (col-span-5) */}
          <div className="md:col-span-5 flex flex-col gap-3.5 pr-2 border-r border-slate-100 dark:border-zinc-800/80">
            <h4 className="text-[10px] font-extrabold text-slate-400 dark:text-zinc-500 uppercase tracking-widest pb-1 border-b border-slate-100 dark:border-zinc-850">
              Thông tin chung
            </h4>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <span className="text-[9px] font-bold text-slate-400 dark:text-zinc-500 uppercase tracking-wider">Mã Phiếu</span>
                <input className="input-field opacity-60 bg-slate-50 dark:bg-zinc-800/60 py-1 text-xs" value={invoice.invoice_number || ""} disabled />
              </div>

              <div className="flex flex-col gap-1">
                <span className="text-[9px] font-bold text-slate-400 dark:text-zinc-500 uppercase tracking-wider">Ngày Lập</span>
                <input className="input-field py-1 text-xs" type="date" value={invoiceDate} onChange={(e) => setInvoiceDate(e.target.value)} />
              </div>
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-[9px] font-bold text-slate-400 dark:text-zinc-500 uppercase tracking-wider">Mối Buôn (Người bán)</span>
              <input className="input-field py-1 text-xs" value={vendorName} onChange={(e) => setVendorName(e.target.value)} />
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-[9px] font-bold text-slate-400 dark:text-zinc-500 uppercase tracking-wider">Địa chỉ Mối Buôn</span>
              <input className="input-field py-1 text-xs" value={vendorAddress} onChange={(e) => setVendorAddress(e.target.value)} />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <span className="text-[9px] font-bold text-slate-400 dark:text-zinc-500 uppercase tracking-wider">Số Điện Thoại</span>
                <input className="input-field py-1 text-xs" value={vendorPhone} onChange={(e) => setVendorPhone(e.target.value)} />
              </div>

              <div className="flex flex-col gap-1">
                <span className="text-[9px] font-bold text-slate-400 dark:text-zinc-500 uppercase tracking-wider">Tổng tiền (VND)</span>
                <input className="input-field py-1 text-xs" type="number" value={totalAmount} onChange={(e) => setTotalAmount(e.target.value)} />
              </div>
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-[9px] font-bold text-slate-400 dark:text-zinc-500 uppercase tracking-wider">Người mua (Khách hàng)</span>
              <input className="input-field py-1 text-xs" value={buyerName} onChange={(e) => setBuyerName(e.target.value)} />
            </div>
          </div>

          {/* RIGHT COLUMN: DETAILED ITEMS TABLE (col-span-7) */}
          <div className="md:col-span-7 flex flex-col gap-3.5">
            <h4 className="text-[10px] font-extrabold text-slate-400 dark:text-zinc-500 uppercase tracking-widest pb-1 border-b border-slate-100 dark:border-zinc-850">
              Chi tiết mặt hàng ({invoice.items?.length || 0})
            </h4>

            {invoice.items && invoice.items.length > 0 ? (
              <div className="border border-slate-100 dark:border-zinc-800 rounded-xl overflow-hidden shadow-xs flex-1 min-h-[200px] overflow-y-auto">
                <table className="modern-table">
                  <thead>
                    <tr>
                      <th className="py-1.5 text-[10px] w-12">STT</th>
                      <th className="py-1.5 text-[10px]">Tên Hàng</th>
                      <th className="py-1.5 text-[10px] text-right w-16">SL</th>
                      <th className="py-1.5 text-[10px] text-right w-24">Đơn Giá</th>
                      <th className="py-1.5 text-[10px] text-right w-24">Thành Tiền</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invoice.items.map((item, index) => (
                      <tr key={item.id || index}>
                        <td className="py-1.5 text-center text-xs">{index + 1}</td>
                        <td className="py-1.5 text-xs text-slate-700 dark:text-zinc-300 font-medium">{item.description}</td>
                        <td className="py-1.5 text-right text-xs">{formatQuantity(item.quantity)}</td>
                        <td className="py-1.5 text-right text-xs font-mono">{formatMoney(item.unit_price, invoice.currency)}</td>
                        <td className="py-1.5 text-right text-xs font-bold font-mono text-slate-800 dark:text-zinc-100">
                          {formatMoney(item.amount || (item.quantity * item.unit_price), invoice.currency)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center border border-dashed border-slate-200 dark:border-zinc-850 rounded-xl p-8 bg-slate-50/50 dark:bg-zinc-950/20">
                <span className="text-xs text-slate-400 dark:text-zinc-500 font-medium">Không phát hiện hàng hóa chi tiết</span>
                <span className="text-[10px] text-slate-400/80 dark:text-zinc-600 mt-1">Phiếu nhập không định dạng bảng hoặc ảnh mờ</span>
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-2.5 pt-3.5 border-t border-slate-100 dark:border-zinc-800/80">
          <button onClick={onClose} disabled={busy} className="btn-secondary py-1 px-3 text-xs">Hủy</button>
          <button
            onClick={() => onSave(invoice.id, {
              total_amount: totalAmount === "" ? null : Number(totalAmount),
              vendor_name: vendorName,
              vendor_address: vendorAddress,
              vendor_phone: vendorPhone,
              invoice_date: invoiceDate,
              buyer_name: buyerName
            })}
            disabled={busy}
            className="btn-primary py-1 px-3 text-xs flex items-center gap-1 shadow-sm"
          >
            {busy && <Loader2 className="animate-spin" size={12} />}
            Lưu thay đổi
          </button>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [activeStep, setActiveStep] = useState("rules");
  const [overview, setOverview] = useState({});
  const [vendors, setVendors] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [paymentBatches, setPaymentBatches] = useState([]);
  const [matches, setMatches] = useState([]);
  const [exceptions, setExceptions] = useState([]);
  const [batches, setBatches] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [rules, setRules] = useState(defaultRules);
  const [auditLogs, setAuditLogs] = useState([]);
  const [reports, setReports] = useState([]);
  const [reportText, setReportText] = useState("");
  const [exceptionDrafts, setExceptionDrafts] = useState({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [fallbackFiles, setFallbackFiles] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "light");
  const [editingInvoice, setEditingInvoice] = useState(null);

  const vendorFileRef = useRef(null);
  const invoiceRegisterRef = useRef(null);
  const attachmentFileRef = useRef(null);
  const paymentFileRef = useRef(null);
  const bankFileRef = useRef(null);
  const fallbackFilesRef = useRef(null);

  const active = steps.find((step) => step.id === activeStep) || steps[0];
  const activeIndex = steps.findIndex((step) => step.id === activeStep);

  const reviewInvoices = useMemo(
    () => invoices.filter((invoice) => ["needs_review", "invalid", "rejected"].includes(invoice.status) || invoice.validation_status !== "valid"),
    [invoices],
  );
  const approvedInvoices = useMemo(
    () => invoices.filter((invoice) => ["approved_for_payment", "payment_scheduled", "paid", "reconciled"].includes(invoice.status)),
    [invoices],
  );

  const flattenedInvoices = useMemo(() => {
    const list = [];
    invoices.forEach((inv) => {
      const items = inv.items || [];
      if (items.length === 0) {
        list.push({
          ...inv,
          _isFirst: true,
          _rowSpan: 1,
          _itemIndex: "-",
          _itemDescription: "-",
          _itemQuantity: "-",
          _itemUnitPrice: "-",
          _itemAmount: "-",
        });
      } else {
        items.forEach((item, index) => {
          list.push({
            ...inv,
            _isFirst: index === 0,
            _rowSpan: items.length,
            _itemIndex: index + 1,
            _itemDescription: item.description || "-",
            _itemQuantity: item.quantity !== null && item.quantity !== undefined ? item.quantity : "-",
            _itemUnitPrice: item.unit_price !== null && item.unit_price !== undefined ? item.unit_price : "-",
            _itemAmount: item.amount !== null && item.amount !== undefined ? item.amount : (item.quantity * item.unit_price) || "-",
          });
        });
      }
    });
    return list;
  }, [invoices]);

  useEffect(() => {
    if (theme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
    localStorage.setItem("theme", theme);
  }, [theme]);

  async function request(path, options = {}) {
    const headers = {
      ...(options.headers || {}),
    };
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Yêu cầu thất bại");
    }
    return res.json();
  }

  async function loadData() {
    try {
      const [over, vnds, invs, txs, pb, mtchs, excps, bts, jbs, rls, logs, rpts] = await Promise.all([
        request("/api/dashboard/summary"),
        request("/api/vendors"),
        request("/api/invoices"),
        request("/api/bank-transactions"),
        request("/api/payment-batches"),
        request("/api/reconciliation/results"),
        request("/api/exceptions"),
        request("/api/batches"),
        request("/api/jobs"),
        request("/api/rules"),
        request("/api/audit-logs"),
        request("/api/reports"),
      ]);
      setOverview(over);
      setVendors(vnds);
      setInvoices(invs);
      setTransactions(txs);
      setPaymentBatches(pb);
      setMatches(mtchs);
      setExceptions(excps);
      setBatches(bts);
      setJobs(jbs);
      setRules(rls);
      setAuditLogs(logs);
      setReports(rpts);
      if (rpts.length > 0) {
        setReportText(rpts[0].report_content || "");
      }
    } catch (e) {
      setNotice(`Không thể load dữ liệu: ${e.message}`);
    }
  }

  useEffect(() => {
    loadData();
    const timer = setInterval(() => {
      loadData();
    }, 60000);
    return () => clearInterval(timer);
  }, []);

  async function withBusy(action, successMessage = "") {
    setBusy(true);
    setNotice("");
    try {
      const res = await action();
      await loadData();
      if (successMessage) {
        setNotice(successMessage);
        setTimeout(() => setNotice(""), 4000);
      }
      return res;
    } catch (e) {
      setNotice(`Lỗi: ${e.message}`);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function refresh() {
    await withBusy(() => loadData(), "Đã cập nhật dữ liệu mới nhất");
  }

  async function importFile(file, endpoint, label) {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    await withBusy(() => request(endpoint, { method: "POST", body: form }), `Đã import ${label} thành công`);
  }

  async function uploadFallback(files) {
    if (!files?.length) return;
    setUploadProgress({ current: 0, total: files.length, currentFile: "Chuẩn bị...", success: 0, error: 0 });
    let successCount = 0;
    let errorCount = 0;
    setBusy(true);
    setNotice("");

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      setUploadProgress({ current: i + 1, total: files.length, currentFile: file.name, success: successCount, error: errorCount });

      const form = new FormData();
      form.append("files", file);

      try {
        const res = await request("/api/batches/invoices/upload", { method: "POST", body: form });
        if (res.errors && res.errors.length > 0) {
          errorCount++;
        } else {
          successCount++;
        }
      } catch (err) {
        errorCount++;
      }
    }

    setUploadProgress(null);
    setBusy(false);
    await refresh();
    setNotice(`Đã upload xong. Thành công: ${successCount}, Lỗi: ${errorCount}`);
  }

  async function uploadAttachment(file) {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("use_fallback_extraction", "true");
    await withBusy(() => request("/api/invoices/upload-attachment", { method: "POST", body: form }), "Đã tải lên tệp đính kèm thành công");
  }

  async function runValidation() {
    await withBusy(() => request("/api/validation/run", { method: "POST" }), "Đã chạy kiểm soát trước thanh toán");
  }

  async function approveInvoice(invoice) {
    const key = invoice.invoice_id || invoice.id;
    await withBusy(() => request(`/api/invoices/${key}/approve`, { method: "POST" }), "Đã duyệt phiếu nhập");
  }

  async function rejectInvoice(invoice) {
    const key = invoice.invoice_id || invoice.id;
    await withBusy(() => request(`/api/invoices/${key}/reject`, { method: "POST" }), "Đã từ chối phiếu nhập");
  }

  async function generatePaymentBatch() {
    await withBusy(
      () => request("/api/payment-batches/generate-from-approved-invoices", { method: "POST" }),
      "Đã sinh bảng kê từ phiếu nhập đã duyệt",
    );
  }

  async function runReconciliation() {
    await withBusy(() => request("/api/reconciliation/run", { method: "POST" }), "Đã chạy đối soát");
  }

  async function approveMatch(matchId) {
    await withBusy(() => request(`/api/reconciliation/${matchId}/approve`, { method: "POST" }), "Đã duyệt match");
  }

  async function rejectMatch(matchId) {
    await withBusy(() => request(`/api/reconciliation/${matchId}/reject`, { method: "POST" }), "Đã từ chối match");
  }

  async function updateException(exceptionId, fallbackStatus) {
    const draft = exceptionDrafts[exceptionId] || {};
    await withBusy(
      () =>
        request(`/api/exceptions/${exceptionId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            status: draft.status || fallbackStatus || "in_review",
            note: draft.note || "",
            resolved: (draft.status || fallbackStatus) === "resolved",
          }),
        }),
      "Đã cập nhật ngoại lệ",
    );
  }

  async function saveRules(event) {
    event.preventDefault();
    await withBusy(
      () =>
        request("/api/rules", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(rules),
        }),
      "Đã lưu cấu hình rule",
    );
  }

  async function generateReport() {
    const result = await withBusy(() => request("/api/reports/generate", { method: "POST" }), "Đã tạo báo cáo");
    if (result?.report) setReportText(result.report);
  }

  async function clearData(endpoint, label) {
    if (window.confirm(`Bạn có chắc chắn muốn xóa toàn bộ dữ liệu ${label} không?`)) {
      await withBusy(
        () => request(endpoint, { method: "DELETE" }),
        `Đã xóa toàn bộ ${label}`
      );
    }
  }

  function quickEditInvoice(invoice) {
    setEditingInvoice(invoice);
  }

  function nextStep() {
    setActiveStep(steps[Math.min(activeIndex + 1, steps.length - 1)].id);
  }

  function previousStep() {
    setActiveStep(steps[Math.max(activeIndex - 1, 0)].id);
  }

  return (
    <main className="min-h-screen flex bg-slate-50 dark:bg-zinc-950 transition-colors duration-300">

      {/* LEFT SIDEBAR NAVIGATION */}
      <aside className="w-64 bg-slate-900 dark:bg-zinc-900 text-slate-100 flex flex-col shrink-0 border-r border-slate-800/40 sticky top-0 h-screen z-10">

        {/* BRAND LOGO */}
        <div className="p-5 border-b border-slate-800/60 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-emerald-500/10 text-emerald-400 rounded-lg border border-emerald-500/20 shadow-sm">
              <Banknote size={18} className="animate-pulse" />
            </div>
            <div>
              <strong className="text-sm font-extrabold tracking-tight bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent">FinRecon Receipt AI</strong>
              <span className="block text-[9px] text-slate-550 dark:text-zinc-400 font-bold tracking-wider uppercase">F&B Receipt Control</span>
            </div>
          </div>
          <button
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            className="p-1.5 bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 dark:text-zinc-300 rounded-lg transition-all duration-200 border border-slate-700/30"
            title="Đổi giao diện"
          >
            {theme === "light" ? <Moon size={14} /> : <Sun size={14} />}
          </button>
        </div>

        {/* NAVIGATION LIST */}
        <nav className="flex-1 overflow-y-auto px-3 py-4 flex flex-col gap-1 scrollbar-thin">
          {steps.map(({ id, number, label, short, icon: Icon }) => {
            const isActive = activeStep === id;
            return (
              <button
                key={id}
                onClick={() => setActiveStep(id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 text-left border relative group ${
                  isActive
                    ? "bg-emerald-600/10 dark:bg-emerald-500/10 text-emerald-400 border-emerald-500/30 font-semibold"
                    : "bg-transparent text-slate-400 hover:text-slate-200 border-transparent hover:bg-slate-800/40"
                }`}
              >
                <div className={`w-5.5 h-5.5 rounded-full flex items-center justify-center text-[9px] font-bold border transition-colors ${
                  isActive
                    ? "bg-emerald-500 text-slate-900 border-emerald-400"
                    : "bg-slate-800/80 text-slate-400 border-slate-700 group-hover:border-slate-500 group-hover:text-slate-200"
                }`}>
                  {number}
                </div>
                <Icon size={14} className={isActive ? "text-emerald-400" : "text-slate-500 group-hover:text-slate-300"} />
                <div className="min-w-0">
                  <p className="text-[11px] leading-none font-bold text-slate-100">{label}</p>
                </div>
                {isActive && (
                  <div className="absolute right-2.5 w-1 h-1 bg-emerald-400 rounded-full shadow-lg shadow-emerald-400/50" />
                )}
              </button>
            );
          })}
        </nav>

        {/* SIDEBAR FOOTER */}
        <div className="p-3 border-t border-slate-800/60 bg-slate-950/20 flex flex-col gap-1.5">
          <div className="flex items-center gap-2 px-2 py-1.5 bg-slate-800/40 dark:bg-zinc-800/40 border border-slate-800 dark:border-zinc-800 rounded-lg">
            <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-ping" />
            <span className="text-[10px] font-semibold text-slate-300">Hoạt động bình thường</span>
          </div>
          <button
            onClick={() => refresh()}
            disabled={busy}
            className="w-full btn-secondary py-1.5 text-[11px] flex items-center justify-center gap-1 shadow-sm"
          >
            {busy ? <Loader2 className="animate-spin" size={11} /> : <RefreshCw size={11} />}
            Làm mới dữ liệu
          </button>
        </div>
      </aside>

      {/* MAIN WORKSPACE PANEL */}
      <section className="flex-1 flex flex-col min-w-0 h-screen overflow-y-auto relative">

        {/* WORKSPACE HEADER */}
        <header className="p-4 border-b border-slate-200/50 dark:border-zinc-800/60 flex justify-between items-center gap-4 bg-white/60 dark:bg-zinc-900/40 backdrop-blur-md sticky top-0 z-10">
          <div>
            <div className="flex items-center gap-2.5 text-[10px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-widest">
              <span>Bước {active.number} của {steps.length}</span>
              <ChevronRight size={10} />
              <span>{active.short}</span>
            </div>
            <h1 className="text-lg font-extrabold text-slate-800 dark:text-zinc-100 mt-0.5">{active.label}</h1>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => refresh()}
              disabled={busy}
              className="p-2 bg-white dark:bg-zinc-800 hover:bg-slate-50 dark:hover:bg-zinc-700 text-slate-600 dark:text-zinc-300 rounded-xl transition-all duration-200 border border-slate-200 dark:border-zinc-700/60 shadow-xs"
              title="Làm mới"
            >
              <RefreshCw size={14} className={busy ? "animate-spin" : ""} />
            </button>
          </div>
        </header>

        {/* WORKSPACE BODY */}
        <div className="flex-1 p-5 space-y-5">

          {/* FLOATING NOTICE BOX */}
          {notice && (
            <div className="fade-in bg-slate-900 dark:bg-zinc-900 text-slate-100 border border-slate-800 dark:border-zinc-800 p-3 rounded-xl shadow-lg flex items-center justify-between gap-3 max-w-md mx-auto fixed bottom-5 right-5 z-50">
              <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
                <p className="text-[11px] font-semibold leading-none">{notice}</p>
              </div>
              <button onClick={() => setNotice("")} className="text-slate-400 hover:text-slate-200 text-xs">✕</button>
            </div>
          )}

          {/* STEP 1: RULES CONFIGURATION */}
          {activeStep === "rules" && (
            <div className="space-y-5 slide-up">
              <form className="premium-card p-5 space-y-5" onSubmit={saveRules}>
                <div className="pb-3 border-b border-slate-100 dark:border-zinc-800/80">
                  <h2 className="text-sm font-bold text-slate-800 dark:text-zinc-100">Thiết lập quy tắc đối soát</h2>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <Field label="Ngưỡng tự động khớp (%)" name="auto_match_threshold" type="number" value={rules.auto_match_threshold} onChange={(e) => setRules({ ...rules, auto_match_threshold: Number(e.target.value) })} />
                  <Field label="Ngưỡng cần review (%)" name="manual_review_threshold" type="number" value={rules.manual_review_threshold} onChange={(e) => setRules({ ...rules, manual_review_threshold: Number(e.target.value) })} />
                  <Field label="Dung sai ngày thanh toán (ngày)" name="date_tolerance_days" type="number" value={rules.date_tolerance_days} onChange={(e) => setRules({ ...rules, date_tolerance_days: Number(e.target.value) })} />
                  <Field label="Dung sai lệch tiền (VND)" name="amount_tolerance_vnd" type="number" value={rules.amount_tolerance_vnd} onChange={(e) => setRules({ ...rules, amount_tolerance_vnd: Number(e.target.value) })} />
                  <Field label="Ngưỡng cảnh báo OCR (%)" name="low_ocr_confidence_threshold" type="number" value={rules.low_ocr_confidence_threshold} onChange={(e) => setRules({ ...rules, low_ocr_confidence_threshold: Number(e.target.value) })} />
                  <Field label="Dung sai lệch thuế VAT (VND)" name="vat_tolerance" type="number" value={rules.vat_tolerance} onChange={(e) => setRules({ ...rules, vat_tolerance: Number(e.target.value) })} />
                </div>

                <div className="flex justify-end pt-3 border-t border-slate-100 dark:border-zinc-800/80">
                  <button type="submit" disabled={busy} className="btn-primary py-1.5 px-5 text-xs flex items-center gap-1 shadow-sm">
                    {busy && <Loader2 className="animate-spin" size={12} />}
                    Lưu quy tắc
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* STEP 2: VENDORS MASTER */}
          {activeStep === "vendors" && (
            <div className="space-y-5 slide-up">
              <div className="premium-card p-5 space-y-4">
                <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-3 pb-3 border-b border-slate-100 dark:border-zinc-800/80">
                  <div>
                    <h2 className="text-sm font-bold text-slate-800 dark:text-zinc-100">Danh mục mối buôn ({vendors.length})</h2>
                  </div>
                  {vendors.length > 0 && (
                    <button onClick={() => clearData("/api/vendors", "mối buôn")} disabled={busy} className="btn-secondary py-1 text-xs text-rose-600 dark:text-rose-400 flex items-center gap-1">
                      <Trash2 size={12} />
                      Xóa tất cả
                    </button>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <UploadCard
                    icon={FileSpreadsheet}
                    title="Import mối buôn (Excel/CSV)"
                    helper="Nguồn đối chiếu mã số thuế và tài khoản ngân hàng."
                    inputRef={vendorFileRef}
                    accept=".csv,.xlsx,.xls"
                    onSubmit={() => importFile(vendorFileRef.current?.files?.[0], "/api/vendors/import", "vendor master")}
                    primary
                    busy={busy}
                  />
                </div>

                <DataTable
                  rows={vendors}
                  pageSize={10}
                  empty="Chưa có thông tin mối buôn nào"
                  columns={[
                    { key: "vendor_id", label: "Mã Mối" },
                    { key: "vendor_name", label: "Tên mối buôn" },
                    { key: "tax_code", label: "MST" },
                    { key: "bank_name", label: "Ngân hàng" },
                    { key: "bank_account", label: "Số tài khoản" },
                    { key: "bank_account_holder", label: "Chủ tài khoản" },
                    { key: "status", label: "Trạng thái", render: (row) => <StatusPill value={row.status} /> },
                  ]}
                />
              </div>
            </div>
          )}

          {/* STEP 3: RECEIPT UPLOAD & OCR */}
          {activeStep === "invoice-source" && (
            <div className="premium-card p-5 space-y-4 slide-up">
              <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-3 pb-3 border-b border-slate-100 dark:border-zinc-800/80">
                <div>
                  <h2 className="text-sm font-bold text-slate-800 dark:text-zinc-100">Tải lên phiếu nhập hàng ({invoices.length})</h2>
                </div>
                {invoices.length > 0 && (
                  <button onClick={() => clearData("/api/invoices", "phiếu nhập")} disabled={busy} className="btn-secondary py-1 text-xs text-rose-600 dark:text-rose-400 flex items-center gap-1">
                    <Trash2 size={12} />
                    Xóa tất cả
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <UploadCard
                  icon={Upload}
                  title="Ảnh chụp phiếu viết tay & PDF (OCR)"
                  helper="Hệ thống quét OCR tự động để đọc số tiền, mã phiếu."
                  inputRef={fallbackFilesRef}
                  accept=".pdf,.png,.jpg,.jpeg,.txt,.xml"
                  multiple
                  selectedFiles={fallbackFiles}
                  onSelectFiles={(files) => setFallbackFiles(files)}
                  onSubmit={() => {
                    uploadFallback(fallbackFiles || fallbackFilesRef.current?.files).then(() => {
                      setFallbackFiles(null);
                      if (fallbackFilesRef.current) fallbackFilesRef.current.value = "";
                    });
                  }}
                  primary
                  busy={busy}
                />
                <UploadCard
                  icon={FileSpreadsheet}
                  title="Bảng kê điện tử Excel/CSV"
                  helper="Nhập trực tiếp danh sách phiếu nhập từ tệp bảng kê."
                  inputRef={invoiceRegisterRef}
                  accept=".csv,.xlsx,.xls"
                  onSubmit={() => importFile(invoiceRegisterRef.current?.files?.[0], "/api/invoices/import-register", "bảng kê phiếu nhập")}
                  busy={busy}
                />
              </div>

              <DataTable
                rows={flattenedInvoices}
                pageSize={20}
                empty="Chưa có phiếu nhập nào được tải lên"
                columns={[
                  {
                    key: "invoice_number",
                    label: "Mã Phiếu",
                    render: (row) => row._isFirst ? <span className="font-bold text-slate-800 dark:text-zinc-100">{row.invoice_number}</span> : ""
                  },
                  {
                    key: "invoice_date",
                    label: "Ngày",
                    render: (row) => row._isFirst ? (row.invoice_date || "-") : ""
                  },
                  {
                    key: "vendor_name",
                    label: "Nhà cung cấp",
                    render: (row) => row._isFirst ? <span className="font-medium text-slate-700 dark:text-zinc-300">{row.vendor_name}</span> : ""
                  },
                  {
                    key: "_itemIndex",
                    label: "STT",
                    render: (row) => <span className="text-slate-400 dark:text-zinc-500">{row._itemIndex}</span>
                  },
                  {
                    key: "_itemDescription",
                    label: "Tên hàng",
                    render: (row) => <span className="font-medium text-slate-700 dark:text-zinc-300">{row._itemDescription}</span>
                  },
                  {
                    key: "_itemQuantity",
                    label: "SL",
                    render: (row) => formatQuantity(row._itemQuantity)
                  },
                  {
                    key: "_itemUnitPrice",
                    label: "Đơn giá",
                    render: (row) => typeof row._itemUnitPrice === "number" ? formatMoney(row._itemUnitPrice, row.currency) : row._itemUnitPrice
                  },
                  {
                    key: "_itemAmount",
                    label: "Thành tiền",
                    render: (row) => typeof row._itemAmount === "number" ? formatMoney(row._itemAmount, row.currency) : row._itemAmount
                  },
                  {
                    key: "total_amount",
                    label: "Tổng tiền",
                    render: (row) => row._isFirst ? <span className="font-bold text-slate-800 dark:text-zinc-100">{formatMoney(row.total_amount, row.currency)}</span> : ""
                  },
                  {
                    key: "status",
                    label: "Trạng thái",
                    render: (row) => row._isFirst ? <StatusPill value={row.status} /> : ""
                  },
                  {
                    key: "actions",
                    label: "Hành động",
                    render: (row) => {
                      if (!row._isFirst) return "";
                      return (
                        <button onClick={() => quickEditInvoice(row)} disabled={busy} className="btn-secondary py-0.5 px-2 text-[10px] rounded-md">
                          Sửa nhanh
                        </button>
                      );
                    }
                  },
                ]}
              />
            </div>
          )}

          {/* STEP 4: PRE-PAYMENT VALIDATION */}
          {activeStep === "prepayment" && (
            <div className="premium-card p-5 space-y-4 slide-up">
              <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-3 pb-3 border-b border-slate-100 dark:border-zinc-800/80">
                <div>
                  <h2 className="text-sm font-bold text-slate-800 dark:text-zinc-100">Kiểm tra lỗi phiếu nhập</h2>
                </div>
                <button onClick={runValidation} disabled={busy} className="btn-primary py-1.5 px-4 text-xs flex items-center gap-1 shadow-sm">
                  {busy ? <Loader2 className="animate-spin" size={12} /> : <FileCheck size={12} />}
                  Chạy kiểm tra
                </button>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <Metric icon={FileText} label="Tổng phiếu" value={invoices.length} />
                <Metric icon={CheckCircle2} label="Phiếu Hợp lệ" value={invoices.filter((item) => item.status === "validated").length} tone="good" />
                <Metric icon={AlertTriangle} label="Có lỗi/cảnh báo" value={reviewInvoices.length} tone="warn" />
                <Metric icon={Banknote} label="Đã duyệt chi" value={approvedInvoices.length} />
              </div>

              <DataTable
                rows={invoices}
                pageSize={12}
                empty="Chưa có dữ liệu phiếu nhập để đối chiếu"
                columns={[
                  { key: "invoice_number", label: "Mã Phiếu" },
                  { key: "vendor_name", label: "Mối buôn" },
                  { key: "total_amount", label: "Tổng tiền", render: (row) => formatMoney(row.total_amount, row.currency) },
                  { key: "validation_status", label: "Kết quả quét", render: (row) => <StatusPill value={row.validation_status} /> },
                  { key: "status", label: "Trạng thái", render: (row) => <StatusPill value={row.status} /> },
                  {
                    key: "actions",
                    label: "Hành động",
                    render: (row) => (
                      <div className="flex gap-1.5">
                        <button onClick={() => approveInvoice(row)} disabled={busy} className="btn-primary py-0.5 px-2 text-[10px] rounded-md">
                          Duyệt
                        </button>
                        <button onClick={() => rejectInvoice(row)} disabled={busy} className="btn-secondary text-rose-600 dark:text-rose-400 py-0.5 px-2 text-[10px] rounded-md">
                          Từ chối
                        </button>
                      </div>
                    ),
                  },
                ]}
              />
            </div>
          )}

          {/* STEP 5: PAYMENT BATCH */}
          {activeStep === "payment" && (
            <div className="premium-card p-5 space-y-4 slide-up">
              <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-3 pb-3 border-b border-slate-100 dark:border-zinc-800/80">
                <div>
                  <h2 className="text-sm font-bold text-slate-800 dark:text-zinc-100">Bảng kê thanh toán chuyển khoản</h2>
                </div>
                <div className="flex gap-2">
                  <button onClick={generatePaymentBatch} disabled={busy} className="btn-primary py-1.5 px-4 text-xs flex items-center gap-1 shadow-sm">
                    {busy ? <Loader2 className="animate-spin" size={12} /> : <CreditCard size={12} />}
                    Sinh bảng kê
                  </button>
                  {paymentBatches.length > 0 && (
                    <button onClick={() => clearData("/api/payment-batches", "bảng kê")} disabled={busy} className="btn-secondary text-rose-600 dark:text-rose-400 py-1.5 px-3 text-xs flex items-center gap-1">
                      <Trash2 size={12} />
                      Xóa bảng kê
                    </button>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <UploadCard
                  icon={ClipboardCheck}
                  title="Import bảng kê (Excel)"
                  helper="Nhập bảng kê chuyển khoản nếu tạo từ hệ thống khác."
                  inputRef={paymentFileRef}
                  accept=".csv,.xlsx,.xls"
                  onSubmit={() => importFile(paymentFileRef.current?.files?.[0], "/api/payment-batches/import", "bảng kê")}
                  busy={busy}
                />
              </div>

              <div className="grid grid-cols-2 gap-3 max-w-md">
                <Metric icon={ClipboardCheck} label="Số dòng bảng kê" value={paymentBatches.length} />
                <Metric icon={CheckCircle2} label="Chờ trả tiền" value={paymentBatches.filter((item) => item.approval_status === "approved").length} tone="good" />
              </div>

              <DataTable
                rows={paymentBatches}
                pageSize={12}
                empty="Chưa có bảng kê thanh toán nào"
                columns={[
                  { key: "payment_id", label: "Mã Bảng kê" },
                  { key: "vendor_id", label: "Mối buôn" },
                  { key: "scheduled_payment_date", label: "Ngày chi dự kiến" },
                  { key: "approved_amount", label: "Tiền duyệt chi", render: (row) => formatMoney(row.approved_amount, row.currency) },
                  { key: "approval_status", label: "Trạng thái", render: (row) => <StatusPill value={row.approval_status} /> },
                ]}
              />
            </div>
          )}

          {/* STEP 6: BANK STATEMENT */}
          {activeStep === "bank" && (
            <div className="premium-card p-5 space-y-4 slide-up">
              <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-3 pb-3 border-b border-slate-100 dark:border-zinc-800/80">
                <div>
                  <h2 className="text-sm font-bold text-slate-800 dark:text-zinc-100">Sao kê tài khoản ngân hàng</h2>
                </div>
                {transactions.length > 0 && (
                  <button onClick={() => clearData("/api/bank-transactions", "giao dịch ngân hàng")} disabled={busy} className="btn-secondary py-1 text-xs text-rose-600 dark:text-rose-400 flex items-center gap-1">
                    <Trash2 size={12} />
                    Xóa tất cả
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <UploadCard
                  icon={Banknote}
                  title="Tải lên tệp sao kê ngân hàng (Excel/CSV)"
                  helper="Nhập lịch sử biến động số dư thực tế."
                  inputRef={bankFileRef}
                  accept=".csv,.xlsx,.xls"
                  onSubmit={() => importFile(bankFileRef.current?.files?.[0], "/api/bank-transactions/import", "sao kê ngân hàng")}
                  primary
                  busy={busy}
                />
              </div>

              <div className="grid grid-cols-2 gap-3 max-w-md">
                <Metric icon={Banknote} label="Tổng giao dịch" value={transactions.length} />
                <Metric icon={FileSpreadsheet} label="Giao dịch chi ra (Outflow)" value={transactions.filter((item) => item.direction === "outflow").length} />
              </div>

              <DataTable
                rows={transactions}
                pageSize={12}
                empty="Chưa có dữ liệu sao kê tài khoản"
                columns={[
                  { key: "transaction_id", label: "Mã GD" },
                  { key: "transaction_date", label: "Ngày" },
                  { key: "description", label: "Nội dung chuyển khoản" },
                  { key: "amount", label: "Số tiền", render: (row) => formatMoney(row.amount, row.currency) },
                  { key: "direction", label: "Loại GD", render: (row) => <StatusPill value={row.direction} /> },
                  { key: "reference_code", label: "Reference" },
                ]}
              />
            </div>
          )}

          {/* STEP 7: RECONCILIATION */}
          {activeStep === "reconcile" && (
            <div className="premium-card p-5 space-y-4 slide-up">
              <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-3 pb-3 border-b border-slate-100 dark:border-zinc-800/80">
                <div>
                  <h2 className="text-sm font-bold text-slate-800 dark:text-zinc-100">Đối soát chuyển khoản ngân hàng</h2>
                </div>
                <button onClick={runReconciliation} disabled={busy} className="btn-primary py-1.5 px-4 text-xs flex items-center gap-1 shadow-sm">
                  {busy ? <Loader2 className="animate-spin" size={12} /> : <Activity size={12} />}
                  Chạy đối soát
                </button>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <Metric icon={CheckCircle2} label="Khớp hoàn toàn" value={overview.matched_count || 0} tone="good" />
                <Metric icon={AlertTriangle} label="Lệch số tiền" value={overview.amount_mismatch_count || 0} tone="danger" />
                <Metric icon={FileText} label="Phiếu chưa trả tiền" value={overview.unmatched_invoice_count || 0} tone="warn" />
                <Metric icon={Banknote} label="Sao kê chưa khớp" value={overview.unmatched_transaction_count || 0} tone="danger" />
              </div>

              <div>
                <h3 className="text-xs font-bold text-slate-850 dark:text-zinc-100 mb-2 uppercase tracking-wider">Kết quả đối soát tự động</h3>
                <DataTable
                  rows={matches}
                  pageSize={10}
                  empty="Chưa chạy đối soát hoặc không tìm thấy kết quả"
                  columns={[
                    { key: "vendor_name", label: "Mối buôn" },
                    { key: "invoice_number", label: "Mã Phiếu" },
                    { key: "invoice_amount", label: "Tiền Phiếu", render: (row) => formatMoney(row.invoice_amount) },
                    { key: "transaction_description", label: "Nội dung CK" },
                    { key: "transaction_amount", label: "Tiền thực CK", render: (row) => formatMoney(row.transaction_amount) },
                    { key: "match_score", label: "Điểm khớp", render: (row) => `${row.match_score}/100` },
                    { key: "match_status", label: "Kết quả", render: (row) => <StatusPill value={row.match_status} /> },
                    { key: "amount_diff", label: "Chênh lệch", render: (row) => formatMoney(row.amount_diff || 0) },
                    { key: "reason", label: "Lý do đối soát" },
                    {
                      key: "actions",
                      label: "Xác thực",
                      render: (row) => (
                        <div className="flex gap-1">
                          <button onClick={() => approveMatch(row.id)} className="btn-primary py-0.5 px-2 text-[10px] rounded-md">
                            Duyệt
                          </button>
                          <button onClick={() => rejectMatch(row.id)} className="btn-secondary py-0.5 px-2 text-[10px] text-rose-600 dark:text-rose-400 rounded-md">
                            Lệch
                          </button>
                        </div>
                      ),
                    },
                  ]}
                />
              </div>

              <div className="pt-2">
                <h3 className="text-xs font-bold text-slate-850 dark:text-zinc-100 mb-2 uppercase tracking-wider">Ngoại lệ & Lỗi giao dịch cần xử lý</h3>
                <DataTable
                  rows={exceptions}
                  pageSize={10}
                  empty="Không phát hiện lỗi ngoại lệ nào"
                  columns={[
                    { key: "exception_type", label: "Loại lỗi", render: (row) => <StatusPill value={row.exception_type} /> },
                    { key: "severity", label: "Mức độ", render: (row) => <StatusPill value={row.severity} /> },
                    { key: "status", label: "Trạng thái", render: (row) => <StatusPill value={row.status} /> },
                    { key: "invoice_number", label: "Phiếu nhập" },
                    { key: "transaction_id", label: "Giao dịch" },
                    { key: "message", label: "Nội dung lỗi" },
                    {
                      key: "workflow",
                      label: "Quyết định",
                      render: (row) => (
                        <div className="flex items-center gap-1">
                          <select
                            className="bg-white dark:bg-zinc-800 border border-slate-200 dark:border-zinc-700/80 rounded-md py-0.5 px-1.5 text-[10px]"
                            value={exceptionDrafts[row.id]?.status || row.status || "open"}
                            onChange={(event) => setExceptionDrafts({ ...exceptionDrafts, [row.id]: { ...(exceptionDrafts[row.id] || {}), status: event.target.value } })}
                          >
                            <option value="open">Mở</option>
                            <option value="in_review">Rà soát</option>
                            <option value="resolved">Đã giải quyết</option>
                            <option value="dismissed">Bỏ qua</option>
                          </select>
                          <input
                            placeholder="Ghi chú..."
                            className="bg-white dark:bg-zinc-800 border border-slate-200 dark:border-zinc-700/80 rounded-md py-0.5 px-1.5 text-[10px] w-24 placeholder-slate-400"
                            value={exceptionDrafts[row.id]?.note || row.note || ""}
                            onChange={(event) => setExceptionDrafts({ ...exceptionDrafts, [row.id]: { ...(exceptionDrafts[row.id] || {}), note: event.target.value } })}
                          />
                          <button onClick={() => updateException(row.id, row.status)} className="btn-primary py-0.5 px-2 text-[10px] rounded-md">Lưu</button>
                        </div>
                      ),
                    },
                  ]}
                />
              </div>
            </div>
          )}

          {/* STEP 8: DASHBOARD & REPORTING */}
          {activeStep === "dashboard" && (
            <div className="space-y-5 slide-up">
              <div className="premium-card p-5 space-y-4">
                <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-3 pb-3 border-b border-slate-100 dark:border-zinc-800/80">
                  <div>
                    <h2 className="text-sm font-bold text-slate-800 dark:text-zinc-100">Báo cáo & Phân tích nghiệp vụ</h2>
                  </div>
                  <div className="flex flex-wrap gap-2 shrink-0">
                    <button onClick={generateReport} disabled={busy} className="btn-primary py-1.5 px-3 text-xs flex items-center gap-1 shadow-sm">
                      {busy ? <Loader2 className="animate-spin" size={12} /> : <WandSparkles size={12} />}
                      Tạo báo cáo AI
                    </button>
                    <a className="btn-secondary py-1.5 px-3 text-xs" href={`${API_BASE}/api/reports/export/reconciliation.xlsx`}>Tải báo cáo đối soát</a>
                    <a className="btn-secondary py-1.5 px-3 text-xs text-rose-600 dark:text-rose-400" href={`${API_BASE}/api/reports/export/exceptions.xlsx`}>Tải báo cáo ngoại lệ</a>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <Metric icon={FileText} label="Tổng phiếu nhập" value={overview.total_invoices || 0} />
                  <Metric icon={CheckCircle2} label="Tỷ lệ khớp tiền" value={`${overview.match_rate || overview.matched_rate || 0}%`} tone="good" />
                  <Metric icon={AlertTriangle} label="Ngoại lệ mở" value={overview.open_exceptions || 0} tone="warn" />
                  <Metric icon={Banknote} label="Tổng nợ hàng" value={formatMoney(overview.total_invoice_value || 0)} />
                  <Metric icon={Banknote} label="Đã thanh toán" value={formatMoney(overview.matched_value || 0)} tone="good" />
                  <Metric icon={Banknote} label="Chênh lệch" value={formatMoney(overview.unmatched_value || overview.total_unmatched_value || 0)} tone="danger" />
                  <Metric icon={FileSpreadsheet} label="Tổng giao dịch sao kê" value={overview.total_bank_transactions || 0} />
                  <Metric icon={WandSparkles} label="Độ tin cậy OCR" value={`${overview.average_ocr_confidence || 0}%`} />
                </div>
              </div>

              {reportText && (
                <div className="premium-card p-5 space-y-2.5">
                  <h3 className="text-xs font-bold text-slate-800 dark:text-zinc-100 flex items-center gap-1.5">
                    <WandSparkles size={14} className="text-purple-500" />
                    AI diễn giải số liệu đối soát
                  </h3>
                  <pre className="p-3 bg-slate-50 dark:bg-zinc-900/60 border border-slate-100 dark:border-zinc-800 text-[11px] font-sans leading-relaxed text-slate-700 dark:text-zinc-300 rounded-xl overflow-auto whitespace-pre-wrap max-h-[260px]">
                    {reportText}
                  </pre>
                </div>
              )}

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <div className="premium-card p-5 space-y-3">
                  <h3 className="text-xs font-bold text-rose-600 dark:text-rose-400 flex items-center gap-1.5 uppercase tracking-wider">
                    <AlertCircle size={14} />
                    Vendor có nhiều sai lệch
                  </h3>
                  <DataTable
                    rows={overview.top_vendor_exceptions || []}
                    pageSize={6}
                    empty="Không phát hiện sai lệch"
                    columns={[
                      { key: "vendor_name", label: "Mối buôn" },
                      { key: "count", label: "Số lượng lỗi" },
                    ]}
                  />
                </div>

                <div className="premium-card p-5 space-y-3">
                  <h3 className="text-xs font-bold text-slate-800 dark:text-zinc-100 flex items-center gap-1.5 uppercase tracking-wider">
                    <History size={14} className="text-indigo-500" />
                    Audit logs gần đây
                  </h3>
                  <DataTable
                    rows={auditLogs}
                    pageSize={6}
                    empty="Chưa ghi nhận hành động"
                    columns={[
                      { key: "action", label: "Hành động" },
                      { key: "entity_type", label: "Loại" },
                      { key: "created_at", label: "Thời gian" },
                    ]}
                  />
                </div>
              </div>

              <div className="premium-card p-5 space-y-3">
                <h3 className="text-xs font-bold text-slate-800 dark:text-zinc-100 flex items-center gap-1.5 uppercase tracking-wider">
                  <FileText size={14} className="text-emerald-500" />
                  Báo cáo đã sinh
                </h3>
                <DataTable
                  rows={reports}
                  pageSize={6}
                  empty="Chưa sinh báo cáo nào"
                  columns={[
                    { key: "report_type", label: "Loại" },
                    { key: "report_content", label: "Tóm tắt" },
                    { key: "created_at", label: "Thời gian tạo" },
                  ]}
                />
              </div>
            </div>
          )}
        </div>

        {/* STEP BUTTON FOOTER */}
        <footer className="p-4 border-t border-slate-200/50 dark:border-zinc-800/60 bg-white/60 dark:bg-zinc-900/40 backdrop-blur-md flex justify-between items-center sticky bottom-0 z-10">
          <button
            onClick={previousStep}
            disabled={activeIndex === 0}
            className="btn-secondary text-xs px-3.5 py-1.5"
          >
            Bước trước
          </button>
          <button
            onClick={nextStep}
            disabled={activeIndex === steps.length - 1}
            className="btn-primary text-xs px-3.5 py-1.5"
          >
            Bước tiếp theo
          </button>
        </footer>
      </section>

      {/* SEQUENTIAL OCR UPLOAD MODAL */}
      {uploadProgress && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 dark:bg-black/70 backdrop-blur-sm fade-in">
          <div className="bg-white dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 rounded-2xl p-5 w-full max-w-xs shadow-xl slide-up flex flex-col items-center">
            <div className="p-3 bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-400 rounded-full animate-bounce mb-3">
              <Upload size={22} />
            </div>
            <h3 className="text-sm font-bold text-slate-800 dark:text-zinc-100 text-center mb-1">Đang trích xuất OCR...</h3>

            <div className="w-full bg-slate-100 dark:bg-zinc-800 p-3 rounded-xl border border-slate-200/40 dark:border-zinc-700/40 space-y-3">
              <div className="flex justify-between items-center text-[11px]">
                <span className="font-semibold text-slate-600 dark:text-zinc-300 truncate w-3/4">Tệp: {uploadProgress.currentFile}</span>
                <span className="font-bold text-emerald-600 dark:text-emerald-400">{uploadProgress.current}/{uploadProgress.total}</span>
              </div>

              <div className="w-full bg-slate-200 dark:bg-zinc-700 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-emerald-500 h-full rounded-full transition-all duration-300"
                  style={{ width: `${(uploadProgress.current / uploadProgress.total) * 100}%` }}
                />
              </div>

              <div className="flex justify-between items-center text-[9px] font-bold text-slate-400 dark:text-zinc-500 pt-1.5 border-t border-slate-200/40 dark:border-zinc-700/40">
                <span className="text-emerald-600 dark:text-emerald-400">Thành công: {uploadProgress.success}</span>
                <span className="text-rose-600 dark:text-rose-400">Thất bại: {uploadProgress.error}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* QUICK EDIT INVOICE MODAL */}
      <QuickEditModal
        invoice={editingInvoice}
        isOpen={!!editingInvoice}
        onClose={() => setEditingInvoice(null)}
        onSave={async (invoiceId, updatedFields) => {
          await withBusy(() => request(`/api/invoices/${invoiceId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              ...editingInvoice,
              ...updatedFields,
              status: "needs_review",
              validation_status: "pending"
            })
          }), "Đã cập nhật phiếu nhập thành công");
          setEditingInvoice(null);
          await refresh();
        }}
        busy={busy}
      />

    </main>
  );
}
