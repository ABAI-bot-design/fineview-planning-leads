"""Daily run: scrape -> filter -> categorise -> enrich (businesses) -> store."""
import logging
import os
import pathlib
import re
import sys
import time

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
        found = enrich_business(name, row.get("email"))  # enrich THIS party; its email domain points to its site
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
    # COUNCILS env (e.g. "Barnet") limits a manual run to some councils; blank = all enabled
    only = {x.strip().lower() for x in (os.environ.get("COUNCILS") or "").split(",") if x.strip()}
    log.info("Looking back %d days%s", days, f" (councils: {', '.join(sorted(only))})" if only else "")
    kept = 0
    for c in CFG["councils"]:
        if not c.get("enabled") or (only and c["name"].lower() not in only):
            continue
        s = IdoxScraper(c["name"], c["base_url"], delay=float(c.get("delay", 2.0)))
        # 'validated' = newly submitted (contact architects early); 'decided' = approvals
        for i, by in enumerate(("validated", "decided")):
            if i and c.get("pause_between_searches"):
                time.sleep(float(c["pause_between_searches"]))  # some councils throttle back-to-back searches
            kept += process_search(s, c["name"], days, by)
    log.info("Run complete: %d new qualifying applications", kept)


def record_run(council, by, stats=None, error=None):
    try:
        db.insert("runs", {"council": council, "search": by, "stats": stats, "error": error})
    except Exception as e:  # logging must never break the scrape
        log.warning("could not record run: %s", e)


def process_search(s, council, days, by):
    try:
        keys = list(s.search(days, by))
    except Exception as e:  # one broken council shouldn't stop the run
        log.error("%s %s search failed: %s", council, by, e)
        record_run(council, by, error=str(e)[:500])
        return 0
    stats = {"found": len(keys), "already_saved": 0, "promoted_to_approved": 0, "refused_or_withdrawn": 0,
             "too_small": 0, "kept": 0, "detail_failed": 0}
    errors = []  # first few failure messages, saved with the run so a gap is never silent
    if not keys and s.diagnostic:
        stats["diagnostic"] = s.diagnostic
    kept = 0
    for key, list_desc in keys:
        # cheap pre-filter on the search-results description (saves ~4 requests per small job)
        if list_desc and not size_score(list_desc):
            stats["too_small"] += 1
            continue
        if db.exists("applications", council=council, key_val=key):
            stats["already_saved"] += 1
            if by == "decided":
                # it was saved at submission; now decided - record the outcome
                try:
                    app = s.application(key)
                    db.upsert("applications", {
                        "council": council, "key_val": key, "decision": app.get("decision"),
                        "decision_date": app.get("decision_date"), "stage": stage_of(app.get("decision")),
                    }, "council,key_val")
                    stats["promoted_to_approved"] += 1
                except Exception as e:
                    log.warning("%s %s update failed: %s", council, key, e)
                    stats["detail_failed"] += 1
                    errors.append(str(e)[:200])
            continue
        try:
            app = s.application(key)
        except Exception as e:
            log.warning("%s %s detail failed: %s", council, key, e)
            stats["detail_failed"] += 1
            errors.append(str(e)[:200])
            continue
        stage = stage_of(app.get("decision"))
        if stage == "dead":
            stats["refused_or_withdrawn"] += 1
            continue
        score = size_score(app.get("description"))
        if not score:
            stats["too_small"] += 1
            continue
        stats["kept"] += 1
        row = {k: app[k] for k in ("council", "key_val", "reference", "address", "description",
                                   "decision", "decision_date", "validated_date", "url")}
        row["stage"] = stage
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
    stats["throttle_waits"] = getattr(s, "throttle_waits", 0)
    if errors:
        stats["errors"] = errors[:3]
    log.info("%s %s: %s", council, by, stats)
    record_run(council, by, stats)
    return kept


def stage_of(decision) -> str:
    d = (decision or "").lower()
    if not d or "pending" in d or "awaiting" in d:
        return "submitted"
    if "refus" in d or "withdraw" in d or "invalid" in d or "dismiss" in d:
        return "dead"
    if "approv" in d or "grant" in d or "permit" in d or "lawful" in d or "not required" in d:
        return "approved"
    return "submitted"


def rescore():
    """Re-apply the current size filter and scoring to everything already saved.
    No scraping. Non-qualifying rows are flagged excluded (kept for audit, hidden from views)."""
    apps = db.select("applications", "id,description,distance_miles")
    links = db.select("application_contacts", "application_id,contact_id")
    biz = {c["id"]: c for c in db.select("contacts", "id,is_business,email,phone") if c["is_business"]}
    by_app = {}
    for l in links:
        if l["contact_id"] in biz:
            by_app.setdefault(l["application_id"], []).append(biz[l["contact_id"]])
    changed = excluded = 0
    for a in apps:
        size = size_score(a["description"])
        if not size:
            db.update("applications", {"excluded": True}, id=a["id"])
            excluded += 1
            continue
        cs = by_app.get(a["id"], [])
        miles = float(a["distance_miles"]) if a["distance_miles"] is not None else None
        db.update("applications", {
            "excluded": False, "size_score": size,
            "lead_score": lead_score(size, miles, any(c.get("email") for c in cs), any(c.get("phone") for c in cs)),
        }, id=a["id"])
        changed += 1
    log.info("Rescore: %d kept and rescored, %d excluded", changed, excluded)


def enrich_existing():
    """Backfill website/socials/phone for saved BUSINESS contacts (never homeowners)."""
    cols = "id,name,email,phone,website,instagram,facebook,linkedin"
    done = 0
    for c in db.select("contacts", cols, is_business="eq.true"):
        if PLACEHOLDER_NAMES.match(c["name"] or "") or (c["website"] and c["instagram"] and c["linkedin"]):
            continue
        try:
            found = enrich_business(c["name"], c["email"])
        except Exception as e:
            log.warning("enrich %s failed: %s", c["name"], e)
            continue
        if found.get("email"):
            found["email"] = clean_email(found["email"])
        updates = {k: v for k, v in found.items()
                   if k in ("website", "instagram", "facebook", "linkedin", "phone",
                            "company_number", "company_status", "directors") and v and not c.get(k)}
        if updates:
            db.update("contacts", updates, id=c["id"])
            done += 1
    log.info("Enrich: updated %d business contacts", done)


if __name__ == "__main__":
    mode = os.environ.get("MODE")
    rescore() if mode == "rescore" else enrich_existing() if mode == "enrich" else run()
