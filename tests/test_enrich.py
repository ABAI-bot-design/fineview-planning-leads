import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
import enrich  # noqa: E402

PAGE = "<html><head><title>{t}</title></head><body>" + "x" * 900 + " {b}</body></html>"


def test_candidates_use_the_whole_name_only():
    c = enrich.domain_candidates("Bellis Architects Ltd")
    assert c[0] == "bellisarchitects.co.uk" and "bellis-architects.co.uk" in c
    assert "bellis.co.uk" not in c                       # never a fragment of the name
    assert not any(d.startswith("apple.") for d in enrich.domain_candidates("Apple Planning and Design Ltd"))
    assert c.index("bellisarchitects.com") > c.index("bellisarchitects.uk")   # UK domains first


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
    # the words appearing separately isn't enough: Apple's site mentions "apple", "design" and "planning"
    assert not enrich.looks_like("Apple Planning and Design Ltd", PAGE.format(t="Apple", b="design ... planning ... apple"))
    # a .com must look British
    us = PAGE.format(t="Shah Designs", b="Shah Designs, Houston TX, call 713 555 0100")
    assert not enrich.looks_like("Shah Designs Ltd", us, uk_only=True)
    assert enrich.looks_like("Shah Designs Ltd", us.replace("Houston TX", "Harrow HA1 2AB"), uk_only=True)


def test_junk_socials_dropped():
    d = enrich.clean_socials({"facebook": "http://www.facebook.com/2008", "instagram": "https://www.instagram.com/p",
                              "linkedin": "https://www.linkedin.com/company/bellis"})
    assert d == {"linkedin": "https://www.linkedin.com/company/bellis"}


def test_freemail_domains_are_never_websites():
    for d in ("mail.com", "gmail.com", "gmx.co.uk", "talktalk.net"):
        assert d in enrich.FREEMAIL
    assert enrich.site_from_email("roy@mail.com") is None
