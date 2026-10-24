import html
import re
from pathlib import Path

import streamlit as st

from i18n import severity_label, status_label

STYLES = (Path(__file__).parent / "styles.css").read_text(encoding="utf-8")

esc = html.escape


def inject_styles(lang):
    direction, align, justify = ("ltr", "left", "flex-start") if lang == "en" else ("rtl", "right", "flex-end")
    start_side = "left" if lang == "en" else "right"      # the side text starts on, used by the about hero
    # Set the page language (screen readers, hyphenation) and stop browsers from auto-translating it.
    st.html(
        f"""<script>{{
        const d = document.documentElement;
        d.lang = '{lang}';
        d.setAttribute('translate', 'no');
        d.classList.add('notranslate');
        }}</script>""",
        unsafe_allow_javascript=True,
    )
    st.markdown(f"<style>:root {{ --dir: {direction}; --align: {align}; --justify: {justify}; --start-side: {start_side}; }}\n{STYLES}</style>",
                unsafe_allow_html=True)


def ltr(text):
    """Keep dates and case numbers left-to-right inside Arabic text (otherwise 2026-10-22 shows as 22-10-2026)."""
    return f"⁦{text}⁩"


def safe_filename(name):
    cleaned = re.sub(r"[^\w\- ]", "_", name or "report").strip()
    return cleaned[:80] or "report"


def md(markup):
    st.markdown(markup, unsafe_allow_html=True)


LOGO_MARK = (
    '<svg class="brand-mark" viewBox="0 0 100 96" aria-hidden="true" focusable="false">'
    '<defs><linearGradient id="alpha-g1" x1="0.1" y1="0" x2="0.5" y2="1"><stop offset="0" stop-color="#3AA6FF"/>'
    '<stop offset="1" stop-color="#0A52F0"/></linearGradient>'
    '<linearGradient id="alpha-g2" x1="0" y1="0" x2="0.6" y2="1"><stop offset="0" stop-color="#1E7BFF"/>'
    '<stop offset="1" stop-color="#0836C8"/></linearGradient></defs>'
    '<path fill="url(#alpha-g1)" d="M50 2 L58 17 L21 90 H3 L10 76 Z"/>'
    '<path fill="url(#alpha-g2)" d="M50 2 L97 92 H72 L38 40 Z"/>'
    '<path fill="url(#alpha-g1)" d="M19 74 H61 L52 90 H8 Z"/></svg>'
)


def brand(tagline):
    md(f'<div class="brand">{LOGO_MARK}<span class="brand-name">Alpha</span>'
       f'<span class="brand-tag">{esc(tagline)}</span></div>')


FEATURE_ICONS = {
    "cases": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
             '<path d="M3 13h18"/><path d="M11 13h2v2h-2z"/>',
    "ai": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/>'
          '<path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    "fast": '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    "local": '<path d="M12 3 4 6v6c0 5 3.4 8.3 8 9.5 4.6-1.2 8-4.5 8-9.5V6z"/>',
}


def features(label, items):
    """The strip of product highlights under the about hero. items: (icon, title, description)."""
    cells = "".join(
        f'<li class="feature"><span class="feature-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{FEATURE_ICONS[icon]}'
        f'</svg></span><h3>{esc(title)}</h3><p>{esc(text)}</p></li>'
        for icon, title, text in items
    )
    md(f'<ul class="features" aria-label="{esc(label)}">{cells}</ul>')


def heading(text, level=1, sub=None, cls=""):
    sub_html = f'<p class="page-sub">{esc(sub)}</p>' if sub else ""
    md(f'<h{level} class="page-h{level} {cls}">{esc(text)}</h{level}>{sub_html}')


def status_pill(lang, status):
    status = status or "draft"
    spinner = ('<svg aria-hidden="true" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
               'stroke-width="3" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.2-8.6"></path></svg>'
               if status == "analyzing" else "")
    return f'<span class="pill pill-{status}">{spinner}{esc(status_label(lang, status))}</span>'


def severity_html(lang, severity):
    cls = "sev-high" if severity == "high" else "sev"
    return f'<span class="{cls}">{esc(severity_label(lang, severity))}</span>'


def counts(items):
    cells = "".join(
        f'<div class="count{" count-alert" if alert else ""}"><dt>{esc(label)}</dt><dd>{value}</dd></div>'
        for label, value, alert in items
    )
    md(f'<dl class="counts">{cells}</dl>')


def type_bars(title, rows):
    top = max((n for _, n in rows), default=1) or 1
    cells = "".join(
        f'<span>{esc(label)}</span><span class="bar" aria-hidden="true" style="width:{n / top * 100:.0f}%"></span>'
        f'<span>{n}</span>'
        for label, n in rows
    )
    md(f'<section class="typebars"><h2>{esc(title)}</h2><div class="typebars-grid">{cells}</div></section>')


def fields(items):
    cells = "".join(
        f'<div class="field"><dt>{esc(label)}</dt><dd class="{cls}">{value_html}</dd></div>'
        for label, value_html, cls in items
    )
    md(f'<dl class="fields">{cells}</dl>')


def stepper(label, steps, current):
    items = []
    for i, text in enumerate(steps, start=1):
        state = "done" if i < current else "current" if i == current else "todo"
        mark = ('<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" '
                'stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5L20 7"></path></svg>'
                if state == "done" else str(i))
        aria = ' aria-current="step"' if state == "current" else ""
        items.append(f'<li class="step step-{state}"{aria}><span class="step-num" aria-hidden="true">{mark}</span>'
                     f'{esc(text)}</li>')
    md(f'<ol class="stepper" aria-label="{esc(label)}">{"".join(items)}</ol>')


def field_label(text, for_id_hint="", suggested_label=None):
    tag = f'<span class="sugg">{esc(suggested_label)}</span>' if suggested_label else ""
    md(f'<div class="flabel">{esc(text)}{tag}</div>')


def evidence_list(items):
    rows = "".join(
        f'<li class="evidence-item"><span class="tag">E-{i:02d}</span><span>{esc(str(item))}</span></li>'
        for i, item in enumerate(items, start=1)
    )
    md(f'<ul class="evidence">{rows}</ul>')


def bullet_list(items):
    md('<ul class="plain-list">' + "".join(f"<li>{esc(str(i))}</li>" for i in items) + "</ul>")


def render_value(value):
    if isinstance(value, str):
        st.markdown(value.replace("\n", "  \n"))
    elif isinstance(value, list) and all(isinstance(v, (str, int, float)) for v in value):
        st.markdown("\n".join(f"- {v}" for v in value))
    elif isinstance(value, dict) and all(isinstance(v, (str, int, float)) for v in value.values()):
        st.markdown("\n".join(f"- **{k}:** {v}" for k, v in value.items()))
    else:
        st.json(value)


def report_card(key, title, value):
    with st.container(key=key):
        md(f'<h2 class="card-h">{esc(str(title))}</h2>')
        render_value(value)


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [f"{k}: {v}" for k, v in value.items()]
    return [value]
