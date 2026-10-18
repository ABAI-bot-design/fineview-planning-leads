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
    ("Certificate of Lawfulness Proposed Development: two storey rear extension", "High"),
    ("Certificate of Lawfulness Existing Use: use of outbuilding as gym", None),
    ("Demolition of existing rear conservatory and construction of single storey rear extension.", "Med"),
    ("Demolition of existing bungalow and erection of a replacement detached dwelling", "High"),
    ("Installation of advertisement signage", None),
    ("Replacement front boundary fence", None),
    ("Demolition of existing modern extension comprising the conservatory, kitchen and utility room.", None),
    ("Demolition of existing garage, erection of single storey side infill extension", "Med"),
    ("Alteration and extension of driveway.", None),
    ("Extension of existing patio and new steps", None),
    ("Formation of vehicle crossover", None),
    ("Single storey rear extension and alterations to driveway", "Med"),
    ("Part single, part two storey rear extension", "High"),
    ("Rear extension with roof lantern", "Med"),
]


def test_scoring():
    from scoring import lead_score, postcode
    assert postcode("56 Williams Way Radlett Hertfordshire WD7 7HB") == "WD7 7HB"
    assert postcode("no postcode here") is None
    assert lead_score("High", 0, True, True) == 100
    assert lead_score("Med", 12, False, False) == 25
    assert lead_score("High", 5, True, False) > lead_score("Med", 5, True, False)


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
