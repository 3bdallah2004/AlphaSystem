"""The conversation panel on a case page, laid out like a messaging app.

The messages live in a fixed-height scrolling area and the composer stays pinned at the bottom
of the window, so a new message never means scrolling the page.
"""
import streamlit as st

import attachments as att
import analysis
import chat
import db
from config import MAX_ATTACHMENT_MB
from i18n import t
from ui import esc, md

# Set before the tabs are built so sending a message keeps the conversation open.
# Streamlit refuses to change a tab's state after its widget exists.
CHAT_TAB_FLAG = "chat_stay_open"


def keep_open():
    return bool(st.session_state.pop(CHAT_TAB_FLAG, False))


def _file_chips(lang, message_id):
    """The attachments that came with one message, as small labels."""
    rows = db.list_message_attachments(message_id)
    if not rows:
        return
    chips = "".join(
        f'<span class="wa-file">{esc(r["file_name"])}'
        f'<span class="wa-file-size">{esc(att.human_size(r["size"]))}</span></span>'
        for r in rows
    )
    md(f'<div class="wa-files">{chips}</div>')


def _bubble(lang, message):
    """One message, as a bubble: mine on one side, Alpha's on the other."""
    role = "user" if message["role"] == "user" else "assistant"
    name = t(lang, "chat_you") if role == "user" else "Alpha"
    stamp = esc(str(message["timestamp"] or "")[11:16])
    with st.container(key=f"msg_{message['id']}"):
        md(f'<div class="wa-meta"><span class="wa-name">{esc(name)}</span>'
           f'<span class="wa-time">{stamp}</span></div>')
        _file_chips(lang, message["id"])
        if message["status"] == "pending":
            md('<div class="wa-typing"><span></span><span></span><span></span></div>')
        elif message["status"] == "failed":
            st.warning(t(lang, "chat_failed"))
            if message["error"]:
                with st.expander(t(lang, "error_details")):
                    st.code(message["error"])
            if st.button(t(lang, "chat_retry"), key=f"chatretry_{message['id']}"):
                chat.retry(message["case_id"], message["id"], lang)
                st.rerun()
        else:
            st.markdown(message["content"] or "")
            if role == "assistant" and (message["content"] or "").strip():
                if st.button(t(lang, "chat_update_report"), key=f"chat_update_report_{message['id']}"):
                    try:
                        db.update_report_from_message(
                            message["case_id"], message["id"],
                            severity=analysis.extract_severity(message["content"]),
                        )
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state["chat_notice"] = ("success", t(lang, "chat_report_updated"))
                        st.rerun()


def _scroll_to_latest():
    """Keep the newest message in view without moving the page itself."""
    st.html("""
    <script>
    (function () {
        const pane = window.parent.document.querySelector('.st-key-chatlog');
        if (pane) { pane.scrollTop = pane.scrollHeight; }
    })();
    </script>
    """, unsafe_allow_javascript=True)


def render(lang, case):
    """Full conversation for one case."""
    case_id = case["id"]
    rows = db.list_messages(case_id)
    pending = any(m["status"] == "pending" for m in rows)

    head, actions = st.columns([3, 1], vertical_alignment="center")
    with head:
        st.caption(t(lang, "chat_help"))
        if rows:
            st.caption(t(lang, "chat_count", n=len(rows)))
    with actions:
        if rows and st.button(t(lang, "chat_clear"), key=f"chatclear_{case_id}", width="stretch"):
            st.session_state[f"chat_confirm_{case_id}"] = True
    if st.session_state.get(f"chat_confirm_{case_id}"):
        st.warning(t(lang, "chat_clear_confirm"))
        c1, c2 = st.columns(2)
        if c1.button(t(lang, "confirm_yes"), key=f"chatclear_yes_{case_id}", width="stretch"):
            chat.clear(case_id)
            st.session_state.pop(f"chat_confirm_{case_id}", None)
            st.session_state["chat_notice"] = ("success", t(lang, "chat_cleared"))
            st.rerun()
        if c2.button(t(lang, "confirm_no"), key=f"chatclear_no_{case_id}", width="stretch"):
            st.session_state.pop(f"chat_confirm_{case_id}", None)
            st.rerun()

    if st.session_state.get("chat_notice"):
        kind, message = st.session_state.pop("chat_notice")
        {"success": st.success, "error": st.error}.get(kind, st.info)(message)

    # The scrolling transcript. Height is fixed so the page itself never grows with the chat.
    with st.container(key="chatlog", gap="small", height=460):
        if not rows:
            md(f'<div class="wa-empty">{esc(t(lang, "chat_empty"))}</div>')
        for message in rows:
            _bubble(lang, message)

    if pending:
        # A reply is being written on a background thread: poll and redraw when it lands.
        @st.fragment(run_every=3)
        def watch_reply():
            if not any(m["status"] == "pending" for m in db.list_messages(case_id)):
                st.rerun()
        watch_reply()

    # chat_input is pinned to the bottom of the viewport by Streamlit, so it is always at hand.
    entry = st.chat_input(t(lang, "chat_ph"), key=f"chat_input_{case_id}",
                          accept_file="multiple", file_type=att.ACCEPTED_MIME)
    if entry:
        question = (entry.text or "").strip()
        files = list(entry.files or [])
        if not question and not files:
            st.warning(t(lang, "chat_need_text"))
            return
        _, _, saved, errors = chat.ask(case_id, question, lang, files)
        for error in errors:
            st.error(error)
        if saved:
            st.session_state["chat_notice"] = ("success", t(lang, "chat_sent_files", n=saved))
        st.session_state[CHAT_TAB_FLAG] = True
        st.rerun()

    _scroll_to_latest()
