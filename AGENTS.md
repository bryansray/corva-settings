# AGENTS.md

## Purpose

This repository contains `corva-settings`, a reusable settings library for Corva applications. The library resolves effective settings by scope and persists append-only versioned scope documents into a Corva dataset.

This file is the working context and collaboration contract for future changes in this repo.

## Current Architecture

Core modules:

- `src/corva_settings/service.py`
  Orchestrates reads and writes. Public API lives here.
- `src/corva_settings/repository.py`
  Wraps dataset persistence and fetches the latest document for a scope.
- `src/corva_settings/resolver.py`
  Resolves `company_id` and asset ancestry from Corva asset APIs.
- `src/corva_settings/models.py`
  Defines `SettingsScope`, `ScopeContext`, `SettingsDocument`, and history types.
- `src/corva_settings/merge.py`
  Contains deep-merge, patch, and delete-path behavior used by the service.

## Scope Model

Persisted scopes are:

- company scope: `company_id=<id>, asset_id=None`
- asset scope: `company_id=<id>, asset_id=<id>`

Unscoped dataset queries are invalid and must not be issued. Package defaults are the only global layer.

Read resolution order:

1. Package defaults from `SettingsService(..., package_defaults=...)`
2. Company-scoped dataset document, when available
3. Ancestor asset-scoped documents from highest parent to lowest parent
4. Requested asset-scoped document

Asset reads resolve ancestry by following `parent_asset_id` via `/v2/assets/{asset_id}`.

## Storage Model

The repository uses an append-only versioned document model per scope:

- each write appends a new document
- the latest version for a scope is the live state
- older documents for that scope are the history

Embedded history inside one document is not used. Version history lives in the dataset as prior scope documents.

The dataset must support multiple documents for the same:

- `app_key`
- `company_id`
- `asset_id`

Recommended index strategy:

- required unique index on `app_key + company_id + asset_id + version`
- optional read-optimized index on `app_key + company_id + asset_id + version desc`

## Write Model

Supported write operations:

- `replace_settings`
- `patch_settings`
- `delete_keys`
- `clear_settings`
- `delete_scope`
- `rollback_settings`

Supported read and inspection operations:

- `get_settings`
- `list_scopes`
- `list_versions`

Behavior:

- Writes must target either a company scope or an asset scope.
- Same-scope writes append a new versioned document.
- `clear_settings` writes an empty active document for the target scope.
- `delete_scope` is a logical delete, not a physical delete. It writes a tombstone document with `data.deleted=True`.
- Reads and `list_scopes` ignore tombstoned latest documents so deleted scopes do not reappear through older versions.
- `rollback_settings` appends a new latest version whose settings are copied from an older version.

## Dataset Shape

Stored documents include:

- top-level: `_id`, `app_key`, `company_id`, `asset_id`, `version`, `timestamp`
- `data.settings`
- `data.updated_by`
- `data.updated_at`
- `data.deleted`

Older documents are the same-scope version history.

## API Client Assumptions

The service is designed around the Corva Python SDK `Api` shape:

- `get_dataset(...)`
- `insert_data(...)`
- `get(...)`

Resolver code currently depends on asset payloads containing enough data to recover:

- `company_id`
- `parent_asset_id`

## Testing

Primary test locations:

- `tests/test_service.py`
  Fast unit coverage for scope resolution, merge behavior, history, clearing, deleting, and scope listing.
- `tests/integration/test_persistence.py`
  Live Corva integration coverage for dataset persistence.

Preferred validation after code changes:

1. `pytest -q tests/test_service.py`
2. `python -m compileall src`
3. Run integration coverage when persistence or API behavior changes

## Workflow Rules

These are repo-specific collaboration rules and should be followed on future tasks:

- Use conventional commits for every commit.
- After making code changes, do not commit immediately. Let the developer review the changes first unless they explicitly ask for a commit.
- After a commit, recommend the best next step or next feature based on the current state of the repo.
- Keep commits scoped and intentional. Avoid bundling unrelated editor or local-environment changes unless explicitly requested.
- When a change naturally breaks into separable units, group the work into multiple commits so review and history stay clear.
- Do not reintroduce global persisted defaults through `company_id=None, asset_id=None` queries or writes.

## Practical Guidance For Future Changes

- Prefer extending `SettingsService` first when adding public behavior.
- Keep repository behavior narrow: persistence concerns only, not merge logic.
- Preserve append-only semantics unless there is an explicit decision to support hard deletes at the dataset layer.
- If adding new persisted document fields, update:
  - `SettingsDocument.to_dict()`
  - `SettingsDocument.from_dict()`
  - relevant unit tests
- If changing scope resolution behavior, update both:
  - service tests
  - README / docs that describe resolution order

## Recommended Near-Term Follow-Ups

Useful next features from the current state of the library:

- `explain_settings(...)` to show which scopes contributed which values
- optimistic concurrency / version checks for same-scope writes
- schema validation per `app_key`
- integration coverage for `clear_settings`, `delete_scope`, and tombstone behavior
