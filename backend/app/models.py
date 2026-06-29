from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def now() -> datetime:
    return datetime.utcnow()


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    tax_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="accountant")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    vendor_id: Mapped[str | None] = mapped_column(String(64))
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tax_code: Mapped[str | None] = mapped_column(String(64), index=True)
    bank_account: Mapped[str | None] = mapped_column(String(64), index=True)
    bank_name: Mapped[str | None] = mapped_column(String(128))
    bank_account_holder: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class InvoiceBatch(Base):
    __tablename__ = "invoice_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    batch_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    batch_type: Mapped[str] = mapped_column(String(32), nullable=False, default="invoice")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processing")
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    completed_jobs: Mapped[int] = mapped_column(Integer, default=0)
    failed_jobs: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    uploaded_files: Mapped[list["UploadedFile"]] = relationship(back_populates="batch")
    jobs: Mapped[list["ProcessingJob"]] = relationship(back_populates="batch")


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("invoice_batches.id"), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(32))
    file_category: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    batch: Mapped[InvoiceBatch | None] = relationship(back_populates="uploaded_files")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("invoice_batches.id"), nullable=True)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_files.id"), nullable=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    batch: Mapped[InvoiceBatch | None] = relationship(back_populates="jobs")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("invoice_batches.id"), nullable=True)
    invoice_id: Mapped[str | None] = mapped_column(String(128), index=True)
    invoice_number: Mapped[str | None] = mapped_column(String(128), index=True)
    invoice_series: Mapped[str | None] = mapped_column(String(64))
    invoice_template_code: Mapped[str | None] = mapped_column(String(64))
    vendor_id: Mapped[str | None] = mapped_column(String(64), index=True)
    vendor_name: Mapped[str | None] = mapped_column(String(255))
    vendor_tax_code: Mapped[str | None] = mapped_column(String(64))
    vendor_bank_account: Mapped[str | None] = mapped_column(String(64))
    vendor_address: Mapped[str | None] = mapped_column(Text)
    vendor_phone: Mapped[str | None] = mapped_column(String(64))
    buyer_name: Mapped[str | None] = mapped_column(String(255))
    buyer_tax_code: Mapped[str | None] = mapped_column(String(64))
    invoice_date: Mapped[datetime | None] = mapped_column(Date)
    due_date: Mapped[datetime | None] = mapped_column(Date)
    subtotal: Mapped[float | None] = mapped_column(Float)
    vat_rate: Mapped[float | None] = mapped_column(Float)
    vat_amount: Mapped[float | None] = mapped_column(Float)
    total_amount: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="VND")
    status: Mapped[str] = mapped_column(String(64), default="imported")
    validation_status: Mapped[str] = mapped_column(String(64), default="pending")
    source_type: Mapped[str | None] = mapped_column(String(64))
    attachment_file: Mapped[str | None] = mapped_column(String(255))
    expected_case: Mapped[str | None] = mapped_column(String(128))
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    uploaded_file_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_files.id"), nullable=True)
    processing_job_id: Mapped[int | None] = mapped_column(ForeignKey("processing_jobs.id"), nullable=True)
    source_file_name: Mapped[str | None] = mapped_column(String(255))
    source_file_path: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    items: Mapped[list[InvoiceItem]] = relationship(back_populates="invoice", cascade="all, delete-orphan")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[float | None] = mapped_column(Float)
    unit_price: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    invoice: Mapped[Invoice] = relationship(back_populates="items")


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    __table_args__ = (UniqueConstraint("transaction_id", name="uq_bank_transactions_transaction_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("invoice_batches.id"), nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(String(128), index=True)
    transaction_date: Mapped[datetime | None] = mapped_column(Date)
    value_date: Mapped[datetime | None] = mapped_column(Date)
    account_number: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    direction: Mapped[str | None] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(8), default="VND")
    balance_after: Mapped[float | None] = mapped_column(Float)
    counterparty_name: Mapped[str | None] = mapped_column(String(255))
    counterparty_account: Mapped[str | None] = mapped_column(String(64))
    bank_account: Mapped[str | None] = mapped_column(String(64))
    reference_code: Mapped[str | None] = mapped_column(String(128))
    expected_case: Mapped[str | None] = mapped_column(String(128))
    validation_status: Mapped[str] = mapped_column(String(64), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class PaymentBatch(Base):
    __tablename__ = "payment_batches"
    __table_args__ = (UniqueConstraint("payment_id", name="uq_payment_batches_payment_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("invoice_batches.id"), nullable=True)
    payment_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    invoice_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    invoice_db_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"))
    vendor_id: Mapped[str | None] = mapped_column(String(64), index=True)
    scheduled_payment_date: Mapped[datetime | None] = mapped_column(Date)
    approved_amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="VND")
    approval_status: Mapped[str] = mapped_column(String(32), default="draft")
    approved_by: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    payment_method: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class ReconciliationMatch(Base):
    __tablename__ = "reconciliation_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"))
    bank_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("bank_transactions.id", ondelete="SET NULL"))
    match_score: Mapped[float | None] = mapped_column(Float)
    match_status: Mapped[str | None] = mapped_column(String(64))
    amount_diff: Mapped[float | None] = mapped_column(Float)
    date_diff: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class ReconciliationException(Base):
    __tablename__ = "reconciliation_exceptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"))
    bank_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("bank_transactions.id", ondelete="SET NULL"))
    exception_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open")
    note: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class ReconciliationRule(Base):
    __tablename__ = "reconciliation_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    auto_match_threshold: Mapped[float] = mapped_column(Float, default=85)
    manual_review_threshold: Mapped[float] = mapped_column(Float, default=60)
    date_tolerance_days: Mapped[int] = mapped_column(Integer, default=30)
    amount_tolerance_vnd: Mapped[float] = mapped_column(Float, default=500000)
    low_ocr_confidence_threshold: Mapped[float] = mapped_column(Float, default=80)
    vat_tolerance: Mapped[float] = mapped_column(Float, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AIReport(Base):
    __tablename__ = "ai_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_type: Mapped[str | None] = mapped_column(String(64))
    report_content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
