import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { DeliveryZone, LatLng } from "@/lib/types";

/** Delivery-zone map on OpenStreetMap (free, no API key). Click adds a vertex to the polygon draft. */
export default function ZoneMap({ center, zones, draft, onClickPoint }: { center: LatLng; zones: DeliveryZone[]; draft: LatLng[]; onClickPoint: (p: LatLng) => void }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const clickRef = useRef(onClickPoint);
  clickRef.current = onClickPoint;

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current).setView([center.lat, center.lng], 13);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "© OpenStreetMap", maxZoom: 19 }).addTo(m);
    layer.current = L.layerGroup().addTo(m);
    m.on("click", (e: L.LeafletMouseEvent) => clickRef.current({ lat: e.latlng.lat, lng: e.latlng.lng }));
    map.current = m;
    return () => { m.remove(); map.current = null; layer.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- map is created once; center changes are handled below
  }, []);

  useEffect(() => { map.current?.setView([center.lat, center.lng]); }, [center.lat, center.lng]);

  useEffect(() => {
    const g = layer.current;
    if (!g) return;
    g.clearLayers();
    L.circleMarker([center.lat, center.lng], { radius: 8, color: "#fff", weight: 2, fillColor: "#C5533B", fillOpacity: 1 }).bindTooltip("Loja").addTo(g);
    for (const z of zones) {
      const label = `${z.name} · R$ ${z.fee.toFixed(2).replace(".", ",")}`;
      if (z.kind === "polygon" && z.polygon.length >= 3) L.polygon(z.polygon.map((p) => [p.lat, p.lng] as [number, number]), { color: "#C5533B", weight: 2, fillOpacity: 0.15 }).bindTooltip(label).addTo(g);
      if (z.kind === "radius" && z.radius_km > 0) L.circle([center.lat, center.lng], { radius: z.radius_km * 1000, color: "#B45309", weight: 1.5, fillOpacity: 0.04 }).bindTooltip(label).addTo(g);
    }
    if (draft.length) {
      const pts = draft.map((p) => [p.lat, p.lng] as [number, number]);
      (draft.length >= 3 ? L.polygon(pts, { color: "#047857", dashArray: "6 6", fillOpacity: 0.12 }) : L.polyline(pts, { color: "#047857", dashArray: "6 6" })).addTo(g);
      pts.forEach((p) => L.circleMarker(p, { radius: 5, color: "#047857", fillColor: "#fff", fillOpacity: 1, weight: 2 }).addTo(g));
    }
  }, [zones, draft, center.lat, center.lng]);

  return <div ref={el} className="isolate z-0 h-80 w-full overflow-hidden rounded-xl border border-stone-200" data-testid="zone-map" />;
}
