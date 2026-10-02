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
    "project",
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

_PROJECT_ORDER = {"safartrip": 0, "mendora": 1}


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
                telegram_id INTEGER NOT NULL,
                project TEXT NOT NULL DEFAULT 'safartrip',
                username TEXT,
                full_name TEXT NOT NULL,
                tg_name TEXT,
                phone TEXT,
                role TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                subscribed INTEGER DEFAULT 0,
                subscribed_at TEXT,
                UNIQUE (telegram_id, project)
            )
            """
        )
        _migrate(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at)"
        )


def _pair_unique(sql: str) -> bool:
    compact = "".join(sql.split()).lower()
    return "unique(telegram_id,project)" in compact


def _migrate(conn: sqlite3.Connection) -> None:
    """Rebuild an older leads table so uniqueness is (telegram_id, project).

    Copy, drop, and rename run in the caller's transaction. Rows, ids,
    subscribed, and subscribed_at are kept. Missing project becomes safartrip.
    """
    info = list(conn.execute("PRAGMA table_info(leads)"))
    if not info:
        return
    names = {row["name"] for row in info}
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'leads'"
    ).fetchone()
    sql = schema["sql"] if schema else ""
    ready = (
        "project" in names
        and "subscribed" in names
        and "subscribed_at" in names
        and _pair_unique(sql)
    )
    if ready:
        return
    _rebuild_leads(conn, names)


def _rebuild_leads(conn: sqlite3.Connection, names: set[str]) -> None:
    conn.execute("DROP TABLE IF EXISTS leads_new")
    conn.execute(
        """
        CREATE TABLE leads_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            project TEXT NOT NULL DEFAULT 'safartrip',
            username TEXT,
            full_name TEXT NOT NULL,
            tg_name TEXT,
            phone TEXT,
            role TEXT NOT NULL,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            subscribed INTEGER DEFAULT 0,
            subscribed_at TEXT,
            UNIQUE (telegram_id, project)
        )
        """
    )
    project_expr = "COALESCE(NULLIF(project, ''), 'safartrip')" if "project" in names else "'safartrip'"
    subscribed_expr = "COALESCE(subscribed, 0)" if "subscribed" in names else "0"
    subscribed_at_expr = "subscribed_at" if "subscribed_at" in names else "NULL"
    conn.execute(
        f"""
        INSERT INTO leads_new (
            id, telegram_id, project, username, full_name, tg_name, phone,
            role, source, created_at, updated_at, subscribed, subscribed_at
        )
        SELECT
            id, telegram_id, {project_expr}, username, full_name, tg_name, phone,
            role, source, created_at, updated_at, {subscribed_expr}, {subscribed_at_expr}
        FROM leads
        """
    )
    conn.execute("DROP TABLE leads")
    conn.execute("ALTER TABLE leads_new RENAME TO leads")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at)")
    max_id = conn.execute("SELECT COALESCE(MAX(id), 0) AS n FROM leads").fetchone()["n"]
    try:
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'leads'")
        renamed = conn.execute(
            "UPDATE sqlite_sequence SET name = 'leads' WHERE name = 'leads_new'"
        ).rowcount
        if max_id and not renamed:
            conn.execute(
                "INSERT INTO sqlite_sequence (name, seq) VALUES ('leads', ?)",
                (max_id,),
            )
        elif max_id:
            conn.execute(
                "UPDATE sqlite_sequence SET seq = ? WHERE name = 'leads' AND seq < ?",
                (max_id, max_id),
            )
    except sqlite3.OperationalError:
        pass


def get_lead(telegram_id: int, project: str = "safartrip") -> dict | None:
    with _lock, _session() as conn:
        row = conn.execute(
            "SELECT * FROM leads WHERE telegram_id = ? AND project = ?",
            (telegram_id, project),
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
    project: str = "safartrip",
) -> tuple[bool, str]:
    """Insert or update one project row. Returns (is_new, updated_at UTC ISO)."""
    name = _clip(full_name, 60)
    if not name:
        raise ValueError("full_name is required")
    chosen = project if project in {"safartrip", "mendora"} else "safartrip"
    now = _utcnow()
    with _lock, _session() as conn:
        existing = conn.execute(
            "SELECT id FROM leads WHERE telegram_id = ? AND project = ?",
            (telegram_id, chosen),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO leads (
                telegram_id, project, username, full_name, tg_name, phone, role, source,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id, project) DO UPDATE SET
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
                chosen,
                _clip(username, 32),
                name,
                _clip(tg_name, 128),
                _clip(phone, 32),
                _clip(role, 32) or role,
                _clip(source, 64) or "direct",
                now,
                now,
            ),
        )
    return existing is None, now


def mark_subscribed(telegram_id: int, project: str = "safartrip") -> bool:
    """Mark one project row subscribed. Returns True only the first time."""
    now = _utcnow()
    with _lock, _session() as conn:
        row = conn.execute(
            "SELECT subscribed FROM leads WHERE telegram_id = ? AND project = ?",
            (telegram_id, project),
        ).fetchone()
        if row is None or row["subscribed"]:
            return False
        conn.execute(
            """
            UPDATE leads
            SET subscribed = 1, subscribed_at = ?
            WHERE telegram_id = ? AND project = ?
            """,
            (now, telegram_id, project),
        )
    return True


def clear_subscription(telegram_id: int, project: str = "safartrip") -> None:
    with _lock, _session() as conn:
        conn.execute(
            "UPDATE leads SET subscribed = 0 WHERE telegram_id = ? AND project = ?",
            (telegram_id, project),
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
        project_names = [
            row["project"]
            for row in conn.execute("SELECT DISTINCT project FROM leads")
        ]
        projects = [
            _project_stats(conn, project, day_start_utc, day_end_utc)
            for project in sorted(project_names, key=lambda name: (_PROJECT_ORDER.get(name, 9), name))
        ]
    return {
        "total": total,
        "today": today,
        "subscribed": subscribed,
        "by_role": [(row["role"], row["n"]) for row in roles],
        "by_source": [(row["source"], row["n"]) for row in sources],
        "projects": projects,
    }


def _project_stats(
    conn: sqlite3.Connection,
    project: str,
    day_start_utc: str,
    day_end_utc: str,
) -> dict:
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM leads WHERE project = ?",
        (project,),
    ).fetchone()["n"]
    today = conn.execute(
        """
        SELECT COUNT(*) AS n FROM leads
        WHERE project = ? AND created_at >= ? AND created_at < ?
        """,
        (project, day_start_utc, day_end_utc),
    ).fetchone()["n"]
    subscribed = conn.execute(
        "SELECT COUNT(*) AS n FROM leads WHERE project = ? AND subscribed = 1",
        (project,),
    ).fetchone()["n"]
    roles = conn.execute(
        "SELECT role, COUNT(*) AS n FROM leads WHERE project = ? GROUP BY role",
        (project,),
    ).fetchall()
    sources = conn.execute(
        """
        SELECT source, COUNT(*) AS n FROM leads
        WHERE project = ?
        GROUP BY source
        ORDER BY n DESC, source ASC
        """,
        (project,),
    ).fetchall()
    return {
        "project": project,
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
