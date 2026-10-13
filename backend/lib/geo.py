"""Delivery-zone fee calculation: polygon (ray casting), radius (haversine from store) and keyword."""

import math


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    dlat, dlng = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def point_in_polygon(lat: float, lng: float, polygon: list[dict]) -> bool:
    inside = False
    n = len(polygon)
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        if (a["lat"] > lat) != (b["lat"] > lat):
            x = (b["lng"] - a["lng"]) * (lat - a["lat"]) / (b["lat"] - a["lat"]) + a["lng"]
            if lng < x:
                inside = not inside
    return inside


def quote_fee(zones: list[dict], store: dict, lat: float | None, lng: float | None, text: str) -> dict:
    """Polygons first, then radius rings (smallest first), then keyword match on the address text."""
    distance = None
    if lat is not None and lng is not None:
        for z in zones:
            if z.get("kind") == "polygon" and len(z.get("polygon", [])) >= 3 and point_in_polygon(lat, lng, z["polygon"]):
                return {"found": True, "fee": z["fee"], "zone_name": z["name"], "distance_km": None}
        if store.get("store_lat") is not None and store.get("store_lng") is not None:
            distance = round(haversine_km(store["store_lat"], store["store_lng"], lat, lng), 2)
            for z in sorted((z for z in zones if z.get("kind") == "radius"), key=lambda z: z.get("radius_km", 0)):
                if distance <= z.get("radius_km", 0):
                    return {"found": True, "fee": z["fee"], "zone_name": z["name"], "distance_km": distance}
    lowered = (text or "").lower()
    if lowered:
        for z in zones:
            names = [k.lower() for k in z.get("keywords", [])] or ([z["name"].lower()] if z.get("kind") == "keyword" else [])
            if any(k and k in lowered for k in names):
                return {"found": True, "fee": z["fee"], "zone_name": z["name"], "distance_km": distance}
    return {"found": False, "fee": store.get("default_delivery_fee", 5), "zone_name": "", "distance_km": distance}
