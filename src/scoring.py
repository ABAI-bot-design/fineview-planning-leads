"""Lead scoring: job size + distance from Radlett + whether a business is reachable."""
import math
import re

import requests

RADLETT = (51.6853, -0.3175)  # Radlett centre (WD7)
POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b", re.I)


def postcode(address: str) -> str | None:
    m = POSTCODE_RE.search(address or "")
    return f"{m.group(1).upper()} {m.group(2).upper()}" if m else None


def distance_miles(pc: str | None) -> float | None:
    """Free lookup via postcodes.io (UK only, no key)."""
    if not pc:
        return None
    try:
        r = requests.get(f"https://api.postcodes.io/postcodes/{pc.replace(' ', '')}", timeout=15)
        if not r.ok:
            return None
        res = r.json()["result"]
        lat, lon = math.radians(res["latitude"]), math.radians(res["longitude"])
    except (requests.RequestException, KeyError, TypeError):
        return None
    rlat, rlon = map(math.radians, RADLETT)
    d = 2 * 3958.8 * math.asin(math.sqrt(
        math.sin((lat - rlat) / 2) ** 2 + math.cos(lat) * math.cos(rlat) * math.sin((lon - rlon) / 2) ** 2))
    return round(d, 1)


def lead_score(size: str, miles: float | None, has_business_email: bool, has_business_phone: bool) -> int:
    """0-100. Size up to 50, proximity up to 30, contactability up to 20."""
    s = 50 if size == "High" else 25
    if miles is not None:
        s += max(0, round(30 * (1 - miles / 10)))  # 30 at Radlett, 0 at 10+ miles
    s += 12 if has_business_email else 0
    s += 8 if has_business_phone else 0
    return min(s, 100)
