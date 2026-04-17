from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from time import time
from typing import Any, Protocol

from corva_settings.merge import apply_patch, deep_merge, delete_paths
from corva_settings.models import (
    ScopeContext,
    SettingsDocument,
    SettingsScope,
)
from corva_settings.repository import CorvaDatasetClientProtocol, CorvaDatasetRepository
from corva_settings.resolver import CorvaResourceClientProtocol, CorvaResourceResolver


class SettingsApiClientProtocol(CorvaDatasetClientProtocol, CorvaResourceClientProtocol, Protocol):
    """Combined protocol for the dataset and resource APIs required by SettingsService."""


DEFAULT_SETTINGS_DATASET = "app.settings"


class SettingsService:
    """Resolve and persist scoped settings documents."""

    def __init__(
        self,
        api_client: SettingsApiClientProtocol,
        *,
        dataset: str = DEFAULT_SETTINGS_DATASET,
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
        """Return the effective settings for the requested scope."""
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
        """Replace the stored settings at one scope and return the resolved result."""
        context = self._resolve_context(company_id=company_id, asset_id=asset_id)
        scope = self._scope_for_write(app_key, context, company_id=company_id, asset_id=asset_id)
        current = self.repository.fetch_latest_document(scope)
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
        """Apply a dotted-path patch to one scope and return the resolved result."""
        context = self._resolve_context(company_id=company_id, asset_id=asset_id)
        scope = self._scope_for_write(app_key, context, company_id=company_id, asset_id=asset_id)
        latest = self.repository.fetch_latest_document(scope)
        current_settings = latest.settings if latest and not latest.deleted else {}
        next_settings = apply_patch(current_settings, patch)
        document = self._build_next_document(
            scope,
            next_settings,
            updated_by=updated_by,
            previous=latest,
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
        """Delete dotted-path keys at one scope and return the resolved result."""
        context = self._resolve_context(company_id=company_id, asset_id=asset_id)
        scope = self._scope_for_write(app_key, context, company_id=company_id, asset_id=asset_id)
        latest = self.repository.fetch_latest_document(scope)
        current_settings = latest.settings if latest and not latest.deleted else {}
        next_settings = delete_paths(current_settings, paths)
        document = self._build_next_document(
            scope,
            next_settings,
            updated_by=updated_by,
            previous=latest,
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
        """Write an empty active document for one scope and return inherited settings."""
        context = self._resolve_context(company_id=company_id, asset_id=asset_id)
        scope = self._scope_for_write(app_key, context, company_id=company_id, asset_id=asset_id)
        current = self.repository.fetch_latest_document(scope)
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
        """Logically delete one scope and return the remaining inherited settings."""
        context = self._resolve_context(company_id=company_id, asset_id=asset_id)
        scope = self._scope_for_write(app_key, context, company_id=company_id, asset_id=asset_id)
        current = self.repository.fetch_latest_document(scope)
        if current is None or current.deleted:
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

    def list_versions(
        self,
        app_key: str,
        *,
        company_id: int | None = None,
        asset_id: int | None = None,
        limit: int = 100,
        include_deleted: bool = True,
    ) -> list[SettingsDocument]:
        """List stored versions for one concrete scope, newest first."""
        context = self._resolve_context(company_id=company_id, asset_id=asset_id)
        scope = self._scope_for_write(app_key, context, company_id=company_id, asset_id=asset_id)
        return self.repository.list_documents(scope, limit=limit, include_deleted=include_deleted)

    def rollback_settings(
        self,
        app_key: str,
        *,
        version: int,
        updated_by: str,
        company_id: int | None = None,
        asset_id: int | None = None,
    ) -> dict[str, Any]:
        """Append a new latest version by copying settings from an earlier active version."""
        context = self._resolve_context(company_id=company_id, asset_id=asset_id)
        scope = self._scope_for_write(app_key, context, company_id=company_id, asset_id=asset_id)
        target = self.repository.fetch_document_version(scope, version)
        if target is None:
            raise ValueError(f"settings version {version} was not found for the requested scope")
        if target.deleted:
            raise ValueError(f"settings version {version} is a tombstone and cannot be rolled back")
        latest = self.repository.fetch_latest_document(scope)
        document = self._build_next_document(
            scope,
            target.settings,
            updated_by=updated_by,
            previous=latest,
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
        """List non-deleted stored scopes that contribute to the requested resolution chain."""
        context = self._resolve_context(company_id=company_id, asset_id=asset_id)
        return [
            scope
            for scope in self._resolution_chain(app_key, context)
            if self.repository.fetch_document(scope) is not None
        ]

    def _resolve_effective_settings(self, app_key: str, context: ScopeContext) -> dict[str, Any]:
        """Merge package defaults with stored scope documents in precedence order."""
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
        """Resolve company and asset ancestry metadata needed for scoped reads and writes."""
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
        """Validate and normalize the concrete persisted scope for one write."""
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
        """Build the ordered list of persisted scopes used during read resolution."""
        chain: list[SettingsScope] = []
        if context.company_id is not None:
            chain.append(
                SettingsScope(app_key=app_key, company_id=context.company_id, asset_id=None)
            )
        for asset_id in context.asset_ids:
            chain.append(
                SettingsScope(app_key=app_key, company_id=context.company_id, asset_id=asset_id)
            )
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
        """Create the next append-only versioned document for a scope."""
        updated_at = self.clock()
        return SettingsDocument.build(
            scope,
            settings=settings,
            updated_by=updated_by,
            updated_at=updated_at,
            version=(previous.version + 1) if previous else 1,
            deleted=deleted,
        )
