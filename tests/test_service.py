from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from corva_settings import SettingsService


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
        self.rigs: dict[int, dict[str, Any]] = {}

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
                            "rig": (
                                {"data": {"id": str(asset["rig_id"]), "type": "rig"}}
                                if asset.get("rig_id") is not None
                                else {"data": None}
                            ),
                        },
                    },
                    "included": [],
                }
                if asset.get("rig_id") is not None and asset["rig_id"] in self.rigs:
                    payload["included"].append(
                        {
                            "id": str(asset["rig_id"]),
                            "type": "rig",
                            "attributes": deepcopy(self.rigs[asset["rig_id"]]),
                        }
                    )
                payload["included"].append(
                    {
                        "id": str(asset["company_id"]),
                        "type": "company",
                        "attributes": {"id": asset["company_id"]},
                    }
                )
                return FakeResponse(payload)
        if path.startswith("/v2/rigs/"):
            rig_id = int(path.split("/v2/rigs/")[1].split("?")[0].strip("/"))
            if rig_id in self.rigs:
                rig = deepcopy(self.rigs[rig_id])
                payload = {
                    "data": {
                        "attributes": rig,
                        "relationships": {
                            "company": {"data": {"id": str(rig["company_id"]), "type": "company"}},
                        },
                    },
                    "included": [
                        {
                            "id": str(rig["company_id"]),
                            "type": "company",
                            "attributes": {"id": rig["company_id"]},
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
    rig_id: int | None,
    asset_id: int | None,
    updated_by: str = "seed@corva.ai",
) -> None:
    api_client.documents.append(
        {
            "_id": f"seed-{len(api_client.documents) + 1}",
            "app_key": app_key,
            "company_id": company_id,
            "rig_id": rig_id,
            "asset_id": asset_id,
            "data": {
                "settings": deepcopy(settings),
                "updated_by": updated_by,
                "updated_at": updated_at,
                "history": [],
            },
            "timestamp": updated_at,
        }
    )


@pytest.fixture
def api_client() -> FakeApiClient:
    client = FakeApiClient()
    client.rigs[10] = {"id": 10, "company_id": 3}
    client.assets[1] = {"id": 1, "company_id": 3, "rig_id": 10, "parent_asset_id": 99}
    return client


@pytest.fixture
def service(api_client: FakeApiClient) -> SettingsService:
    clock_values = iter([100, 200, 300, 400, 500, 600])
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


def test_get_settings_merges_package_remote_company_rig_asset(
    service: SettingsService, api_client: FakeApiClient
) -> None:
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=None,
        rig_id=None,
        asset_id=None,
        settings={"a": "remote", "nested": {"shared": "remote", "remote_only": True}},
        updated_at=10,
    )
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        rig_id=None,
        asset_id=None,
        settings={"nested": {"shared": "company"}, "company_only": True},
        updated_at=20,
    )
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        rig_id=10,
        asset_id=None,
        settings={"nested": {"rig_only": True}},
        updated_at=30,
    )
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        rig_id=None,
        asset_id=1,
        settings={"a": "asset", "asset_only": True},
        updated_at=40,
    )

    settings = service.get_settings("corva.dysfunction_detection", asset_id=1)

    assert settings == {
        "a": "asset",
        "nested": {
            "package_only": True,
            "shared": "company",
            "remote_only": True,
            "rig_only": True,
        },
        "company_only": True,
        "asset_only": True,
    }


def test_get_settings_uses_sdk_asset_resolution_to_find_rig(
    service: SettingsService, api_client: FakeApiClient
) -> None:
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        rig_id=10,
        asset_id=None,
        settings={"rig_only": "value"},
        updated_at=30,
    )

    settings = service.get_settings("corva.dysfunction_detection", asset_id=1)

    assert settings["rig_only"] == "value"


def test_get_settings_uses_rig_endpoint_when_rig_id_is_provided(
    service: SettingsService, api_client: FakeApiClient
) -> None:
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        rig_id=10,
        asset_id=None,
        settings={"rig_only": True},
        updated_at=30,
    )

    settings = service.get_settings("corva.dysfunction_detection", rig_id=10)

    assert settings["rig_only"] is True


def test_patch_settings_creates_scope_document_and_merges_effective_value(
    service: SettingsService, api_client: FakeApiClient
) -> None:
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        rig_id=None,
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
        rig_id=None,
        asset_id=None,
        settings={"a": "company", "nested": {"value": 10}},
        updated_at=10,
    )
    seed_document(
        api_client,
        app_key="corva.dysfunction_detection",
        company_id=3,
        rig_id=None,
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
        rig_id=None,
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
            if doc["company_id"] == 3 and doc["asset_id"] is None and doc["rig_id"] is None
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
