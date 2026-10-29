import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
import idox  # noqa: E402


class Resp:
    def __init__(self, code, headers=None):
        self.status_code, self.headers, self.text = code, headers or {}, "<html><title>ok</title></html>"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise idox.requests.HTTPError(str(self.status_code), response=self)


def scraper(codes, monkeypatch):
    s = idox.IdoxScraper("Barnet", "https://example.invalid/online-applications", delay=6, sleep=lambda x: waits.append(x))
    seq = iter(codes)
    monkeypatch.setattr(s.s, "request", lambda *a, **k: next(seq))
    return s


waits = []


def test_waits_then_succeeds_after_429(monkeypatch):
    waits.clear()
    s = scraper([Resp(429), Resp(429, {"Retry-After": "90"}), Resp(200)], monkeypatch)
    soup = s._post("https://example.invalid/search", {})
    assert soup.title.get_text() == "ok"
    assert s.throttle_waits == 2
    # 6s pace before each request; back-offs are 60s, then max(120s default, Retry-After 90) = 120s
    assert waits == [6, 60, 6, 120, 6]


def test_gives_up_with_throttled(monkeypatch):
    waits.clear()
    s = scraper([Resp(429)] * 4, monkeypatch)
    with pytest.raises(idox.Throttled):
        s._get("https://example.invalid/x")
    assert s.throttle_waits == 3


def test_other_errors_raise_immediately(monkeypatch):
    waits.clear()
    s = scraper([Resp(404)], monkeypatch)
    with pytest.raises(idox.requests.HTTPError):
        s._get("https://example.invalid/x")
    assert s.throttle_waits == 0
