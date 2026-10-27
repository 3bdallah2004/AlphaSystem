"""Turn an attached file into something the analysis can read.

Text documents and text-based PDFs give their text directly; images and video frames are
sent to a vision model. Anything that cannot be read is reported, never silently skipped.
"""
import base64
import io
import json
import logging
import re
import shutil
import subprocess
import tempfile
import zipfile
from xml.etree import ElementTree
from pathlib import Path

from PIL import Image

import attachments as att
import db
import llm
import requests
from config import AUDIO_TRANSCRIPTION_MODEL, PROVIDER_TIMEOUT

log = logging.getLogger(__name__)

TEXT_SUFFIXES = (".txt", ".md", ".csv", ".log", ".json", ".xml", ".html", ".htm", ".yaml", ".yml", ".svg")

MAX_TEXT_CHARS = 12000          # per document, keeps the analysis prompt manageable
MAX_VIDEO_FRAMES = 4            # per video
FRAME_WIDTH = 900
IMAGE_MAX_BYTES = 4 * 1024 * 1024
IMAGE_MAX_SIDE = 2000
ARCHIVE_MAX_FILES = 100
ARCHIVE_MAX_BYTES = 10 * 1024 * 1024


def _ffmpeg():
    """The bundled ffmpeg binary, or one on PATH. None when neither exists."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def _shrink(data, mime):
    """Downscale and recompress so a phone photo doesn't blow up the request."""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        return data, mime
    img = img.convert("RGB")
    if max(img.size) > IMAGE_MAX_SIDE:
        img.thumbnail((IMAGE_MAX_SIDE, IMAGE_MAX_SIDE))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=82, optimize=True)
    encoded = out.getvalue()
    if len(encoded) < len(data):
        return encoded, "image/jpeg"
    return data, mime


def image_data_uri(row):
    """A data: URI the vision model can read, or None when the file is unusable."""
    data = att.read(row)
    if not data:
        return None
    mime = row["mime_type"] or "image/png"
    data, mime = _shrink(data, mime)
    if len(data) > IMAGE_MAX_BYTES:
        return None
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def text_of(row, limit=MAX_TEXT_CHARS):
    """Extract text from supported documents and archives."""
    name = (row["file_name"] or "").lower()
    data = att.read(row)
    if not data:
        return None
    if name.endswith(TEXT_SUFFIXES):
        return data.decode("utf-8", "replace")[:limit]
    if name.endswith(".pdf"):
        return _pdf_text(data, limit)
    if name.endswith(".docx"):
        return _docx_text(data, limit)
    if name.endswith((".xlsx", ".pptx", ".odt")):
        return _office_zip_text(data, name, limit)
    if name.endswith(".rtf"):
        return _rtf_text(data, limit)
    if name.endswith((".zip", ".rar", ".7z")):
        return _archive_text(data, name, limit)
    return None


def _pdf_text(data, limit):
    try:
        import pypdf
    except ImportError:
        return None
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        chunks = []
        for page in reader.pages:
            try:
                chunks.append(page.extract_text() or "")
            except Exception:
                continue
            if sum(len(c) for c in chunks) > limit:
                break
        text = "\n".join(chunks).strip()
    except Exception:
        return None
    return text[:limit] or None


def _docx_text(data, limit):
    try:
        import docx
    except ImportError:
        return None
    try:
        document = docx.Document(io.BytesIO(data))
        parts = [p.text for p in document.paragraphs if p.text.strip()]
        for table in document.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))
        text = "\n".join(parts).strip()
    except Exception:
        return None
    return text[:limit] or None


def _xml_text(data):
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return ""
    return " ".join(value.strip() for value in root.itertext() if value.strip())


def _office_zip_text(data, name, limit):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.namelist()
            if name.endswith(".xlsx"):
                paths = [p for p in members if p == "xl/sharedStrings.xml"
                         or (p.startswith("xl/worksheets/") and p.endswith(".xml"))]
            elif name.endswith(".pptx"):
                paths = sorted(p for p in members
                               if p.startswith("ppt/slides/slide") and p.endswith(".xml"))
            else:
                paths = ["content.xml"] if "content.xml" in members else []
            chunks = []
            for path in paths:
                if archive.getinfo(path).file_size > ARCHIVE_MAX_BYTES:
                    continue
                chunks.append(_xml_text(archive.read(path)))
                if sum(map(len, chunks)) >= limit:
                    break
    except Exception:  # a damaged archive can raise zlib.error, NotImplementedError, EOFError...
        return None
    text = "\n".join(part for part in chunks if part).strip()
    return text[:limit] or None


def _rtf_text(data, limit):
    text = data.decode("latin-1", "replace")
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", text)
    text = re.sub(r"[{}]", " ", text)
    text = text.replace(r"\~", " ").replace(r"\_", "-").replace(r"\-", "")
    text = " ".join(text.split())
    return text[:limit] or None


def _archive_text(data, name, limit):
    if not name.endswith(".zip"):
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            chunks = []
            total_size = 0
            for info in archive.infolist():
                if info.is_dir() or len(chunks) >= ARCHIVE_MAX_FILES:
                    continue
                suffix = Path(info.filename).suffix.lower()
                if suffix not in (".txt", ".md", ".csv", ".log", ".json", ".xml", ".html", ".htm",
                                  ".yaml", ".yml", ".rtf"):
                    continue
                total_size += info.file_size
                if total_size > ARCHIVE_MAX_BYTES:
                    break
                chunks.append(f"[{info.filename}]\n{archive.read(info).decode('utf-8', 'replace')}")
                if sum(map(len, chunks)) >= limit:
                    break
    except Exception:  # a damaged archive can raise zlib.error, NotImplementedError, EOFError...
        return None
    text = "\n\n".join(chunks).strip()
    return text[:limit] or None


def transcribe_audio(data, filename):
    """Transcribe audio using each configured OpenAI-compatible transcription endpoint."""
    errors = []
    for provider in llm.candidates("analysis"):
        try:
            response = requests.post(
                f'{provider["url"]}/audio/transcriptions',
                headers={"Authorization": f'Bearer {provider["key"]}'},
                data={"model": AUDIO_TRANSCRIPTION_MODEL},
                files={"file": (filename, data, "application/octet-stream")},
                timeout=(10, PROVIDER_TIMEOUT),
            )
        except requests.exceptions.RequestException as exc:
            errors.append(f'{provider["name"]}: {exc}')
            continue
        if response.ok:
            try:
                text = str(response.json().get("text") or "").strip()
            except (ValueError, AttributeError):
                text = ""
            if text:
                return text[:MAX_TEXT_CHARS], None
            errors.append(f'{provider["name"]}: empty transcription')
            continue
        detail = _response_detail(response)
        errors.append(f'{provider["name"]}: HTTP {response.status_code}: {detail}')
        if llm.looks_like_quota(response.status_code, response.text[:2000]):
            llm.set_aside(provider["index"])
    return None, "; ".join(errors) or "no transcription provider is configured"


def _response_detail(response):
    try:
        body = response.json()
    except ValueError:
        return (response.text or "")[:200]
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or json.dumps(error, ensure_ascii=False))[:200]
    return str(error or "")[:200]


def _remember_transcript(row, text):
    """Cache a transcript on its attachment. Best effort: a failed write only costs a re-run."""
    try:
        db.set_attachment_transcript(row["id"], text)
    except Exception:
        log.exception("Could not cache the transcript of attachment %s", row.get("id"))


def _cached_transcript(row):
    """The stored transcript: None when not transcribed yet, "" when there was nothing to hear."""
    return row.get("transcript") if hasattr(row, "get") else None


def _video_audio(row):
    exe = _ffmpeg()
    source = att.path_of(row)
    if not exe or not source:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "audio.mp3"
        try:
            result = subprocess.run(
                [exe, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-vn",
                 "-ac", "1", "-ar", "16000", "-b:a", "48k", str(target)],
                capture_output=True, timeout=90, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0 or not target.is_file():
            return None
        return target.read_bytes()


def video_frames(row, duration_guess=None):
    """Up to MAX_VIDEO_FRAMES evenly spaced JPEG data URIs, or [] when the video can't be read."""
    exe = _ffmpeg()
    source = att.path_of(row)
    if not exe or not source:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        duration = duration_guess or _duration(exe, source)
        if not duration or duration <= 0:
            return []
        uris = []
        for i in range(MAX_VIDEO_FRAMES):
            stamp = round(duration * (i + 1) / (MAX_VIDEO_FRAMES + 1), 2)
            out = Path(tmp) / f"f{i}.jpg"
            try:
                subprocess.run(
                    [exe, "-y", "-hide_banner", "-loglevel", "error", "-ss", str(stamp), "-i", str(source),
                     "-frames:v", "1", "-vf", f"scale={FRAME_WIDTH}:-2", "-q:v", "4", str(out)],
                    capture_output=True, timeout=45, check=False,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if out.is_file() and out.stat().st_size:
                uris.append(f"data:image/jpeg;base64,{base64.b64encode(out.read_bytes()).decode()}")
            if len(uris) >= MAX_VIDEO_FRAMES:
                break
        return uris


def _duration(exe, source):
    try:
        result = subprocess.run([exe, "-hide_banner", "-i", str(source)],
                                capture_output=True, text=True, timeout=30, errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    for line in (result.stderr or "").splitlines():
        if "Duration:" in line:
            stamp = line.split("Duration:")[1].split(",")[0].strip()
            try:
                hours, minutes, seconds = stamp.split(":")
                return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
            except ValueError:
                return None
    return None


def describe(lang, rows, cache=None):
    """What could be read from the attachments, as plain text for the prompt.

    Returns (text, images) where images is [(label, data_uri, attachment_id)] for the vision
    model; text covers documents and anything already described.
    """
    from i18n import t

    texts, images, skipped = [], [], []
    for row in rows:
        kind = row["kind"] or "file"
        name = row["file_name"] or "file"
        att_id = row["id"]
        if kind == "image" and name.lower().endswith(".svg"):
            kind = "text"   # older uploads stored SVG as an image; it is read as text now
        if kind == "image":
            uri = image_data_uri(row)
            if uri:
                images.append((name, uri, att_id))
            else:
                skipped.append(name)
        elif kind == "video":
            cached = cache.get(att_id) if cache else None
            if cached and cached.startswith("[video-frames-v1]\n"):
                cached_description = cached[len("[video-frames-v1]\n"):]
                texts.append(f"[{name}]\n{cached_description}")
            else:
                frames = video_frames(row)
                if frames:
                    images.extend((f"{name} ({t(lang, 'ex_label_frame', i=i + 1)})", uri, att_id, "video")
                                  for i, uri in enumerate(frames))
                else:
                    skipped.append(name)
            transcript, error = _cached_transcript(row), None
            if transcript is None:
                # Transcribed once and cached, like the frame descriptions above.
                audio = _video_audio(row)
                if audio:
                    transcript, error = transcribe_audio(audio, f"{Path(name).stem}.mp3")
                    if transcript:
                        _remember_transcript(row, transcript)
                elif _ffmpeg() and att.path_of(row):
                    _remember_transcript(row, "")   # the video has no sound track
            if transcript:
                texts.append(f"[{name} — {t(lang, 'ex_audio_transcript')}]\n{transcript}")
            elif error:
                skipped.append(f"{name} ({t(lang, 'ex_audio_transcript')}: {error})")
        elif kind in ("text", "pdf", "file"):
            text = text_of(row)
            if text:
                texts.append(f"[{name}]\n{text}")
            else:
                # Binaries, corrupt documents and unreadable PDFs: say so instead of dropping them.
                skipped.append(name)
        elif kind == "audio":
            transcript, error = _cached_transcript(row), None
            if not transcript:
                data = att.read(row)
                transcript, error = transcribe_audio(data, name) if data else (None, "file missing or empty")
                if transcript:
                    _remember_transcript(row, transcript)
            if transcript:
                texts.append(f"[{name}]\n{transcript}")
            else:
                skipped.append(f"{name} ({error})")
        else:
            skipped.append(name)

    parts = []
    if texts:
        parts.append(t(lang, "ex_documents") + "\n\n" + "\n\n".join(texts))
    if images:
        parts.append(t(lang, "ex_images", n=len(images)))
    if skipped:
        parts.append(t(lang, "ex_skipped", names="، ".join(skipped) if lang != "en" else ", ".join(skipped)))
    return "\n\n".join(parts), images
