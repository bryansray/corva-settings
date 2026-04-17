# corva-settings

`corva-settings` is a reusable settings library for Corva applications. It resolves configuration by scope and persists append-only versioned documents into a Corva dataset.

## Resolution order

Reads resolve in this order:

1. Package defaults passed into the service as a Python dict
2. Company settings
3. Ancestor asset settings from highest parent to lowest parent
4. Requested asset settings

For asset reads, the service resolves the asset's `company_id` and ancestor asset chain through the injected API client by following `parent_asset_id`.

Persisted scopes are limited to:

- company scope: `company_id=<id>, asset_id=None`
- asset scope: `company_id=<id>, asset_id=<id>`

Unscoped dataset queries are invalid. Package defaults are the only global layer.

## Documentation

Additional guides:

- [docs/settings-hierarchy.md](docs/settings-hierarchy.md): how inheritance works across company, rig, and well scopes
- [docs/deleting-keys.md](docs/deleting-keys.md): how `delete_keys(...)` interacts with inheritance and append-only versioning

## Storage Model

Each write appends a new document version for one scope. The latest version is treated as the live state for that scope, and older documents are the version history.

This library assumes the dataset can store multiple documents for the same:

- `app_key`
- `company_id`
- `asset_id`

In practice, the dataset index must support append-only versions per scope. A scope-only unique index on `app_key + company_id + asset_id` is not compatible with this model.

Recommended index strategy:

- required unique index: `app_key + company_id + asset_id + version`
- optional read-optimized index: `app_key + company_id + asset_id + version desc`

The required unique index guarantees that each scope/version pair is unique while still allowing multiple versions for the same scope. The optional descending read index improves “latest version for scope” queries if the collection becomes hot.

## Stored payload shape

```json
{
  "_id": "",
  "app_key": "corva.dysfunction_detection",
  "asset_id": 1,
  "company_id": 3,
  "version": 1,
  "data": {
    "settings": {
      "feature_enabled": true
    },
    "updated_by": "user@corva.ai",
    "updated_at": 1710000000,
    "deleted": false
  },
  "timestamp": 1710000000
}
```

Older documents for the same scope are the history. `deleted` marks a logical delete tombstone for a scope. Reads and scope listing ignore a scope whose latest document is marked deleted.

## Public API

```python
from corva_settings import SettingsService

service = SettingsService(
    api_client,
    package_defaults={
        "corva.dysfunction_detection": {
            "alerts": {"enabled": True}
        }
    },
)

# Uses the default dataset name "app.settings".
# Pass dataset="..." to override it.

settings = service.get_settings("corva.dysfunction_detection", asset_id=123)

updated = service.patch_settings(
    "corva.dysfunction_detection",
    {"alerts.threshold": 12},
    updated_by="user@corva.ai",
    asset_id=123,
)

scopes = service.list_scopes("corva.dysfunction_detection", asset_id=123)

cleared = service.clear_settings(
    "corva.dysfunction_detection",
    updated_by="user@corva.ai",
    asset_id=123,
)

versions = service.list_versions(
    "corva.dysfunction_detection",
    asset_id=123,
)

rolled_back = service.rollback_settings(
    "corva.dysfunction_detection",
    version=2,
    updated_by="user@corva.ai",
    asset_id=123,
)

explanation = service.explain_settings(
    "corva.dysfunction_detection",
    asset_id=123,
)
```

Supported read and inspection operations:

- `get_settings`
- `explain_settings`
- `list_scopes`
- `list_versions`

Supported write operations:

- `replace_settings`
- `patch_settings`
- `delete_keys`
- `clear_settings`
- `delete_scope`
- `rollback_settings`

Writes are scoped to either:

- `company_id`
- `company_id + asset_id`

Operation semantics:

- `patch_settings` and `delete_keys` use dotted paths such as `alerts.threshold`
- `clear_settings` writes an empty active document for the target scope
- `delete_scope` writes a logical delete tombstone for the target scope
- `list_scopes` returns the non-deleted scopes present in the applicable resolution chain
- `list_versions` returns stored versions for one concrete scope, newest first
- `rollback_settings` appends a new latest version by copying the settings from an older version
- `explain_settings` returns the effective settings plus the contributing package-default and dataset layers in precedence order

## Expected API client surface

The library is designed around `corva_sdk`'s `Api` client. It uses:

```python
api.get_dataset(provider, dataset, query=..., sort=..., limit=..., skip=0)
api.insert_data(provider, dataset, [document])
api.get("/v2/assets/{asset_id}", params={"fields": ...})
```

The dataset methods come directly from the `corva-sdk` docs and repository:

- Docs: https://corva-ai.github.io/python-sdk/corva-sdk/2.1.1/index.html#api
- Repo: https://github.com/corva-ai/python-sdk

Asset hierarchy resolution uses raw platform requests through `Api.get(...)` because the SDK exposes generic HTTP methods but does not provide dedicated hierarchy helpers.

Current resolver behavior:

- `GET /v2/assets/{asset_id}` to extract `company_id`
- follow `parent_asset_id` recursively to build the ancestor chain used for inheritance

The company endpoint is not currently required for settings resolution because `company_id` is already present on asset payloads.

## Testing

Preferred validation after code changes:

1. `pytest -q tests/test_service.py`
2. `python -m compileall src`
3. `uv run pytest`

Live integration test:

```bash
CORVA_API_KEY=... \
CORVA_APP_KEY=... \
CORVA_SETTINGS_TEST_COMPANY_ID=... \
uv run pytest tests/integration -m integration
```

Optional integration env vars:

- `CORVA_API_URL` defaults to `https://api.qa.corva.ai`
- `CORVA_DATA_API_URL` defaults to `https://data.qa.corva.ai`
- `CORVA_SETTINGS_TEST_PROVIDER` defaults to `corva`
- `CORVA_SETTINGS_TEST_DATASET` defaults to `app.settings`
