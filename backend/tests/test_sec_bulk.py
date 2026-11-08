"""ING-11/ING-12: SEC bulk backfills, latest-period holders and cross-checking."""

from __future__ import annotations

import logging
import zipfile
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import CrossCheckDiscrepancy, Holder, InsiderTxn
from app.providers.base import InsiderTxnData
from app.services.cross_check import cross_check_insiders
from app.services.ingest import active_tickers
from app.services.sec_bulk import load_13f_dataset, load_insider_dataset, read_cusip_map

FIXTURES = Path(__file__).parent / "fixtures" / "sec"


class SecondaryProvider:
    name = "fixture_secondary"

    def __init__(self, rows: list[InsiderTxnData]) -> None:
        self._rows = rows

    async def fetch_transactions(
        self, symbol: str, cik: str | None, since: date
    ) -> list[InsiderTxnData]:
        return [row for row in self._rows if row.symbol == symbol]


async def test_insider_dataset_loads_form4_rows_idempotently(seeded) -> None:  # type: ignore[no-untyped-def]
    async with seeded.state.db.session() as session:
        first = await load_insider_dataset(session, FIXTURES / "insider")
        second = await load_insider_dataset(session, FIXTURES / "insider")
        rows = list(
            await session.scalars(select(InsiderTxn).where(InsiderTxn.source == "sec_bulk_insider"))
        )

    assert first.rows == 2
    assert first.skipped == 0
    assert first.symbols == ["NVDA"]
    assert second.rows == 2
    assert len(rows) == 2
    assert {row.txn_code for row in rows} == {"P", "S"}
    buy = next(row for row in rows if row.txn_code == "P")
    assert buy.insider_name == "HUANG JEN HSUN"
    assert buy.role == "CEO"
    assert buy.shares == Decimal("1500.0000")
    assert buy.value == Decimal("300000.0000")
    assert buy.source == "sec_bulk_insider"


async def test_13f_dataset_loads_zip_and_ranks_holders(seeded, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    archive = tmp_path / "form13f.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for source in (FIXTURES / "13f").iterdir():
            handle.write(source, arcname=source.name)

    async with seeded.state.db.session() as session:
        result = await load_13f_dataset(
            session,
            archive,
            cusip_map=read_cusip_map(FIXTURES / "cusip-map.csv"),
        )
        nvda = list(
            await session.scalars(
                select(Holder)
                .where(Holder.symbol == "NVDA")
                .order_by(Holder.report_period.desc(), Holder.rank)
            )
        )

    assert result.rows == 2
    assert result.symbols == ["AAPL", "NVDA"]
    assert result.skipped == 0
    bulk = next(row for row in nvda if row.institution == "BULK 13F CAPITAL LLC")
    assert bulk.source == "sec_13f"
    assert bulk.shares == Decimal("2000000.0000")
    assert bulk.value == Decimal("360000000.0000")
    assert bulk.rank == 1
    assert nvda[0].institution == "BULK 13F CAPITAL LLC"


async def test_13f_dataset_matches_issuer_names_without_a_cusip_map(seeded) -> None:  # type: ignore[no-untyped-def]
    async with seeded.state.db.session() as session:
        result = await load_13f_dataset(session, FIXTURES / "13f")
        nvda = await session.scalar(
            select(Holder).where(
                Holder.symbol == "NVDA", Holder.institution == "BULK 13F CAPITAL LLC"
            )
        )
    assert result.rows == 2
    assert nvda is not None


async def test_holders_read_path_returns_only_the_latest_period(client: AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    async with app.state.db.session() as session:
        session.add(
            Holder(
                symbol="NVDA",
                report_period=date(2025, 12, 31),
                institution_cik="OLD-MANAGER",
                institution="OLD MANAGER",
                shares=Decimal("1"),
                value=Decimal("1"),
                rank=1,
                source="fixtures",
            )
        )
        await session.commit()

    response = await client.get("/api/holders/NVDA")
    assert response.status_code == 200
    assert [row["institution"] for row in response.json()] == ["VANGUARD GROUP INC"]


async def test_cross_check_persists_and_logs_only_differences_above_one_percent(
    client: AsyncClient, caplog
) -> None:  # type: ignore[no-untyped-def]
    app = client._transport.app  # type: ignore[attr-defined]
    async with app.state.db.session() as session:
        primary = await session.scalar(
            select(InsiderTxn).where(InsiderTxn.accession_no == "0001-26-000001")
        )
        assert primary is not None
        tickers = await active_tickers(session)
        matching = replace(
            InsiderTxnData(
                symbol=primary.symbol,
                accession_no="secondary-accession",
                line_no=primary.line_no,
                filing_date=primary.filing_date,
                txn_date=primary.txn_date,
                insider_name=primary.insider_name,
                insider_cik=primary.insider_cik,
                officer_title=primary.officer_title,
                role=primary.role,
                txn_code=primary.txn_code,
                action=primary.action,
                shares=primary.shares * Decimal("1.20"),
                price=primary.price,
                value=(primary.value or Decimal("0")) * Decimal("1.20"),
                shares_after=primary.shares_after,
                is_10b5_1=primary.is_10b5_1,
                is_amendment=primary.is_amendment,
                source="fixture_secondary",
            )
        )
        with caplog.at_level(logging.WARNING):
            result = await cross_check_insiders(
                session,
                SecondaryProvider([matching]),
                since=date.today() - timedelta(days=7),
                tickers=tickers,
            )
        discrepancies = list(await session.scalars(select(CrossCheckDiscrepancy)))

    assert result.checked == 1
    assert result.discrepancies == 2
    assert {row.field for row in discrepancies} == {"shares", "value"}
    assert all(row.difference_pct == Decimal("20.0000") for row in discrepancies)
    assert "insider cross-check discrepancy" in caplog.text

    quality = await client.get("/api/data-quality")
    assert quality.status_code == 200
    body = quality.json()
    assert body["crossCheck"]["status"] == "ok"
    assert body["crossCheck"]["provider"] == "fixture_secondary"
    assert body["crossCheck"]["checked"] == 1
    assert body["crossCheck"]["discrepancies"] == 2
    assert len(body["discrepancies"]) == 2
    assert body["discrepancies"][0]["differencePct"] == 20.0
    assert body["bulk13f"]["status"] == "never"


async def test_cross_check_ignores_differences_at_or_below_one_percent(seeded) -> None:  # type: ignore[no-untyped-def]
    async with seeded.state.db.session() as session:
        primary = await session.scalar(
            select(InsiderTxn).where(InsiderTxn.accession_no == "0001-26-000001")
        )
        assert primary is not None
        tickers = await active_tickers(session)
        secondary = replace(
            InsiderTxnData(
                symbol=primary.symbol,
                accession_no="secondary-accession",
                line_no=primary.line_no,
                filing_date=primary.filing_date,
                txn_date=primary.txn_date,
                insider_name=primary.insider_name,
                insider_cik=primary.insider_cik,
                officer_title=primary.officer_title,
                role=primary.role,
                txn_code=primary.txn_code,
                action=primary.action,
                shares=primary.shares * Decimal("1.01"),
                price=primary.price,
                value=(primary.value or Decimal("0")) * Decimal("1.01"),
                shares_after=primary.shares_after,
                is_10b5_1=primary.is_10b5_1,
                is_amendment=primary.is_amendment,
                source="fixture_secondary",
            )
        )
        result = await cross_check_insiders(
            session,
            SecondaryProvider([secondary]),
            since=date.today() - timedelta(days=7),
            tickers=tickers,
        )
        count = len(list(await session.scalars(select(CrossCheckDiscrepancy))))
    assert result.checked == 1
    assert result.discrepancies == 0
    assert count == 0
