"""Scraper for Idox Public Access planning portals (used by most UK councils)."""
import pathlib
import re
import tempfile
import time
from datetime import date, timedelta

import certifi
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UA = "FineViewPlanningLeads/1.0 (+contact: fineviewwindows.co.uk)"
DELAY = 2.0  # seconds between requests; be polite to council servers


CERTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "certs"
TIMEOUT = (15, 60)  # (connect, read) - council portals are slow, especially search results


def ca_bundle() -> str:
    """certifi's roots plus the intermediates in certs/. Some council servers
    (e.g. Hertsmere) omit their intermediate certificate; shipping it here keeps
    full TLS verification on. Only add public CA intermediates (see certs/README)."""
    extra = "".join(p.read_text() for p in sorted(CERTS_DIR.glob("*.pem")))
    path = pathlib.Path(tempfile.gettempdir()) / "fineview_ca_bundle.pem"
    path.write_text(pathlib.Path(certifi.where()).read_text() + "\n" + extra)
    return str(path)


class IdoxScraper:
    def __init__(self, council: str, base_url: str):
        self.council = council
        self.base = base_url.rstrip("/")
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.s.verify = ca_bundle()
        # Retry slow/flaky GETs a couple of times with a long backoff; never retry
        # the search POST (it's not idempotent and hammering gets us throttled).
        retry = Retry(total=2, backoff_factor=10, status_forcelist=(502, 503, 504),
                      allowed_methods=frozenset({"GET"}))
        self.s.mount("https://", HTTPAdapter(max_retries=retry))

    def _get(self, url, **kw):
        time.sleep(DELAY)
        r = self.s.get(url, timeout=TIMEOUT, **kw)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")

    def _post(self, url, data):
        time.sleep(DELAY)
        r = self.s.post(url, data=data, timeout=TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")

    def search_decided(self, days: int):
        """Yield keyVals of applications decided in the last `days` days."""
        form = self._get(f"{self.base}/search.do?action=advanced")
        csrf = form.find("input", {"name": "_csrf"})
        end = date.today()
        start = end - timedelta(days=days)
        fmt = "%d/%m/%Y"
        data = {
            "date(applicationDecisionStart)": start.strftime(fmt),
            "date(applicationDecisionEnd)": end.strftime(fmt),
            "searchType": "Application",
        }
        if csrf:
            data["_csrf"] = csrf["value"]
        page = self._post(f"{self.base}/advancedSearchResults.do?action=firstPage", data)
        # Idox shows 10 results per page by default; ask for 100 to cut requests
        try:
            page = self._post(f"{self.base}/pagedSearchResults.do",
                              {"action": "page", "searchCriteria.page": "1",
                               "searchCriteria.resultsPerPage": "100",
                               **({"_csrf": csrf["value"]} if csrf else {})})
        except requests.RequestException:
            pass  # fall back to default paging
        seen = set()
        while True:
            for a in page.select("li.searchresult a[href*='keyVal=']"):
                m = re.search(r"keyVal=([A-Z0-9]+)", a["href"])
                if m and m.group(1) not in seen:
                    seen.add(m.group(1))
                    # link text is the proposal description: lets us skip small jobs
                    # without fetching their detail pages
                    yield m.group(1), a.get_text(" ", strip=True)
            nxt = page.select_one("a.next")
            if not nxt:
                break
            page = self._get(requests.compat.urljoin(self.base + "/", nxt["href"]))

    def agent_contact(self, key) -> dict:
        """Email/phone from the AGENT section of the contacts tab only.
        The tab also lists ward councillors / case officers - never take those."""
        try:
            soup = self._get(f"{self.base}/applicationDetails.do", params={"activeTab": "contacts", "keyVal": key})
        except requests.HTTPError:
            return {}
        out = {}
        for heading in soup.find_all(["h2", "h3", "h4", "th", "p", "strong"]):
            if "agent" not in heading.get_text(" ", strip=True).lower():
                continue
            table = heading.find_next("table")
            if not table:
                continue
            for row in table.select("tr"):
                th, td = row.find("th"), row.find("td")
                if not (th and td):
                    continue
                label, val = th.get_text(" ", strip=True).lower(), td.get_text(" ", strip=True)
                if "mail" in label:
                    out.setdefault("email", val)
                elif "phone" in label or "tel" in label:
                    out.setdefault("phone", val)
            break
        return out

    def _table(self, key, tab):
        soup = self._get(f"{self.base}/applicationDetails.do", params={"activeTab": tab, "keyVal": key})
        out = {}
        for row in soup.select("table tr"):
            th, td = row.find("th"), row.find("td")
            if th and td:
                out[th.get_text(" ", strip=True)] = td.get_text(" ", strip=True)
        return out

    def application(self, key):
        summary = self._table(key, "summary")
        details = self._table(key, "details")
        contacts = self.agent_contact(key) if details.get("Agent Name") or details.get("Agent Company Name") else {}
        return {
            "council": self.council,
            "key_val": key,
            "reference": summary.get("Reference"),
            "address": summary.get("Address"),
            "description": summary.get("Proposal"),
            "status": summary.get("Status"),
            "decision": summary.get("Decision"),
            "decision_date": summary.get("Decision Issued Date"),
            "applicant_name": details.get("Applicant Name"),
            "applicant_address": details.get("Applicant Address"),
            "agent_name": details.get("Agent Name"),
            "agent_company": details.get("Agent Company Name"),
            "agent_address": details.get("Agent Address"),
            "agent_phone": contacts.get("phone") or details.get("Agent Phone Number"),
            "agent_email": contacts.get("email"),
            "url": f"{self.base}/applicationDetails.do?activeTab=summary&keyVal={key}",
        }
