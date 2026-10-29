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
DELAY = 2.0  # default seconds between requests; be polite to council servers
# When a council says "Too Many Requests" (429) or is briefly unavailable (503),
# wait and try again instead of dropping the application. Waits grow each time.
THROTTLE_WAITS = (60, 120, 240)


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


class Throttled(requests.HTTPError):
    """The council kept refusing requests after every wait."""


class IdoxScraper:
    def __init__(self, council: str, base_url: str, delay: float = DELAY, sleep=time.sleep):
        self.council = council
        self.base = base_url.rstrip("/")
        self.delay = delay
        self.sleep = sleep          # injectable for tests
        self.throttle_waits = 0     # how many times the council made us back off (for run stats)
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.s.verify = ca_bundle()
        # Retry slow/flaky GETs a couple of times with a long backoff; never retry
        # the search POST (it's not idempotent and hammering gets us throttled).
        retry = Retry(total=2, backoff_factor=10, status_forcelist=(502, 503, 504),
                      allowed_methods=frozenset({"GET"}))
        self.s.mount("https://", HTTPAdapter(max_retries=retry))

    def _request(self, method, url, **kw):
        """One polite request. On 429/503, honour Retry-After (or our own growing wait)
        and retry; give up with Throttled after THROTTLE_WAITS are used up."""
        for attempt in range(len(THROTTLE_WAITS) + 1):
            self.sleep(self.delay)
            r = self.s.request(method, url, timeout=TIMEOUT, **kw)
            if r.status_code not in (429, 503):
                r.raise_for_status()
                return BeautifulSoup(r.text, "html.parser")
            if attempt == len(THROTTLE_WAITS):
                break
            wait = THROTTLE_WAITS[attempt]
            ra = r.headers.get("Retry-After", "")
            if ra.isdigit():
                wait = max(wait, min(int(ra), 900))
            self.throttle_waits += 1
            self.sleep(wait)
        raise Throttled(f"{r.status_code} from {self.council} after {len(THROTTLE_WAITS)} waits: {url}", response=r)

    def _get(self, url, **kw):
        return self._request("GET", url, **kw)

    def _post(self, url, data):
        return self._request("POST", url, data=data)

    # Idox advanced-search date fields
    DATE_FIELDS = {"decided": "applicationDecision", "validated": "applicationValidated"}

    def search_decided(self, days: int):
        yield from self.search(days, "decided")

    def search(self, days: int, by: str = "decided"):
        """Yield (keyVal, description) for applications decided/validated in the last `days` days.
        Sets self.diagnostic when the search returns nothing, so the run log says why."""
        self.diagnostic = None
        form = self._get(f"{self.base}/search.do?action=advanced")
        csrf = form.find("input", {"name": "_csrf"})
        end = date.today()
        start = end - timedelta(days=days)
        fmt = "%d/%m/%Y"
        field = self.DATE_FIELDS[by]
        data = {
            f"date({field}Start)": start.strftime(fmt),
            f"date({field}End)": end.strftime(fmt),
            "searchType": "Application",
        }
        if csrf:
            data["_csrf"] = csrf["value"]
        page = self._post(f"{self.base}/advancedSearchResults.do?action=firstPage", data)
        if not page.select("li.searchresult"):
            title = page.title.get_text(strip=True) if page.title else ""
            msg = page.select_one(".messagebox, .errors, #searchResultsContainer p, .content p")
            self.diagnostic = {
                "page_title": title[:120],
                "message": msg.get_text(" ", strip=True)[:300] if msg else None,
                "form_has_field": bool(form.find(attrs={"name": f"date({field}Start)"})),
                "csrf_found": bool(csrf),
            }
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
        except Throttled:
            raise
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
            "validated_date": summary.get("Application Validated"),
            "applicant_name": details.get("Applicant Name"),
            "applicant_address": details.get("Applicant Address"),
            "agent_name": details.get("Agent Name"),
            "agent_company": details.get("Agent Company Name"),
            "agent_address": details.get("Agent Address"),
            "agent_phone": contacts.get("phone") or details.get("Agent Phone Number"),
            "agent_email": contacts.get("email"),
            "url": f"{self.base}/applicationDetails.do?activeTab=summary&keyVal={key}",
        }
