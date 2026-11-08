"""Form 4 XML parser: pure, provider-free, golden-file tested (ING-03, ING-04)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

from app.core.errors import ParseError
from app.providers.base import InsiderTxnData
from app.services.classification import classify, normalise_role


@dataclass(frozen=True, slots=True)
class ParsedFiling:
    document_type: str
    issuer_cik: str | None
    issuer_symbol: str | None
    is_amendment: bool
    transactions: list[InsiderTxnData] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _Owner:
    name: str
    cik: str | None
    officer_title: str | None
    role: str
    is_10b5_1: bool


def _localise(root: ElementTree.Element) -> None:
    for element in root.iter():
        if "}" in element.tag:
            element.tag = element.tag.rsplit("}", 1)[1]


def _text(parent: ElementTree.Element | None, path: str) -> str | None:
    if parent is None:
        return None
    found = parent.find(path)
    if found is None or found.text is None:
        return None
    value = found.text.strip()
    return value or None


def _bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "y", "yes"}


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    cleaned = value.replace(",", "").replace("$", "").strip()
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _footnote_ids(element: ElementTree.Element) -> list[str]:
    """Form 4 uses ``<footnoteId id="F1"/>`` (schema) and older files ``<footnote id="F1"/>``."""

    return [
        node.get("id", "") for node in element.iter() if node.get("id") and "ootnote" in node.tag
    ]


def _owners(root: ElementTree.Element) -> list[_Owner]:
    document_10b5 = _bool(_text(root, ".//aff10b5One"))
    owners: list[_Owner] = []
    for node in root.findall("reportingOwner"):
        owner_id = node.find("reportingOwnerId")
        relationship = node.find("reportingOwnerRelationship")
        title = _text(relationship, "officerTitle")
        owners.append(
            _Owner(
                name=_text(owner_id, "rptOwnerName") or "Unknown",
                cik=_text(owner_id, "rptOwnerCik"),
                officer_title=title,
                role=normalise_role(
                    officer_title=title,
                    is_director=_bool(_text(relationship, "isDirector")),
                    is_officer=_bool(_text(relationship, "isOfficer")),
                    is_ten_percent_owner=_bool(_text(relationship, "isTenPercentOwner")),
                ),
                is_10b5_1=_bool(_text(relationship, "aff10b5One")) or document_10b5,
            )
        )
    return owners


def parse_form4(
    xml: str | bytes,
    *,
    accession_no: str,
    filing_date: date,
    source: str = "sec_edgar",
    fallback_symbol: str | None = None,
) -> ParsedFiling:
    """Extract every non-derivative transaction from a Form 4 or 4/A document.

    The transaction table is a sibling of ``reportingOwner``, so transactions are
    attributed to the primary (first) reporting owner; joint filers share one
    table in EDGAR's schema. Derivative tables are ignored by design. Raises
    ``ParseError`` only when the document itself is unreadable.
    """

    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise ParseError(f"{accession_no}: malformed XML") from exc
    _localise(root)

    if root.tag != "ownershipDocument":
        raise ParseError(f"{accession_no}: not an ownershipDocument")

    document_type = _text(root, "documentType") or "4"
    is_amendment = document_type.endswith("/A") or _bool(_text(root, "isAmendment"))

    issuer = root.find("issuer")
    issuer_cik = _text(issuer, "issuerCik")
    issuer_symbol = _text(issuer, "issuerTradingSymbol") or fallback_symbol
    if issuer_symbol is not None:
        issuer_symbol = issuer_symbol.strip().upper()

    owners = _owners(root)
    table = root.find("nonDerivativeTable")
    if not owners or table is None:
        return ParsedFiling(document_type, issuer_cik, issuer_symbol, is_amendment, [])

    primary = owners[0]
    remarks = _text(root, "remarks") or ""
    footnotes = {node.get("id", ""): (node.text or "") for node in root.iter("footnote")}

    transactions: list[InsiderTxnData] = []
    line_no = 0

    for txn in table.findall("nonDerivativeTransaction"):
        shares = _decimal(_text(txn, "transactionAmounts/transactionShares/value"))
        code = _text(txn, "transactionCoding/transactionCode")
        if shares is None or code is None:
            continue

        price = _decimal(_text(txn, "transactionAmounts/transactionPricePerShare/value"))
        if price is not None and price == 0:
            price = None

        referenced = _footnote_ids(txn)
        note_text = " ".join([footnotes.get(fid, "") for fid in referenced] + [remarks])
        note_text = note_text.replace("\u2011", "-").lower()
        is_10b5 = primary.is_10b5_1 or "10b5-1" in note_text

        info = classify(code)
        line_no += 1
        transactions.append(
            InsiderTxnData(
                symbol=issuer_symbol or "",
                accession_no=accession_no,
                line_no=line_no,
                filing_date=filing_date,
                txn_date=_parse_date(_text(txn, "transactionDate/value")) or filing_date,
                insider_name=primary.name,
                insider_cik=primary.cik,
                officer_title=primary.officer_title,
                role=primary.role,
                txn_code=code.strip().upper(),
                action=info.action,
                shares=shares,
                price=price,
                value=(shares * price) if price is not None else None,
                shares_after=_decimal(
                    _text(txn, "postTransactionAmounts/sharesOwnedFollowingTransaction/value")
                ),
                is_10b5_1=is_10b5,
                is_amendment=is_amendment,
                source=source,
                extra={
                    "acquired_disposed": _text(
                        txn, "transactionAmounts/transactionAcquiredDisposedCode/value"
                    )
                    or "",
                },
            )
        )

    return ParsedFiling(
        document_type=document_type,
        issuer_cik=issuer_cik,
        issuer_symbol=issuer_symbol,
        is_amendment=is_amendment,
        transactions=transactions,
    )
