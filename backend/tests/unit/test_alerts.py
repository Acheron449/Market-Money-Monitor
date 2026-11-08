"""ADM-03 unit coverage: triggers, dedupe and delivery channels."""

from __future__ import annotations

import json
import smtplib
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select

from app.config import Settings
from app.db.models import AlertEvent
from app.providers.base import InsiderTxnData
from app.services.alerts import (
    Alert,
    EmailSender,
    TelegramSender,
    WebhookSender,
    build_ingest_alerts,
    build_senders,
    dispatch_alerts,
)
from app.services.signals import SignalResult

AS_OF = date(2026, 11, 8)


def txn(
    *,
    action: str = "buy",
    role: str = "CEO",
    value: str | None = "100000",
    symbol: str = "NVDA",
    accession: str = "0001-26-000001",
    line: int = 1,
) -> InsiderTxnData:
    return InsiderTxnData(
        symbol=symbol,
        accession_no=accession,
        line_no=line,
        filing_date=AS_OF,
        txn_date=AS_OF,
        insider_name="TEST INSIDER",
        insider_cik="123456",
        officer_title=None,
        role=role,
        txn_code="P" if action == "buy" else "S",
        action=action,
        shares=Decimal("100"),
        price=Decimal("100"),
        value=Decimal(value) if value is not None else None,
        shares_after=None,
        is_10b5_1=False,
        is_amendment=False,
        source="tests",
    )


def signal(net: str = "0", *, cluster: bool = False) -> SignalResult:
    return SignalResult(
        net_value=Decimal(net),
        buy_value=Decimal("0"),
        sell_value=Decimal("0"),
        txn_count=0,
        starred_count=0,
        cluster_buy=cluster,
    )


def test_ceo_buy_and_large_transaction_are_separate_triggers() -> None:
    alerts = build_ingest_alerts(
        [txn(value="2000000")],
        previous_net={},
        current={"NVDA": signal("2000000")},
        as_of=AS_OF,
    )
    assert {alert.kind for alert in alerts} == {"ceo_cfo_buy", "large_transaction"}
    assert all("TEST INSIDER" in alert.body for alert in alerts)


def test_threshold_is_strict_and_non_open_market_rows_do_not_alert() -> None:
    threshold = build_ingest_alerts(
        [txn(role="Director", value="1000000")],
        previous_net={},
        current={"NVDA": signal("1000000")},
        as_of=AS_OF,
    )
    assert threshold == []

    award = build_ingest_alerts(
        [txn(action="other", role="CEO", value="9999999")],
        previous_net={},
        current={"NVDA": signal("0")},
        as_of=AS_OF,
    )
    assert award == []


def test_cluster_alert_requires_new_buy_and_cluster_signal() -> None:
    alerts = build_ingest_alerts(
        [txn(role="Director")],
        previous_net={},
        current={"NVDA": signal(cluster=True)},
        as_of=AS_OF,
    )
    assert [alert.kind for alert in alerts] == ["cluster_buy"]

    no_buy = build_ingest_alerts(
        [txn(action="sell", role="Director")],
        previous_net={},
        current={"NVDA": signal(cluster=True)},
        as_of=AS_OF,
    )
    assert no_buy == []


def test_net_crossing_detects_both_directions_and_needs_previous_snapshot() -> None:
    up = build_ingest_alerts(
        [],
        previous_net={"NVDA": Decimal("9000000")},
        current={"NVDA": signal("11000000")},
        as_of=AS_OF,
    )
    assert [alert.kind for alert in up] == ["net_crossing"]
    assert "+$10,000,000" in up[0].title

    down = build_ingest_alerts(
        [],
        previous_net={"NVDA": Decimal("-9000000")},
        current={"NVDA": signal("-11000000")},
        as_of=AS_OF,
    )
    assert [alert.kind for alert in down] == ["net_crossing"]
    assert "-$10,000,000" in down[0].title

    already_above = build_ingest_alerts(
        [],
        previous_net={"NVDA": Decimal("11000000")},
        current={"NVDA": signal("12000000")},
        as_of=AS_OF,
    )
    assert already_above == []

    first_run = build_ingest_alerts(
        [],
        previous_net={},
        current={"NVDA": signal("12000000")},
        as_of=AS_OF,
    )
    assert first_run == []


class RecordingSender:
    name = "recording"

    def __init__(self) -> None:
        self.sent: list[Alert] = []

    async def send(self, alert: Alert) -> None:
        self.sent.append(alert)


class FailingSender:
    name = "failing"

    async def send(self, alert: Alert) -> None:
        raise RuntimeError("transport down")


async def test_dispatch_persists_once_and_sends_once(seeded: Any, settings: Settings) -> None:
    sender = RecordingSender()
    alert = Alert(
        kind="ceo_cfo_buy",
        symbol="NVDA",
        title="CEO/CFO open-market buy: NVDA",
        body="body",
        dedupe_key="ceo_cfo_buy:test:1",
    )

    async with seeded.state.db.session() as session:
        first = await dispatch_alerts(session, settings, [alert], senders=[sender])
        second = await dispatch_alerts(session, settings, [alert], senders=[sender])
        rows = list(await session.scalars(select(AlertEvent)))

    assert len(first) == 1
    assert second == []
    assert len(rows) == 1
    assert rows[0].status == "delivered"
    assert rows[0].channels == "recording"
    assert len(sender.sent) == 1


async def test_dispatch_records_failed_delivery_without_raising(
    seeded: Any, settings: Settings
) -> None:
    alert = Alert(
        kind="large_transaction",
        symbol="NVDA",
        title="Large insider transaction: NVDA",
        body="body",
        dedupe_key="large_transaction:test:1",
    )

    async with seeded.state.db.session() as session:
        events = await dispatch_alerts(session, settings, [alert], senders=[FailingSender()])
        rows = list(await session.scalars(select(AlertEvent)))

    assert len(events) == 1
    assert rows[0].status == "failed"
    assert rows[0].channels == ""


def test_build_senders_only_builds_configured_channels() -> None:
    configured = Settings(
        alert_webhook_url="https://example.test/hook",
        alert_telegram_bot_token="token",
        alert_telegram_chat_id="chat",
        smtp_host="smtp.example.test",
        alert_email_to="to@example.test",
        alert_email_from="from@example.test",
    )
    assert [sender.name for sender in build_senders(configured)] == [
        "webhook",
        "telegram",
        "email",
    ]

    disabled = Settings(
        alerts_enabled=False,
        alert_webhook_url="https://example.test/hook",
    )
    assert build_senders(disabled) == []


async def test_webhook_and_telegram_payloads() -> None:
    alert = Alert(
        kind="net_crossing",
        symbol="NVDA",
        title="Net signal crossed +$10,000,000: NVDA",
        body="body",
        dedupe_key="net_crossing:test",
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await WebhookSender("https://example.test/hook", client=client).send(alert)
        await TelegramSender("secret", "chat-1", client=client).send(alert)

    webhook, telegram = requests
    assert json.loads(webhook.content) == {
        "kind": "net_crossing",
        "symbol": "NVDA",
        "title": "Net signal crossed +$10,000,000: NVDA",
        "body": "body",
        "dedupeKey": "net_crossing:test",
    }
    assert str(webhook.url) == "https://example.test/hook"
    assert str(telegram.url).endswith("/botsecret/sendMessage")
    assert json.loads(telegram.content) == {
        "chat_id": "chat-1",
        "text": "Net signal crossed +$10,000,000: NVDA\n\nbody",
    }


async def test_email_sender_builds_a_message(monkeypatch: Any) -> None:
    sent: list[Any] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self) -> FakeSMTP:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def starttls(self) -> None:
            return None

        def login(self, username: str, password: str) -> None:
            return None

        def send_message(self, message: Any) -> None:
            sent.append(message)

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    sender = EmailSender(
        host="smtp.example.test",
        port=587,
        to="to@example.test",
        from_addr="from@example.test",
        username="user",
        password="password",
    )
    await sender.send(
        Alert(
            kind="cluster_buy",
            symbol="NVDA",
            title="Cluster buy: NVDA",
            body="body",
            dedupe_key="cluster_buy:test",
        )
    )

    assert len(sent) == 1
    assert sent[0]["Subject"] == "[Smart Money Monitor] Cluster buy: NVDA"
    assert sent[0]["To"] == "to@example.test"
    assert sent[0].get_content().strip() == "body"
