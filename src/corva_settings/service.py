from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from time import time
from typing import Any

from corva_settings.merge import apply_patch, deep_merge, delete_paths
from corva_settings.models import ScopeContext, SettingsDocument, SettingsHistoryEntry, SettingsScope
from corva_settings.repository import CorvaDatasetRepository, CorvaDatasetClientProtocol
from corva_settings.resolver import CorvaResourceClientProtocol, CorvaResourceResolver


class SettingsService:
    def __init__(
        self,
        api_client: CorvaDatasetClientProtocol & CorvaResourceClientProtocol,
        *,
        dataset: str,
        provider: str = "corva",
        package_defaults: Mapping[str, Mapping[str, Any]] | None = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self.api_client = api_client
        self.repository = CorvaDatasetRepository(api_client, provider=provider, dataset=dataset)
        self.resource_resolver = CorvaResourceResolver(api_client)
        self.package_defaults = dict(package_defaults or {})
        self.clock = clock or (lambda: int(time()))

    def get_settings(
        self,
        app_key: str,
        *,
        company_id: int | None = None,
        asset_id: int | None = None,
    ) -> dict[str, Any]:
        context = self._resolve_context(company_id=company_id, asset_id=asset_id)
        return self._resolve_effective_settings(app_key, context)

    def replace_settings(
        self,
        app_key: str,
        settings: Mapping[str, Any],
        *,
        updated_by: str,
        company_id: int | None = None,
        asset_id: int | None = None,
    ) -> dict[str, Any]:
        context = self._resolve_context(company_id=company_id, asset_id=asset_id)
        scope = self._scope_for_write(app_key, context, company_id=company_id, asset_id=asset_id)
        current = self.repository.fetch_document(scope)
        document = self._build_next_document(
            scope,
            dict(settings),
            updated_by=updated_by,
            previous=current,
        )
        self.repository.save_document(document)
        return self._resolve_effective_settings(app_key, context)

    def patch_settings(
        self,
        app_key: str,
        patch: Mapping[str, Any],
        *,
        updated_by: str,
        company_id: int | None = None,
        asset_id: int | None = None,
    ) -> dict[str, Any]:
        context = self._resolve_context(company_id=company_id, asset_id=asset_id)
        scope = self._scope_for_write(app_key, context, company_id=company_id, asset_id=asset_id)
        current = self.repository.fetch_document(scope)
        current_settings = current.settings if current else {}
        next_settings = apply_patch(current_settings, patch)
        document = self._build_next_document(
            scope,
            next_settings,
            updated_by=updated_by,
            previous=current,
        )
        self.repository.save_document(document)
        return self._resolve_effective_settings(app_key, context)

    def delete_keys(
        self,
        app_key: str,
        paths: Sequence[str],
        *,
        updated_by: str,
        company_id: int | None = None,
        asset_id: int | None = None,
    ) -> dict[str, Any]:
        context = self._resolve_context(company_id=company_id, asset_id=asset_id)
        scope = self._scope_for_write(app_key, context, company_id=company_id, asset_id=asset_id)
        current = self.repository.fetch_document(scope)
        current_settings = current.settings if current else {}
        next_settings = delete_paths(current_settings, paths)
        document = self._build_next_document(
            scope,
            next_settings,
            updated_by=updated_by,
            previous=current,
        )
        self.repository.save_document(document)
        return self._resolve_effective_settings(app_key, context)

    def clear_settings(
        self,
        app_key: str,
        *,
        updated_by: str,
        company_id: int | None = None,
        asset_id: int | None = None,
    ) -> dict[str, Any]:
        context = self._resolve_context(company_id=company_id, asset_id=asset_id)
        scope = self._scope_for_write(app_key, context, company_id=company_id, asset_id=asset_id)
        current = self.repository.fetch_document(scope)
        document = self._build_next_document(
            scope,
            {},
            updated_by=updated_by,
            previous=current,
        )
        self.repository.save_document(document)
        return self._resolve_effective_settings(app_key, context)

    def delete_scope(
        self,
        app_key: str,
        *,
        updated_by: str,
        company_id: int | None = None,
        asset_id: int | None = None,
    ) -> dict[str, Any]:
        context = self._resolve_context(company_id=company_id, asset_id=asset_id)
        scope = self._scope_for_write(app_key, context, company_id=company_id, asset_id=asset_id)
        current = self.repository.fetch_document(scope)
        if current is None:
            return self._resolve_effective_settings(app_key, context)
        document = self._build_next_document(
            scope,
            {},
            updated_by=updated_by,
            previous=current,
            deleted=True,
        )
        self.repository.save_document(document)
        return self._resolve_effective_settings(app_key, context)

    def list_scopes(
        self,
        app_key: str,
        *,
        company_id: int | None = None,
        asset_id: int | None = None,
    ) -> list[SettingsScope]:
        context = self._resolve_context(company_id=company_id, asset_id=asset_id)
        return [
            scope
            for scope in self._resolution_chain(app_key, context)
            if self.repository.fetch_document(scope) is not None
        ]

    def _resolve_effective_settings(self, app_key: str, context: ScopeContext) -> dict[str, Any]:
        merged = deepcopy(self.package_defaults.get(app_key, {}))
        for scope in self._resolution_chain(app_key, context):
            document = self.repository.fetch_document(scope)
            if document is None:
                continue
            merged = deep_merge(merged, document.settings)
        return merged

    def _resolve_context(
        self,
        *,
        company_id: int | None,
        asset_id: int | None,
    ) -> ScopeContext:
        if asset_id is None:
            return ScopeContext(company_id=company_id)
        return self.resource_resolver.resolve(company_id=company_id, asset_id=asset_id)

    def _scope_for_write(
        self,
        app_key: str,
        context: ScopeContext,
        *,
        company_id: int | None,
        asset_id: int | None,
    ) -> SettingsScope:
        if asset_id is not None:
            return SettingsScope(
                app_key=app_key,
                company_id=context.company_id,
                asset_id=asset_id,
            )
        if company_id is not None:
            return SettingsScope(app_key=app_key, company_id=context.company_id, asset_id=None)
        raise ValueError("settings writes must target a company or asset scope")

    def _resolution_chain(self, app_key: str, context: ScopeContext) -> list[SettingsScope]:
        chain: list[SettingsScope] = []
        if context.company_id is not None:
            chain.append(SettingsScope(app_key=app_key, company_id=context.company_id, asset_id=None))
        for asset_id in context.asset_ids:
            chain.append(SettingsScope(app_key=app_key, company_id=context.company_id, asset_id=asset_id))
        return chain

    def _build_next_document(
        self,
        scope: SettingsScope,
        settings: dict[str, Any],
        *,
        updated_by: str,
        previous: SettingsDocument | None = None,
        deleted: bool = False,
    ) -> SettingsDocument:
        updated_at = self.clock()
        history: list[SettingsHistoryEntry] = previous.history if previous else []
        if previous is not None:
            history = [*history, previous.snapshot()]
        return SettingsDocument.build(
            scope,
            settings=settings,
            updated_by=updated_by,
            updated_at=updated_at,
            history=history,
            deleted=deleted,
        )
