"""Rendering and upload widgets for case attachments."""
import streamlit as st

import attachments as att
import db
from config import MAX_ATTACHMENT_MB
from i18n import t

ICONS = {"image": ":material/image:", "video": ":material/movie:", "audio": ":material/audio_file:",
         "pdf": ":material/picture_as_pdf:", "text": ":material/description:", "file": ":material/draft:"}

DEFAULT_OPEN = {"image": True, "video": False, "audio": False, "pdf": False, "text": False, "file": False}


def _meta(lang, att_row):
    kind = att_row["kind"] or "file"
    return f'{t(lang, att.KIND_LABEL_KEY.get(kind, "att_kind_file"))} · {att.human_size(att_row["size"])}'


def read_summary(lang, rows):
    """One line saying what of these attachments the analysis can actually read."""
    readable, unreadable = [], []
    for row in rows:
        name = row["file_name"] or "file"
        kind = row["kind"] or "file"
        if kind in ("image", "video"):
            readable.append(name)
        elif kind in ("text", "pdf") or name.lower().endswith(".docx"):
            readable.append(name)
        else:
            unreadable.append(name)
    parts = []
    if readable:
        parts.append(t(lang, "att_readable", n=len(readable)))
    if unreadable:
        parts.append(t(lang, "att_not_readable", names=", ".join(unreadable)))
    return " · ".join(parts)


def read_preview(lang, case_id, key):
    """Show the exact text the analysis will receive from these attachments."""
    rows = db.list_attachments(case_id)
    if not rows:
        return
    if not st.button(t(lang, "att_preview"), key=key, width="stretch"):
        return
    import extract
    import vision
    with st.spinner(t(lang, "analysing_attachments")):
        cache = {r["id"]: r.get("description") for r in rows if r.get("description")}
        text, images = extract.describe(lang, rows, cache=cache)
        if images:
            described, errors = vision.describe_many(lang, images, cache=cache)
            text = "\n\n".join(p for p in (text, described) if p)
            for err in errors:
                st.warning(err)
    if text:
        st.code(text[:8000], language=None)
    else:
        st.caption(t(lang, "att_nothing_read"))


def uploader(lang, case_id, key):
    """Upload widget for one case. Files are written as soon as they are chosen."""
    if case_id is None:
        st.caption(t(lang, "att_save_first"))
        return
    generation_key = f"{key}_generation"
    widget_key = f"{key}_{st.session_state.get(generation_key, 0)}"
    files = st.file_uploader(
        t(lang, "att_add"), type=att.ACCEPTED_MIME, accept_multiple_files=True, key=widget_key,
        label_visibility="collapsed",
        help=t(lang, "att_help", mb=MAX_ATTACHMENT_MB),
    )
    if not files:
        return
    saved, errors = 0, []
    for f in files:
        ok, reason = att.save(case_id, f)
        if ok:
            saved += 1
        else:
            errors.append(f"{f.name}: {t(lang, reason, mb=MAX_ATTACHMENT_MB)}")
    # A fresh widget key clears the browser selection, so later reruns cannot save it twice.
    st.session_state[generation_key] = st.session_state.get(generation_key, 0) + 1
    st.session_state["att_notice"] = (
        ("success", t(lang, "att_uploaded", n=saved)) if saved else ("error", " · ".join(errors))
    )
    st.rerun()


def preview(lang, att_row, key):
    """Show the file inline: image, video, audio, PDF, or text."""
    kind = att_row["kind"] or "file"
    data = att.read(att_row)
    if data is None:
        st.caption(t(lang, "att_missing"))
        return
    mime = att_row["mime_type"] or "application/octet-stream"
    try:
        if kind == "image":
            st.image(data, width="stretch")
        elif kind == "video":
            st.video(data, format=mime)
        elif kind == "audio":
            st.audio(data, format=mime)
        elif kind == "pdf":
            st.pdf(data, height=520)
        elif kind == "text":
            st.code(data.decode("utf-8", "replace")[:20000] or " ",
                    language="markdown" if att_row["file_name"].endswith(".md") else None)
        else:
            st.caption(t(lang, "att_no_preview"))
    except Exception:  # a corrupt or unsupported file must not break the page
        st.caption(t(lang, "att_no_preview"))


def _download(lang, att_row):
    data = att.read(att_row)
    if data is None:
        return
    st.download_button(
        t(lang, "att_download"), data=data, file_name=att_row["file_name"],
        mime=att_row["mime_type"] or "application/octet-stream",
        icon=":material/download:", key=f"attdl_{att_row['id']}", width="stretch",
    )


def list_case_attachments(lang, case_id, editable=True):
    """Gallery for the case page, newest last, each with preview, download and delete."""
    rows = db.list_attachments(case_id)
    if not rows:
        st.caption(t(lang, "att_none"))
        return
    total = sum(r["size"] or 0 for r in rows)
    st.caption(t(lang, "att_summary", n=len(rows), size=att.human_size(total)))
    st.caption(read_summary(lang, rows))
    for row in rows:
        kind = row["kind"] or "file"
        title = f'{ICONS.get(kind, ICONS["file"])} {row["file_name"]}'
        with st.expander(title, expanded=kind == "image" and row is rows[-1]):
            st.caption(_meta(lang, row))
            preview(lang, row, key=f"attpv_{row['id']}")
            c1, c2 = st.columns([1, 1])
            with c1:
                _download(lang, row)
            if editable:
                with c2:
                    if st.button(t(lang, "att_delete"), key=f"attdel_{row['id']}", width="stretch"):
                        att.remove(row)
                        st.rerun()

