"""Database layer: schema, CRUD, numbering, search, export."""
import csv
import datetime
import io

import pytest


def test_init_creates_tables(database):
    import sqlite3

    from config import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    columns = {
        table: {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for table in ("investigations", "messages")
    }
    conn.close()
    assert {"investigations", "attachments", "messages", "report_versions"} <= names
    assert journal_mode.lower() == "wal"
    assert "worker" in columns["investigations"]
    assert "worker" in columns["messages"]


def test_init_is_idempotent(database):
    database.init_db()
    database.init_db()
    assert database.stats()["total"] == 0


def test_init_adds_worker_columns_to_existing_database(database, monkeypatch, tmp_path):
    import sqlite3

    import db as db_module

    path = tmp_path / "existing.db"
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE investigations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, case_name TEXT, case_number TEXT, case_type TEXT,
        location TEXT, date TEXT, case_text TEXT, report_text TEXT, timestamp DATETIME
    )""")
    conn.execute("""CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, case_id INTEGER NOT NULL, role TEXT NOT NULL,
        content TEXT, status TEXT, error TEXT, reply_to INTEGER, timestamp DATETIME
    )""")
    conn.commit()
    conn.close()
    monkeypatch.setattr(db_module, "DB_PATH", str(path))

    db_module.init_db()

    conn = sqlite3.connect(path)
    for table in ("investigations", "messages"):
        assert "worker" in {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    conn.close()


def test_create_draft_defaults(database):
    case_id = database.create_draft("نص البلاغ")
    row = database.get_case(case_id)
    assert row["status"] == "draft"
    assert row["case_type"] == "عام"
    assert row["case_text"] == "نص البلاغ"


def test_update_case_editable_fields(database, case):
    database.update_case(case, status="analyzed", severity="high", latitude=31.9, longitude=35.2)
    row = database.get_case(case)
    assert (row["status"], row["severity"]) == ("analyzed", "high")
    assert (row["latitude"], row["longitude"]) == (31.9, 35.2)


def test_update_case_rejects_unknown_field(database, case):
    with pytest.raises(ValueError):
        database.update_case(case, id=99, something_else="x")


def test_update_case_rejects_sql_in_field_name(database, case):
    with pytest.raises(ValueError):
        database.update_case(case, **{"status=1, case_name": "hacked"})
    assert database.get_case(case)["case_name"] == "قضية تجريبية"


def test_update_case_survives_quotes_in_values(database, case):
    nasty = "اسم 'غريب' AND 1=1; DROP TABLE investigations;--"
    database.update_case(case, case_name=nasty)
    assert database.get_case(case)["case_name"] == nasty


def test_update_case_with_no_fields_is_noop(database, case):
    database.update_case(case)
    assert database.get_case(case)["id"] == case


def test_get_missing_case(database):
    assert database.get_case(424242) is None


def test_delete_case_cascades(database, case):
    database.add_attachment(case, "a.txt", f"{case}/a.txt", "text/plain", 3, "text")
    database.add_message(case, "user", "سؤال")
    database.delete_case(case)
    assert database.get_case(case) is None
    assert database.list_attachments(case) == []
    assert database.list_messages(case) == []
    assert database.list_report_versions(case) == []


def test_next_case_number_starts_at_one(database):
    year = datetime.date.today().year
    assert database.next_case_number() == f"ALP-{year}-001"


def test_next_case_number_increments(database, case):
    year = datetime.date.today().year
    database.update_case(case, case_number=f"ALP-{year}-007")
    assert database.next_case_number() == f"ALP-{year}-008"


def test_next_case_number_ignores_other_years_and_junk(database, case):
    database.create_draft("x")
    other = database.list_cases()[0]["id"]
    database.update_case(other, case_number="ALP-1999-999")
    database.update_case(case, case_number="not-a-number")
    year = datetime.date.today().year
    assert database.next_case_number() == f"ALP-{year}-001"


def test_case_number_exists(database, case):
    assert database.case_number_exists("ALP-2026-001")
    assert not database.case_number_exists("ALP-2026-001", exclude_id=case)
    assert not database.case_number_exists("")
    assert not database.case_number_exists(None)


def test_list_cases_search_matches_text_and_title(database, case):
    assert len(database.list_cases(search="تجريبية")) == 1
    assert len(database.list_cases(search="المستودع")) == 1
    assert database.list_cases(search="لا-يوجد-هذا") == []


def test_list_cases_filters(database, case):
    database.update_case(case, status="analyzed", severity="low", case_type="سرقة")
    assert len(database.list_cases(status="analyzed")) == 1
    assert database.list_cases(status="failed") == []
    assert len(database.list_cases(case_type="سرقة")) == 1
    assert database.list_cases(severity="high") == []


def test_list_cases_limit_and_order(database):
    first = database.create_draft("أول")
    second = database.create_draft("ثاني")
    rows = database.list_cases()
    assert [r["id"] for r in rows] == [second, first]      # newest first
    assert len(database.list_cases(limit=1)) == 1


def test_stats_groups_by_status_and_type(database):
    a = database.create_draft("a")
    b = database.create_draft("b")
    database.update_case(a, case_type="سرقة", severity="high")
    database.update_case(b, case_type="سرقة", status="analyzed", severity="medium")
    database.create_draft("c")
    stats = database.stats()
    assert stats["total"] == 3
    assert stats["by_status"] == {"draft": 2, "analyzed": 1}
    assert dict(stats["by_type"])["سرقة"] == 2
    assert dict(stats["by_severity"]) == {"high": 1, "medium": 1, "unknown": 1}
    assert {(case_type, severity): count for case_type, severity, count in stats["by_type_severity"]} == {
        ("عام", "unknown"): 1,
        ("سرقة", "high"): 1,
        ("سرقة", "medium"): 1,
    }


def test_export_csv_has_bom_and_rows(database, case):
    data = database.export_cases_csv(["id", "number"])
    assert data.startswith("﻿".encode("utf-8"))
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    assert rows[0] == ["id", "number"]
    assert rows[1][0] == str(case)


def test_analyzing_ids_and_fail_interrupted(database):
    a = database.create_draft("a")
    database.update_case(a, status="analyzing")
    assert database.analyzing_ids() == {a}
    database.fail_interrupted("restarted")
    row = database.get_case(a)
    assert row["status"] == "failed"
    assert row["error"] == "restarted"
    assert database.analyzing_ids() == set()


def test_fail_interrupted_only_marks_work_for_requested_worker(database):
    other_case = database.create_draft("other")
    api_case = database.create_draft("api")
    database.update_case(other_case, status="analyzing", worker="other")
    database.update_case(api_case, status="analyzing", worker="api")
    other_msg = database.add_message(
        other_case, "assistant", "", status="pending", worker="other")
    api_msg = database.add_message(api_case, "assistant", "", status="pending", worker="api")

    database.fail_interrupted("restarted", worker="api")

    assert database.get_case(api_case)["status"] == "failed"
    assert database.get_case(other_case)["status"] == "analyzing"
    assert database.get_message(api_msg)["status"] == "failed"
    assert database.get_message(other_msg)["status"] == "pending"


# ── Messages ─────────────────────────────────────────────────────────────────
def test_message_roundtrip(database, case):
    msg_id = database.add_message(case, "user", "سؤال")
    assert database.get_message(msg_id)["content"] == "سؤال"
    database.update_message(msg_id, content="رد", status="ok")
    assert database.get_message(msg_id)["status"] == "ok"
    assert len(database.list_messages(case)) == 1


def test_update_message_rejects_unknown(database, case):
    msg_id = database.add_message(case, "user", "سؤال")
    with pytest.raises(ValueError):
        database.update_message(msg_id, case_id=1)


def test_export_csv_neutralises_formulas(database, case):
    database.update_case(case, case_name='=HYPERLINK("http://evil","x")', location="+972 test",
                         latitude=-31.5)
    data = database.export_cases_csv([str(i) for i in range(13)])
    row = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))[1]
    assert row[2] == '\'=HYPERLINK("http://evil","x")'
    assert row[6] == "'+972 test"
    # Numbers are not text, so a negative coordinate keeps its value.
    assert row[7] == "-31.5"


def test_update_report_from_message_can_save_a_merged_report(database, case):
    database.update_case(case, report_text='{"الملخص": "أ"}', status="analyzed", severity="high")
    reply = database.add_message(case, "assistant", "معلومة جديدة", status="ok")
    database.update_report_from_message(case, reply, severity="high",
                                        report_text='{"الملخص": "أ", "تحديث": "معلومة جديدة"}')
    saved = database.get_case(case)
    assert saved["report_text"] == '{"الملخص": "أ", "تحديث": "معلومة جديدة"}'
    assert saved["severity"] == "high"


def test_fail_interrupted_marks_pending_messages(database, case):
    msg_id = database.add_message(case, "assistant", "", status="pending")
    database.fail_interrupted("boom")
    assert database.get_message(msg_id)["status"] == "failed"


def test_delete_messages(database, case):
    database.add_message(case, "user", "أ")
    database.delete_messages(case)
    assert database.list_messages(case) == []


def test_update_report_from_message_preserves_previous_versions(database, case):
    database.update_case(case, report_text="التقرير الأصلي", status="analyzed", severity="low")
    first = database.add_message(case, "assistant", "التقرير الجديد", status="ok")
    database.update_report_from_message(case, first, severity="high")
    assert database.get_case(case)["report_text"] == "التقرير الجديد"
    assert database.get_case(case)["severity"] == "high"
    assert [v["report_text"] for v in database.list_report_versions(case)] == ["التقرير الأصلي"]

    second = database.add_message(case, "assistant", "التقرير الأحدث", status="ok")
    database.update_report_from_message(case, second)
    assert [v["report_text"] for v in database.list_report_versions(case)] == [
        "التقرير الأصلي", "التقرير الجديد"
    ]


def test_update_report_rejects_non_assistant_or_incomplete_message(database, case):
    user_message = database.add_message(case, "user", "سؤال")
    pending_reply = database.add_message(case, "assistant", "", status="pending")
    for msg_id in (user_message, pending_reply):
        with pytest.raises(ValueError):
            database.update_report_from_message(case, msg_id)
    assert database.list_report_versions(case) == []


# ── Attachments ──────────────────────────────────────────────────────────────
def test_case_files_exclude_message_files(database, case):
    msg_id = database.add_message(case, "user", "سؤال")
    database.add_attachment(case, "case.txt", f"{case}/case.txt", "text/plain", 1, "text")
    database.add_attachment(case, "msg.txt", f"{case}/msg.txt", "text/plain", 1, "text", message_id=msg_id)
    assert [a["file_name"] for a in database.list_case_files(case)] == ["case.txt"]
    assert [a["file_name"] for a in database.list_message_attachments(msg_id)] == ["msg.txt"]
    assert len(database.list_attachments(case)) == 2


def test_attachment_description_cache(database, case):
    att_id = database.add_attachment(case, "p.png", f"{case}/p.png", "image/png", 10, "image")
    database.set_attachment_description(att_id, "وصف", "vision-model")
    row = database.get_attachment(att_id)
    assert row["description"] == "وصف"
    assert row["description_model"] == "vision-model"


def test_attachment_counts(database, case):
    database.add_attachment(case, "a", f"{case}/a", "text/plain", 100, "text")
    database.add_attachment(case, "b", f"{case}/b", "text/plain", 50, "text")
    assert database.attachment_counts() == {case: (2, 150)}


def test_delete_attachment(database, case):
    att_id = database.add_attachment(case, "a", f"{case}/a", "text/plain", 1, "text")
    database.delete_attachment(att_id)
    assert database.get_attachment(att_id) is None


def test_stored_name_is_unique(database, case):
    import sqlite3

    database.add_attachment(case, "a", f"{case}/same.txt", "text/plain", 1, "text")
    with pytest.raises(sqlite3.IntegrityError):
        database.add_attachment(case, "b", f"{case}/same.txt", "text/plain", 1, "text")
