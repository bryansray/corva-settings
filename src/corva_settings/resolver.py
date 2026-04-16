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
        rig_id: int | None = None,
        asset_id: int | None = None,
    ) -> ScopeContext:
        resolved_company_id = company_id
        resolved_rig_id = rig_id

        if asset_id is not None:
            asset_payload = self._get_resource_payload(f"/v2/assets/{asset_id}", fields="*")
            asset = self._get_attributes(asset_payload)
            included = asset_payload.get("included", [])
            resolved_company_id = self._coalesce_int(asset.get("company_id"), resolved_company_id)
            resolved_company_id = self._coalesce_int(
                self._find_included_attribute(included, resource_type="company", attribute="id"),
                resolved_company_id,
            )
            if resolved_rig_id is None:
                resolved_rig_id = self._coalesce_int(asset.get("rig_id"), None)
            if resolved_rig_id is None:
                resolved_rig_id = self._coalesce_int(
                    self._find_relationship_id(asset_payload, relationship="rig"),
                    None,
                )
            if resolved_rig_id is None:
                resolved_rig_id = self._coalesce_int(
                    self._find_included_id(included, resource_type="rig"),
                    None,
                )

        if resolved_rig_id is not None:
            rig_payload = self._get_resource_payload(f"/v2/rigs/{resolved_rig_id}", fields="*")
            resolved_company_id = self._coalesce_int(
                self._find_relationship_id(rig_payload, relationship="company"),
                resolved_company_id,
            )
            resolved_company_id = self._coalesce_int(
                self._find_included_attribute(rig_payload.get("included", []), resource_type="company", attribute="id"),
                resolved_company_id,
            )

        return ScopeContext(
            company_id=resolved_company_id,
            rig_id=resolved_rig_id,
            asset_id=asset_id,
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

    @staticmethod
    def _get_attributes(payload: dict[str, Any]) -> dict[str, Any]:
        return dict(payload.get("data", {}).get("attributes", {}))

    @staticmethod
    def _find_relationship_id(payload: dict[str, Any], *, relationship: str) -> int | None:
        value = payload.get("data", {}).get("relationships", {}).get(relationship, {}).get("data")
        if not isinstance(value, dict):
            return None
        relationship_id = value.get("id")
        if relationship_id is None:
            return None
        return int(relationship_id)

    @staticmethod
    def _find_included_id(included: list[dict[str, Any]], *, resource_type: str) -> int | None:
        for item in included:
            if item.get("type") != resource_type:
                continue
            identifier = item.get("id")
            if identifier is None:
                return None
            return int(identifier)
        return None

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
