"""ADM-03 alerts: trigger evaluation, persisted history and delivery channels."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from email.message import EmailMessage
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import AlertEvent
from app.providers.base import InsiderTxnData
from app.services.signals import SignalResult

LOGGER = logging.getLogger(__name__)
ZERO = Decimal("0")
DEFAULT_TXN_THRESHOLD = Decimal("1000000")
DEFAULT_NET_THRESHOLD = Decimal("10000000")


@dataclass(frozen=True, slots=True)
class Alert:
    """A deduplicated notification candidate."""

    kind: str
    symbol: str
    title: str
    body: str
    dedupe_key: str


class AlertSender(Protocol):
    name: str

    async def send(self, alert: Alert) -> None: ...


class WebhookSender:
    name = "webhook"

    def __init__(self, url: str, *, client: httpx.AsyncClient | None = None) -> None:
        self.url = url
        self._client = client

    async def send(self, alert: Alert) -> None:
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.post(self.url, json=_payload(alert))
            response.raise_for_status()
        finally:
            if self._client is None:
                await client.aclose()


class TelegramSender:
    name = "telegram"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self.chat_id = chat_id
        self._client = client

    async def send(self, alert: Alert) -> None:
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.post(
                self.url,
                json={"chat_id": self.chat_id, "text": f"{alert.title}\n\n{alert.body}"},
            )
            response.raise_for_status()
        finally:
            if self._client is None:
                await client.aclose()


class EmailSender:
    name = "email"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        to: str,
        from_addr: str,
        username: str = "",
        password: str = "",
        starttls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.to = [address.strip() for address in to.split(",") if address.strip()]
        self.from_addr = from_addr
        self.username = username
        self.password = password
        self.starttls = starttls

    async def send(self, alert: Alert) -> None:
        await asyncio.to_thread(self._send, alert)

    def _send(self, alert: Alert) -> None:
        message = EmailMessage()
        message["Subject"] = f"[Smart Money Monitor] {alert.title}"
        message["From"] = self.from_addr
        message["To"] = ", ".join(self.to)
        message.set_content(alert.body)

        with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
            if self.starttls:
                smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(message)


def build_senders(settings: Settings) -> list[AlertSender]:
    """Build only the channels the operator configured; empty means record-only."""

    if not settings.alerts_enabled:
        return []
    senders: list[AlertSender] = []
    if settings.alert_webhook_url:
        senders.append(WebhookSender(settings.alert_webhook_url))
    if settings.alert_telegram_bot_token and settings.alert_telegram_chat_id:
        senders.append(
            TelegramSender(
                settings.alert_telegram_bot_token,
                settings.alert_telegram_chat_id,
            )
        )
    if settings.smtp_host and settings.alert_email_to and settings.alert_email_from:
        senders.append(
            EmailSender(
                host=settings.smtp_host,
                port=settings.smtp_port,
                to=settings.alert_email_to,
                from_addr=settings.alert_email_from,
                username=settings.smtp_username,
                password=settings.smtp_password,
                starttls=settings.smtp_starttls,
            )
        )
    return senders


def build_ingest_alerts(
    new_rows: Sequence[InsiderTxnData],
    *,
    previous_net: Mapping[str, Decimal],
    current: Mapping[str, SignalResult],
    as_of: date,
    txn_threshold: Decimal = DEFAULT_TXN_THRESHOLD,
    net_threshold: Decimal = DEFAULT_NET_THRESHOLD,
) -> list[Alert]:
    """Evaluate the four ADM-03 triggers against rows added by this ingestion."""

    alerts: list[Alert] = []
    seen: set[str] = set()

    def add(alert: Alert) -> None:
        if alert.dedupe_key not in seen:
            seen.add(alert.dedupe_key)
            alerts.append(alert)

    for row in new_rows:
        if row.action not in {"buy", "sell"}:
            continue
        base = f"{row.accession_no}:{row.line_no}"
        if row.action == "buy" and row.role in {"CEO", "CFO"}:
            add(
                Alert(
                    kind="ceo_cfo_buy",
                    symbol=row.symbol,
                    title=f"CEO/CFO open-market buy: {row.symbol}",
                    body=_transaction_body(row),
                    dedupe_key=f"ceo_cfo_buy:{base}",
                )
            )
        if row.value is not None and row.value > txn_threshold:
            add(
                Alert(
                    kind="large_transaction",
                    symbol=row.symbol,
                    title=f"Large insider transaction: {row.symbol}",
                    body=_transaction_body(row),
                    dedupe_key=f"large_transaction:{base}",
                )
            )

    buy_symbols = sorted({row.symbol for row in new_rows if row.action == "buy"})
    for symbol in buy_symbols:
        result = current.get(symbol)
        if result is None or not result.cluster_buy:
            continue
        add(
            Alert(
                kind="cluster_buy",
                symbol=symbol,
                title=f"Cluster buy: {symbol}",
                body=(
                    f"Three or more distinct insiders bought {symbol} within 14 days. "
                    "The current signal is flagged as a cluster buy."
                ),
                dedupe_key=f"cluster_buy:{symbol}:{as_of.isoformat()}",
            )
        )

    for symbol, result in sorted(current.items()):
        previous = previous_net.get(symbol)
        if previous is None:
            continue
        if previous <= net_threshold < result.net_value:
            add(
                Alert(
                    kind="net_crossing",
                    symbol=symbol,
                    title=f"Net signal crossed +{_money(net_threshold)}: {symbol}",
                    body=(
                        f"{symbol} net signal crossed above +{_money(net_threshold)}: "
                        f"{_signed_money(previous)} → {_signed_money(result.net_value)}."
                    ),
                    dedupe_key=f"net_crossing:{symbol}:up:{as_of.isoformat()}",
                )
            )
        elif previous >= -net_threshold > result.net_value:
            add(
                Alert(
                    kind="net_crossing",
                    symbol=symbol,
                    title=f"Net signal crossed -{_money(net_threshold)}: {symbol}",
                    body=(
                        f"{symbol} net signal crossed below -{_money(net_threshold)}: "
                        f"{_signed_money(previous)} → {_signed_money(result.net_value)}."
                    ),
                    dedupe_key=f"net_crossing:{symbol}:down:{as_of.isoformat()}",
                )
            )

    return alerts


async def emit_ingest_alerts(
    session: AsyncSession,
    settings: Settings,
    *,
    new_rows: Sequence[InsiderTxnData],
    previous_net: Mapping[str, Decimal],
    current: Mapping[str, SignalResult],
    as_of: date,
    senders: Sequence[AlertSender] | None = None,
) -> list[AlertEvent]:
    """Evaluate and persist alerts after an insider ingest, then deliver them."""

    candidates = build_ingest_alerts(
        new_rows,
        previous_net=previous_net,
        current=current,
        as_of=as_of,
        txn_threshold=settings.alert_txn_threshold,
        net_threshold=settings.alert_net_threshold,
    )
    return await dispatch_alerts(session, settings, candidates, senders=senders)


async def dispatch_alerts(
    session: AsyncSession,
    settings: Settings,
    alerts: Sequence[Alert],
    *,
    senders: Sequence[AlertSender] | None = None,
) -> list[AlertEvent]:
    """Persist new candidates once, then deliver them without failing the job."""

    if not alerts:
        return []

    unique: dict[str, Alert] = {alert.dedupe_key: alert for alert in alerts}
    existing = set(
        await session.scalars(
            select(AlertEvent.dedupe_key).where(AlertEvent.dedupe_key.in_(unique))
        )
    )
    pending = [alert for key, alert in unique.items() if key not in existing]
    if not pending:
        return []

    events: dict[str, AlertEvent] = {}
    for alert in pending:
        event = AlertEvent(
            dedupe_key=alert.dedupe_key,
            kind=alert.kind,
            symbol=alert.symbol,
            title=alert.title,
            body=alert.body,
            channels="",
            status="recorded",
        )
        session.add(event)
        events[alert.dedupe_key] = event
    await session.commit()

    configured = list(senders) if senders is not None else build_senders(settings)
    if configured:
        for alert in pending:
            event = events[alert.dedupe_key]
            delivered: list[str] = []
            failures = 0
            for sender in configured:
                try:
                    await sender.send(alert)
                except Exception as exc:  # delivery failures must not fail ingestion
                    failures += 1
                    LOGGER.warning(
                        "alert delivery failed",
                        extra={
                            "channel": sender.name,
                            "kind": alert.kind,
                            "symbol": alert.symbol,
                            "error": type(exc).__name__,
                        },
                    )
                    continue
                delivered.append(sender.name)
            event.channels = ",".join(delivered)
            if failures == 0:
                event.status = "delivered"
            elif delivered:
                event.status = "partial"
            else:
                event.status = "failed"
        await session.commit()

    return [events[alert.dedupe_key] for alert in pending]


def _payload(alert: Alert) -> dict[str, str]:
    return {
        "kind": alert.kind,
        "symbol": alert.symbol,
        "title": alert.title,
        "body": alert.body,
        "dedupeKey": alert.dedupe_key,
    }


def _transaction_body(row: InsiderTxnData) -> str:
    verb = "bought" if row.action == "buy" else "sold"
    return (
        f"{row.insider_name} ({row.role}) {verb} {row.shares:,.0f} shares of "
        f"{row.symbol} on {row.txn_date.isoformat()} for {_money(row.value)}."
    )


def _money(value: Decimal | None) -> str:
    if value is None:
        return "an unreported value"
    return f"${value:,.0f}"


def _signed_money(value: Decimal) -> str:
    if value > ZERO:
        return f"+${value:,.0f}"
    if value < ZERO:
        return f"-${abs(value):,.0f}"
    return "$0"
