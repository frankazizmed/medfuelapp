from __future__ import annotations

from medfuel.ip.extract.claim_parser import (
    classify_breadth,
    classify_claim_type,
    parse_claims,
)
from medfuel.ip.models import ClaimBreadth, ClaimType


def test_classify_composition_claim():
    text = "A pharmaceutical composition comprising an antibody and a buffer."
    assert classify_claim_type(text) == ClaimType.COMPOSITION


def test_classify_method_claim():
    text = (
        "A method of treating cancer comprising administering an effective amount "
        "of compound X to a patient in need thereof."
    )
    assert classify_claim_type(text) == ClaimType.METHOD


def test_classify_software_claim_above_method():
    text = "A computer-implemented method comprising training a neural network."
    assert classify_claim_type(text) == ClaimType.SOFTWARE


def test_broad_independent_claim():
    text = "A composition comprising compound X."
    assert classify_breadth(text) == ClaimBreadth.BROAD


def test_narrow_claim_long_or_closed_transition():
    text = "A composition consisting of compound X and water."
    assert classify_breadth(text) == ClaimBreadth.NARROW


def test_parse_claims_from_patentsview_shape():
    raw = [
        {"claim_number": 1, "claim_text": "A composition comprising X.", "claim_dependent": False},
        {
            "claim_number": 2,
            "claim_text": "The composition of claim 1, wherein X is an antibody.",
            "claim_dependent": True,
        },
    ]
    claims = parse_claims(raw)
    assert len(claims) == 2
    assert claims[0].is_independent is True
    assert claims[1].is_independent is False
    assert claims[1].depends_on == 1
    assert claims[0].claim_type == ClaimType.COMPOSITION
