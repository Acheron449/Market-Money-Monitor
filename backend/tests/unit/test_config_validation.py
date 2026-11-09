from pathlib import Path

import pytest

from app.config import ProductionConfigError, Settings, validate_settings


def test_development_defaults_are_accepted() -> None:
    validate_settings(Settings())


def test_production_rejects_the_dev_contact_and_missing_token() -> None:
    with pytest.raises(ProductionConfigError) as excinfo:
        validate_settings(Settings(environment="production"))

    message = str(excinfo.value)
    assert "SEC_USER_AGENT" in message
    assert "ADMIN_TOKEN" in message


def test_production_accepts_a_complete_configuration() -> None:
    validate_settings(
        Settings(
            environment="production",
            sec_user_agent="Smart Money Monitor ops@smart-money.example",
            admin_token="a-long-random-token",
            cors_origins="https://monitor.smart-money.example",
        )
    )


def test_production_rejects_a_wildcard_cors_origin() -> None:
    with pytest.raises(ProductionConfigError, match="CORS_ORIGINS"):
        validate_settings(
            Settings(
                environment="production",
                sec_user_agent="Smart Money Monitor ops@smart-money.example",
                admin_token="a-long-random-token",
                cors_origins="*",
            )
        )


def test_config_file_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = tmp_path / "smm.yaml"
    config.write_text("lookback_months: 3\n", encoding="utf-8")
    monkeypatch.setenv("CONFIG_FILE", str(config))

    assert Settings(_env_file=None).config_file == str(config)
