"""Translation table integrity and the HTML builders that do not need a Streamlit runtime."""
import importlib
import re

import pytest

import i18n


def test_every_string_has_both_languages():
    for key, value in i18n.STRINGS.items():
        assert isinstance(value, tuple) and len(value) == 2, key
        assert value[0] and value[1], key


def test_placeholders_match_between_languages():
    """A `{name}` in one language must exist in the other, or one of them formats wrong."""
    for key, (ar, en) in i18n.STRINGS.items():
        if not isinstance(ar, str):
            continue
        assert set(re.findall(r"{(\w+)}", ar)) == set(re.findall(r"{(\w+)}", en)), key


def test_t_formats():
    assert i18n.t("ar", "chars", n=5) == "5 حرفاً"
    assert i18n.t("en", "chars", n=5) == "5 characters"


def test_t_does_not_format_literal_braces_when_no_kwargs():
    # csv_headers and similar literal strings must come back untouched.
    assert i18n.t("en", "tagline") == "Case analysis lab"


def test_t_unknown_key_raises():
    with pytest.raises(KeyError):
        i18n.t("ar", "no_such_key")


def test_case_type_labels():
    assert i18n.case_type_label("en", "سرقة") == "Theft"
    assert i18n.case_type_label("ar", "سرقة") == "سرقة"
    assert i18n.case_type_label("en", "غير معروف") == "غير معروف"
    assert i18n.case_type_label("en", i18n.ALL) == "All types"


def test_status_labels_cover_all_statuses_and_all_sentinel():
    for status in i18n.STATUSES:
        assert i18n.status_label("ar", status)
        assert i18n.status_label("en", status)
    assert i18n.status_label("ar", None)          # falls back to draft
    assert i18n.status_label("en", i18n.ALL) == "All statuses"


def test_severity_labels():
    assert i18n.severity_label("ar", "high") == "مرتفع"
    assert i18n.severity_label("en", "low") == "Low"
    assert i18n.severity_label("en", None) == "—"
    assert i18n.severity_label("ar", i18n.ALL)


def test_samples_exist_in_both_languages():
    import samples

    assert len(samples.SAMPLES["ar"]) == len(samples.SAMPLES["en"]) > 0
    for lang in ("ar", "en"):
        for item in samples.SAMPLES[lang]:
            assert len(item["text"]) > 20
            assert item["type"] in i18n.CASE_TYPES


# ── ui helpers that raise no Streamlit calls ─────────────────────────────────
def test_esc_escapes_html():
    import ui

    assert ui.esc("<b>&") == "&lt;b&gt;&amp;"


def test_ltr_wraps_text():
    import ui

    assert ui.ltr("2026-10-22").startswith("⁦") and ui.ltr("2026-10-22").endswith("⁩")


def test_safe_filename():
    import ui

    assert ui.safe_filename("قضية/سرقة") == "قضية_سرقة"
    assert ui.safe_filename("") == "report"
    assert len(ui.safe_filename("x" * 200)) == 80


def test_as_list_shapes():
    import ui

    assert ui.as_list(None) == []
    assert ui.as_list(["a"]) == ["a"]
    assert ui.as_list({"k": "v"}) == ["k: v"]
    assert ui.as_list("x") == ["x"]


def test_styles_css_is_present():
    import ui

    assert len(ui.STYLES) > 1000
    assert "--dir" in ui.STYLES or ":root" in ui.STYLES
