"""Daily run: scrape -> filter -> categorise -> enrich (businesses) -> store."""
import logging
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import db  # noqa: E402
from enrich import enrich_business  # noqa: E402
from filters import classify_party, is_business, size_score  # noqa: E402
from idox import IdoxScraper  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("planning")

CFG = yaml.safe_load((pathlib.Path(__file__).parent.parent / "config/councils.yaml").read_text())


def save_contact(name, role, app, app_id):
    if not name:
        return
    category = classify_party(name, role)
    biz = is_business(category)
    row = {"name": name, "category": category, "is_business": biz}
    if biz:
        if role == "agent":
            row.update({
                "phone": app.get("agent_phone"),
                "email": app.get("agent_email"),
                "postal_address": app.get("agent_address"),
            })
        # enrichment only fills gaps - details from the planning record win
        row.update({k: v for k, v in enrich_business(app.get("agent_company") or name).items()
                    if v and not row.get(k)})
        row["status"] = "new"
    contact = db.upsert("contacts", {k: v for k, v in row.items() if v is not None}, "name,category")
    db.upsert("application_contacts",
              {"application_id": app_id, "contact_id": contact["id"], "role": role},
              "application_id,contact_id,role")
    if category == "Homeowner":
        # queue a consent-first letter to the property address
        db.upsert("letters", {"application_id": app_id}, "application_id")


def run():
    kept = 0
    for c in CFG["councils"]:
        if not c.get("enabled"):
            continue
        s = IdoxScraper(c["name"], c["base_url"])
        try:
            keys = list(s.search_decided(CFG["lookback_days"]))
        except Exception as e:  # one broken council shouldn't stop the run
            log.error("%s search failed: %s", c["name"], e)
            continue
        log.info("%s: %d decided applications", c["name"], len(keys))
        for key in keys:
            if db.exists("applications", council=c["name"], key_val=key):
                continue
            try:
                app = s.application(key)
            except Exception as e:
                log.warning("%s %s detail failed: %s", c["name"], key, e)
                continue
            if "approv" not in (app.get("decision") or "").lower() and "grant" not in (app.get("decision") or "").lower():
                continue
            score = size_score(app.get("description"))
            if not score:
                continue
            row = {k: app[k] for k in ("council", "key_val", "reference", "address", "description",
                                       "decision", "decision_date", "url")}
            row["size_score"] = score
            saved = db.upsert("applications", row, "council,key_val")
            save_contact(app.get("applicant_name"), "applicant", app, saved["id"])
            save_contact(app.get("agent_company") or app.get("agent_name"), "agent", app, saved["id"])
            kept += 1
    log.info("Run complete: %d new qualifying applications", kept)


if __name__ == "__main__":
    run()
