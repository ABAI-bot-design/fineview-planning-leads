import os
import pathlib
import sys

os.environ.setdefault("SUPABASE_URL", "https://example.invalid")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test")
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
import main  # noqa: E402
from idox import Throttled  # noqa: E402


class FakeScraper:
    """Every detail page is blocked."""
    def __init__(self):
        self.calls, self.throttle_waits, self.diagnostic = 0, 0, None

    def search(self, days, by):
        return [(f"K{i}", "Two storey rear extension") for i in range(10)]

    def application(self, key):
        self.calls += 1
        raise Throttled("429 from Barnet")


def test_stops_after_two_blocked_applications(monkeypatch):
    runs = []
    monkeypatch.setattr(main.db, "exists", lambda *a, **k: False)
    monkeypatch.setattr(main, "record_run", lambda council, by, stats=None, error=None: runs.append((by, stats, error)))
    s = FakeScraper()
    assert main.process_search(s, "Barnet", 8, "validated") == 0
    assert s.calls == 2 and s.blocked
    by, stats, _ = runs[0]
    assert stats["stopped_early"] and stats["detail_failed"] == 2 and stats["errors"]
