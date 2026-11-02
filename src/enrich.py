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


_SUFFIX = re.compile(r"\b(ltd|limited|llp|plc|uk|the|and|&|co|company)\b")


def norm_company(name: str) -> str:
    """'Lisa Estates (Paragon) Ltd.' -> 'lisa estates paragon'"""
    n = re.sub(r"[^a-z0-9& ]", " ", (name or "").lower())
    n = _SUFFIX.sub(" ", n)
    return " ".join(n.split())


def companies_house(name: str) -> dict:
    """Return Companies House data only when a result's name genuinely matches."""
    if not CH_KEY or not name:
        return {}
    r = requests.get(
        "https://api.company-information.service.gov.uk/search/companies",
        params={"q": name, "items_per_page": 10},
        auth=(CH_KEY, ""),
        timeout=20,
    )
    if r.status_code != 200:
        return {}
    want = norm_company(name)
    if not want:
        return {}
    match = next((c for c in r.json().get("items", []) if norm_company(c.get("title")) == want), None)
    if not match:
        return {}
    c = match
    out = {
        "company_number": c.get("company_number"),
        "company_status": c.get("company_status"),
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


FREEMAIL = {"gmail.com", "googlemail.com", "hotmail.com", "hotmail.co.uk", "outlook.com", "live.com",
            "live.co.uk", "yahoo.com", "yahoo.co.uk", "aol.com", "icloud.com", "me.com", "btinternet.com",
            "sky.com", "virginmedia.com", "msn.com", "protonmail.com", "mail.com", "gmx.com", "gmx.co.uk",
            "ymail.com", "rocketmail.com", "talktalk.net", "tiscali.co.uk", "ntlworld.com", "blueyonder.co.uk",
            "aol.co.uk", "proton.me", "zoho.com", "yandex.com", "plus.com", "orange.net", "fsmail.net"}


def site_from_email(email: str | None) -> str | None:
    """A firm's own email domain is almost always its website (info@smith-newton.com -> smith-newton.com)."""
    if not email or "@" not in email:
        return None
    domain = email.rsplit("@", 1)[1].strip().lower()
    if domain in FREEMAIL or domain.endswith(".gov.uk"):
        return None
    for url in (f"https://www.{domain}", f"https://{domain}"):
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
            if r.ok and len(r.text) > 500:
                return r.url.rstrip("/")
        except requests.RequestException:
            continue
    return None


# Words that describe the trade rather than the firm: a firm called "Bellis Architects"
# can live at bellisarchitects.co.uk or bellis.co.uk, but "architects.co.uk" is never it.
GENERIC = {"architects", "architect", "architecture", "architectural", "design", "designs", "planning",
           "studio", "studios", "associates", "partnership", "consulting", "consultants", "services",
           "group", "and", "the", "of", "uk", "london", "drawing", "drawings", "plans", "plan"}
PARKED = re.compile(r"domain (?:is )?for sale|buy this domain|this domain (?:may be|is) (?:for sale|parked)|"
                    r"parked (?:free|domain)|godaddy|sedo|hugedomains|dan\.com|future home of", re.I)


def domain_candidates(name: str) -> list[str]:
    """Likely websites for a firm, from its name alone - e.g. 'Bellis Architects Ltd' ->
    bellisarchitects.co.uk, bellis-architects.co.uk, bellisarchitects.com, ..."""
    n = (name or "").lower().replace("&", " and ").replace("+", " and ")
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = _SUFFIX.sub(" ", n)
    words = [w for w in n.split() if w]
    if not words or not any(w not in GENERIC and len(w) >= 3 for w in words):
        return []  # nothing distinctive enough to guess from
    stems = ["".join(words), "-".join(words)]
    core = [w for w in words if w not in GENERIC]
    if core and core != words:
        stems.append("".join(core))
    out = []
    for stem in dict.fromkeys(stems):
        if 3 <= len(stem) <= 40:
            out += [f"{stem}.co.uk", f"{stem}.com", f"{stem}.uk"]
    return out[:9]


def looks_like(name: str, html: str) -> bool:
    """The page must mention the firm's distinctive name, and not be a parked/for-sale page."""
    if len(html) < 800 or PARKED.search(html[:20000]):
        return False
    text = re.sub(r"\s+", " ", BeautifulSoup(html[:200000], "html.parser").get_text(" ")).lower()
    core = [w for w in re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split() if w not in GENERIC and len(w) >= 3
            and not _SUFFIX.fullmatch(w)]
    return bool(core) and all(w in text for w in core)


def guess_site(name: str) -> str | None:
    for domain in domain_candidates(name):
        for url in (f"https://www.{domain}", f"https://{domain}"):
            try:
                r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
            except requests.RequestException:
                continue
            if r.ok and looks_like(name, r.text):
                return r.url.rstrip("/")
            break  # domain answered but isn't theirs; try the next domain
    return None


# template/placeholder social links that site builders ship by default
JUNK_SOCIAL = re.compile(r"(wix|squarespace|godaddy|wordpress|weebly|jimdo)(?:com)?/?$|/sharer|/share\?|/intent/", re.I)


def clean_socials(d: dict) -> dict:
    for k in ("instagram", "facebook", "linkedin"):
        if d.get(k) and JUNK_SOCIAL.search(d[k]):
            d.pop(k)
    return d


def enrich_business(name: str, email: str | None = None) -> dict:
    data = companies_house(name)
    site = site_from_email(email) or guess_site(name) or find_website(name)
    if site:
        found = scrape_site(site)
        found.pop("email", None) if email else None  # keep the planning-record email as primary
        data.update(found)
    return clean_socials(data)
