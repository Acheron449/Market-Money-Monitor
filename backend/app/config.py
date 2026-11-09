"""Configuration: environment variables (pydantic-settings) plus an optional YAML file."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_WATCHLIST = ("NVDA", "AAPL", "TSLA", "AMZN", "META", "AMD", "PLTR", "COIN")


class Settings(BaseSettings):
    """Environment configuration. Secrets live here and never reach the browser."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./smm.db"

    sec_user_agent: str = "Smart Money Monitor dev@example.com"
    sec_max_rps: float = 5.0

    alpaca_key_id: str = ""
    alpaca_secret_key: str = ""
    alpaca_feed: str = "iex"

    finnhub_api_key: str = ""

    admin_token: str = ""

    # ADM-03 alert channels and thresholds. Empty channels record alerts without delivery.
    alerts_enabled: bool = True
    alert_txn_threshold: Decimal = Decimal("1000000")
    alert_net_threshold: Decimal = Decimal("10000000")
    alert_webhook_url: str = ""
    alert_telegram_bot_token: str = ""
    alert_telegram_chat_id: str = ""
    alert_email_to: str = ""
    alert_email_from: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True

    # Comma separated; the YAML watchlist wins when present.
    watchlist: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    config_file: str = "smm.yaml"

    log_level: str = "INFO"
    providers_enabled: bool = True
    # Comma separated provider names dropped from every chain (AC-03 drills).
    disabled_providers: str = ""
    refresh_throttle_seconds: int = 30
    quote_stale_seconds: int = 60
    # AUT-03: SSE cadence. Polling is a store read, never a provider call.
    stream_poll_seconds: float = 1.0
    stream_heartbeat_seconds: float = 20.0
    scheduler_enabled: bool = True

    @property
    def parsed_watchlist(self) -> list[str]:
        raw = self.watchlist.strip()
        symbols = raw.split(",") if raw else list(DEFAULT_WATCHLIST)
        return [s.strip().upper() for s in symbols if s.strip()]

    @property
    def parsed_cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def parsed_disabled_providers(self) -> list[str]:
        raw = self.disabled_providers.strip()
        if not raw:
            return []
        return [name.strip().lower() for name in raw.split(",") if name.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


class Cadences(BaseModel):
    quotes_market_seconds: int = 20
    quotes_offhours_seconds: int = 900
    form4_seconds: int = 300
    form4_evening_seconds: int = 3600
    holders_seconds: int = 86400
    ticker_map_seconds: int = 604800
    health_seconds: int = 60


class RuntimeConfig(BaseModel):
    """Deployment configuration that operators may tune without redeploying code."""

    watchlist: list[str] = Field(default_factory=lambda: list(DEFAULT_WATCHLIST))
    lookback_months: int = 6
    disabled_providers: list[str] = Field(default_factory=list)
    provider_order: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "quotes": ["alpaca", "finnhub", "yfinance"],
            "bars": ["alpaca", "yfinance"],
            "insiders": ["sec_edgar", "finnhub", "yfinance"],
            "holders": ["yfinance"],
        }
    )
    cadences: Cadences = Field(default_factory=Cadences)


def _read_yaml(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def load_runtime_config(settings: Settings) -> RuntimeConfig:
    """Merge the YAML file over the defaults, falling back to the environment watchlist."""

    raw = _read_yaml(Path(settings.config_file))
    watchlist = raw.get("watchlist")
    if not isinstance(watchlist, list) or not watchlist:
        watchlist = settings.parsed_watchlist
    symbols = [str(s).strip().upper() for s in watchlist if str(s).strip()]

    lookback = raw.get("lookback_months", 6)
    lookback_months = int(lookback) if isinstance(lookback, int | str) else 6
    lookback_months = min(24, max(1, lookback_months))

    provider_order = raw.get("provider_order")
    cadences = raw.get("cadences")
    configured_disabled = raw.get("disabled_providers")
    if isinstance(configured_disabled, list):
        disabled = [str(name).strip().lower() for name in configured_disabled if str(name).strip()]
    else:
        disabled = settings.parsed_disabled_providers

    return RuntimeConfig(
        watchlist=symbols,
        lookback_months=lookback_months,
        disabled_providers=disabled,
        provider_order=provider_order if isinstance(provider_order, dict) else {},
        cadences=Cadences.model_validate(cadences) if isinstance(cadences, dict) else Cadences(),
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
