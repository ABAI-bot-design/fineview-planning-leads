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


def insert(table: str, row: dict) -> None:
    r = requests.post(f"{URL}/{table}", headers=H, json=row, timeout=30)
    r.raise_for_status()


def select(table: str, columns: str = "*", **params) -> list[dict]:
    """Fetch all rows (paged) - e.g. select('applications', 'id,description')."""
    rows, start = [], 0
    while True:
        r = requests.get(f"{URL}/{table}", headers={**H, "Range": f"{start}-{start + 999}"},
                         params={"select": columns, **params}, timeout=30)
        r.raise_for_status()
        batch = r.json()
        rows += batch
        if len(batch) < 1000:
            return rows
        start += 1000


def update(table: str, values: dict, **eq) -> None:
    r = requests.patch(f"{URL}/{table}", headers=H, json=values,
                       params={k: f"eq.{v}" for k, v in eq.items()}, timeout=30)
    r.raise_for_status()


def exists(table: str, **eq) -> bool:
    params = {k: f"eq.{v}" for k, v in eq.items()}
    params["select"] = "id"
    r = requests.get(f"{URL}/{table}", headers=H, params=params, timeout=30)
    r.raise_for_status()
    return bool(r.json())
