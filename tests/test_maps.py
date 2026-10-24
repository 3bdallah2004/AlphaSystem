"""Map builders. st_folium is stubbed out so nothing needs a browser or a Streamlit runtime."""
import folium
import pytest

import maps


@pytest.fixture()
def rendered(monkeypatch):
    """Collect every folium map handed to st_folium instead of rendering it."""
    seen = []
    monkeypatch.setattr(maps, "st_folium", lambda m, **kw: seen.append((m, kw)) or None)
    return seen


def _markers(folium_map):
    found = []

    def walk(node):
        if isinstance(node, folium.CircleMarker):
            found.append(node)
        for child in getattr(node, "_children", {}).values():
            walk(child)

    walk(folium_map)
    return found


def test_format_coords():
    assert maps.format_coords(31.9, 35.25) == "31.90000, 35.25000"


def test_pick_location_without_pin_centres_on_the_region(rendered):
    maps.pick_location(None, None)
    folium_map, kwargs = rendered[0]
    assert folium_map.location == list(maps.DEFAULT_CENTER)
    assert kwargs["height"] == 340
    assert kwargs["returned_objects"] == ["last_clicked"]


def test_pick_location_with_pin_draws_one_marker(rendered):
    maps.pick_location(31.9, 35.2)
    folium_map, _ = rendered[0]
    markers = _markers(folium_map)
    assert len(markers) == 1
    assert markers[0].location == [31.9, 35.2]


def test_pick_location_returns_new_click(monkeypatch):
    monkeypatch.setattr(maps, "st_folium", lambda m, **kw: {"last_clicked": {"lat": 32.123456, "lng": 35.654321}})
    assert maps.pick_location(None, None) == (32.123456, 35.654321)


def test_pick_location_ignores_repeat_click_on_same_spot(monkeypatch):
    monkeypatch.setattr(maps, "st_folium", lambda m, **kw: {"last_clicked": {"lat": 31.9, "lng": 35.2}})
    assert maps.pick_location(31.9, 35.2) is None


def test_pick_location_handles_no_click(monkeypatch):
    monkeypatch.setattr(maps, "st_folium", lambda m, **kw: None)
    assert maps.pick_location(None, None) is None


def test_show_case_renders_a_marker(rendered):
    maps.show_case(31.9, 35.2, key="k")
    folium_map, kwargs = rendered[0]
    assert len(_markers(folium_map)) == 1
    assert kwargs["returned_objects"] == []


def test_show_cases_returns_zero_when_nothing_is_pinned(rendered):
    assert maps.show_cases([{"id": 1, "latitude": None, "longitude": None}], lambda c: ("", ""), key="k") == 0
    assert rendered == []


def test_show_cases_colours_by_severity_and_status(rendered):
    cases = [
        {"id": 1, "case_name": "خطير", "latitude": 31.9, "longitude": 35.2,
         "severity": "high", "status": "analyzed", "case_number": "A", "case_type": "عام"},
        {"id": 2, "case_name": "عادي", "latitude": 32.0, "longitude": 35.3,
         "severity": None, "status": "analyzed", "case_number": "B", "case_type": "عام"},
        {"id": 3, "case_name": "مسودة", "latitude": 32.1, "longitude": 35.4,
         "severity": None, "status": "draft", "case_number": "C", "case_type": "عام"},
    ]
    n = maps.show_cases(cases, lambda c: (c["case_name"], c["case_number"]), key="k")
    assert n == 3
    colors = [m.options["fillColor"] for m in _markers(rendered[0][0])]
    assert colors == [maps.ACCENT, maps.INK, maps.GREY]


def test_show_cases_escapes_popup_html(rendered):
    cases = [{"id": 1, "case_name": "<script>x</script>", "latitude": 31.9, "longitude": 35.2,
              "severity": None, "status": "analyzed", "case_number": "A", "case_type": "عام"}]
    maps.show_cases(cases, lambda c: (c["case_name"], ""), key="k")
    marker = _markers(rendered[0][0])[0]
    popups = [child for child in marker._children.values() if isinstance(child, folium.Popup)]
    assert len(popups) == 1
    popup_html = popups[0].html.render()
    assert "<script>" not in popup_html
    assert "&lt;script&gt;" in popup_html
