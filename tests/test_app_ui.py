"""The real Streamlit app, driven through Streamlit's AppTest harness.

These run app/main.py exactly as the browser does: widgets are clicked and the resulting
page is inspected, so a broken import, an unbound widget key or a template error shows up
here rather than in front of the user. Network calls are stubbed out.
"""
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

MAIN = str(Path(__file__).resolve().parent.parent / "app" / "main.py")


def _run(at, times=1):
    for _ in range(times):
        at.run(timeout=30)
    return at


@pytest.fixture()
def app(database):
    def make(**session):
        at = AppTest.from_file(MAIN, default_timeout=30)
        for key, value in session.items():
            at.session_state[key] = value
        return _run(at)

    return make


def _markdown_text(at):
    return "\n".join(m.value for m in at.markdown)


def _page_text(at):
    """Everything visible on the page, whichever widget renders it."""
    parts = [m.value for m in at.markdown]
    parts += [c.value for c in at.caption] + [w.value for w in at.warning]
    parts += [code.value for code in at.code] + [e.label for e in at.expander]
    return "\n".join(str(p) for p in parts)


def test_app_starts_on_the_overview(app):
    at = app()
    assert not at.exception, at.exception
    assert "كل القضايا" in _markdown_text(at)

def test_about_page_shows_video_and_contact_links(app):
    at = app(view="about")
    assert not at.exception, at.exception
    assert any(button.label == "من أنا" for button in at.button)
    text = _markdown_text(at)
    assert "عبدالله حاج علي" in text
    assert "https://wa.me/97056939064" in text
    assert "https://github.com/3bdallah2004" in text
    assert "mailto:pcabdallah501@gmail.com" in text
    assert "about-email" not in text
    assert (Path(MAIN).parent / "assets" / "about-video-user.mp4").is_file()
    assert (Path(MAIN).parent / "assets" / "about-video-poster.jpg").is_file()

def test_about_navigation_label_uses_selected_language(app):
    at = app(view="about", lang="en")
    assert not at.exception, at.exception
    assert any(button.label == "About ME" for button in at.button)

def test_about_navigation_opens_the_page(app):
    at = app()
    at.button(key="nav_about").click().run()
    assert not at.exception, at.exception
    assert at.session_state["view"] == "about"

def test_empty_overview_offers_to_add_a_case(app):
    at = app()
    labels = [b.label for b in at.button]
    assert any("قضية جديدة" in label for label in labels)


def test_overview_lists_a_case(app, database, case):
    at = app()
    assert "قضية تجريبية" in _markdown_text(at)
    assert "ALP-2026-001" in _markdown_text(at)


def test_overview_counts_and_filters(app, database, case):
    database.update_case(case, status="analyzed", severity="high")
    at = app()
    text = _markdown_text(at)
    assert "محلَّلة" in text
    # Filtering by a status with no matches says so instead of tracing back.
    at.selectbox(key="ov_status").set_value("failed").run()
    assert not at.exception
    assert "لا توجد قضايا تطابق" in _page_text(at)


def test_search_filters_the_table(app, database, case):
    at = app()
    at.text_input(key="ov_q").set_value("لا-يوجد").run()
    assert "لا توجد قضايا تطابق" in _page_text(at)


def test_new_case_flow_saves_a_draft(app, database, monkeypatch):
    import analysis

    monkeypatch.setattr(analysis, "suggest_details", lambda text, lang: {})
    at = app()
    at.button(key="empty_new").click().run()
    assert at.session_state["view"] == "new"

    at.text_area(key="w_case_text").set_value("بلاغ كامل عن حادثة سرقة داخل المستودع المركزي ليلاً").run()
    at.button(key="flow_next").click().run()
    assert at.session_state["flow"]["step"] == 2
    assert database.list_cases()[0]["status"] == "draft"

    at.text_input(key="w_case_name").set_value("قضية جديدة").run()
    at.button(key="flow_save").click().run()
    assert not at.exception, at.exception
    rows = database.list_cases()
    assert len(rows) == 1
    assert rows[0]["case_name"] == "قضية جديدة"
    assert rows[0]["status"] == "draft"


def test_short_report_is_rejected(app):
    at = app()
    at.button(key="empty_new").click().run()
    at.text_area(key="w_case_text").set_value("قصير").run()
    at.button(key="flow_next").click().run()
    assert at.warning
    assert at.session_state["flow"]["step"] == 1


def test_sample_case_button_fills_the_form(app):
    at = app()
    at.button(key="empty_new").click().run()
    at.button(key="flow_sample").click().run()
    assert len(at.text_area(key="w_case_text").value) > 20


def test_case_page_shows_a_draft(app, database, case):
    at = app(view="case", case_id=case)
    text = _markdown_text(at)
    assert "قضية تجريبية" in text
    assert "مسودة" in text


def test_case_page_renders_an_analyzed_report(app, database, case):
    report = {"الملخص": "سرقة", "مستوى الخطورة": "مرتفع", "أدلة": ["بصمة"], "أطراف": ["متهم"]}
    database.update_case(case, status="analyzed", severity="high",
                         report_text=json.dumps(report, ensure_ascii=False))
    at = app(view="case", case_id=case)
    text = _markdown_text(at)
    assert "الملخص" in text
    assert "E-01" in text        # the evidence list
    assert "متهم" in text


def test_case_severity_does_not_show_case_status(app, database, case):
    database.update_case(case, status="analyzed", report_text="{}")
    at = app(view="case", case_id=case)
    fields = next(markdown.value for markdown in at.markdown if "مستوى الخطورة" in markdown.value)
    assert "pill-analyzed" not in fields
    assert "<span class=\"sev\">—</span>" in fields


@pytest.mark.parametrize(("initial_severity", "initial_label", "updated_severity", "updated_label"), [
    ("high", "مرتفع", "low", "منخفض"),
    ("low", "منخفض", "high", "مرتفع"),
])
def test_updating_report_refreshes_case_severity(
    app, database, case, initial_severity, initial_label, updated_severity, updated_label
):
    database.update_case(
        case, status="analyzed", severity=initial_severity,
        report_text=json.dumps({"مستوى الخطورة": initial_label}, ensure_ascii=False),
    )
    reply = json.dumps({"مستوى الخطورة": updated_label}, ensure_ascii=False)
    message_id = database.add_message(case, "assistant", reply)
    tab_key = f"case_tabs_{case}"
    at = app(view="case", case_id=case, **{tab_key: "المحادثة"})
    at.button(key=f"chat_update_report_{message_id}").click().run()
    assert not at.exception, at.exception
    assert database.get_case(case)["severity"] == updated_severity
    fields = next(markdown.value for markdown in at.markdown if "مستوى الخطورة" in markdown.value)
    assert updated_label in fields


def test_chat_reply_can_update_report_and_show_previous_version(app, database, case):
    database.update_case(case, status="analyzed", report_text="التقرير السابق")
    reply_id = database.add_message(case, "assistant", "التقرير المحدّث")
    tab_key = f"case_tabs_{case}"
    at = app(view="case", case_id=case, **{tab_key: "المحادثة"})
    at.button(key=f"chat_update_report_{reply_id}").click().run()
    assert not at.exception, at.exception
    assert database.get_case(case)["report_text"] == "التقرير المحدّث"
    assert [v["report_text"] for v in database.list_report_versions(case)] == ["التقرير السابق"]

    newer_reply_id = database.add_message(case, "assistant", "تقرير أحدث")
    at.run()
    at.button(key=f"chat_update_report_{newer_reply_id}").click().run()
    assert not at.exception, at.exception
    assert database.get_case(case)["report_text"] == "تقرير أحدث"
    versions = database.list_report_versions(case)
    assert [v["report_text"] for v in versions] == ["التقرير السابق", "التقرير المحدّث"]

    latest_reply_id = database.add_message(case, "assistant", "آخر تقرير")
    at.run()
    at.button(key=f"chat_update_report_{latest_reply_id}").click().run()
    assert not at.exception, at.exception
    assert database.get_case(case)["report_text"] == "آخر تقرير"
    versions = database.list_report_versions(case)
    assert [v["report_text"] for v in versions] == [
        "التقرير السابق", "التقرير المحدّث", "تقرير أحدث"
    ]

    report_at = app(view="case", case_id=case)
    labels = [b.label for b in report_at.button]
    assert "النسخة الأولى" in labels
    assert "النسخة الثانية" in labels
    assert "النسخة الثالثة" in labels
    version_id = versions[0]["id"]
    report_at.button(key=f"report_version_{case}_{version_id}").click().run()
    assert not report_at.exception, report_at.exception
    assert "التقرير السابق" in _markdown_text(report_at)
    assert database.get_case(case)["report_text"] == "آخر تقرير"


def test_case_page_shows_a_failure_and_offers_retry(app, database, case):
    database.update_case(case, status="failed", error="HTTP 500")
    at = app(view="case", case_id=case)
    assert "تعذّر تحليل" in _page_text(at)
    assert any(b.key == "retry" for b in at.button)


def test_case_page_shows_attachments(app, database, case):
    import attachments

    class F:
        name, type = "note.txt", "text/plain"
        _data = b"attachment text"

        def getvalue(self):
            return self._data

    attachments.save(case, F())
    at = app(view="case", case_id=case)
    assert "note.txt" in _page_text(at)


def test_delete_needs_confirmation_and_removes_the_case(app, database, case):
    at = app(view="case", case_id=case)
    at.button(key="del_ask").click().run()
    assert "حذف هذه القضية نهائياً" in _page_text(at)
    at.button(key="del_no").click().run()
    assert database.get_case(case) is not None

    at.button(key="del_ask").click().run()
    at.button(key="del_yes").click().run()
    assert database.get_case(case) is None
    assert at.session_state["view"] == "overview"


def test_english_language_toggle(app, database, case):
    at = app(view="case", case_id=case, lang="en")
    text = _markdown_text(at)
    assert "Severity" in text
    assert "This case is a draft" in text
    assert "Case" in text


def test_unknown_case_falls_back_to_overview(app):
    at = app(view="case", case_id=99999)
    assert not at.exception, at.exception
    assert at.session_state["view"] == "overview"


def test_reanalyze_from_the_case_page_starts_analysis(app, database, case, monkeypatch):
    import analysis

    started = []
    monkeypatch.setattr(analysis, "start_analysis", lambda cid, lang: started.append(cid))
    database.update_case(case, status="analyzed", report_text="{}")
    at = app(view="case", case_id=case)
    at.button(key="case_reanalyze").click().run()
    assert started == [case]


# ── automatic map pin ────────────────────────────────────────────────────────
def test_saving_a_case_pins_it_from_its_location(app, database, monkeypatch):
    import analysis
    import geocode

    monkeypatch.setattr(analysis, "suggest_details",
                        lambda text, lang: {"case_name": "قضية", "location": "رام الله"})
    monkeypatch.setattr(geocode, "GEOCODE_ENABLED", True)
    monkeypatch.setattr(geocode, "find", lambda location, lang="ar": (31.897801, 35.192422))

    at = app()
    at.button(key="empty_new").click().run()
    at.text_area(key="w_case_text").set_value("بلاغ كامل عن سرقة في المستودع المركزي بمدينة رام الله").run()
    at.button(key="flow_next").click().run()

    # The map opens on the suggested place, and says where the pin came from.
    assert at.session_state["flow"]["data"]["latitude"] == 31.897801
    assert "حُدّد الموقع تلقائياً" in _page_text(at)

    at.button(key="flow_save").click().run()
    assert not at.exception, at.exception
    row = database.list_cases()[0]
    assert database.get_case(row["id"])["latitude"] == 31.897801


def test_case_list_pins_older_cases_a_few_at_a_time(app, database, monkeypatch):
    import analysis

    ids = [database.create_draft(f"بلاغ رقم {i} عن حادثة في رام الله ليلاً")
           for i in range(5)]
    for i, case_id in enumerate(ids):
        database.update_case(case_id, case_name=f"قضية {i}", location="رام الله")

    asked = []
    monkeypatch.setattr(analysis, "locate", lambda cid, lang: asked.append(cid) or True)
    app()
    assert len(asked) == MAX_PINS if (MAX_PINS := 3) else True
    assert len(set(asked)) == len(asked)


def test_failed_lookup_is_explained_on_the_map(app, database, monkeypatch):
    import analysis
    import geocode

    monkeypatch.setattr(analysis, "suggest_details",
                        lambda text, lang: {"case_name": "قضية", "location": "عبر الإنترنت"})
    monkeypatch.setattr(geocode, "GEOCODE_ENABLED", True)
    monkeypatch.setattr(geocode, "find", lambda location, lang="ar": None)

    at = app()
    at.button(key="empty_new").click().run()
    at.text_area(key="w_case_text").set_value("بلاغ عن احتيال مالي عبر منصة على الإنترنت نفّذ عملياته").run()
    at.button(key="flow_next").click().run()
    assert at.session_state["flow"]["data"]["latitude"] is None
    assert "لم نتمكن من تحديد الموقع" in _page_text(at)


def test_clicking_the_map_overrides_the_automatic_pin(app, database, monkeypatch):
    import analysis
    import geocode
    import maps

    monkeypatch.setattr(analysis, "suggest_details",
                        lambda text, lang: {"case_name": "قضية", "location": "رام الله"})
    monkeypatch.setattr(geocode, "GEOCODE_ENABLED", True)
    monkeypatch.setattr(geocode, "find", lambda location, lang="ar": (31.9, 35.2))
    # One click: the map returns a point once, then reports no further clicks.
    clicks = [(32.5, 35.5)]

    def one_click(lat, lng, height=340):
        return clicks.pop() if clicks else None

    monkeypatch.setattr(maps, "pick_location", one_click)

    at = app()
    at.button(key="empty_new").click().run()
    at.text_area(key="w_case_text").set_value("بلاغ كامل عن سرقة في المستودع المركزي بمدينة رام الله").run()
    at.button(key="flow_next").click().run()

    data = at.session_state["flow"]["data"]
    assert (data["latitude"], data["longitude"]) == (32.5, 35.5)
    assert at.session_state["flow"]["auto_pin"] is False
