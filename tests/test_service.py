from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from corva_settings import SettingsScope, SettingsService


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return deepcopy(self.payload)


class FakeApiClient:
    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []
        self.assets: dict[int, dict[str, Any]] = {}

    def get_dataset(
        self,
        provider: str,
        dataset: str,
        *,
        query: dict[str, Any],
        sort: dict[str, int],
        limit: int,
        skip: int = 0,
        fields: str | None = None,
    ) -> list[dict[str, Any]]:
        matching = [
            deepcopy(document)
            for document in self.documents
            if all(document.get(key) == value for key, value in query.items())
        ]
        matching.sort(key=lambda item: item["timestamp"], reverse=sort.get("timestamp", -1) < 0)
        return matching[skip : skip + limit]

    def insert_data(
        self,
        provider: str,
        dataset: str,
        data: list[dict[str, Any]],
        *,
        produce: bool = False,
    ) -> dict[str, Any]:
        for record in data:
            stored = deepcopy(record)
            stored["_id"] = f"doc-{len(self.documents) + 1}"
            self.documents.append(stored)
        return {"inserted_count": len(data)}

    def get(self, path: str, **kwargs: Any) -> FakeResponse:
        if path.startswith("/v2/assets/"):
            asset_id = int(path.split("/v2/assets/")[1].split("?")[0].strip("/"))
            if asset_id in self.assets:
                asset = deepcopy(self.assets[asset_id])
                payload = {
                    "data": {
                        "attributes": asset,
                        "relationships": {
                            "company": {"data": {"id": str(asset["company_id"]), "type": "company"}},
                        },
                    },
                    "included": [
                        {
                            "id": str(asset["company_id"]),
                            "type": "company",
                            "attributes": {"id": asset["company_id"]},
                        }
                    ],
                }
                return FakeResponse(payload)
        raise KeyError(f"Unhandled GET path: {path}")


def seed_document(
    api_client: FakeApiClient,
    *,
    app_key: str,
    settings: dict[str, Any],
    updated_at: int,
    company_id: int | None,
    asset_id: int | None,
    updated_by: str = "seed@corva.ai",
) -> None:
    api_client.documents.append(
        {
            "_id": f"seed-{len(api_client.documents) + 1}",
            "app_key": app_key,
            "company_id": company_id,
            "asset_id": asset_id,
            "data": {
                "settings": deepcopy(settings),
                "updated_by": updated_by,
                "updated_at": updated_at,
                "deleted": False,
                "history": [],
            },
            "timestamp": updated_at,
        }
    )


@pytest.fixture
def api_client() -> FakeApiClient:
    client = FakeApiClient()
    client.assets[100] = {"id": 100, "company_id": 3, "parent_asset_id": None, "type": "Asset::Program"}
    client.assets[10] = {"id": 10, "company_id": 3, "parent_asset_id": 100, "type": "Asset::Rig"}
    client.assets[1] = {"id": 1, "company_id": 3, "parent_asset_id": 10, "type": "Asset::Well"}
    return client


@pytest.fixture
def service(api_client: FakeApiClient) -> SettingsService:
    clock_values = iter([100, 200, 300, 400, 500, 600, 700, 800, 900, 1000])
    return SettingsService(
        api_client,
        dataset="app.settings",
        package_defaults={
            "corva.dysfunction_detection": {
                "a": "package",
                "nested": {"package_only": True, "shared": "package"},
            }
        },
        clock=lambda: next(clock_values),
    )


def test_get_settings_merges_package_company_and_asset_ancestry(
    service: SettingsService, api_client: FakeApiClient
) -> None:
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=None,
        settings={"nested": {"shared": "company"}, "company_only": True},
        updated_at=20,
    )
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=100,
        settings={"nested": {"program_only": True}, "program_only": True},
        updated_at=30,
    )
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=10,
        settings={"nested": {"rig_only": True}, "rig_only": True},
        updated_at=40,
    )
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=1,
        settings={"a": "asset", "asset_only": True},
        updated_at=50,
    )

    settings = service.get_settings("corva.dysfunction_detection", asset_id=1)

    assert settings == {
        "a": "asset",
        "nested": {
            "package_only": True,
            "shared": "company",
            "program_only": True,
            "rig_only": True,
        },
        "company_only": True,
        "program_only": True,
        "rig_only": True,
        "asset_only": True,
    }


def test_get_settings_resolves_all_ancestor_assets_for_requested_asset(
    service: SettingsService, api_client: FakeApiClient
) -> None:
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=100,
        settings={"program_only": "program"},
        updated_at=30,
    )
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=10,
        settings={"rig_only": "rig"},
        updated_at=40,
    )

    settings = service.get_settings("corva.dysfunction_detection", asset_id=1)

    assert settings["program_only"] == "program"
    assert settings["rig_only"] == "rig"


def test_get_settings_reads_company_scope_without_asset_hierarchy(
    service: SettingsService, api_client: FakeApiClient
) -> None:
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=None,
        settings={"company_only": True},
        updated_at=30,
    )

    settings = service.get_settings("corva.dysfunction_detection", company_id=3)

    assert settings["company_only"] is True


def test_patch_settings_creates_scope_document_and_merges_effective_value(
    service: SettingsService, api_client: FakeApiClient
) -> None:
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=None,
        settings={"nested": {"threshold": 10}},
        updated_at=10,
    )

    settings = service.patch_settings(
        "corva.dysfunction_detection",
        {"nested.threshold": 25, "new_flag": True},
        updated_by="user@corva.ai",
        asset_id=1,
    )

    assert settings["nested"]["threshold"] == 25
    assert settings["new_flag"] is True

    asset_documents = [doc for doc in api_client.documents if doc["asset_id"] == 1]
    assert len(asset_documents) == 1
    assert asset_documents[0]["data"]["settings"]["nested"]["threshold"] == 25


def test_delete_keys_reverts_to_inherited_value(service: SettingsService, api_client: FakeApiClient) -> None:
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=None,
        settings={"a": "company", "nested": {"value": 10}},
        updated_at=10,
    )
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=1,
        settings={"a": "asset", "nested": {"value": 99}},
        updated_at=20,
    )

    settings = service.delete_keys(
        "corva.dysfunction_detection",
        ["a", "nested.value"],
        updated_by="user@corva.ai",
        asset_id=1,
    )

    assert settings["a"] == "company"
    assert settings["nested"]["value"] == 10


def test_replace_settings_appends_full_prior_snapshot_to_history(
    service: SettingsService, api_client: FakeApiClient
) -> None:
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=None,
        settings={"a": "old"},
        updated_at=10,
        updated_by="old@corva.ai",
    )

    service.replace_settings(
        "corva.dysfunction_detection",
        {"a": "new"},
        updated_by="new@corva.ai",
        company_id=3,
    )

    latest_company_document = max(
        (
            doc
            for doc in api_client.documents
            if doc["company_id"] == 3 and doc["asset_id"] is None
        ),
        key=lambda item: item["timestamp"],
    )
    assert latest_company_document["data"]["history"] == [
        {
            "settings": {"a": "old"},
            "updated_by": "old@corva.ai",
            "updated_at": 10,
        }
    ]


def test_replace_settings_rejects_unscoped_write(service: SettingsService) -> None:
    with pytest.raises(ValueError, match="must target a company or asset scope"):
        service.replace_settings(
            "corva.dysfunction_detection",
            {"a": "new"},
            updated_by="new@corva.ai",
        )


def test_list_scopes_returns_existing_resolution_chain(
    service: SettingsService, api_client: FakeApiClient
) -> None:
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=None,
        settings={"company_only": True},
        updated_at=10,
    )
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=10,
        settings={"rig_only": True},
        updated_at=20,
    )
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=1,
        settings={"asset_only": True},
        updated_at=30,
    )

    scopes = service.list_scopes("corva.dysfunction_detection", asset_id=1)

    assert scopes == [
        SettingsScope("corva.dysfunction_detection", company_id=3, asset_id=None),
        SettingsScope("corva.dysfunction_detection", company_id=3, asset_id=10),
        SettingsScope("corva.dysfunction_detection", company_id=3, asset_id=1),
    ]


def test_clear_settings_preserves_scope_and_reverts_to_inherited_values(
    service: SettingsService, api_client: FakeApiClient
) -> None:
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=None,
        settings={"a": "company", "nested": {"value": 10}},
        updated_at=10,
    )
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=1,
        settings={"a": "asset", "nested": {"value": 99}},
        updated_at=20,
    )

    settings = service.clear_settings(
        "corva.dysfunction_detection",
        updated_by="user@corva.ai",
        asset_id=1,
    )

    assert settings["a"] == "company"
    assert settings["nested"]["value"] == 10

    latest_asset_document = max(
        (doc for doc in api_client.documents if doc["company_id"] == 3 and doc["asset_id"] == 1),
        key=lambda item: item["timestamp"],
    )
    assert latest_asset_document["data"]["settings"] == {}
    assert latest_asset_document["data"]["deleted"] is False

    scopes = service.list_scopes("corva.dysfunction_detection", asset_id=1)
    assert scopes[-1] == SettingsScope("corva.dysfunction_detection", company_id=3, asset_id=1)


def test_delete_scope_hides_deleted_scope_without_revealing_prior_version(
    service: SettingsService, api_client: FakeApiClient
) -> None:
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=None,
        settings={"a": "company"},
        updated_at=10,
    )
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        asset_id=1,
        settings={"a": "asset"},
        updated_at=20,
    )

    settings = service.delete_scope(
        "corva.dysfunction_detection",
        updated_by="user@corva.ai",
        asset_id=1,
    )

    assert settings["a"] == "company"

    latest_asset_document = max(
        (doc for doc in api_client.documents if doc["company_id"] == 3 and doc["asset_id"] == 1),
        key=lambda item: item["timestamp"],
    )
    assert latest_asset_document["data"]["settings"] == {}
    assert latest_asset_document["data"]["deleted"] is True

    current_asset_settings = service.get_settings("corva.dysfunction_detection", asset_id=1)
    assert current_asset_settings["a"] == "company"
    assert service.list_scopes("corva.dysfunction_detection", asset_id=1) == [
        SettingsScope("corva.dysfunction_detection", company_id=3, asset_id=None)
    ]
