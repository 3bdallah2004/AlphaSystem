import L from "leaflet";
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";
import { useEffect } from "react";
import type { GeoPoint } from "../api/client";
import "leaflet/dist/leaflet.css";

function MapClick({ onChange }: { onChange: (point: GeoPoint) => void }) {
  useMapEvents({
    click(event) {
      onChange({ latitude: event.latlng.lat, longitude: event.latlng.lng });
    },
  });
  return null;
}

function Recenter({ point }: { point: GeoPoint | null }) {
  const map = useMap();
  useEffect(() => {
    if (point) map.setView([point.latitude, point.longitude], Math.max(map.getZoom(), 13));
  }, [map, point]);
  return null;
}

export default function LocationPicker({ point, onChange }: {
  point: GeoPoint | null; onChange: (point: GeoPoint) => void;
}) {
  const center: [number, number] = point ? [point.latitude, point.longitude] : [31.95, 35.2];
  return (
    <MapContainer center={center} zoom={point ? 13 : 8} scrollWheelZoom className="location-picker-map">
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <MapClick onChange={onChange} />
      <Recenter point={point} />
      {point && <Marker position={[point.latitude, point.longitude]} icon={L.divIcon({
        className: "location-picker-marker",
        html: "<span></span>",
        iconSize: [22, 28],
        iconAnchor: [11, 26],
      })} />}
    </MapContainer>
  );
}
