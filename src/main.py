"""Daily run: scrape -> filter -> categorise -> enrich (businesses) -> store."""
import logging
import os
import pathlib
import re
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import db  # noqa: E402
from enrich import enrich_business  # noqa: E402
from filters import classify_party, is_business, size_score  # noqa: E402
from idox import IdoxScraper  # noqa: E402
from scoring import distance_miles, lead_score, postcode  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("planning")

CFG = yaml.safe_load((pathlib.Path(__file__).parent.parent / "config/councils.yaml").read_text())


PLACEHOLDER_NAMES = re.compile(r"^\s*(not available|n/?a|none|unknown|tbc|-+|\.)?\s*$", re.I)
BLOCKED_EMAIL = re.compile(r"(\.gov\.uk|\.police\.uk|\.nhs\.uk|plandaportalcomms\.co\.uk)$", re.I)


def clean_email(email):
    if not email or "@" not in email or BLOCKED_EMAIL.search(email.strip()):
        return None
    return email.strip()


def save_contact(name, role, app, app_id, reachable):
    if not name or PLACEHOLDER_NAMES.match(name):
        return
    category = classify_party(name, role)
    biz = is_business(category)
    row = {"name": name.strip(), "category": category, "is_business": biz}
    if biz:
        if role == "agent":
            row.update({
                "phone": app.get("agent_phone"),
                "email": clean_email(app.get("agent_email")),
                "postal_address": app.get("agent_address"),
            })
        found = enrich_business(name)  # enrich THIS party, not the other one
        if found.get("email"):
            found["email"] = clean_email(found["email"])
        for k, v in found.items():
            if v and not row.get(k):
                row[k] = v
        row["status"] = "new"
    contact = db.upsert("contacts", {k: v for k, v in row.items() if v is not None}, "name,category")
    reachable["email"] |= bool(biz and contact.get("email"))
    reachable["phone"] |= bool(biz and contact.get("phone"))
    db.upsert("application_contacts",
              {"application_id": app_id, "contact_id": contact["id"], "role": role},
              "application_id,contact_id,role")
    if category == "Homeowner":
        # queue a consent-first letter to the property address
        db.upsert("letters", {"application_id": app_id}, "application_id")


def run():
    # LOOKBACK_DAYS env (set from the "Run workflow" form) overrides config, e.g. 90 for a backfill
    days = int(os.environ.get("LOOKBACK_DAYS") or CFG["lookback_days"])
    log.info("Looking back %d days", days)
    kept = 0
    for c in CFG["councils"]:
        if not c.get("enabled"):
            continue
        s = IdoxScraper(c["name"], c["base_url"])
        try:
            keys = list(s.search_decided(days))
        except Exception as e:  # one broken council shouldn't stop the run
            log.error("%s search failed: %s", c["name"], e)
            continue
        stats = {"decided": len(keys), "already_saved": 0, "not_approved": 0, "too_small": 0, "kept": 0}
        for key, list_desc in keys:
            # cheap pre-filter on the search-results description (saves ~4 requests per small job)
            if list_desc and not size_score(list_desc):
                stats["too_small"] += 1
                continue
            if db.exists("applications", council=c["name"], key_val=key):
                stats["already_saved"] += 1
                continue
            try:
                app = s.application(key)
            except Exception as e:
                log.warning("%s %s detail failed: %s", c["name"], key, e)
                continue
            decision = (app.get("decision") or "").lower()
            if "approv" not in decision and "grant" not in decision:
                stats["not_approved"] += 1
                continue
            score = size_score(app.get("description"))
            if not score:
                stats["too_small"] += 1
                continue
            stats["kept"] += 1
            row = {k: app[k] for k in ("council", "key_val", "reference", "address", "description",
                                       "decision", "decision_date", "url")}
            row["size_score"] = score
            row["postcode"] = postcode(app.get("address"))
            row["distance_miles"] = distance_miles(row["postcode"])
            saved = db.upsert("applications", row, "council,key_val")
            reachable = {"email": False, "phone": False}
            save_contact(app.get("applicant_name"), "applicant", app, saved["id"], reachable)
            save_contact(app.get("agent_company") or app.get("agent_name"), "agent", app, saved["id"], reachable)
            db.upsert("applications", {"council": row["council"], "key_val": row["key_val"],
                                       "lead_score": lead_score(score, row["distance_miles"],
                                                                reachable["email"], reachable["phone"])},
                      "council,key_val")
            kept += 1
        log.info("%s: %s", c["name"], stats)
    log.info("Run complete: %d new qualifying applications", kept)


if __name__ == "__main__":
    run()
