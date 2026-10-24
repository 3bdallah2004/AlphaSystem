import base64
import datetime
from pathlib import Path

import streamlit as st

from i18n import (ALL, CASE_TYPES, DEFAULT_LANG, LANGUAGES, SEVERITIES, STATUSES, case_type_label,
                  severity_label, status_label, t)

# The language toggle is bound to the URL (?lang=English), so it survives refreshes and shared links.
# The URL stores the button label, so map it back to a language code on the first run.
_url_lang = st.query_params.get("lang", "")
LANG = st.session_state.get("lang") or next(
    (code for code, label in LANGUAGES.items() if _url_lang in (code, label)), DEFAULT_LANG)

def tr(key, **kwargs):
    return t(LANG, key, **kwargs)

st.set_page_config(page_title=tr("page_title"), page_icon="🔎", layout="wide", initial_sidebar_state="collapsed")

import analysis
import attachment_ui
import attachments
import chat_ui
import db
import geocode
import maps
import ui
from samples import SAMPLES

MIN_CASE_TEXT_LEN = 20
# Older cases are pinned on the map a few at a time when the case list opens.
MAX_AUTO_PINS_PER_VIEW = 3
FLOW_FIELDS = ("case_text", "case_name", "case_number", "case_type", "location", "date")

@st.cache_resource
def startup():
    db.init_db()
    db.fail_interrupted(f"{t('ar', 'interrupted')}\n{t('en', 'interrupted')}")
    # Cases analyzed before severity was tracked: read it from their saved analysis.
    for case in db.list_cases(status="analyzed"):
        if not case["severity"]:
            full = db.get_case(case["id"])
            severity = analysis.extract_severity(full["report_text"])
            if severity:
                db.update_case(case["id"], severity=severity)
    return True

startup()
ui.inject_styles(LANG)

# ── Helpers ──────────────────────────────────────────────────────────────────
def type_label(case_type):
    return case_type_label(LANG, case_type or "عام")

def render_report_cards(report_text, prefix):
    report_data = analysis.parse_report(report_text)
    if not report_data:
        ui.report_card(prefix, tr("analysis_title"), report_text or "")
        return
    ev_key = analysis.find_key(report_data, "أدلة", "evidence")
    party_key = analysis.find_key(report_data, "أطراف", "parties")
    sev_key = analysis.find_key(report_data, "خطورة", "severity")
    items = [(k, v) for k, v in report_data.items() if k not in (ev_key, party_key, sev_key)]
    if items:
        ui.report_card(f"{prefix}_0", *items[0])
    rest = items[1:]
    i = 0
    while i < len(rest):
        pair = rest[i:i + 2]
        if len(pair) == 2 and all(isinstance(v, list) and len(v) <= 4 for _, v in pair):
            cols = st.columns(2, gap="small")
            for col, (key, value), n in zip(cols, pair, (i, i + 1)):
                with col:
                    ui.report_card(f"{prefix}_{n + 1}", key, value)
            i += 2
        else:
            ui.report_card(f"{prefix}_{i + 1}", *pair[0])
            i += 1

def report_version_label(index):
    if LANG == "en":
        return f"Version {index}"
    ordinals = ("الأولى", "الثانية", "الثالثة", "الرابعة", "الخامسة",
                "السادسة", "السابعة", "الثامنة", "التاسعة", "العاشرة")
    return f"النسخة {ordinals[index - 1]}" if index <= len(ordinals) else f"النسخة رقم {index}"

def parse_date(value):
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        return None

def flash(kind, message):
    st.session_state["flash"] = (kind, message)

def go(view, case_id=None, play_about_video=False):
    if view == "about" and play_about_video and st.session_state.get("view") != "about":
        st.session_state["about_video_autoplay"] = True
    st.session_state["view"] = view
    st.session_state["case_id"] = case_id
    st.session_state["confirm_delete"] = False
    st.query_params["view"] = view
    if case_id:
        st.query_params["case"] = str(case_id)
    elif "case" in st.query_params:
        del st.query_params["case"]
    if view == "case" and case_id:
        st.session_state["last_case"] = case_id

def start_flow(case_id=None, step=1):
    """Open the new-case flow, or the same flow for editing an existing case."""
    case = db.get_case(case_id) if case_id else None
    st.session_state["flow"] = {
        "id": case["id"] if case else None,
        "step": step,
        "editing": bool(case and case["status"] != "draft"),
        "suggested": set(),
        "auto_pin": False,          # the pin came from the report, not from a click
        "auto_lookup_failed": False,
        "data": {
            "case_text": (case or {}).get("case_text") or "",
            "case_name": (case or {}).get("case_name") or "",
            "case_number": (case or {}).get("case_number") or "",
            "case_type": (case or {}).get("case_type") if (case or {}).get("case_type") in CASE_TYPES else "عام",
            "location": (case or {}).get("location") or "",
            "date": parse_date((case or {}).get("date")),
            "latitude": (case or {}).get("latitude"),
            "longitude": (case or {}).get("longitude"),
        },
    }
    for field in FLOW_FIELDS:
        st.session_state.pop(f"w_{field}", None)
    go("new", case_id)

def set_flow_values(values, suggested=False):
    flow = st.session_state["flow"]
    for field, value in values.items():
        flow["data"][field] = value
        st.session_state.pop(f"w_{field}", None)   # the widget re-reads the new value on its next render
        if suggested:
            flow["suggested"].add(field)

def bound(widget, label, field, **kwargs):
    """A widget whose value lives in the flow's data, so it survives switching between steps."""
    data = st.session_state["flow"]["data"]
    key = f"w_{field}"
    if key not in st.session_state:
        st.session_state[key] = data[field]
    data[field] = widget(label, key=key, **kwargs)
    return data[field]

def reanalyze(case_id):
    analysis.start_analysis(case_id, LANG)

def ask_delete():
    st.session_state["confirm_delete"] = True

def cancel_delete():
    st.session_state["confirm_delete"] = False

def do_delete(case_id):
    attachments.remove_for_case(case_id)
    db.delete_case(case_id)
    if st.session_state.get("last_case") == case_id:
        st.session_state["last_case"] = None
    flash("success", tr("deleted"))
    go("overview")

def open_last_case():
    last = st.session_state.get("last_case")
    if not (last and db.get_case(last)):
        recent = db.list_cases(limit=1)
        last = recent[0]["id"] if recent else None
    if last:
        go("case", last)

def use_sample():
    cases = SAMPLES[LANG]
    idx = st.session_state.get("sample_idx", 0) % len(cases)
    s = cases[idx]
    st.session_state["sample_idx"] = idx + 1
    st.session_state["flow"]["suggested"] = set()
    set_flow_values({"case_text": s["text"], "case_name": s["name"], "case_type": s["type"],
                     "location": s["loc"], "date": parse_date(s["date"])})

# ── First run: restore the view from the URL ─────────────────────────────────
if "view" not in st.session_state:
    url_view = st.query_params.get("view", "overview")
    url_case = st.query_params.get("case", "")
    url_case = int(url_case) if url_case.isdigit() else None
    if url_view == "new":
        start_flow(url_case, step=2 if url_case else 1)
    elif url_view == "case" and url_case and db.get_case(url_case):
        go("case", url_case)
    elif url_view == "about":
        go("about")
    else:
        go("overview")

VIEW = st.session_state["view"]
if VIEW == "new" and "flow" not in st.session_state:
    start_flow()

# ── App bar ──────────────────────────────────────────────────────────────────
def language_toggle():
    with st.container(horizontal_alignment="right"):
        st.segmented_control(
            tr("language"), list(LANGUAGES), format_func=LANGUAGES.get, key="lang",
            default=DEFAULT_LANG, required=True, bind="query-params", label_visibility="collapsed",
        )

if VIEW == "new":
    flow = st.session_state["flow"]
    with st.container(key="appbar_light"):
        c1, c2, c3 = st.columns([3, 2, 1.3], vertical_alignment="center")
        with c1:
            ui.brand(tr("edit_case") if flow["editing"] else tr("new_case"))
        with c2:
            with st.container(horizontal_alignment="right"):
                st.button(tr("cancel_back"), type="tertiary", on_click=go, args=("overview",), key="flow_cancel")
        with c3:
            language_toggle()
else:
    with st.container(key="appbar_about" if VIEW == "about" else "appbar"):
        columns = [2.0, 2.5, 2.2] if VIEW == "about" else [2, 4, 2.2]
        c1, c2, c3 = st.columns(columns, vertical_alignment="center")
        with c1:
            ui.brand(tr("tagline"))
        with c2:
            with st.container(horizontal=True, horizontal_alignment="center", key="navlinks"):
                if VIEW == "about":
                    st.button(tr("nav_about"), type="tertiary", on_click=go, args=("about", None, True),
                              key="nav_about_on")
                    st.button(tr("nav_all"), type="tertiary", on_click=go, args=("overview",), key="nav_all")
                else:
                    st.button(tr("nav_all"), type="tertiary", on_click=go, args=("overview",),
                              key="nav_all_on" if VIEW == "overview" else "nav_all")
                    if VIEW != "about":
                        st.button(tr("nav_last"), type="tertiary", on_click=open_last_case,
                                  key="nav_last_on" if VIEW == "case" else "nav_last")
                    st.button(tr("nav_about"), type="tertiary", on_click=go, args=("about", None, True), key="nav_about")
        with c3:
            with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center"):
                st.button(tr("new_case"), type="primary", on_click=start_flow, key="appbar_new")
                st.segmented_control(
                    tr("language"), list(LANGUAGES), format_func=LANGUAGES.get, key="lang",
                    default=DEFAULT_LANG, required=True, bind="query-params", label_visibility="collapsed",
                )

# ── Background analyses: refresh the page when one finishes ──────────────────
running = db.analyzing_ids()
if running:
    @st.fragment(run_every=3)
    def watch_analyses():
        finished = running - db.analyzing_ids()
        if finished:
            case = db.get_case(next(iter(finished)))
            if case:
                name = case["case_name"] or tr("untitled")
                if case["status"] == "analyzed":
                    flash("success", tr("analysis_done", name=name))
                else:
                    flash("warning", tr("analysis_failed", name=name))
            st.rerun()
    watch_analyses()

def show_flash():
    if st.session_state.get("flash"):
        kind, message = st.session_state.pop("flash")
        {"success": st.success, "warning": st.warning, "error": st.error}.get(kind, st.info)(message)

ABOUT_ICONS = {
    "WA_SVG": "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M20.5 3.5A11.8 11.8 0 0 0 2 17.8L.5 23.5l5.8-1.5a11.8 11.8 0 0 0 5.6 1.4h.1A11.8 11.8 0 0 0 20.5 3.5ZM12 21.4a9.8 9.8 0 0 1-5-1.4l-.4-.2-3.4.9.9-3.3-.2-.4A9.8 9.8 0 1 1 12 21.4Zm5.4-7.3c-.3-.2-1.7-.9-2-.9-.3-.1-.5-.2-.7.2-.2.3-.8.9-1 1.1-.2.2-.4.2-.7.1-.3-.2-1.2-.5-2.3-1.5-.8-.7-1.4-1.7-1.6-2-.2-.3 0-.5.1-.6l.5-.6.3-.5c.1-.2 0-.4 0-.6l-.9-2.1c-.2-.6-.5-.5-.7-.5h-.6c-.2 0-.6.1-.9.4-.3.3-1.2 1.1-1.2 2.7s1.2 3.1 1.4 3.3c.2.2 2.3 3.5 5.6 4.9.8.3 1.4.5 1.8.6.8.2 1.5.2 2 .1.6-.1 1.7-.7 1.9-1.4.2-.7.2-1.3.2-1.4-.1-.2-.3-.3-.6-.4Z'/></svg>",
    "GH_SVG": "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M12 .8a11.2 11.2 0 0 0-3.5 21.8c.6.1.8-.2.8-.6v-2.1c-3.1.7-3.8-1.3-3.8-1.3-.5-1.3-1.2-1.6-1.2-1.6-1-.7.1-.7.1-.7 1.1.1 1.7 1.1 1.7 1.1 1 1.7 2.6 1.2 3.2.9.1-.7.4-1.2.7-1.5-2.5-.3-5.1-1.2-5.1-5.6 0-1.2.4-2.2 1.1-3-.1-.3-.5-1.5.1-3 0 0 .9-.3 3.1 1.1a10.7 10.7 0 0 1 5.7 0c2.2-1.4 3.1-1.1 3.1-1.1.6 1.5.2 2.7.1 3 .7.8 1.1 1.8 1.1 3 0 4.4-2.6 5.3-5.1 5.6.4.4.8 1 .8 2v3c0 .4.2.7.8.6A11.2 11.2 0 0 0 12 .8Z'/></svg>",
    "MAIL_SVG": "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M3 5h18a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Zm9 8.2L20.5 7h-17l8.5 6.2Zm0 2.4L3 8.7V17h18V8.7l-9 6.9Z'/></svg>",
}

ABOUT_CONTACTS = (
    ("https://wa.me/97056939064", "about_whatsapp", "WA_SVG", True),
    ("https://github.com/3bdallah2004", "about_github", "GH_SVG", True),
    ("mailto:pcabdallah501@gmail.com", "about_email", "MAIL_SVG", False),
)

def render_about():
    first, _, rest = tr("about_name").partition(" ")
    new_tab = " target='_blank' rel='noopener noreferrer'"
    links = "".join(
        f"<a href='{url}'{new_tab if external else ''} "
        f"aria-label='{ui.esc(tr(label))}' title='{ui.esc(tr(label))}'>{ABOUT_ICONS[icon]}</a>"
        for url, label, icon, external in ABOUT_CONTACTS
    )
    with st.container(key="aboutpage"):
        with st.container(key="aboutvideo"):
            assets = Path(__file__).parent / "assets"
            poster = base64.b64encode((assets / "about-video-poster.jpg").read_bytes()).decode("ascii")
            autoplay = st.session_state.pop("about_video_autoplay", False)
            st.video(str(assets / "about-video-user.mp4"),
                     autoplay=autoplay, loop=False, muted=True, width="stretch")
            player_controls = """
<div class="about-player-controlbar" role="group" aria-label="__CONTROLS__">
  <button class="about-player-button about-player-play" type="button" aria-label="__PLAY__" title="__PLAY__">
    <span class="player-icon-play" aria-hidden="true">▶</span>
    <span class="player-icon-pause" aria-hidden="true">Ⅱ</span>
  </button>
  <span class="about-player-time" aria-live="off">0:00 / 0:00</span>
  <input class="about-player-progress" type="range" min="0" max="100" step="0.1" value="0" aria-label="__SEEK__">
  <button class="about-player-button about-player-volume" type="button" aria-label="__MUTE__" title="__MUTE__">
    <span class="player-volume-on" aria-hidden="true"><i></i></span>
    <span class="player-volume-off" aria-hidden="true"><i></i></span>
  </button>
  <button class="about-player-button about-player-fullscreen" type="button" aria-label="__FULLSCREEN__" title="__FULLSCREEN__">
    <span class="player-fullscreen-icon" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
  </button>
  <button class="about-player-button about-player-more" type="button" aria-label="__MORE__" title="__MORE__" aria-expanded="false">
    <span aria-hidden="true">⋮</span>
  </button>
  <div class="about-player-menu" role="menu" aria-label="__MORE__" hidden>
    <button class="about-player-speed" type="button" role="menuitem" aria-label="__SPEED__">1×</button>
  </div>
</div>
<script>
(() => {
  const bindPlayer = () => {
    const root = document.querySelector('.st-key-aboutvideo');
    const video = root?.querySelector('video');
    const bar = root?.querySelector('.about-player-controlbar');
    if (!root || !video || !bar) { setTimeout(bindPlayer, 80); return; }
    if (bar.dataset.bound === 'true') return;
    bar.dataset.bound = 'true';
    video.poster = 'data:image/jpeg;base64,__POSTER__';
    video.controls = false;
    video.loop = false;
    const playButton = bar.querySelector('.about-player-play');
    const volumeButton = bar.querySelector('.about-player-volume');
    const fullscreenButton = bar.querySelector('.about-player-fullscreen');
    const moreButton = bar.querySelector('.about-player-more');
    const menu = bar.querySelector('.about-player-menu');
    const speedButton = bar.querySelector('.about-player-speed');
    const progress = bar.querySelector('.about-player-progress');
    const time = bar.querySelector('.about-player-time');
    const formatTime = (value) => {
      const seconds = Math.max(0, Math.floor(Number.isFinite(value) ? value : 0));
      return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    };
    const sync = () => {
      const duration = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : 8.041667;
      const currentTime = Number.isFinite(video.currentTime) ? video.currentTime : 0;
      const percent = duration > 0 ? Math.max(0, Math.min(100, (currentTime / duration) * 100)) : 0;
      progress.value = String(percent);
      progress.style.setProperty('--progress', `${percent}%`);
      time.textContent = `${formatTime(currentTime)} / ${formatTime(duration)}`;
      const playing = !video.paused && !video.ended;
      playButton.classList.toggle('is-playing', playing);
      playButton.setAttribute('aria-label', playing ? '__PAUSE__' : '__PLAY__');
      playButton.title = playing ? '__PAUSE__' : '__PLAY__';
      volumeButton.classList.toggle('is-muted', video.muted || video.volume === 0);
      volumeButton.setAttribute('aria-label', video.muted || video.volume === 0 ? '__UNMUTE__' : '__MUTE__');
      volumeButton.title = video.muted || video.volume === 0 ? '__UNMUTE__' : '__MUTE__';
    };
    playButton.addEventListener('click', () => {
      if (video.paused || video.ended) {
        if (video.ended) video.currentTime = 0;
        video.play().catch((error) => { console.error('ABOUT video playback failed:', error); sync(); });
      } else { video.pause(); }
    });
    progress.addEventListener('input', () => {
      if (!Number.isFinite(video.duration) || video.duration <= 0) return;
      const duration = video.duration;
      video.currentTime = (Number(progress.value) / 100) * duration;
      sync();
    });
    volumeButton.addEventListener('click', () => { video.muted = !video.muted; sync(); });
    let speedIndex = 0;
    const speeds = [1, 1.25, 1.5, 2];
    moreButton.addEventListener('click', () => {
      menu.hidden = !menu.hidden;
      moreButton.setAttribute('aria-expanded', String(!menu.hidden));
    });
    speedButton.addEventListener('click', () => {
      speedIndex = (speedIndex + 1) % speeds.length;
      video.playbackRate = speeds[speedIndex];
      speedButton.textContent = `${speeds[speedIndex]}×`;
    });
    document.addEventListener('click', (event) => {
      if (!bar.contains(event.target)) {
        menu.hidden = true;
        moreButton.setAttribute('aria-expanded', 'false');
      }
    });
    fullscreenButton.addEventListener('click', async () => {
      try {
        if (document.fullscreenElement) await document.exitFullscreen();
        else await root.requestFullscreen();
      } catch (_) {}
    });
    document.addEventListener('fullscreenchange', () => {
      const label = document.fullscreenElement ? '__EXIT_FULLSCREEN__' : '__FULLSCREEN__';
      fullscreenButton.setAttribute('aria-label', label);
      fullscreenButton.title = label;
    });
    ['loadedmetadata', 'durationchange', 'timeupdate', 'play', 'pause', 'ended', 'volumechange', 'error'].forEach((event) => video.addEventListener(event, sync));
    video.muted = true;
    const startAutoplay = () => {
      if (video.autoplay && video.paused && !video.ended) {
        video.play().catch((error) => { console.error('ABOUT video autoplay failed:', error); sync(); });
      }
    };
    if (video.autoplay) {
      startAutoplay();
      ['loadedmetadata', 'loadeddata', 'canplay'].forEach((event) => {
        video.addEventListener(event, startAutoplay, { once: true });
      });
    }
    sync();
  };
  bindPlayer();
})();
</script>
"""
            player_controls = player_controls.replace("__POSTER__", poster)
            for token, key in (
                ("__CONTROLS__", "about_video_controls"), ("__PLAY__", "about_video_play"),
                ("__PAUSE__", "about_video_pause"), ("__SEEK__", "about_video_seek"),
                ("__MUTE__", "about_video_mute"), ("__UNMUTE__", "about_video_unmute"),
                ("__FULLSCREEN__", "about_video_fullscreen"),
                ("__EXIT_FULLSCREEN__", "about_video_exit_fullscreen"),
                ("__MORE__", "about_video_more"), ("__SPEED__", "about_video_speed"),
            ):
                player_controls = player_controls.replace(token, ui.esc(tr(key)))
            st.html(player_controls, unsafe_allow_javascript=True)
            ui.md("<div class='about-scrim' aria-hidden='true'></div>")
            ui.md(f"<nav class='about-social' aria-label='{ui.esc(tr('about_contact_label'))}'>{links}</nav>")
            with st.container(key="aboutcopy"):
                ui.md(
                    f"<h1 class='about-name' aria-label='{ui.esc(tr('about_name'))}'>"
                    f"<span aria-hidden='true'>{ui.esc(first)}</span> "
                    f"<span class='about-name-accent' aria-hidden='true'>{ui.esc(rest)}</span></h1>"
                    f"<p class='about-description'>{ui.esc(tr('about_description'))}</p>"
                )
                st.button(tr("about_cta"), type="primary", on_click=go, args=("overview",), key="about_cta")
        ui.features(tr("about_features_label"), [
            ("cases", tr("feat_cases"), tr("feat_cases_d")),
            ("ai", tr("feat_ai"), tr("feat_ai_d")),
            ("fast", tr("feat_fast"), tr("feat_fast_d")),
            ("local", tr("feat_local"), tr("feat_local_d")),
        ])

# ── View: all cases ──────────────────────────────────────────────────────────
def render_overview():
    with st.container(key="page", gap="medium"):
        show_flash()
        h1, h2 = st.columns([3, 1.2], vertical_alignment="bottom")
        with h1:
            ui.heading(tr("ov_title"))
        with h2:
            st.download_button(tr("export_csv"), data=lambda: db.export_cases_csv(tr("csv_headers")),
                               file_name="alpha_cases.csv", mime="text/csv", icon=":material/download:",
                               width="stretch")

        stats = db.stats()
        by_status = stats["by_status"]
        if not stats["total"]:
            st.info(tr("ov_empty"))
            st.button(tr("new_case"), type="primary", on_click=start_flow, key="empty_new")
            return

        s1, s2 = st.columns([2.4, 1], gap="medium")
        with s1:
            ui.counts([
                (tr("count_all"), stats["total"], False),
                (tr("count_analyzed"), by_status.get("analyzed", 0), False),
                (tr("count_analyzing"), by_status.get("analyzing", 0), False),
                (tr("count_draft"), by_status.get("draft", 0), False),
                (tr("count_failed"), by_status.get("failed", 0), bool(by_status.get("failed"))),
            ])
        with s2:
            ui.type_bars(tr("by_type"), [(type_label(ct), n) for ct, n in stats["by_type"]])

        f1, f2, f3, f4 = st.columns([2.4, 1, 1, 1])
        search = f1.text_input(tr("search"), placeholder=tr("search_ph"), key="ov_q")
        f_type = f2.selectbox(tr("f_type"), [ALL] + CASE_TYPES, key="ov_type",
                              format_func=lambda v: case_type_label(LANG, v))
        f_status = f3.selectbox(tr("f_status"), [ALL] + STATUSES, key="ov_status",
                                format_func=lambda v: status_label(LANG, v))
        f_sev = f4.selectbox(tr("f_severity"), [ALL] + SEVERITIES, key="ov_sev",
                             format_func=lambda v: severity_label(LANG, v))

        rows = db.list_cases(search.strip(), *(None if v == ALL else v for v in (f_type, f_status, f_sev)))
        if not rows:
            st.caption(tr("ov_no_match"))
            return

        # Cases saved before map pins were filled in get one here, a few per visit, so a big
        # existing register does not fire dozens of place lookups on a single page load.
        geolocated, candidates = 0, []
        for c in reversed(rows):
            if geolocated >= MAX_AUTO_PINS_PER_VIEW or len(candidates) >= MAX_AUTO_PINS_PER_VIEW * 3:
                break
            if c["latitude"] is None:
                candidates.append(c["id"])
        for case_id in candidates:
            if geolocated >= MAX_AUTO_PINS_PER_VIEW:
                break
            if analysis.locate(case_id, LANG):
                geolocated += 1
        if geolocated:
            rows = db.list_cases(search.strip(), *(None if v == ALL else v for v in (f_type, f_status, f_sev)))

        with st.container(key="mapcard", gap="small"):
            ui.heading(tr("ov_map"), level=2)
            pinned = maps.show_cases(
                rows,
                lambda c: (c["case_name"] or tr("untitled"),
                           f"{c['case_number'] or ''} {type_label(c['case_type'])}, {status_label(LANG, c['status'])}"),
                key="overview_map",
            )
            st.caption(tr("ov_map_count", n=pinned, total=len(rows)) if pinned else tr("ov_map_none"))

        widths = [1.25, 3.0, 1.4, 1.7, 0.9, 0.8, 1.1, 1.2]
        files = db.attachment_counts()
        with st.container(key="casetable", gap=None):
            with st.container(key="tablehead"):
                cols = st.columns(widths)
                for col, key in zip(cols, ("th_number", "th_case", "th_type", "th_status", "th_severity",
                                           "th_files", "th_added")):
                    col.markdown(tr(key))
            for c in rows:
                status = c["status"] or "draft"
                with st.container(key=f"row_{c['id']}_{status}"):
                    cols = st.columns(widths, vertical_alignment="center")
                    ui_cell = lambda col, markup: col.markdown(markup, unsafe_allow_html=True)
                    ui_cell(cols[0], f'<span class="cell-num">{ui.esc(c["case_number"] or "—")}</span>')
                    ui_cell(cols[1], f'<span class="cell-name">{ui.esc(c["case_name"] or tr("untitled"))}</span>')
                    cols[2].markdown(type_label(c["case_type"]))
                    ui_cell(cols[3], ui.status_pill(LANG, status))
                    ui_cell(cols[4], ui.severity_html(LANG, c["severity"]))
                    count = files.get(c["id"], (0, 0))[0]
                    cols[5].markdown(f'<span class="cell-files">📎 {count}</span>' if count else "—",
                                     unsafe_allow_html=True)
                    cols[6].markdown(ui.ltr(str(c["timestamp"])[:10]))
                    with cols[7]:
                        if status == "draft":
                            st.button(tr("complete"), key=f"act_{c['id']}", type="tertiary",
                                      on_click=start_flow, args=(c["id"], 2))
                        elif status == "failed":
                            st.button(tr("reanalyze"), key=f"act_{c['id']}", on_click=reanalyze, args=(c["id"],))
                        else:
                            st.button(tr("open"), key=f"act_{c['id']}", type="tertiary",
                                      on_click=go, args=("case", c["id"]))

# ── View: one case ───────────────────────────────────────────────────────────
def render_case():
    case = db.get_case(st.session_state.get("case_id"))
    if not case:
        go("overview")
        st.rerun()
    status = case["status"] or "draft"
    report = analysis.parse_report(case["report_text"]) if status == "analyzed" else None
    ev_key = analysis.find_key(report, "أدلة", "evidence") if report else None
    party_key = analysis.find_key(report, "أطراف", "parties") if report else None
    sev_key = analysis.find_key(report, "خطورة", "severity") if report else None

    with st.container(key="workspace"):
        rail, main, aside = st.columns([1.05, 2.8, 1.2], gap="medium")

        with rail:
            with st.container(key="rail", gap="small"):
                st.button(tr("new_case"), type="primary", on_click=start_flow, key="rail_new", width="stretch")
                r1, r2 = st.columns([1.4, 1], vertical_alignment="center")
                with r1:
                    ui.heading(tr("register"), level=2)
                with r2:
                    st.button(tr("nav_all"), type="tertiary", on_click=go, args=("overview",), key="rail_all")
                for c in db.list_cases(limit=12):
                    key = f"railon_{c['id']}" if c["id"] == case["id"] else f"railcase_{c['id']}"
                    st.button(c["case_name"] or tr("untitled"), key=key, type="tertiary",
                              on_click=go, args=("case", c["id"]), width="stretch")
                st.divider()
                st.download_button(tr("export_csv"), data=lambda: db.export_cases_csv(tr("csv_headers")),
                                   file_name="alpha_cases.csv", mime="text/csv", width="stretch", key="rail_csv")
                if st.button(tr("check_service"), width="stretch", key="rail_check"):
                    level, msg = analysis.check_n8n(LANG)
                    {"success": st.success, "warning": st.warning}.get(level, st.error)(msg)

        with main:
            show_flash()
            ui.md(f'<div class="case-number">{ui.esc(case["case_number"] or "")}</div>')
            ui.heading(case["case_name"] or tr("untitled"))
            with st.container(horizontal=True, gap="small"):
                st.button(tr("edit"), on_click=start_flow, args=(case["id"], 2), key="case_edit")
                st.button(tr("reanalyze"), on_click=reanalyze, args=(case["id"],), key="case_reanalyze",
                          disabled=status in ("analyzing", "draft"))
                st.download_button(tr("download_report"), data=analysis.report_as_text(case["report_text"]),
                                   file_name=f"{ui.safe_filename(case['case_name'])}_report.txt", mime="text/plain",
                                   key="dlreport", disabled=status != "analyzed")
                st.button(tr("delete"), on_click=ask_delete, key="del_ask")
            if st.session_state.get("confirm_delete"):
                st.warning(tr("confirm_delete"))
                with st.container(horizontal=True, gap="small"):
                    st.button(tr("confirm_yes"), on_click=do_delete, args=(case["id"],), key="del_yes")
                    st.button(tr("confirm_no"), on_click=cancel_delete, key="del_no")

            ui.fields([
                (tr("m_type"), ui.esc(type_label(case["case_type"])), ""),
                (tr("m_location"), ui.esc(case["location"] or tr("not_set")), ""),
                (tr("m_date"), ui.esc(case["date"] or tr("not_set")), ""),
                (tr("m_severity"), ui.severity_html(LANG, case["severity"]), ""),
            ])

            # Labels stay stable: the tabs widget stores the selected label, so a label that
            # carried the message count would stop matching once a message is sent.
            report_label = tr("tab_report")
            chat_label = tr("tab_chat")
            tab_key = f"case_tabs_{case['id']}"
            # Read before the tabs widget exists: sending a message sets this so the
            # conversation stays open instead of the page falling back to the report.
            if chat_ui.keep_open():
                st.session_state[tab_key] = chat_label
            st.session_state.setdefault(tab_key, report_label)
            tab_report, tab_chat = st.tabs([report_label, chat_label], key=tab_key,
                                           on_change="rerun")

            with tab_report:
                if status == "analyzing":
                    with st.container(key="card_status"):
                        ui.md(ui.status_pill(LANG, "analyzing"))
                        st.markdown(tr("analyzing_card"))
                elif status == "failed":
                    with st.container(key="card_status_failed"):
                        st.markdown(tr("failed_card"))
                        if case["error"]:
                            with st.expander(tr("error_details")):
                                st.code(case["error"])
                        st.button(tr("reanalyze"), type="primary", on_click=reanalyze,
                                  args=(case["id"],), key="retry")
                elif status == "draft":
                    with st.container(key="card_status"):
                        st.markdown(tr("draft_card"))
                        with st.container(horizontal=True, gap="small"):
                            st.button(tr("analyze_now"), type="primary", on_click=reanalyze,
                                      args=(case["id"],), key="draft_analyze")
                            st.button(tr("continue_editing"), on_click=start_flow, args=(case["id"], 2),
                                      key="draft_edit")
                else:
                    render_report_cards(case["report_text"], "card")

                versions = db.list_report_versions(case["id"])
                if versions:
                    ui.heading(tr("report_versions_title"), level=2)
                    selected_key = f"report_version_selected_{case['id']}"
                    selected_id = st.session_state.get(selected_key)
                    for start in range(0, len(versions), 3):
                        cols = st.columns(3, gap="small")
                        for offset, version in enumerate(versions[start:start + 3], start=start + 1):
                            with cols[offset - start - 1]:
                                if st.button(report_version_label(offset),
                                             key=f"report_version_{case['id']}_{version['id']}",
                                             type="primary" if selected_id == version["id"] else "secondary",
                                             width="stretch"):
                                    st.session_state[selected_key] = version["id"]
                                    st.rerun()
                    selected = next((v for v in versions if v["id"] == selected_id), None)
                    if selected:
                        st.caption(tr("report_version_selected",
                                      version=report_version_label(versions.index(selected) + 1),
                                      timestamp=selected["timestamp"]))
                        render_report_cards(selected["report_text"],
                                            f"report_version_content_{selected['id']}")
                    else:
                        st.caption(tr("report_version_empty"))

            with tab_chat:
                if status == "draft":
                    st.caption(tr("chat_needs_analysis"))
                else:
                    chat_ui.render(LANG, case)

        with aside:
            with st.container(key="mapcard", gap="small"):
                ui.heading(tr("map_pin"), level=2)
                if case["latitude"] is not None and case["longitude"] is not None:
                    maps.show_case(case["latitude"], case["longitude"], key=f"casemap_{case['id']}")
                    st.caption(ui.ltr(maps.format_coords(case["latitude"], case["longitude"])))
                else:
                    st.caption(tr("map_case_none"))
            with st.container(key="attachments", gap="small"):
                n_files = len(db.list_attachments(case["id"]))
                ui.heading(tr("attachments"), level=2,
                           sub=tr("att_count", n=n_files) if n_files else None)
                attachment_ui.uploader(LANG, case["id"], key=f"attup_{case['id']}")
                if st.session_state.get("att_notice"):
                    kind, message = st.session_state.pop("att_notice")
                    {"success": st.success, "error": st.error}.get(kind, st.info)(message)
                attachment_ui.list_case_attachments(LANG, case["id"])
                attachment_ui.read_preview(LANG, case["id"], key=f"attread_{case['id']}")
            with st.container(key="evidence", gap="small"):
                ui.heading(tr("evidence"), level=2)
                evidence = ui.as_list(report.get(ev_key)) if report and ev_key else []
                if evidence:
                    ui.evidence_list(evidence)
                else:
                    st.caption(tr("no_evidence"))
                parties = ui.as_list(report.get(party_key)) if report and party_key else []
                if parties:
                    ui.heading(tr("parties"), level=2)
                    ui.bullet_list(parties)
                with st.expander(tr("original_report")):
                    st.markdown((case["case_text"] or "").replace("\n", "  \n"))

# ── View: new case / edit case ───────────────────────────────────────────────
def render_flow():
    flow = st.session_state["flow"]
    data = flow["data"]
    with st.container(key="flowpage", gap="medium"):
        show_flash()
        ui.stepper(tr("steps_label"), [tr("step1"), tr("step2")], flow["step"])

        if flow["step"] == 1:
            form, tips = st.columns([2.4, 1], gap="large")
            with form:
                ui.heading(tr("step1"), sub=tr("s1_help"))
                bound(st.text_area, tr("step1"), "case_text", height=300, label_visibility="collapsed")
                n1, n2 = st.columns(2)
                n1.caption(tr("s1_saved_note"))
                n2.caption(tr("chars", n=len(data["case_text"])))
                with st.container(horizontal=True, gap="small", vertical_alignment="center"):
                    go_next = st.button(tr("next"), type="primary", key="flow_next")
                    st.button(tr("use_sample"), type="tertiary", on_click=use_sample, key="flow_sample")
            with tips:
                with st.container(key="tips"):
                    ui.heading(tr("tips_title"), level=2)
                    ui.md('<dl class="tips">' + "".join(
                        f"<div><dt>{ui.esc(tr(k))}</dt><dd>{ui.esc(tr(k + '_d'))}</dd></div>"
                        for k in ("tip_when", "tip_where", "tip_who", "tip_evidence")) + "</dl>")
                    st.caption(tr("tips_note"))

            if go_next:
                text = data["case_text"].strip()
                if len(text) < MIN_CASE_TEXT_LEN:
                    st.warning(tr("v_text_short", n=MIN_CASE_TEXT_LEN))
                    return
                if flow["id"] is None:
                    flow["id"] = db.create_draft(text)
                    st.query_params["case"] = str(flow["id"])
                else:
                    db.update_case(flow["id"], case_text=text)
                if not data["case_name"]:
                    with st.spinner(tr("suggesting")):
                        suggestion = analysis.suggest_details(text, LANG)
                    if "date" in suggestion:
                        suggestion["date"] = parse_date(suggestion["date"])
                    set_flow_values({k: v for k, v in suggestion.items() if not data.get(k) or k == "case_type"},
                                    suggested=True)
                # Pin the suggested location so the map opens on it; a click still overrides it.
                if data["latitude"] is None and data.get("location"):
                    point = geocode.find(data["location"], LANG)
                    if point:
                        data["latitude"], data["longitude"] = point
                        flow["auto_pin"] = True
                    else:
                        flow["auto_lookup_failed"] = True
                if not data["case_number"]:
                    set_flow_values({"case_number": db.next_case_number()})
                flow["step"] = 2
                st.rerun()
            return

        # Step 2: details
        def sugg(field):
            return tr("suggested") if field in flow["suggested"] else None

        form, story = st.columns([2.4, 1], gap="large")
        with form:
            ui.heading(tr("step2"), sub=tr("s2_help_edit") if flow["editing"] else tr("s2_help"))
            ui.field_label(tr("f_name") + " *", suggested_label=sugg("case_name"))
            bound(st.text_input, tr("f_name"), "case_name", label_visibility="collapsed")
            g1, g2 = st.columns(2)
            with g1:
                ui.field_label(tr("f_type"), suggested_label=sugg("case_type"))
                bound(st.selectbox, tr("f_type"), "case_type", options=CASE_TYPES, format_func=type_label,
                      label_visibility="collapsed")
                ui.field_label(tr("f_date"), suggested_label=sugg("date"))
                bound(st.date_input, tr("f_date"), "date", format="YYYY-MM-DD", label_visibility="collapsed")
                if data["date"] is None:
                    ui.md(f'<div class="field-hint field-hint-warn">{ui.esc(tr("date_missing"))}</div>')
            with g2:
                ui.field_label(tr("f_number"))
                bound(st.text_input, tr("f_number"), "case_number", label_visibility="collapsed")
                ui.md(f'<div class="field-hint">{ui.esc(tr("number_help"))}</div>')
                ui.field_label(tr("f_location"), suggested_label=sugg("location"))
                bound(st.text_input, tr("f_location"), "location", label_visibility="collapsed")

            ui.field_label(tr("map_pin"))
            st.caption(tr("map_pin_help"))
            picked = maps.pick_location(data["latitude"], data["longitude"])
            if picked:
                data["latitude"], data["longitude"] = picked
                flow["auto_pin"] = False
                st.rerun()
            if data["latitude"] is not None:
                p1, p2 = st.columns([3, 1], vertical_alignment="center")
                p1.caption(tr("map_pin_set", coords=ui.ltr(maps.format_coords(data["latitude"], data["longitude"]))))
                if p2.button(tr("map_pin_clear"), type="tertiary", key="pin_clear"):
                    data["latitude"] = data["longitude"] = None
                    flow["auto_pin"] = False
                    st.rerun()
                if flow.get("auto_pin"):
                    st.caption(tr("map_auto_set"))
            elif data.get("location") and flow.get("auto_lookup_failed"):
                st.caption(tr("map_auto_failed"))
                st.caption(tr("map_pin_none"))
            else:
                st.caption(tr("map_pin_none"))

            st.divider()
            ui.heading(tr("attachments"), level=2)
            attachment_ui.uploader(LANG, flow["id"], key=f"attup_flow_{flow['id'] or 'new'}")
            if flow["id"]:
                attachment_ui.list_case_attachments(LANG, flow["id"])

            with st.container(horizontal=True, gap="small", vertical_alignment="center"):
                save_analyze = st.button(tr("save_reanalyze") if flow["editing"] else tr("save_analyze"),
                                         type="primary", key="flow_analyze")
                save_only = st.button(tr("save_changes") if flow["editing"] else tr("save_draft"), key="flow_save")
                back = st.button(tr("back"), type="tertiary", key="flow_back")
            st.caption(tr("s2_note"))
        with story:
            with st.container(key="storycard", gap="small"):
                ui.heading(tr("story_title"), level=2)
                st.markdown(data["case_text"].replace("\n", "  \n"))
                edit_text = st.button(tr("edit"), type="tertiary", key="flow_edit_text")

        if back or edit_text:
            flow["step"] = 1
            st.rerun()
        if save_analyze or save_only:
            if not data["case_name"].strip():
                st.warning(tr("v_name"))
                return
            case_id = flow["id"] or db.create_draft(data["case_text"])
            db.update_case(
                case_id,
                case_name=data["case_name"].strip(), case_number=data["case_number"].strip(),
                case_type=data["case_type"], location=data["location"].strip(),
                date=data["date"].isoformat() if data["date"] else "", case_text=data["case_text"].strip(),
                latitude=data["latitude"], longitude=data["longitude"],
            )
            # Saving without analyzing still puts the case on the map.
            analysis.locate(case_id, LANG)
            dup = tr("dup_number") if db.case_number_exists(data["case_number"].strip(), exclude_id=case_id) else ""
            if save_analyze:
                analysis.start_analysis(case_id, LANG)
                flash("warning" if dup else "success", tr("analysis_started") + dup)
                go("overview")
            elif flow["editing"]:
                flash("warning" if dup else "success", tr("changes_saved") + dup)
                go("case", case_id)
            else:
                flash("warning" if dup else "success", tr("draft_saved") + dup)
                go("overview")
            st.session_state.pop("flow", None)
            st.rerun()

{"overview": render_overview, "case": render_case, "new": render_flow,
 "about": render_about}.get(VIEW, render_overview)()
