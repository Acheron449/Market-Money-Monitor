"""Golden-file tests for the Form 4 parser (NFR-04)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.errors import ParseError
from app.parsers.form4 import parse_form4

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "form4"
FILED = date(2026, 11, 6)


def parse(name: str):  # type: ignore[no-untyped-def]
    return parse_form4(
        (FIXTURES / name).read_bytes(),
        accession_no="0001045810-26-000123",
        filing_date=FILED,
    )


def test_ceo_open_market_buy() -> None:
    parsed = parse("ceo_open_market_buy.xml")
    assert parsed.issuer_symbol == "NVDA"
    assert parsed.issuer_cik == "0001045810"
    assert parsed.is_amendment is False
    assert len(parsed.transactions) == 1

    txn = parsed.transactions[0]
    assert txn.insider_name == "HUANG JEN HSUN"
    assert txn.insider_cik == "0001214128"
    assert txn.role == "CEO"
    assert txn.officer_title == "President and Chief Executive Officer"
    assert txn.txn_code == "P"
    assert txn.action == "buy"
    assert txn.shares == Decimal("10000")
    assert txn.price == Decimal("182.5")
    assert txn.value == Decimal("1825000.0")
    assert txn.shares_after == Decimal("85000000")
    assert txn.txn_date == date(2026, 11, 5)
    assert txn.filing_date == FILED
    assert txn.is_10b5_1 is False
    assert txn.accession_no == "0001045810-26-000123"
    assert txn.line_no == 1


def test_cfo_10b5_sale_flags_plan_and_footnote() -> None:
    parsed = parse("cfo_10b5_sale.xml")
    txn = parsed.transactions[0]
    assert txn.role == "CFO"
    assert txn.action == "sell"
    assert txn.value == Decimal("775500.0")
    assert txn.is_10b5_1 is True


def test_joint_filers_use_the_primary_owner() -> None:
    parsed = parse("joint_filers.xml")
    assert len(parsed.transactions) == 2
    assert {t.insider_name for t in parsed.transactions} == {"LEVINSON ARTHUR D"}
    assert {t.role for t in parsed.transactions} == {"Director"}
    assert [t.line_no for t in parsed.transactions] == [1, 2]
    assert parsed.transactions[1].shares == Decimal("800")
    assert parsed.transactions[0].value == Decimal("325368.00")


def test_derivative_only_filing_yields_no_rows() -> None:
    parsed = parse("derivative_only.xml")
    assert parsed.transactions == []


def test_awards_and_gifts_have_no_value() -> None:
    parsed = parse("award_and_gift.xml")
    assert len(parsed.transactions) == 2
    award, gift = parsed.transactions
    assert award.txn_code == "A"
    assert award.action == "other"
    assert award.price is None
    assert award.value is None
    assert gift.txn_code == "G"
    assert gift.value is None
    assert gift.shares == Decimal("500")


def test_amendment_is_flagged() -> None:
    parsed = parse("amendment.xml")
    assert parsed.is_amendment is True
    assert parsed.transactions[0].is_amendment is True
    assert parsed.transactions[0].txn_code == "S"


def test_malformed_xml_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        parse_form4(b"<ownershipDocument>", accession_no="x", filing_date=FILED)
