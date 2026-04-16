from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SettingsScope:
    app_key: str
    company_id: int | None = None
    asset_id: int | None = None

    def to_query(self) -> dict[str, Any]:
        if self.company_id is None and self.asset_id is None:
            raise ValueError("settings queries must target a company or asset scope")
        return {
            "app_key": self.app_key,
            "company_id": self.company_id,
            "asset_id": self.asset_id,
        }


@dataclass(slots=True)
class SettingsHistoryEntry:
    settings: dict[str, Any]
    updated_by: str
    updated_at: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "settings": self.settings,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SettingsHistoryEntry:
        return cls(
            settings=dict(payload.get("settings", {})),
            updated_by=str(payload.get("updated_by", "")),
            updated_at=int(payload.get("updated_at", 0)),
        )


@dataclass(slots=True)
class SettingsDocument:
    app_key: str
    data: dict[str, Any]
    timestamp: int
    company_id: int | None = None
    asset_id: int | None = None
    _id: str | None = None
    version: int = 1

    @property
    def settings(self) -> dict[str, Any]:
        return dict(self.data.get("settings", {}))

    @property
    def updated_by(self) -> str:
        return str(self.data.get("updated_by", ""))

    @property
    def updated_at(self) -> int:
        return int(self.data.get("updated_at", 0))

    @property
    def history(self) -> list[SettingsHistoryEntry]:
        raw_history = self.data.get("history", [])
        return [SettingsHistoryEntry.from_dict(entry) for entry in raw_history]

    @property
    def scope(self) -> SettingsScope:
        return SettingsScope(
            app_key=self.app_key,
            company_id=self.company_id,
            asset_id=self.asset_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "_id": self._id or "",
            "app_key": self.app_key,
            "company_id": self.company_id,
            "asset_id": self.asset_id,
            "version": self.version,
            "data": {
                "settings": self.settings,
                "updated_by": self.updated_by,
                "updated_at": self.updated_at,
                "history": [entry.to_dict() for entry in self.history],
            },
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SettingsDocument:
        data = dict(payload.get("data", {}))
        history = [
            SettingsHistoryEntry.from_dict(entry).to_dict()
            for entry in data.get("history", [])
        ]
        return cls(
            _id=payload.get("_id"),
            app_key=str(payload["app_key"]),
            company_id=payload.get("company_id"),
            asset_id=payload.get("asset_id"),
            data={
                "settings": dict(data.get("settings", {})),
                "updated_by": str(data.get("updated_by", "")),
                "updated_at": int(data.get("updated_at", payload.get("timestamp", 0))),
                "history": history,
            },
            timestamp=int(payload["timestamp"]),
        )

    @classmethod
    def build(
        cls,
        scope: SettingsScope,
        *,
        settings: dict[str, Any],
        updated_by: str,
        updated_at: int,
        history: list[SettingsHistoryEntry] | None = None,
        _id: str | None = None,
    ) -> SettingsDocument:
        return cls(
            _id=_id,
            app_key=scope.app_key,
            company_id=scope.company_id,
            asset_id=scope.asset_id,
            timestamp=updated_at,
            data={
                "settings": dict(settings),
                "updated_by": updated_by,
                "updated_at": updated_at,
                "history": [entry.to_dict() for entry in (history or [])],
            },
        )

    def snapshot(self) -> SettingsHistoryEntry:
        return SettingsHistoryEntry(
            settings=self.settings,
            updated_by=self.updated_by,
            updated_at=self.updated_at,
        )


@dataclass(frozen=True, slots=True)
class ScopeContext:
    company_id: int | None = None
    asset_ids: tuple[int, ...] = ()

    @property
    def asset_id(self) -> int | None:
        if not self.asset_ids:
            return None
        return self.asset_ids[-1]
