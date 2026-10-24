"""OpenStreetMap maps: pick an incident location, show one case, show all cases."""
import html

import folium
from branca.element import MacroElement, Template
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

# Centre of the West Bank; zoom 9 fits Jenin to Hebron.
DEFAULT_CENTER = (31.95, 35.25)
DEFAULT_ZOOM = 9
PIN_ZOOM = 14

INK = "#2B8CFF"      # analyzed cases: the brand blue
ACCENT = "#FF6B4A"   # high severity and the picked pin: warm, so it stands out against the blue map
GREY = "#8195B8"     # cases that are not analyzed yet

# The standard OpenStreetMap tiles (Arabic place names included) recoloured to match the dark UI.
# Only the tile images are filtered, so markers, popups and controls keep their own colours.
DARK_MAP_CSS = """
<style>
  .leaflet-container { background: #0A1224; }
  .leaflet-tile-pane { filter: invert(1) hue-rotate(205deg) saturate(.55) brightness(.92) contrast(.92); }
  .leaflet-control-attribution { background: rgba(5, 11, 26, .8) !important; color: #8FA0BF; }
  .leaflet-control-attribution a { color: #7DB8FF; }
  .leaflet-bar a, .leaflet-bar a:hover { background: #0C1A33; color: #E6EDFF; border-bottom-color: #22304F; }
  .leaflet-control-scale-line { background: rgba(5, 11, 26, .75); color: #C7D2EA; border-color: #8FA0BF; }
  .leaflet-popup-content-wrapper, .leaflet-popup-tip { background: #0C1A33; color: #E6EDFF; }
</style>
"""


def _base_map(center, zoom):
    m = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap", control_scale=True,
                   scroll_wheel_zoom=True)
    m.get_root().header.add_child(folium.Element(DARK_MAP_CSS))
    return m


class _ZoomOnClick(MacroElement):
    """Clicking a case marker flies the map in to that case."""
    _template = Template("""
        {% macro script(this, kwargs) %}
        {{ this._parent.get_name() }}.on('popupopen', function (e) {
            var map = {{ this._parent.get_name() }};
            var target = e.popup._source;
            if (!target || !target.getLatLng) { return; }
            var here = target.getLatLng();
            if (map.getZoom() >= {{ this.zoom }}) {
                // Circle markers open their popup where the click landed; anchor it on the case instead.
                e.popup.setLatLng(here);
                return;
            }
            // Zooming re-draws the clustered markers, which closes popups: fly in first, then reopen it.
            map.closePopup();
            map.once('moveend', function () { target.openPopup(here); });
            map.flyTo(here, {{ this.zoom }}, {duration: 0.8});
        });
        {% endmacro %}
    """)

    def __init__(self, zoom):
        super().__init__()
        self._name = "ZoomOnClick"
        self.zoom = zoom


def _pin(lat, lng, color, tooltip=None, popup=None, radius=9):
    return folium.CircleMarker(
        location=(lat, lng), radius=radius, color="#FFFFFF", weight=2,
        fill=True, fill_color=color, fill_opacity=0.95,
        tooltip=tooltip, popup=folium.Popup(popup, max_width=260) if popup else None,
    )


def format_coords(lat, lng):
    return f"{lat:.5f}, {lng:.5f}"


def pick_location(lat, lng, height=340):
    """A map where a click places the pin. Returns the clicked (lat, lng), or None if nothing new was clicked."""
    has_pin = lat is not None and lng is not None
    m = _base_map((lat, lng) if has_pin else DEFAULT_CENTER, PIN_ZOOM if has_pin else DEFAULT_ZOOM)
    if has_pin:
        _pin(lat, lng, ACCENT).add_to(m)
    # The key changes with the pin, so the map redraws around the new pin and forgets the old click.
    result = st_folium(m, key=f"pick_{lat}_{lng}", height=height, use_container_width=True,
                       returned_objects=["last_clicked"])
    clicked = (result or {}).get("last_clicked")
    if not clicked:
        return None
    point = (round(clicked["lat"], 6), round(clicked["lng"], 6))
    return None if has_pin and point == (round(lat, 6), round(lng, 6)) else point


def show_case(lat, lng, key, height=220):
    m = _base_map((lat, lng), PIN_ZOOM)
    _pin(lat, lng, ACCENT).add_to(m)
    st_folium(m, key=key, height=height, use_container_width=True, returned_objects=[])


def show_cases(cases, label_for, key, height=600):
    """All pinned cases, large and clickable: a click zooms in to the case, a cluster click zooms into the group.
    High severity in the accent colour, unanalyzed cases in grey."""
    pinned = [c for c in cases if c.get("latitude") is not None and c.get("longitude") is not None]
    if not pinned:
        return 0
    m = _base_map(DEFAULT_CENTER, DEFAULT_ZOOM)
    cluster = MarkerCluster(options={"showCoverageOnHover": False, "maxClusterRadius": 45,
                                     "spiderfyOnMaxZoom": True}).add_to(m)
    for c in pinned:
        color = ACCENT if c.get("severity") == "high" else INK if c.get("status") == "analyzed" else GREY
        title, detail = label_for(c)
        popup = (f'<div dir="auto" style="font-family:sans-serif;font-size:13px;line-height:1.6;color:#E6EDFF">'
                 f'<b>{html.escape(title)}</b><br>{html.escape(detail)}</div>')
        _pin(c["latitude"], c["longitude"], color, tooltip=title, popup=popup, radius=14).add_to(cluster)
    m.add_child(_ZoomOnClick(PIN_ZOOM + 1))
    if len(pinned) > 1:
        lats = [c["latitude"] for c in pinned]
        lngs = [c["longitude"] for c in pinned]
        m.fit_bounds([(min(lats), min(lngs)), (max(lats), max(lngs))], padding=(30, 30), max_zoom=13)
    st_folium(m, key=key, height=height, use_container_width=True, returned_objects=[])
    return len(pinned)
