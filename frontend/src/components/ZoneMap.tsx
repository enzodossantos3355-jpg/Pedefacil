import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { DeliveryZone, LatLng } from "@/lib/types";

// Minimal typing for the Google Maps JS objects we use (no @types package needed).
type GMap = { addListener: (e: string, cb: (ev: { latLng: { lat: () => number; lng: () => number } }) => void) => void };
type GOverlay = { setMap: (m: GMap | null) => void };
type GoogleNS = { maps: { Map: new (el: HTMLElement, o: object) => GMap; Polygon: new (o: object) => GOverlay; Circle: new (o: object) => GOverlay; Marker: new (o: object) => GOverlay } };
declare global { interface Window { google?: GoogleNS; __gmapsLoading?: Promise<void> } }

function loadMaps(key: string): Promise<void> {
  if (window.google?.maps) return Promise.resolve();
  window.__gmapsLoading ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}`;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("maps"));
    document.head.appendChild(s);
  });
  return window.__gmapsLoading;
}

export default function ZoneMap({ center, zones, draft, onClickPoint }: { center: LatLng; zones: DeliveryZone[]; draft: LatLng[]; onClickPoint: (p: LatLng) => void }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<GMap | null>(null);
  const overlays = useRef<GOverlay[]>([]);
  const clickRef = useRef(onClickPoint);
  clickRef.current = onClickPoint;
  const [error, setError] = useState("");
  const config = useQuery({ queryKey: ["maps-config"], queryFn: () => apiGet<{ api_key: string }>("/maps/config") });

  useEffect(() => {
    if (!config.data?.api_key || !el.current) return;
    loadMaps(config.data.api_key).then(() => {
      if (!window.google || !el.current || map.current) return;
      map.current = new window.google.maps.Map(el.current, { center, zoom: 13, mapTypeControl: false, streetViewControl: false });
      map.current.addListener("click", (ev) => clickRef.current({ lat: ev.latLng.lat(), lng: ev.latLng.lng() }));
    }).catch(() => setError("Não foi possível carregar o Google Maps. Verifique se a chave tem a Maps JavaScript API ativa."));
  }, [config.data, center]);

  useEffect(() => {
    const g = window.google;
    if (!g || !map.current) return;
    overlays.current.forEach((o) => o.setMap(null));
    overlays.current = [new g.maps.Marker({ position: center, map: map.current, title: "Loja" })];
    for (const z of zones) {
      if (z.kind === "polygon" && z.polygon.length >= 3) overlays.current.push(new g.maps.Polygon({ paths: z.polygon, map: map.current, strokeColor: "#C5533B", fillColor: "#E28B61", fillOpacity: 0.22, strokeWeight: 2, clickable: false }));
      if (z.kind === "radius" && z.radius_km > 0) overlays.current.push(new g.maps.Circle({ center, radius: z.radius_km * 1000, map: map.current, strokeColor: "#6B8E7B", fillColor: "#6B8E7B", fillOpacity: 0.08, strokeWeight: 1, clickable: false }));
    }
    if (draft.length) overlays.current.push(new g.maps.Polygon({ paths: draft, map: map.current, strokeColor: "#1C1917", fillColor: "#D99A45", fillOpacity: 0.3, strokeWeight: 2, clickable: false }));
  });

  if (config.data && !config.data.api_key) return <div className="grid h-80 place-items-center rounded-xl border border-dashed border-stone-300 text-sm text-stone-500">Chave do Google Maps não configurada.</div>;
  return <div className="relative" data-testid="zone-map">{error && <div className="absolute inset-x-3 top-3 z-10 rounded-lg border border-red-200 bg-red-50 p-2 text-xs text-red-700">{error}</div>}<div ref={el} className="h-80 w-full overflow-hidden rounded-xl border border-stone-200 bg-stone-100" /></div>;
}
