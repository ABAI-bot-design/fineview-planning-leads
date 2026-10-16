"""Scraper for Idox Public Access planning portals (used by most UK councils)."""
import re
import time
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

UA = "FineViewPlanningLeads/1.0 (+contact: fineviewwindows.co.uk)"
DELAY = 2.0  # seconds between requests; be polite to council servers


def ca_bundle_for(url: str) -> str:
    """Some council servers omit the intermediate certificate. Fetch the missing
    chain via AIA and add it to certifi's bundle, keeping full TLS verification."""
    import pathlib
    import tempfile

    import certifi
    try:
        from aia import AIASession
        chain = AIASession().cadata_from_url(url)
    except Exception:
        return certifi.where()
    path = pathlib.Path(tempfile.gettempdir()) / f"ca_{abs(hash(url))}.pem"
    path.write_text(pathlib.Path(certifi.where()).read_text() + "\n" + chain)
    return str(path)


class IdoxScraper:
    def __init__(self, council: str, base_url: str):
        self.council = council
        self.base = base_url.rstrip("/")
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.s.verify = ca_bundle_for(self.base)

    def _get(self, url, **kw):
        time.sleep(DELAY)
        r = self.s.get(url, timeout=30, **kw)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")

    def _post(self, url, data):
        time.sleep(DELAY)
        r = self.s.post(url, data=data, timeout=30)
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
        seen = set()
        while True:
            for a in page.select("li.searchresult a[href*='keyVal=']"):
                m = re.search(r"keyVal=([A-Z0-9]+)", a["href"])
                if m and m.group(1) not in seen:
                    seen.add(m.group(1))
                    yield m.group(1)
            nxt = page.select_one("a.next")
            if not nxt:
                break
            page = self._get(requests.compat.urljoin(self.base + "/", nxt["href"]))

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
        try:
            contacts = self._table(key, "contacts")
        except requests.HTTPError:
            contacts = {}
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
            "agent_phone": contacts.get("Phone") or details.get("Agent Phone Number"),
            "agent_email": contacts.get("Email"),
            "url": f"{self.base}/applicationDetails.do?activeTab=summary&keyVal={key}",
        }
