"""Attachment storage: naming, sizes, kinds, path safety, save/read/remove."""
from pathlib import Path

import attachments
import pytest


class Uploaded:
    """Stands in for Streamlit's UploadedFile."""

    def __init__(self, name, data=b"hello", mime="text/plain"):
        self.name, self.type, self._data = name, mime, data

    def getvalue(self):
        return self._data


# ── pure helpers ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ext,mime,expected", [
    (".png", "", "image"),
    (".MP4", "", "video"),
    (".mp3", "", "audio"),
    (".pdf", "", "pdf"),
    (".txt", "", "text"),
    (".svg", "image/svg+xml", "text"),     # vision models cannot read SVG; its text can be read
    (".docx", "", "file"),
    ("", "image/jpeg", "image"),
    ("", "video/mp4", "video"),
    ("", "application/pdf", "pdf"),
    ("", "application/octet-stream", "file"),
    (None, "", "file"),
])
def test_kind_of(ext, mime, expected):
    assert attachments.kind_of(ext, mime) == expected


@pytest.mark.parametrize("n,expected", [
    (0, "0 B"), (512, "512 B"), (1024, "1.0 KB"), (1536, "1.5 KB"),
    (1024 ** 2, "1.0 MB"), (1024 ** 3, "1.0 GB"), (5 * 1024 ** 4, "5120.0 GB"),
])
def test_human_size(n, expected):
    assert attachments.human_size(n) == expected


@pytest.mark.parametrize("name,expected", [
    ("report.pdf", "report.pdf"),
    ("../../etc/passwd", "passwd"),
    ("a/b\\c.txt", "c.txt"),
    ("مستند مهم.pdf", "مستند مهم.pdf"),
    ("", "file"),
    ("...", "file"),
])
def test_safe_name_never_escapes(name, expected):
    assert attachments.safe_name(name) == expected


def test_safe_name_strips_dangerous_characters():
    assert attachments.safe_name("a$b;c|d.txt") == "a_b_c_d.txt"


def test_safe_name_length_is_bounded():
    assert len(attachments.safe_name("x" * 500 + ".txt")) == 120


def test_traversal_name_is_refused_by_resolve():
    assert attachments._resolve("../../etc/passwd") is None


def test_absolute_name_is_refused_by_resolve():
    assert attachments._resolve(str(Path(attachments.ATTACHMENTS_DIR) / "x") + "/../../evil") is None


# ── save / read / remove ─────────────────────────────────────────────────────
def test_save_and_read(database, case):
    ok, key = attachments.save(case, Uploaded("notes.txt", b"content", "text/plain"))
    assert ok and key == "att_uploaded"
    rows = database.list_attachments(case)
    assert len(rows) == 1
    assert rows[0]["kind"] == "text" and rows[0]["size"] == 7
    assert attachments.read(rows[0]) == b"content"
    assert attachments.path_of(rows[0]).is_file()


def test_save_rejects_empty_file(database, case):
    ok, key = attachments.save(case, Uploaded("empty.txt", b""))
    assert not ok and key == "att_empty"
    assert database.list_attachments(case) == []


def test_save_rejects_oversized_file(database, case, monkeypatch):
    monkeypatch.setattr(attachments, "MAX_ATTACHMENT_MB", 0)
    ok, key = attachments.save(case, Uploaded("big.bin", b"x"))
    assert not ok and key == "att_too_big"


def test_save_uses_a_fresh_stored_name_each_time(database, case):
    attachments.save(case, Uploaded("same.txt", b"one"))
    attachments.save(case, Uploaded("same.txt", b"two"))
    stored = [r["stored_name"] for r in database.list_attachments(case)]
    assert len(set(stored)) == 2


def test_save_binds_upload_to_message(database, case):
    msg_id = database.add_message(case, "user", "سؤال")
    attachments.save(case, Uploaded("m.txt", b"x"), message_id=msg_id)
    assert len(database.list_message_attachments(msg_id)) == 1
    assert database.list_case_files(case) == []


def test_read_missing_file_returns_none(database, case):
    attachments.save(case, Uploaded("gone.txt", b"x"))
    row = database.list_attachments(case)[0]
    attachments.path_of(row).unlink()
    assert attachments.read(row) is None
    assert attachments.path_of(row) is None


def test_remove_deletes_row_and_file(database, case):
    attachments.save(case, Uploaded("r.txt", b"x"))
    row = database.list_attachments(case)[0]
    path = attachments.path_of(row)
    attachments.remove(row)
    assert database.get_attachment(row["id"]) is None
    assert not path.exists()


def test_remove_for_case_cleans_folder(database, case):
    attachments.save(case, Uploaded("a.txt", b"x"))
    attachments.save(case, Uploaded("b.txt", b"y"))
    attachments.remove_for_case(case)
    assert not (Path(attachments.ATTACHMENTS_DIR) / str(case)).exists()
