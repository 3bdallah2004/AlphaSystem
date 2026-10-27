import { Icon } from "@mdi/react";
import { mdiMapMarkerOutline } from "@mdi/js";
import L from "leaflet";
import "leaflet.markercluster";
import { useEffect } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import type { CaseSummary } from "../api/client";
import type { Language } from "../i18n";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";

type Props = { cases: CaseSummary[]; search: string; lang: Language; untitled: string };

function MarkerLayer({ cases, search, lang, untitled }: Props) {
  const map = useMap();
  useEffect(() => {
    const group = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 48 });
    cases.forEach((item) => {
      if (item.latitude == null || item.longitude == null) return;
      const color = item.severity === "high" ? "#ff6b4a" : item.severity === "medium" ? "#f2b35c" : "#6ee7a8";
      const marker = L.marker([item.latitude, item.longitude], {
        icon: L.divIcon({
          className: "case-map-marker",
          html: `<span style="--pin-color:${color}"></span>`,
          iconSize: [22, 28],
          iconAnchor: [11, 25],
        }),
      });
      const popup = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = item.case_name || untitled;
      const number = document.createElement("small");
      number.textContent = item.case_number || `#${item.id}`;
      const link = document.createElement("a");
      const params = new URLSearchParams(search);
      params.set("lang", lang);
      link.href = `/cases/${item.id}?${params.toString()}`;
      link.textContent = lang === "ar" ? "فتح القضية" : "Open case";
      popup.append(title, number, link);
      marker.bindPopup(popup);
      group.addLayer(marker);
    });
    map.addLayer(group);
    if (group.getLayers().length) map.fitBounds(group.getBounds().pad(0.12), { maxZoom: 12 });
    return () => { map.removeLayer(group); };
  }, [cases, lang, map, search, untitled]);
  return null;
}

export default function MapCanvas(props: Props) {
  const visibleCount = props.cases.filter((item) => item.latitude != null && item.longitude != null).length;
  return (
    <div className="leaflet-map-wrap">
      <MapContainer center={[31.95, 35.2]} zoom={8} scrollWheelZoom className="leaflet-map">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <MarkerLayer {...props} />
      </MapContainer>
      {visibleCount === 0 && <div className="map-empty"><Icon path={mdiMapMarkerOutline} size={0.9} />
        {props.lang === "ar" ? "لا توجد نتائج لها موقع جغرافي بعد." : "No results have coordinates yet."}</div>}
    </div>
  );
}
