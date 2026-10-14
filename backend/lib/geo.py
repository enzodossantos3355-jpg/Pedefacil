"""Delivery-zone fee calculation: polygon (ray casting), radius (haversine from store), CEP and keyword.
Also: Google Maps link/coords parsing, CEP lookup (ViaCEP) and address geocoding (OpenStreetMap Nominatim)."""

import logging
import math
import re

import httpx

logger = logging.getLogger(__name__)
MAPS_RE = re.compile(r"(-?\d{1,2}\.\d{3,})\s*,\s*(-?\d{1,3}\.\d{3,})")
LINK_RE = re.compile(r"https?://\S*(?:maps\.app\.goo\.gl|goo\.gl/maps|google\.[^/\s]+/maps|maps\.google)\S*", re.I)
CEP_RE = re.compile(r"\b(\d{5})-?(\d{3})\b")
OSM_HEADERS = {"User-Agent": "PedeFacil/1.0 (delivery fee calculator)"}


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


def find_cep(text: str) -> str:
    m = CEP_RE.search(text or "")
    return f"{m.group(1)}{m.group(2)}" if m else ""


def cep_matches(cep: str, rules: list[str]) -> bool:
    """Rules: exact CEP ("01310-100"), prefix ("01310") or range ("01000-000 a 01099-999")."""
    for rule in rules:
        nums = re.findall(r"\d+", rule.replace("-", ""))
        if len(nums) >= 2 and len(nums[0]) == 8 and len(nums[1]) == 8:
            if nums[0] <= cep <= nums[1]:
                return True
        elif nums and cep.startswith(nums[0]):
            return True
    return False


def quote_fee(zones: list[dict], store: dict, lat: float | None, lng: float | None, text: str) -> dict:
    """Polygons first, then radius rings (smallest first), then CEP rules, then keyword match on the address text."""
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
    cep = find_cep(text)
    if cep:
        for z in zones:
            if z.get("kind") == "cep" and cep_matches(cep, z.get("ceps", [])):
                return {"found": True, "fee": z["fee"], "zone_name": z["name"], "distance_km": distance}
    lowered = (text or "").lower()
    if lowered:
        for z in zones:
            names = [k.lower() for k in z.get("keywords", [])] or ([z["name"].lower()] if z.get("kind") == "keyword" else [])
            if any(k and k in lowered for k in names):
                return {"found": True, "fee": z["fee"], "zone_name": z["name"], "distance_km": distance}
    return {"found": False, "fee": store.get("default_delivery_fee", 5), "zone_name": "", "distance_km": distance}


async def lookup_cep(cep: str) -> str:
    """ViaCEP → "logradouro, bairro, cidade" so bairro keywords also match a bare CEP."""
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            data = (await client.get(f"https://viacep.com.br/ws/{cep}/json/")).json()
        if data.get("erro"):
            return ""
        return ", ".join(v for v in (data.get("logradouro"), data.get("bairro"), data.get("localidade")) if v)
    except Exception as exc:
        logger.warning("viacep %s: %s", cep, exc)
        return ""


async def quote_fee_full(zones: list[dict], store: dict, lat: float | None, lng: float | None, text: str) -> dict:
    """quote_fee plus CEP enrichment: a CEP in the text adds its street/bairro (ViaCEP) to the keyword match."""
    cep = find_cep(text)
    if cep:
        text = f"{text} {await lookup_cep(cep)}"
    return quote_fee(zones, store, lat, lng, text)


async def coords_from_text(text: str) -> tuple[float, float] | None:
    """Reads a Google Maps link (resolving short links) or raw "lat,lng" from the message."""
    link = LINK_RE.search(text or "")
    target = text or ""
    if link:
        target = link.group(0)
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=8) as client:
                target = str((await client.get(target)).url) + " " + target
        except Exception:
            pass
    m = MAPS_RE.search(target)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    return None


async def geocode_address(address: str) -> tuple[float, float] | None:
    """Address or CEP → coordinates using OpenStreetMap Nominatim (free, no key)."""
    if not address.strip():
        return None
    cep = find_cep(address)
    query = (await lookup_cep(cep) or address) if cep else address
    try:
        async with httpx.AsyncClient(timeout=8, headers=OSM_HEADERS) as client:
            res = (await client.get("https://nominatim.openstreetmap.org/search", params={"q": query, "format": "json", "limit": 1, "countrycodes": "br"})).json()
        if res:
            return float(res[0]["lat"]), float(res[0]["lon"])
    except Exception as exc:
        logger.warning("geocode %s: %s", address, exc)
    return None
