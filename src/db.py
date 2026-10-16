"""Minimal Supabase REST client (PostgREST) - no SDK needed."""
import os

import requests

URL = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1"
KEY = os.environ["SUPABASE_SERVICE_KEY"]
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}


def upsert(table: str, row: dict, on_conflict: str) -> dict:
    r = requests.post(
        f"{URL}/{table}",
        params={"on_conflict": on_conflict},
        headers={**H, "Prefer": "resolution=merge-duplicates,return=representation"},
        json=row,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()[0]


def exists(table: str, **eq) -> bool:
    params = {k: f"eq.{v}" for k, v in eq.items()}
    params["select"] = "id"
    r = requests.get(f"{URL}/{table}", headers=H, params=params, timeout=30)
    r.raise_for_status()
    return bool(r.json())
