import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
import enrich  # noqa: E402

PAGE = "<html><head><title>{t}</title></head><body>" + "x" * 900 + " {b}</body></html>"


def test_candidates_from_name():
    c = enrich.domain_candidates("Bellis Architects Ltd")
    assert c[:3] == ["bellisarchitects.co.uk", "bellisarchitects.com", "bellisarchitects.uk"]
    assert "bellis-architects.co.uk" in c and "bellis.co.uk" in c


def test_ampersand_and_generic_only_names():
    assert "smithjonesarchitects.co.uk" in enrich.domain_candidates("Smith & Jones Architects")
    assert enrich.domain_candidates("AA Design+Architecture") == []   # too short to verify safely
    assert enrich.domain_candidates("Architects & Design Ltd") == []   # nothing distinctive
    assert enrich.domain_candidates("") == []


def test_page_must_name_the_firm_and_not_be_parked():
    good = PAGE.format(t="Bellis Architects | Home extensions", b="Contact Bellis Architects on 020 7946 0000")
    assert enrich.looks_like("Bellis Architects Ltd", good)
    assert not enrich.looks_like("Bellis Architects Ltd", PAGE.format(t="Smith Architects", b="Smith"))
    assert not enrich.looks_like("Bellis Architects Ltd", PAGE.format(t="bellis", b="This domain is for sale"))


def test_freemail_domains_are_never_websites():
    for d in ("mail.com", "gmail.com", "gmx.co.uk", "talktalk.net"):
        assert d in enrich.FREEMAIL
    assert enrich.site_from_email("roy@mail.com") is None
