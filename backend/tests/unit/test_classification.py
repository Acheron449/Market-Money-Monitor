"""SIG-01, SIG-03 and SIG-04 rules."""

from __future__ import annotations

import pytest

from app.services.classification import classify, is_starred, normalise_role


@pytest.mark.parametrize(
    ("code", "label", "action", "counts"),
    [
        ("P", "Open-market buy", "buy", True),
        ("S", "Open-market sell", "sell", True),
        ("A", "Award / grant", "other", False),
        ("M", "Option exercise / conversion", "other", False),
        ("X", "Option exercise / conversion", "other", False),
        ("C", "Option exercise / conversion", "other", False),
        ("F", "Tax withholding", "other", False),
        ("G", "Gift", "other", False),
        ("D", "Disposed to issuer", "other", False),
    ],
)
def test_code_mapping(code: str, label: str, action: str, counts: bool) -> None:
    info = classify(code)
    assert (info.type_label, info.action, info.counts) == (label, action, counts)


def test_lowercase_and_unknown_codes() -> None:
    assert classify("p").action == "buy"
    unknown = classify("Z")
    assert (unknown.type_label, unknown.action, unknown.counts) == ("Other", "other", False)


@pytest.mark.parametrize(
    ("title", "kwargs", "expected"),
    [
        ("Chief Executive Officer", {}, "CEO"),
        ("President and Chief Executive Officer", {}, "CEO"),
        ("CEO", {}, "CEO"),
        ("Chief Financial Officer", {}, "CFO"),
        ("EVP & CFO", {"is_officer": True}, "CFO"),
        ("Chief Operating Officer", {}, "COO"),
        ("Chief Technology Officer", {}, "CTO"),
        ("President", {}, "President"),
        ("Vice President, Finance", {"is_officer": True}, "Other"),
        (None, {"is_director": True}, "Director"),
        (None, {"is_ten_percent_owner": True}, "10% Owner"),
        (None, {}, "Other"),
    ],
)
def test_role_normalisation(title: str | None, kwargs: dict[str, bool], expected: str) -> None:
    assert normalise_role(officer_title=title, **kwargs) == expected


def test_starred_only_for_ceo_or_cfo_open_market_buys() -> None:
    assert is_starred("buy", "CEO") is True
    assert is_starred("buy", "CFO") is True
    assert is_starred("buy", "Director") is False
    assert is_starred("sell", "CEO") is False
    assert is_starred("other", "CFO") is False


def test_director_with_ceo_title_prefers_title() -> None:
    role = normalise_role(officer_title="Chief Executive Officer", is_director=True)
    assert role == "CEO"
