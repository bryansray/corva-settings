from __future__ import annotations

import os
from pathlib import Path
import sys
from time import time
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from corva.api import Api

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from corva_settings import SettingsService


pytestmark = pytest.mark.integration

DEFAULT_API_URL = "https://api.qa.corva.ai"
DEFAULT_DATA_API_URL = "https://data.qa.corva.ai"
REQUIRED_ENV_VARS = ["CORVA_API_KEY"]


def _env_url_or_default(var_name: str, default: str) -> str:
    value = os.getenv(var_name)
    if not value:
        return default

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return default
    if not parsed.netloc or ".." in parsed.netloc:
        return default
    return value


def _require_env(var_name: str) -> str:
    value = os.getenv(var_name)
    if not value:
        pytest.skip(f"Set {var_name} to run live integration tests.")
    return value


def _build_api() -> Api:
    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        pytest.skip(f"Set {', '.join(missing)} to run live integration tests.")

    return Api(
        api_url=_env_url_or_default("CORVA_API_URL", DEFAULT_API_URL),
        data_api_url=_env_url_or_default("CORVA_DATA_API_URL", DEFAULT_DATA_API_URL),
        api_key=_require_env("CORVA_API_KEY"),
        app_key=os.getenv("CORVA_APP_KEY", "corva.settings-integration-test"),
    )


def test_replace_settings_persists_company_scoped_document_to_dataset() -> None:
    api = _build_api()
    provider = os.getenv("CORVA_SETTINGS_TEST_PROVIDER", "corva")
    dataset = "app.settings"
    company_id = 1
    unique_app_key = f"corva-settings.integration.{uuid4()}"
    updated_by = "corva-settings-integration-test"
    run_id = str(uuid4())
    now = int(time())

    service = SettingsService(
        api,
        provider=provider,
        dataset=dataset,
        package_defaults={},
        clock=lambda: now,
    )

    expected_settings = {
        "integration_run_id": run_id,
        "nested": {"flag": True},
    }

    resolved = service.replace_settings(
        unique_app_key,
        expected_settings,
        updated_by=updated_by,
        company_id=company_id,
    )

    assert resolved == expected_settings

    results = api.get_dataset(
        provider,
        dataset,
        query={
            "app_key": unique_app_key,
            "company_id": company_id,
            "asset_id": None,
        },
        sort={"timestamp": -1},
        limit=1,
        skip=0,
    )

    assert results, (
        "Expected inserted settings document to be readable from the target dataset."
    )

    document = results[0]
    assert document["app_key"] == unique_app_key
    assert document["company_id"] == company_id
    assert document["asset_id"] is None
    assert document["timestamp"] == now
    assert document["data"]["settings"] == expected_settings
    assert document["data"]["updated_by"] == updated_by
    assert document["data"]["updated_at"] == now
    assert document["data"]["history"] == []
