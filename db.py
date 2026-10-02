"""SQLite storage for leads. All queries are parameterized."""

from __future__ import annotations

import csv
import io
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

_lock = threading.Lock()
_path = "leads.db"

_COLUMNS = (
    "id",
    "telegram_id",
    "username",
    "full_name",
    "tg_name",
    "phone",
    "role",
    "source",
    "created_at",
    "updated_at",
    "subscribed",
    "subscribed_at",
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def _session():
    conn = _connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _clip(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:limit]


def init_db(path: str | None = None) -> None:
    global _path
    if path:
        _path = path
    parent = os.path.dirname(os.path.abspath(_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with _lock, _session() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                username TEXT,
                full_name TEXT NOT NULL,
                tg_name TEXT,
                phone TEXT,
                role TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                subscribed INTEGER DEFAULT 0,
                subscribed_at TEXT
            )
            """
        )
        _migrate(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at)"
        )


def _migrate(conn: sqlite3.Connection) -> None:
    """Add subscription columns to a database created before this step."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(leads)")}
    if "subscribed" not in existing:
        conn.execute("ALTER TABLE leads ADD COLUMN subscribed INTEGER DEFAULT 0")
    if "subscribed_at" not in existing:
        conn.execute("ALTER TABLE leads ADD COLUMN subscribed_at TEXT")


def get_lead(telegram_id: int) -> dict | None:
    with _lock, _session() as conn:
        row = conn.execute(
            "SELECT * FROM leads WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def upsert_lead(
    *,
    telegram_id: int,
    username: str | None,
    full_name: str,
    tg_name: str | None,
    phone: str | None,
    role: str,
    source: str,
) -> tuple[bool, str]:
    """Insert or update by telegram_id. Returns (is_new, updated_at UTC ISO)."""
    name = _clip(full_name, 60)
    if not name:
        raise ValueError("full_name is required")
    now = _utcnow()
    with _lock, _session() as conn:
        existing = conn.execute(
            "SELECT id FROM leads WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO leads (
                telegram_id, username, full_name, tg_name, phone, role, source,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                tg_name = excluded.tg_name,
                phone = COALESCE(excluded.phone, leads.phone),
                role = excluded.role,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                telegram_id,
                _clip(username, 32),
                name,
                _clip(tg_name, 128),
                _clip(phone, 32),
                _clip(role, 16) or role,
                _clip(source, 64) or "direct",
                now,
                now,
            ),
        )
    return existing is None, now


def mark_subscribed(telegram_id: int) -> bool:
    """Mark a lead subscribed. Returns True only the first time."""
    now = _utcnow()
    with _lock, _session() as conn:
        row = conn.execute(
            "SELECT subscribed FROM leads WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if row is None or row["subscribed"]:
            return False
        conn.execute(
            """
            UPDATE leads
            SET subscribed = 1, subscribed_at = ?
            WHERE telegram_id = ?
            """,
            (now, telegram_id),
        )
    return True


def clear_subscription(telegram_id: int) -> None:
    with _lock, _session() as conn:
        conn.execute(
            "UPDATE leads SET subscribed = 0 WHERE telegram_id = ?",
            (telegram_id,),
        )


def stats(day_start_utc: str, day_end_utc: str) -> dict:
    with _lock, _session() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM leads").fetchone()["n"]
        today = conn.execute(
            """
            SELECT COUNT(*) AS n FROM leads
            WHERE created_at >= ? AND created_at < ?
            """,
            (day_start_utc, day_end_utc),
        ).fetchone()["n"]
        roles = conn.execute(
            "SELECT role, COUNT(*) AS n FROM leads GROUP BY role"
        ).fetchall()
        sources = conn.execute(
            """
            SELECT source, COUNT(*) AS n FROM leads
            GROUP BY source
            ORDER BY n DESC, source ASC
            """
        ).fetchall()
        subscribed = conn.execute(
            "SELECT COUNT(*) AS n FROM leads WHERE subscribed = 1"
        ).fetchone()["n"]
    return {
        "total": total,
        "today": today,
        "subscribed": subscribed,
        "by_role": [(row["role"], row["n"]) for row in roles],
        "by_source": [(row["source"], row["n"]) for row in sources],
    }


def _csv_safe(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def export_csv() -> tuple[bytes, int]:
    """UTF-8 with BOM so Excel opens Uzbek letters correctly."""
    with _lock, _session() as conn:
        rows = conn.execute("SELECT * FROM leads ORDER BY id").fetchall()
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(_COLUMNS)
    for row in rows:
        writer.writerow(_csv_safe(row[column]) for column in _COLUMNS)
    return buffer.getvalue().encode("utf-8-sig"), len(rows)
