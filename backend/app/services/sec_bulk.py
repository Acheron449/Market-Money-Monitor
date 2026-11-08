"""SEC bulk data-set loaders for historical backfill (ING-12).

The loaders read the official tab-delimited quarterly archives (or a directory
containing the extracted tables). They never fetch from the network, so an
operator can backfill from a local SEC archive without credentials.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Holder, InsiderTxn, Ticker
from app.services.classification import classify, normalise_role
from app.services.ingest import track_run

LOGGER = logging.getLogger(__name__)
INSIDER_SOURCE = "sec_bulk_insider"
FORM13F_SOURCE = "sec_13f"
FORM4_TYPES = frozenset({"4", "4/A"})


@dataclass(frozen=True, slots=True)
class BulkLoadResult:
    dataset: str
    rows: int
    skipped: int
    symbols: list[str]


@dataclass(slots=True)
class _Holding:
    symbol: str
    report_period: date
    institution_cik: str
    institution: str
    shares: Decimal
    value: Decimal


def read_cusip_map(path: Path) -> dict[str, str]:
    """Read an optional ``cusip,symbol`` CSV used to resolve 13F issuers."""

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        result: dict[str, str] = {}
        for row in reader:
            cusip = (row.get("cusip") or "").strip().upper()
            symbol = (row.get("symbol") or "").strip().upper()
            if cusip and symbol:
                result[cusip] = symbol
        return result


async def load_insider_dataset(
    session: AsyncSession,
    path: Path,
    *,
    symbols: Sequence[str] | None = None,
) -> BulkLoadResult:
    """Backfill non-derivative Form 4 rows from an Insider Transactions archive."""

    files = _read_dataset(path)
    submissions = _rows(files, "SUBMISSION")
    owners = _owner_index(_rows(files, "REPORTINGOWNER"))
    transactions = _rows(files, "NONDERIV_TRANS")
    tickers = await _tickers(session, symbols)
    cik_to_symbol = {ticker.cik: ticker.symbol for ticker in tickers.values() if ticker.cik}
    written = 0
    skipped = 0
    touched: set[str] = set()

    async with track_run(session, job="bulk_insider", provider=INSIDER_SOURCE) as run:
        for submission in submissions:
            accession = submission.get("ACCESSION_NUMBER", "")
            document_type = submission.get("DOCUMENT_TYPE", "").upper()
            if not accession or document_type not in FORM4_TYPES:
                skipped += 1
                continue
            owner_rows = owners.get(accession, [])
            owner: dict[str, str] | None = owner_rows[0] if owner_rows else None
            raw_symbol = submission.get("ISSUERTRADINGSYMBOL", "").upper()
            symbol = (
                raw_symbol
                if raw_symbol in tickers
                else cik_to_symbol.get(submission.get("ISSUERCIK", ""))
            )
            if symbol is None or owner is None:
                skipped += 1
                continue
            filing_date = _date(submission.get("FILING_DATE"))
            if filing_date is None:
                skipped += 1
                continue
            accession_rows = sorted(
                (row for row in transactions if row.get("ACCESSION_NUMBER") == accession),
                key=lambda row: _integer(row.get("NONDERIV_TRANS_SK")),
            )
            for line_no, row in enumerate(accession_rows, start=1):
                shares = _decimal(row.get("TRANS_SHARES"))
                code = (row.get("TRANS_CODE") or "").strip().upper()
                txn_date = _date(row.get("TRANS_DATE"))
                if shares is None or not code or txn_date is None:
                    skipped += 1
                    continue
                price = _decimal(row.get("TRANS_PRICEPERSHARE"))
                if price == 0:
                    price = None
                info = classify(code)
                is_amendment = document_type.endswith("/A")
                insider_cik = owner.get("RPTOWNERCIK") or None
                if is_amendment and insider_cik:
                    await session.execute(
                        delete(InsiderTxn).where(
                            InsiderTxn.symbol == symbol,
                            InsiderTxn.insider_cik == insider_cik,
                            InsiderTxn.txn_date == txn_date,
                            InsiderTxn.txn_code == code,
                            InsiderTxn.is_amendment.is_(False),
                        )
                    )
                await session.merge(
                    InsiderTxn(
                        accession_no=accession,
                        line_no=line_no,
                        symbol=symbol,
                        filing_date=filing_date,
                        txn_date=txn_date,
                        insider_name=owner.get("RPTOWNERNAME") or "Unknown",
                        insider_cik=insider_cik,
                        officer_title=owner.get("RPTOWNER_TITLE") or None,
                        role=_role(owner),
                        txn_code=code,
                        action=info.action,
                        shares=shares,
                        price=price,
                        value=(shares * price) if price is not None else None,
                        shares_after=_decimal(row.get("SHRS_OWND_FOLWNG_TRANS")),
                        is_10b5_1=_truthy(submission.get("AFF10B5ONE"))
                        or _truthy(owner.get("AFF10B5ONE")),
                        is_amendment=is_amendment,
                        source=INSIDER_SOURCE,
                    )
                )
                written += 1
                touched.add(symbol)
        run.rows = written

    return BulkLoadResult("insider", written, skipped, sorted(touched))


async def load_13f_dataset(
    session: AsyncSession,
    path: Path,
    *,
    cusip_map: Mapping[str, str] | None = None,
    symbols: Sequence[str] | None = None,
) -> BulkLoadResult:
    """Backfill institutional holdings from a Form 13F data-set archive."""

    files = _read_dataset(path)
    submissions = _rows(files, "SUBMISSION")
    cover_pages = {row.get("ACCESSION_NUMBER", ""): row for row in _rows(files, "COVERPAGE")}
    info_rows = _rows(files, "INFOTABLE")
    tickers = await _tickers(session, symbols)
    name_to_symbol = {
        _normalise_name(ticker.name or ""): ticker.symbol
        for ticker in tickers.values()
        if ticker.name
    }
    selected = _latest_13f_submissions(submissions)
    holdings: dict[tuple[str, date, str], _Holding] = {}
    skipped = 0

    for row in info_rows:
        submission = selected.get(row.get("ACCESSION_NUMBER", ""))
        if submission is None:
            continue
        period = _date(submission.get("PERIODOFREPORT")) or _date(
            cover_pages.get(submission["ACCESSION_NUMBER"], {}).get("REPORTCALENDARORQUARTER")
        )
        filer_cik = submission.get("CIK", "")
        if period is None or not filer_cik:
            skipped += 1
            continue
        amount_type = (row.get("SSHPRNAMTTYPE") or "SH").upper()
        shares = _decimal(row.get("SSHPRNAMT"))
        value = _decimal(row.get("VALUE"))
        if amount_type != "SH" or shares is None or value is None:
            skipped += 1
            continue
        symbol = _resolve_symbol(
            row.get("NAMEOFISSUER", ""),
            row.get("CUSIP", ""),
            cusip_map or {},
            name_to_symbol,
        )
        if symbol is None:
            skipped += 1
            continue
        cover = cover_pages.get(submission["ACCESSION_NUMBER"], {})
        manager = cover.get("FILINGMANAGER_NAME") or "Unknown"
        key = (symbol, period, f"{symbol}-{filer_cik}")
        existing = holdings.get(key)
        if existing is None:
            holdings[key] = _Holding(
                symbol=symbol,
                report_period=period,
                institution_cik=f"{symbol}-{filer_cik}",
                institution=manager,
                shares=shares,
                value=value * Decimal("1000"),
            )
        else:
            existing.shares += shares
            existing.value += value * Decimal("1000")

    written = 0
    touched: set[str] = set()
    async with track_run(session, job="bulk_13f", provider=FORM13F_SOURCE) as run:
        for holding in holdings.values():
            previous = await session.scalar(
                select(Holder)
                .where(
                    Holder.symbol == holding.symbol,
                    Holder.institution_cik == holding.institution_cik,
                    Holder.report_period < holding.report_period,
                )
                .order_by(Holder.report_period.desc())
                .limit(1)
            )
            prev_shares = previous.shares if previous is not None else None
            qoq = _qoq(holding.shares, prev_shares)
            await session.merge(
                Holder(
                    symbol=holding.symbol,
                    report_period=holding.report_period,
                    institution_cik=holding.institution_cik,
                    institution=holding.institution,
                    shares=holding.shares,
                    value=holding.value,
                    prev_shares=prev_shares,
                    qoq_change_pct=qoq,
                    rank=0,
                    source=FORM13F_SOURCE,
                )
            )
            written += 1
            touched.add(holding.symbol)

        periods = {(holding.symbol, holding.report_period) for holding in holdings.values()}
        for symbol, period in periods:
            period_rows = list(
                await session.scalars(
                    select(Holder)
                    .where(Holder.symbol == symbol, Holder.report_period == period)
                    .order_by(Holder.value.desc(), Holder.institution)
                )
            )
            for rank, holder_row in enumerate(period_rows, start=1):
                holder_row.rank = rank
        run.rows = written

    return BulkLoadResult("13f", written, skipped, sorted(touched))


def _latest_13f_submissions(rows: Sequence[dict[str, str]]) -> dict[str, dict[str, str]]:
    """Keep the latest holdings submission per manager/report period."""

    latest: dict[tuple[str, date], dict[str, str]] = {}
    for row in rows:
        if not row.get("SUBMISSIONTYPE", "").upper().startswith("13F-HR"):
            continue
        period = _date(row.get("PERIODOFREPORT"))
        if period is None:
            continue
        key = (row.get("CIK", ""), period)
        current = latest.get(key)
        filed = _date(row.get("FILING_DATE")) or date.min
        current_filed = (
            _date(current.get("FILING_DATE")) or date.min if current is not None else date.min
        )
        if current is None or filed >= current_filed:
            latest[key] = row
    return {row["ACCESSION_NUMBER"]: row for row in latest.values()}


def _resolve_symbol(
    issuer: str,
    cusip: str,
    cusip_map: Mapping[str, str],
    name_to_symbol: Mapping[str, str],
) -> str | None:
    mapped = cusip_map.get(cusip.strip().upper())
    if mapped:
        return mapped
    normalised = _normalise_name(issuer)
    if normalised in name_to_symbol:
        return name_to_symbol[normalised]
    for name, symbol in name_to_symbol.items():
        if name and (name in normalised or normalised in name):
            return symbol
    return None


async def _tickers(session: AsyncSession, symbols: Sequence[str] | None) -> dict[str, Ticker]:
    rows = list(await session.scalars(select(Ticker)))
    allowed = {symbol.upper() for symbol in symbols} if symbols else None
    return {row.symbol: row for row in rows if allowed is None or row.symbol in allowed}


def _owner_index(rows: Sequence[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    indexed: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        indexed[row.get("ACCESSION_NUMBER", "")].append(row)
    for values in indexed.values():
        values.sort(key=lambda row: row.get("RPTOWNERCIK", ""))
    return indexed


def _read_dataset(path: Path) -> dict[str, bytes]:
    if path.is_dir():
        files: dict[str, bytes] = {}
        for item in path.rglob("*"):
            if item.is_file():
                files[item.stem.upper()] = item.read_bytes()
        return files
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            return {
                Path(info.filename).stem.upper(): archive.read(info)
                for info in archive.infolist()
                if not info.is_dir()
            }
    raise ValueError(f"{path}: expected a ZIP archive or extracted data-set directory")


def _rows(files: Mapping[str, bytes], name: str) -> list[dict[str, str]]:
    raw = files.get(name)
    if raw is None:
        raise ValueError(f"missing {name} table")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter="\t")
    return [
        {(key or "").strip().upper(): (value or "").strip() for key, value in row.items()}
        for row in reader
    ]


def _role(owner: Mapping[str, str]) -> str:
    relationship = owner.get("RPTOWNER_RELATIONSHIP", "").upper()
    return normalise_role(
        officer_title=owner.get("RPTOWNER_TITLE") or None,
        is_director="DIRECTOR" in relationship,
        is_officer="OFFICER" in relationship,
        is_ten_percent_owner="TENPERCENTOWNER" in relationship.replace(" ", ""),
    )


def _date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%b-%y"):
        try:
            return datetime.strptime(text[:11], fmt).date()
        except ValueError:
            continue
    return None


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("$", "").strip()
    if not text:
        return None
    try:
        result = Decimal(text)
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def _integer(value: Any) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "y", "yes"}


def _normalise_name(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def _qoq(shares: Decimal, previous: Decimal | None) -> Decimal | None:
    if previous is None or previous == 0:
        return None
    return ((shares - previous) / previous * Decimal("100")).quantize(Decimal("0.0001"))
