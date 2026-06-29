from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = BACKEND_DIR / "data"
DEFAULT_UPLOAD_DIR = DEFAULT_DATA_DIR / "uploads"

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", DEFAULT_UPLOAD_DIR))
RAW_DATABASE_URL = os.getenv("DATABASE_URL")
SQLITE_PATH = Path(os.getenv("DATABASE_PATH", DEFAULT_DATA_DIR / "finrecon.db"))


def _database_url() -> str:
    if RAW_DATABASE_URL:
        if RAW_DATABASE_URL.startswith("postgresql://"):
            return RAW_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
        return RAW_DATABASE_URL
    return f"sqlite:///{SQLITE_PATH.as_posix()}"


DATABASE_URL = _database_url()
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def ensure_storage() -> None:
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if DATABASE_URL.startswith("sqlite"):
        SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_db() -> Iterator[Session]:
    ensure_storage()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    ensure_storage()
    from app import models  # noqa: F401
    from app.seed import seed_defaults

    Base.metadata.create_all(bind=engine)
    if DATABASE_URL.startswith("sqlite"):
        _sqlite_compat_migration()
    with SessionLocal() as db:
        seed_defaults(db)
        db.commit()


def _sqlite_compat_migration() -> None:
    import sqlite3

    table_columns: dict[str, dict[str, str]] = {
        "vendors": {
            "company_id": "INTEGER",
            "bank_name": "VARCHAR(128)",
            "bank_account_holder": "VARCHAR(255)",
            "email": "VARCHAR(255)",
            "phone": "VARCHAR(64)",
            "category": "VARCHAR(64)",
            "status": "VARCHAR(32) DEFAULT 'active'",
        },
        "invoice_batches": {},
        "uploaded_files": {"company_id": "INTEGER", "batch_id": "INTEGER"},
        "processing_jobs": {"company_id": "INTEGER", "batch_id": "INTEGER"},
        "invoices": {
            "company_id": "INTEGER",
            "batch_id": "INTEGER",
            "invoice_id": "VARCHAR(128)",
            "invoice_series": "VARCHAR(64)",
            "invoice_template_code": "VARCHAR(64)",
            "vendor_id": "VARCHAR(64)",
            "vendor_bank_account": "VARCHAR(64)",
            "vendor_address": "TEXT",
            "vendor_phone": "VARCHAR(64)",
            "buyer_name": "VARCHAR(255)",
            "buyer_tax_code": "VARCHAR(64)",
            "vat_rate": "FLOAT",
            "source_type": "VARCHAR(64)",
            "attachment_file": "VARCHAR(255)",
            "expected_case": "VARCHAR(128)",
        },
        "bank_transactions": {
            "company_id": "INTEGER",
            "batch_id": "INTEGER",
            "value_date": "DATE",
            "account_number": "VARCHAR(64)",
            "currency": "VARCHAR(8) DEFAULT 'VND'",
            "balance_after": "FLOAT",
            "counterparty_name": "VARCHAR(255)",
            "counterparty_account": "VARCHAR(64)",
            "expected_case": "VARCHAR(128)",
        },
        "reconciliation_matches": {"reviewed_by": "INTEGER", "updated_at": "DATETIME"},
        "reconciliation_exceptions": {
            "status": "VARCHAR(32) DEFAULT 'open'",
            "note": "TEXT",
            "assigned_to": "INTEGER",
            "updated_at": "DATETIME",
        },
        "audit_logs": {"user_id": "INTEGER"},
    }
    with sqlite3.connect(SQLITE_PATH) as conn:
        for table, columns in table_columns.items():
            existing_tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if table not in existing_tables:
                continue
            existing_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column, definition in columns.items():
                if column not in existing_columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
