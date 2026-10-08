"""In-memory state for the mock business systems (CRM sheet, accounting, helpdesk, chat, purchasing, content).

Everything resets to the seed files in data/seed on start and on POST /admin/reset, so every run starts from the
same known state. Sales orders live in a read-only SQLite database built from data/seed/sales_orders.csv.
"""

from __future__ import annotations

import copy
import csv
import json
import re
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opsflow.paths import SAMPLES, SEED

Record = dict[str, Any]

# Collections the workflows write to; they start empty (or from a seed file of the same name).
COLLECTIONS = (
    "crm_contacts",
    "crm_notes",
    "crm_drafts",
    "lead_log",
    "suppliers",
    "purchase_orders",
    "bills",
    "invoice_exceptions",
    "tickets",
    "chat_messages",
    "purchase_history",
    "approvals",
    "audit_log",
    "review_queue",
    "ops_errors",
)

ID_PREFIX = {
    "crm_contacts": "C",
    "crm_notes": "N",
    "crm_drafts": "D",
    "lead_log": "LL",
    "bills": "BILL-",
    "invoice_exceptions": "EX",
    "tickets": "T",
    "chat_messages": "M",
    "approvals": "AP",
    "audit_log": "A",
    "review_queue": "R",
    "ops_errors": "E",
    "purchase_history": "PR",
}


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm_email(value: str | None) -> str:
    return (value or "").strip().lower()


def norm_phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("64"):
        digits = "0" + digits[2:]
    return digits


class Store:
    """Thread-safe collections plus the sales database."""

    def __init__(self, seed_dir: Path = SEED, samples_dir: Path = SAMPLES) -> None:
        self.seed_dir = seed_dir
        self.samples_dir = samples_dir
        self.lock = threading.Lock()
        self.data: dict[str, list[Record]] = {}
        self.counters: dict[str, int] = {}
        self.policy: Record = {}
        self.sales = self._load_sales()
        self.reset()

    # ------------------------------------------------------------------------------------------------ state
    def reset(self) -> None:
        with self.lock:
            self.data = {name: [] for name in COLLECTIONS}
            for name in COLLECTIONS:
                path = self.seed_dir / f"{name}.json"
                if path.exists():
                    self.data[name] = json.loads(path.read_text(encoding="utf-8"))
            policy_path = self.seed_dir / "policy.json"
            self.policy = json.loads(policy_path.read_text(encoding="utf-8")) if policy_path.exists() else {}
            self.counters = {name: len(rows) for name, rows in self.data.items()}

    def snapshot(self) -> dict[str, list[Record]]:
        with self.lock:
            return copy.deepcopy(self.data)

    def add(self, collection: str, record: Record) -> Record:
        if collection not in self.data:
            raise KeyError(collection)
        with self.lock:
            self.counters[collection] += 1
            row = {"id": f"{ID_PREFIX.get(collection, 'X')}{self.counters[collection]:04d}", **record}
            row.setdefault("created_at", now_iso())
            self.data[collection].append(row)
            return copy.deepcopy(row)

    def update(self, collection: str, row_id: str, changes: Record) -> Record | None:
        with self.lock:
            for row in self.data[collection]:
                if row.get("id") == row_id:
                    row.update(changes)
                    return copy.deepcopy(row)
        return None

    def find(self, collection: str, **match: Any) -> list[Record]:
        with self.lock:
            rows = self.data[collection]
            return [copy.deepcopy(r) for r in rows if all(r.get(k) == v for k, v in match.items())]

    # ------------------------------------------------------------------------------------------------- CRM
    def crm_lookup(self, email: str | None, phone: str | None) -> list[Record]:
        email_n, phone_n = norm_email(email), norm_phone(phone)
        with self.lock:
            hits = []
            for row in self.data["crm_contacts"]:
                same_email = bool(email_n) and norm_email(row.get("email")) == email_n
                same_phone = len(phone_n) >= 7 and norm_phone(row.get("phone")) == phone_n
                if same_email or same_phone:
                    hits.append(copy.deepcopy(row))
            return hits

    # ------------------------------------------------------------------------------------------------ sales
    def _load_sales(self) -> sqlite3.Connection:
        db = sqlite3.connect(":memory:", check_same_thread=False)
        db.execute(
            "CREATE TABLE orders (order_id TEXT, order_date TEXT, channel TEXT, sku TEXT, product TEXT, "
            "category TEXT, qty INTEGER, unit_price REAL, total_nzd REAL, status TEXT)"
        )
        path = self.seed_dir / "sales_orders.csv"
        if path.exists():
            with path.open(encoding="utf-8", newline="") as fh:
                rows = [
                    (
                        r["order_id"],
                        r["order_date"],
                        r["channel"],
                        r["sku"],
                        r["product"],
                        r["category"],
                        int(r["qty"]),
                        float(r["unit_price"]),
                        float(r["total_nzd"]),
                        r["status"],
                    )
                    for r in csv.DictReader(fh)
                ]
            db.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
        db.commit()
        db.execute("PRAGMA query_only = ON")
        return db

    def sales_query(self, sql: str, params: list[Any] | None = None) -> list[Record]:
        """Runs one read-only SELECT. Anything else is refused before it reaches the database."""
        text = sql.strip().rstrip(";")
        if not re.match(r"(?is)^\s*(select|with)\b", text) or ";" in text:
            raise ValueError("only a single SELECT statement is allowed")
        with self.lock:
            cur = self.sales.execute(text, params or [])
            cols = [c[0] for c in cur.description or []]
            return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]

    # ---------------------------------------------------------------------------------------------- samples
    def samples(self, workflow: str, split: str = "all", with_labels: bool = False) -> list[Record]:
        path = self.samples_dir / f"{workflow}.json"
        if not path.exists():
            raise KeyError(workflow)
        items = json.loads(path.read_text(encoding="utf-8"))["items"]
        if split != "all":
            items = [i for i in items if i["split"] == split]
        if with_labels:
            return items
        return [{"sample_id": i["id"], **i["input"]} for i in items]
