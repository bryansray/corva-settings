from __future__ import annotations

from typing import Any, Protocol

from corva_settings.models import ScopeContext


class CorvaResponseProtocol(Protocol):
    def raise_for_status(self) -> None: ...

    def json(self) -> dict[str, Any]: ...


class CorvaResourceClientProtocol(Protocol):
    def get(self, path: str, **kwargs: Any) -> CorvaResponseProtocol: ...


class CorvaResourceResolver:
    def __init__(self, api_client: CorvaResourceClientProtocol) -> None:
        self.api_client = api_client

    def resolve(
        self,
        *,
        company_id: int | None = None,
        asset_id: int | None = None,
    ) -> ScopeContext:
        resolved_company_id = company_id
        asset_ids: list[int] = []

        if asset_id is not None:
            resolved_company_id, asset_ids = self._resolve_asset_hierarchy(
                asset_id, resolved_company_id
            )

        return ScopeContext(
            company_id=resolved_company_id,
            asset_ids=tuple(asset_ids),
        )

    @staticmethod
    def _coalesce_int(primary: Any, fallback: int | None) -> int | None:
        if primary is None:
            return fallback
        return int(primary)

    def _get_resource_payload(self, path: str, *, fields: str) -> dict[str, Any]:
        response = self.api_client.get(path, params={"fields": fields})
        response.raise_for_status()
        return dict(response.json())

    def _resolve_asset_hierarchy(
        self, asset_id: int, company_id: int | None
    ) -> tuple[int | None, list[int]]:
        resolved_company_id = company_id
        lineage: list[int] = []
        current_asset_id: int | None = asset_id

        while current_asset_id is not None:
            payload = self._get_resource_payload(
                f"/v2/assets/{current_asset_id}",
                fields="asset.name,asset.type,asset.parent_asset_id,include.children,include.company,include.parent_asset",
            )
            attributes = self._get_attributes(payload)
            included = payload.get("included", [])

            lineage.append(current_asset_id)
            resolved_company_id = self._coalesce_int(
                attributes.get("company_id"), resolved_company_id
            )
            resolved_company_id = self._coalesce_int(
                self._find_included_attribute(included, resource_type="company", attribute="id"),
                resolved_company_id,
            )
            current_asset_id = self._coalesce_int(attributes.get("parent_asset_id"), None)

        lineage.reverse()
        return resolved_company_id, lineage

    @staticmethod
    def _get_attributes(payload: dict[str, Any]) -> dict[str, Any]:
        return dict(payload.get("data", {}).get("attributes", {}))

    @staticmethod
    def _find_included_attribute(
        included: list[dict[str, Any]], *, resource_type: str, attribute: str
    ) -> int | None:
        for item in included:
            if item.get("type") != resource_type:
                continue
            value = item.get("attributes", {}).get(attribute)
            if value is None:
                continue
            return int(value)
        return None
