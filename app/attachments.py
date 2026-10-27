"""Files attached to a case: images, video, audio, documents.

The bytes live on disk under ATTACHMENTS_DIR (inside the app's data volume in Docker),
and only their metadata is kept in SQLite, so the database stays small and fast.
"""
import mimetypes
import os
import re
import shutil
import uuid
from pathlib import Path

import db
from config import ATTACHMENTS_DIR, MAX_ATTACHMENT_MB

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v", ".ogv", ".avi", ".mkv"}
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".opus"}
# SVG is XML text: vision models and Pillow cannot read it as a picture, but its text (labels,
# titles) is readable, so it is treated as a text document.
TEXT_EXT = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".html", ".htm", ".yaml", ".yml", ".svg"}
PDF_EXT = {".pdf"}

# What the uploader offers: everything the UI knows how to preview, plus archives and Office files.
ACCEPTED = sorted(IMAGE_EXT | VIDEO_EXT | AUDIO_EXT | TEXT_EXT | PDF_EXT
                  | {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".rtf", ".odt", ".zip", ".rar", ".7z"})
ACCEPTED_MIME = ["image/*", "video/*", "audio/*", "application/pdf", "text/*"] + [e.lstrip(".") for e in ACCEPTED]

KIND_LABEL_KEY = {"image": "att_kind_image", "video": "att_kind_video", "audio": "att_kind_audio",
                  "pdf": "att_kind_pdf", "text": "att_kind_text", "file": "att_kind_file"}


def kind_of(ext, mime=""):
    ext = (ext or "").lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in PDF_EXT:
        return "pdf"
    if ext in TEXT_EXT:
        return "text"
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    if mime == "application/pdf":
        return "pdf"
    return "file"


def human_size(n):
    step = 0
    size = float(n or 0)
    while size >= 1024 and step < 3:
        size /= 1024
        step += 1
    unit = ("B", "KB", "MB", "GB")[step]
    return f"{size:.0f} {unit}" if step == 0 else f"{size:.1f} {unit}"


def safe_name(name):
    """Keep the extension, drop anything that could escape the folder."""
    cleaned = re.sub(r"[^\w.\- ]", "_", os.path.basename(name or "")).strip(" .")
    return cleaned[:120] or "file"


def _path(rel):
    return Path(ATTACHMENTS_DIR) / rel


def _resolve(rel):
    """Path for a stored file, refusing any name that would reach outside the attachments folder."""
    root = Path(ATTACHMENTS_DIR).resolve()
    target = (root / rel).resolve()
    return target if root in target.parents else None


def ensure_dir():
    os.makedirs(ATTACHMENTS_DIR, exist_ok=True)


def save(case_id, uploaded, message_id=None):
    """Store one uploaded file for a case. Returns (ok, message_key_or_detail).

    message_id ties the file to a chat message instead of the case itself.
    """
    data = uploaded.getvalue()
    if not data:
        return False, "att_empty"
    if len(data) > MAX_ATTACHMENT_MB * 1024 * 1024:
        return False, "att_too_big"
    ensure_dir()
    name = safe_name(uploaded.name)
    stored = f"{case_id}/{uuid.uuid4().hex}{Path(name).suffix.lower()}"
    target = _path(stored)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    mime = uploaded.type or mimetypes.guess_type(name)[0] or "application/octet-stream"
    db.add_attachment(case_id, name, stored, mime, len(data),
                      kind_of(Path(name).suffix, mime), message_id=message_id)
    return True, "att_uploaded"


def remove(att):
    db.delete_attachment(att["id"])
    target = _resolve(att["stored_name"])
    if target and target.is_file():
        try:
            target.unlink()
        except OSError:
            pass


def remove_for_case(case_id):
    """Delete every file of a case, called when the case itself is deleted."""
    for att in db.list_attachments(case_id):
        target = _resolve(att["stored_name"])
        if target and target.is_file():
            try:
                target.unlink()
            except OSError:
                pass
    folder = _path(str(case_id))
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)


def read(att):
    target = _resolve(att["stored_name"])
    if not target or not target.is_file():
        return None
    return target.read_bytes()


def path_of(att):
    target = _resolve(att["stored_name"])
    return target if target and target.is_file() else None
