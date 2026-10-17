import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
from filters import classify_party, size_score  # noqa: E402

CASES = [
    ("Demolition of existing dwelling and erection of a detached dwelling", "High"),
    ("Erection of 4 dwellings with associated parking", "High"),
    ("Two storey side and rear extension", "High"),
    ("Single storey rear extension", "Med"),
    ("Loft conversion with rear dormer", "Med"),
    ("Erection of conservatory", "Med"),
    ("T1 Oak - crown reduce by 2m (TPO)", None),
    ("Discharge of conditions 3 and 4 of planning permission 23/0012/FUL", None),
    ("Certificate of lawful development for single storey rear extension", None),
    ("Installation of advertisement signage", None),
    ("Replacement front boundary fence", None),
    ("Demolition of existing modern extension comprising the conservatory, kitchen and utility room.", None),
    ("Demolition of existing garage, erection of single storey side infill extension", "Med"),
]


def test_norm_company():
    from enrich import norm_company
    assert norm_company("Lisa Estates (Paragon) Ltd") == norm_company("LISA ESTATES (PARAGON) LIMITED")
    assert norm_company("Beechcroft Developments Ltd") != norm_company("Lisa Estates (Paragon) Ltd")
    assert norm_company("Not Available") != norm_company("Rock Andrew Ltd")


def test_size_score():
    for desc, want in CASES:
        assert size_score(desc) == want, desc


def test_classify():
    assert classify_party("Mr J Smith", "applicant") == "Homeowner"
    assert classify_party("Radlett Homes Ltd", "applicant") == "Developer"
    assert classify_party("ABC Construction", "applicant") == "Builder"
    assert classify_party("Jane Doe", "agent") == "Architect-agent"
