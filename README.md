# corva-settings

`corva-settings` is a reusable settings library for Corva applications. It resolves configuration by scope, persists versioned documents into a Corva dataset, and keeps same-scope history snapshots for later inspection.

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
    "deleted": false,
    "history": [
      {
        "settings": {
          "feature_enabled": false
        },
        "updated_by": "user@corva.ai",
        "updated_at": 1700000000
      }
    ]
  },
  "timestamp": 1710000000
}
```

`history` is write history for the same stored scope document. Inheritance provenance is not mixed into history.

`deleted` marks a logical delete tombstone for a scope. Reads and scope listing ignore a scope whose latest document is marked deleted.

## Public API

```python
from corva_settings import SettingsService

service = SettingsService(
    api_client,
    dataset="app.settings",
    package_defaults={
        "corva.dysfunction_detection": {
            "alerts": {"enabled": True}
        }
    },
)

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
```

Supported read and inspection operations:

- `get_settings`
- `list_scopes`

Supported write operations:

- `replace_settings`
- `patch_settings`
- `delete_keys`
- `clear_settings`
- `delete_scope`

Writes are scoped to either:

- `company_id`
- `company_id + asset_id`

Operation semantics:

- `patch_settings` and `delete_keys` use dotted paths such as `alerts.threshold`
- `clear_settings` writes an empty active document for the target scope
- `delete_scope` writes a logical delete tombstone for the target scope
- `list_scopes` returns the non-deleted scopes present in the applicable resolution chain

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
