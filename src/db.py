"""Minimal Supabase REST client (PostgREST) - no SDK needed."""
import os

import requests

URL = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1"
KEY = os.environ["SUPABASE_SERVICE_KEY"]
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}


def _check(r: requests.Response) -> None:
    """raise_for_status, but include PostgREST's error body (it names the bad column/constraint)."""
    if not r.ok:
        raise requests.HTTPError(f"{r.status_code} {r.reason}: {r.text[:500]}", response=r)


def upsert(table: str, row: dict, on_conflict: str) -> dict:
    r = requests.post(
        f"{URL}/{table}",
        params={"on_conflict": on_conflict},
        headers={**H, "Prefer": "resolution=merge-duplicates,return=representation"},
        json=row,
        timeout=30,
    )
    _check(r)
    return r.json()[0]


def exists(table: str, **eq) -> bool:
    params = {k: f"eq.{v}" for k, v in eq.items()}
    params["select"] = "id"
    r = requests.get(f"{URL}/{table}", headers=H, params=params, timeout=30)
    _check(r)
    return bool(r.json())
