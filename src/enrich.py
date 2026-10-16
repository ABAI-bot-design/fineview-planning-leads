"""Enrichment for BUSINESS contacts only (developers, builders, architects/agents).

Private-individual applicants are never enriched: they are kept with the
planning record and property address only, for the consent-first letter route.
"""
import os
import re
import time

import requests
from bs4 import BeautifulSoup

CH_KEY = os.environ.get("COMPANIES_HOUSE_API_KEY")
SERP_KEY = os.environ.get("SERPAPI_KEY")  # optional: find a company's website

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+44\s?|0)(?:\d[\s-]?){9,10}")
SOCIALS = {
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.]+"),
    "facebook": re.compile(r"https?://(?:www\.)?facebook\.com/[A-Za-z0-9_.\-]+"),
    "linkedin": re.compile(r"https?://(?:www\.)?linkedin\.com/company/[A-Za-z0-9_\-]+"),
}


def companies_house(name: str) -> dict:
    if not CH_KEY or not name:
        return {}
    r = requests.get(
        "https://api.company-information.service.gov.uk/search/companies",
        params={"q": name, "items_per_page": 1},
        auth=(CH_KEY, ""),
        timeout=20,
    )
    if r.status_code != 200 or not r.json().get("items"):
        return {}
    c = r.json()["items"][0]
    out = {
        "company_number": c.get("company_number"),
        "company_status": c.get("company_status"),
        "postal_address": c.get("address_snippet"),  # registered office
    }
    officers = requests.get(
        f"https://api.company-information.service.gov.uk/company/{c['company_number']}/officers",
        auth=(CH_KEY, ""),
        timeout=20,
    )
    if officers.ok:
        out["directors"] = [
            o["name"] for o in officers.json().get("items", [])
            if o.get("officer_role") == "director" and not o.get("resigned_on")
        ]
    return out


def find_website(name: str) -> str | None:
    if not SERP_KEY or not name:
        return None
    r = requests.get(
        "https://serpapi.com/search.json",
        params={"q": name, "location": "Hertfordshire, England, United Kingdom", "api_key": SERP_KEY},
        timeout=30,
    )
    if not r.ok:
        return None
    for res in r.json().get("organic_results", []):
        link = res.get("link", "")
        if not any(x in link for x in ("companieshouse", "endole", "linkedin", "facebook", "yell.")):
            return link
    return None


def scrape_site(url: str) -> dict:
    out = {"website": url}
    for path in ("", "/contact", "/contact-us"):
        try:
            time.sleep(1)
            r = requests.get(url.rstrip("/") + path, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if not r.ok:
                continue
            text = r.text
            out.setdefault("email", next(iter(EMAIL_RE.findall(text)), None))
            phone = PHONE_RE.search(BeautifulSoup(text, "html.parser").get_text(" "))
            if phone:
                out.setdefault("phone", phone.group(0).strip())
            for k, rx in SOCIALS.items():
                m = rx.search(text)
                if m:
                    out.setdefault(k, m.group(0))
        except requests.RequestException:
            continue
    return {k: v for k, v in out.items() if v}


def enrich_business(name: str) -> dict:
    data = companies_house(name)
    site = find_website(name)
    if site:
        data.update(scrape_site(site))
    return data
