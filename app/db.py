import csv
import datetime
import io
import os
import re
import sqlite3
from contextlib import contextmanager

from config import DB_PATH

# Columns the app may change through update_case().
EDITABLE = {"case_name", "case_number", "case_type", "location", "date", "case_text",
            "report_text", "status", "severity", "error", "latitude", "longitude"}


@contextmanager
def db():
    # Analyses finish on background threads, so every call opens its own connection.
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS investigations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_name TEXT,
                case_number TEXT,
                case_type TEXT,
                location TEXT,
                date TEXT,
                case_text TEXT,
                report_text TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(investigations)")}
        for column, kind in (("case_name", "TEXT"), ("status", "TEXT"), ("severity", "TEXT"), ("error", "TEXT"),
                             ("latitude", "REAL"), ("longitude", "REAL")):
            if column not in existing:
                conn.execute(f"ALTER TABLE investigations ADD COLUMN {column} {kind}")
        # Cases saved before statuses existed were always analyzed.
        conn.execute("""UPDATE investigations
                        SET status = CASE WHEN COALESCE(report_text, '') = '' THEN 'draft' ELSE 'analyzed' END
                        WHERE status IS NULL""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                file_name TEXT,
                stored_name TEXT NOT NULL UNIQUE,
                mime_type TEXT,
                size INTEGER DEFAULT 0,
                kind TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS attachments_case ON attachments(case_id)")
        # Descriptions of images and video frames are cached: a vision model can take a minute
        # per image, and re-analysis should not pay that cost twice.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(attachments)")}
        for column, kind in (("description", "TEXT"), ("description_model", "TEXT"), ("message_id", "INTEGER")):
            if column not in cols:
                conn.execute(f"ALTER TABLE attachments ADD COLUMN {column} {kind}")
        # The conversation about a case: the investigator's questions, notes and the replies.
        # reply_to points a reply at the question it answers, whose files it must read.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                status TEXT,
                error TEXT,
                reply_to INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS messages_case ON messages(case_id)")
        mcols = {r["name"] for r in conn.execute("PRAGMA table_info(messages)")}
        if "reply_to" not in mcols:
            conn.execute("ALTER TABLE messages ADD COLUMN reply_to INTEGER")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS report_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                report_text TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS report_versions_case ON report_versions(case_id)")


def add_message(case_id, role, content="", status="ok", error=None, reply_to=None):
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO messages (case_id, role, content, status, error, reply_to) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (case_id, role, content, status, error, reply_to),
        )
        return cur.lastrowid


def update_message(msg_id, **fields):
    unknown = set(fields) - {"content", "status", "error"}
    if unknown:
        raise ValueError(f"Not editable: {unknown}")
    if not fields:
        return
    assignments = ", ".join(f"{k}=?" for k in fields)
    with db() as conn:
        conn.execute(f"UPDATE messages SET {assignments} WHERE id=?", (*fields.values(), msg_id))


def get_message(msg_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM messages WHERE id=?", (msg_id,)).fetchone()
    return dict(row) if row else None


def list_messages(case_id):
    with db() as conn:
        rows = conn.execute("SELECT * FROM messages WHERE case_id=? ORDER BY id", (case_id,)).fetchall()
    return [dict(r) for r in rows]


def count_messages(case_id):
    with db() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM messages WHERE case_id=? AND status='ok'",
                           (case_id,)).fetchone()
    return row["c"]


def delete_messages(case_id):
    with db() as conn:
        conn.execute("DELETE FROM messages WHERE case_id=?", (case_id,))


def add_attachment(case_id, file_name, stored_name, mime_type, size, kind, message_id=None):
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO attachments (case_id, file_name, stored_name, mime_type, size, kind, message_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (case_id, file_name, stored_name, mime_type, size, kind, message_id),
        )
        return cur.lastrowid


def list_attachments(case_id):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM attachments WHERE case_id=? ORDER BY id", (case_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def list_case_files(case_id):
    """Files that belong to the case itself, not to a chat message."""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM attachments WHERE case_id=? AND message_id IS NULL ORDER BY id", (case_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def list_message_attachments(message_id):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM attachments WHERE message_id=? ORDER BY id", (message_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_attachment(att_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM attachments WHERE id=?", (att_id,)).fetchone()
    return dict(row) if row else None


def delete_attachment(att_id):
    with db() as conn:
        conn.execute("DELETE FROM attachments WHERE id=?", (att_id,))


def set_attachment_description(att_id, description, model):
    with db() as conn:
        conn.execute("UPDATE attachments SET description=?, description_model=? WHERE id=?",
                     (description, model, att_id))


def attachment_counts():
    """{case_id: (count, total_bytes)} for the case list."""
    with db() as conn:
        rows = conn.execute(
            "SELECT case_id, COUNT(*) AS n, COALESCE(SUM(size), 0) AS total FROM attachments GROUP BY case_id"
        ).fetchall()
    return {r["case_id"]: (r["n"], r["total"]) for r in rows}


def fail_interrupted(error):
    """Analyses run on threads; after a restart none of them is still running."""
    with db() as conn:
        conn.execute("UPDATE investigations SET status='failed', error=? WHERE status='analyzing'", (error,))
        conn.execute("UPDATE messages SET status='failed', error=? WHERE status='pending'", (error,))


def next_case_number():
    year = datetime.date.today().year
    with db() as conn:
        rows = conn.execute("SELECT case_number FROM investigations WHERE case_number LIKE ?",
                            (f"ALP-{year}-%",)).fetchall()
    numbers = [int(m.group(1)) for r in rows if (m := re.fullmatch(rf"ALP-{year}-(\d+)", r["case_number"] or ""))]
    return f"ALP-{year}-{(max(numbers) + 1) if numbers else 1:03d}"


def create_draft(case_text):
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO investigations (case_text, case_type, status) VALUES (?, 'عام', 'draft')", (case_text,)
        )
        return cur.lastrowid


def update_case(inv_id, **fields):
    unknown = set(fields) - EDITABLE
    if unknown:
        raise ValueError(f"Not editable: {unknown}")
    if not fields:
        return
    assignments = ", ".join(f"{k}=?" for k in fields)
    with db() as conn:
        conn.execute(f"UPDATE investigations SET {assignments} WHERE id=?", (*fields.values(), inv_id))


def delete_case(inv_id):
    with db() as conn:
        conn.execute("DELETE FROM report_versions WHERE case_id=?", (inv_id,))
        conn.execute("DELETE FROM messages WHERE case_id=?", (inv_id,))
        conn.execute("DELETE FROM attachments WHERE case_id=?", (inv_id,))
        conn.execute("DELETE FROM investigations WHERE id=?", (inv_id,))


def update_report_from_message(case_id, message_id, severity=None):
    """Save an assistant reply as the current report, preserving the previous version."""
    with db() as conn:
        message = conn.execute(
            "SELECT content FROM messages WHERE id=? AND case_id=? AND role='assistant' AND status='ok'",
            (message_id, case_id),
        ).fetchone()
        if not message or not (message["content"] or "").strip():
            raise ValueError("The selected message is not a completed assistant reply")
        case = conn.execute("SELECT report_text FROM investigations WHERE id=?", (case_id,)).fetchone()
        if not case:
            raise ValueError("Case not found")
        previous = case["report_text"]
        if previous and previous != message["content"]:
            conn.execute(
                "INSERT INTO report_versions (case_id, report_text) VALUES (?, ?)",
                (case_id, previous),
            )
        conn.execute(
            "UPDATE investigations SET report_text=?, status='analyzed', severity=?, error=NULL WHERE id=?",
            (message["content"], severity, case_id),
        )


def save_analysis_report(case_id, report_text, severity=None):
    """Save a new analysis and preserve the report it replaces."""
    with db() as conn:
        case = conn.execute(
            "SELECT report_text FROM investigations WHERE id=?", (case_id,)
        ).fetchone()
        if not case:
            return False
        previous = case["report_text"]
        if previous and previous != report_text:
            conn.execute(
                "INSERT INTO report_versions (case_id, report_text) VALUES (?, ?)",
                (case_id, previous),
            )
        conn.execute(
            "UPDATE investigations SET report_text=?, status='analyzed', severity=?, error=NULL WHERE id=?",
            (report_text, severity, case_id),
        )
    return True


def list_report_versions(case_id):
    with db() as conn:
        rows = conn.execute(
            "SELECT id, report_text, timestamp FROM report_versions WHERE case_id=? ORDER BY id",
            (case_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_case(inv_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM investigations WHERE id=?", (inv_id,)).fetchone()
    return dict(row) if row else None


def list_cases(search="", case_type=None, status=None, severity=None, limit=None):
    sql = ("SELECT id, case_name, case_number, case_type, status, severity, latitude, longitude, timestamp "
           "FROM investigations")
    where, params = [], []
    if search:
        like = f"%{search}%"
        where.append("(case_name LIKE ? OR case_number LIKE ? OR case_text LIKE ? OR report_text LIKE ?)")
        params += [like] * 4
    for column, value in (("case_type", case_type), ("status", status), ("severity", severity)):
        if value:
            where.append(f"{column} = ?")
            params.append(value)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with db() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def analyzing_ids():
    with db() as conn:
        return {r["id"] for r in conn.execute("SELECT id FROM investigations WHERE status='analyzing'")}


def stats():
    with db() as conn:
        by_status = {r["status"]: r["c"] for r in conn.execute(
            "SELECT status, COUNT(*) AS c FROM investigations GROUP BY status")}
        by_type = [(r["case_type"] or "عام", r["c"]) for r in conn.execute(
            "SELECT case_type, COUNT(*) AS c FROM investigations GROUP BY case_type ORDER BY c DESC")]
    return {"total": sum(by_status.values()), "by_status": by_status, "by_type": by_type}


def case_number_exists(case_number, exclude_id=None):
    if not case_number:
        return False
    with db() as conn:
        row = conn.execute(
            "SELECT 1 FROM investigations WHERE case_number = ? AND id IS NOT ? LIMIT 1",
            (case_number, exclude_id),
        ).fetchone()
    return row is not None


def export_cases_csv(headers):
    with db() as conn:
        rows = conn.execute(
            "SELECT id, case_number, case_name, case_type, status, severity, location, latitude, longitude, date, "
            "case_text, report_text, timestamp FROM investigations ORDER BY id DESC"
        ).fetchall()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for r in rows:
        writer.writerow(list(r))
    return buf.getvalue().encode("utf-8-sig")
