from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

import requests

from corva_settings.models import SettingsDocument, SettingsScope


class CorvaDatasetClientProtocol(Protocol):
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
    ) -> list[dict[str, Any]]: ...

    def insert_data(
        self,
        provider: str,
        dataset: str,
        data: Sequence[dict[str, Any]],
        *,
        produce: bool = False,
    ) -> requests.Response: ...


class CorvaDatasetRepository:
    def __init__(
        self, api_client: CorvaDatasetClientProtocol, *, provider: str, dataset: str
    ) -> None:
        self.api_client = api_client
        self.provider = provider
        self.dataset = dataset

    def fetch_document(self, scope: SettingsScope) -> SettingsDocument | None:
        document = self.fetch_latest_document(scope)
        if document is None or document.deleted:
            return None
        return document

    def fetch_latest_document(self, scope: SettingsScope) -> SettingsDocument | None:
        results = self.api_client.get_dataset(
            provider=self.provider,
            dataset=self.dataset,
            query=scope.to_query(),
            sort={"timestamp": -1},
            limit=1,
            skip=0,
        )
        if not results:
            return None

        document = results[0]
        if not isinstance(document, dict):
            raise TypeError("Expected mapping document from Corva API client")
        return SettingsDocument.from_dict(document)

    def save_document(self, document: SettingsDocument) -> SettingsDocument:
        self.api_client.insert_data(self.provider, self.dataset, [document.to_dict()])
        return document
