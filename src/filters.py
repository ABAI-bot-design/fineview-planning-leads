"""Size filter and lead categorisation.

Goal: keep only applications likely to need >£5k of windows/doors.
"""
import re

# Strong signals of a large glazing job -> High
HIGH = [
    r"\berection of (?:a |an |one |two |three |four |five |\d+ )?(?:detached |semi-detached |terraced )?(?:dwelling|house|houses|dwellings|homes?)\b",
    r"\bnew (?:dwelling|house|build|home)s?\b",
    r"\breplacement dwelling\b",
    r"\bdemolition of .* and (?:the )?(?:erection|construction)\b",
    r"\b\d+\s*(?:no\.?\s*)?(?:flats|apartments|dwellings|units)\b",
    r"\btwo[- ]storey\b.*\bextension\b",
    r"\bdouble[- ]storey\b",
    r"\bbasement\b",
    r"\bconversion of .* (?:to|into) (?:\d+ )?(?:dwelling|flats|residential)",
    r"\borangery\b",
    r"\breplacement (?:of )?(?:all )?windows\b",
]
# Medium signals -> Med
MED = [
    r"\bsingle[- ]storey (?:rear|side|front|wrap[- ]around)? ?extension\b",
    r"\bwrap[- ]around\b",
    r"\bloft conversion\b.*\bdormer\b|\bdormer\b",
    r"\bconservatory\b",
    r"\bextension\b",
    r"\broof lantern\b",
    r"\bglazing\b|\bbi-?fold\b|\bsliding doors?\b",
]
# Anything matching these is dropped regardless
EXCLUDE = [
    # demolition-only applications (nothing being built)
    r"^demolition of(?!.*\b(?:erection|construction|replacement|rebuild|new)\b)",
    r"\btree\b|\btpo\b|\bfell\b|\bprune\b|\bcrown\b",
    r"\bdischarge of conditions?\b|\bdetails pursuant\b|\bnon[- ]material amendment\b",
    r"\bcertificate of lawful\b|\blawful development\b",
    r"\badvertisement\b|\bsignage\b|\bsign\b",
    r"\bfence\b|\bgate\b|\bwall\b(?!.*extension)",
    r"\bporch\b(?!.*extension)",
    r"\bsatellite\b|\btelecom|\bmast\b",
    r"\bchange of use\b(?!.*dwelling)",
    r"\bprior approval\b(?!.*(?:dwelling|extension))",
]


def _any(patterns, text):
    return any(re.search(p, text) for p in patterns)


def size_score(description: str) -> str | None:
    """Return 'High', 'Med', or None (drop)."""
    d = (description or "").lower()
    if _any(EXCLUDE, d):
        return None
    if _any(HIGH, d):
        return "High"
    if _any(MED, d):
        return "Med"
    return None


COMPANY_MARKERS = re.compile(
    r"\b(ltd|limited|llp|plc|homes|developments?|properties|property|estates?|"
    r"construction|builders?|building|investments?|holdings|group|partnership)\b",
    re.I,
)
AGENT_MARKERS = re.compile(
    r"\b(architect|architecture|design|planning|surveyor|consult|associates|studio|drawing)\b",
    re.I,
)
BUILDER_MARKERS = re.compile(r"\b(construction|builders?|building|contractors?)\b", re.I)


def classify_party(name: str, role: str) -> str:
    """role is 'applicant' or 'agent'. Returns Developer/Builder/Architect-agent/Homeowner."""
    n = name or ""
    if role == "agent":
        return "Architect-agent"
    if BUILDER_MARKERS.search(n):
        return "Builder"
    if COMPANY_MARKERS.search(n):
        return "Developer"
    return "Homeowner"


def is_business(category: str) -> bool:
    return category in {"Developer", "Builder", "Architect-agent"}
