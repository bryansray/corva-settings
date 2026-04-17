from __future__ import annotations

import os
import sys
from pathlib import Path
from time import time
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from corva.api import Api

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from corva_settings import SettingsService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_CORVA_INTEGRATION_TESTS") != "1",
        reason="Set RUN_CORVA_INTEGRATION_TESTS=1 to run live integration tests.",
    ),
]

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


def _test_company_id() -> int:
    return int(os.getenv("CORVA_SETTINGS_TEST_COMPANY_ID", "1"))


def _test_dataset() -> str:
    return os.getenv("CORVA_SETTINGS_TEST_DATASET", "app.settings")


def _test_provider() -> str:
    return os.getenv("CORVA_SETTINGS_TEST_PROVIDER", "corva")


def _fetch_latest_scope_document(
    api: Api,
    *,
    provider: str,
    dataset: str,
    app_key: str,
    company_id: int,
    asset_id: int | None = None,
) -> dict[str, Any]:
    results = api.get_dataset(
        provider,
        dataset,
        query={
            "app_key": app_key,
            "company_id": company_id,
            "asset_id": asset_id,
        },
        sort={"timestamp": -1},
        limit=1,
        skip=0,
    )
    assert results, "Expected a settings document to be readable from the target dataset."
    document = results[0]
    assert isinstance(document, dict)
    return document


def test_replace_settings_persists_company_scoped_document_to_dataset() -> None:
    api = _build_api()
    provider = _test_provider()
    dataset = _test_dataset()
    company_id = _test_company_id()
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

    document = _fetch_latest_scope_document(
        api,
        provider=provider,
        dataset=dataset,
        app_key=unique_app_key,
        company_id=company_id,
    )
    assert document["app_key"] == unique_app_key
    assert document["company_id"] == company_id
    assert document["asset_id"] is None
    assert document["timestamp"] == now
    assert document["data"]["settings"] == expected_settings
    assert document["data"]["updated_by"] == updated_by
    assert document["data"]["updated_at"] == now
    assert document["data"]["deleted"] is False
    assert document["data"]["history"] == []


def test_get_settings_reads_company_scoped_default_settings() -> None:
    api = _build_api()
    provider = _test_provider()
    dataset = _test_dataset()
    company_id = _test_company_id()
    unique_app_key = f"corva-settings.integration.{uuid4()}"
    updated_by = "corva-settings-integration-test"
    now = int(time())

    service = SettingsService(
        api,
        provider=provider,
        dataset=dataset,
        package_defaults={},
        clock=lambda: now,
    )

    company_default_settings = {
        "baseline_enabled": True,
        "alerts": {"threshold": 12},
    }

    service.replace_settings(
        unique_app_key,
        company_default_settings,
        updated_by=updated_by,
        company_id=company_id,
    )

    resolved = service.get_settings(unique_app_key, company_id=company_id)

    assert resolved == company_default_settings

    document = _fetch_latest_scope_document(
        api,
        provider=provider,
        dataset=dataset,
        app_key=unique_app_key,
        company_id=company_id,
    )
    assert document["data"]["settings"] == company_default_settings
    assert document["asset_id"] is None
    assert document["data"]["deleted"] is False


def test_clear_settings_persists_empty_active_scope_document() -> None:
    api = _build_api()
    provider = _test_provider()
    dataset = _test_dataset()
    company_id = _test_company_id()
    unique_app_key = f"corva-settings.integration.{uuid4()}"
    updated_by = "corva-settings-integration-test"
    initial_timestamp = int(time())
    cleared_timestamp = initial_timestamp + 1

    service = SettingsService(
        api,
        provider=provider,
        dataset=dataset,
        package_defaults={unique_app_key: {"default_flag": True}},
        clock=lambda: initial_timestamp,
    )

    initial_settings = {
        "integration_run_id": str(uuid4()),
        "nested": {"flag": True},
    }

    service.replace_settings(
        unique_app_key,
        initial_settings,
        updated_by=updated_by,
        company_id=company_id,
    )

    service.clock = lambda: cleared_timestamp
    cleared = service.clear_settings(
        unique_app_key,
        updated_by=updated_by,
        company_id=company_id,
    )

    assert cleared == {"default_flag": True}

    document = _fetch_latest_scope_document(
        api,
        provider=provider,
        dataset=dataset,
        app_key=unique_app_key,
        company_id=company_id,
    )
    assert document["timestamp"] == cleared_timestamp
    assert document["data"]["settings"] == {}
    assert document["data"]["deleted"] is False
    assert document["data"]["updated_by"] == updated_by
    assert document["data"]["updated_at"] == cleared_timestamp
    assert document["data"]["history"] == [
        {
            "settings": initial_settings,
            "updated_by": updated_by,
            "updated_at": initial_timestamp,
        }
    ]


def test_delete_scope_persists_tombstone_document() -> None:
    api = _build_api()
    provider = _test_provider()
    dataset = _test_dataset()
    company_id = _test_company_id()
    unique_app_key = f"corva-settings.integration.{uuid4()}"
    updated_by = "corva-settings-integration-test"
    initial_timestamp = int(time())
    deleted_timestamp = initial_timestamp + 1

    service = SettingsService(
        api,
        provider=provider,
        dataset=dataset,
        package_defaults={unique_app_key: {"default_flag": True}},
        clock=lambda: initial_timestamp,
    )

    initial_settings = {
        "integration_run_id": str(uuid4()),
        "nested": {"flag": True},
    }

    service.replace_settings(
        unique_app_key,
        initial_settings,
        updated_by=updated_by,
        company_id=company_id,
    )

    service.clock = lambda: deleted_timestamp
    deleted = service.delete_scope(
        unique_app_key,
        updated_by=updated_by,
        company_id=company_id,
    )

    assert deleted == {"default_flag": True}

    document = _fetch_latest_scope_document(
        api,
        provider=provider,
        dataset=dataset,
        app_key=unique_app_key,
        company_id=company_id,
    )
    assert document["timestamp"] == deleted_timestamp
    assert document["data"]["settings"] == {}
    assert document["data"]["deleted"] is True
    assert document["data"]["updated_by"] == updated_by
    assert document["data"]["updated_at"] == deleted_timestamp
    assert document["data"]["history"] == [
        {
            "settings": initial_settings,
            "updated_by": updated_by,
            "updated_at": initial_timestamp,
        }
    ]
