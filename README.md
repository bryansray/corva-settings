# corva-settings

`corva-settings` is a reusable settings library for Corva applications. It resolves configuration by scope, persists documents into a Corva dataset, and keeps a full-snapshot history for same-scope writes.

## Resolution order

Reads resolve in this order:

1. Package defaults passed into the service as a Python dict
2. Remote defaults stored in the dataset with `company_id`, `rig_id`, and `asset_id` all set to `null`
3. Company settings
4. Rig settings
5. Asset settings

For asset reads, the service resolves the asset's `rig_id` and `company_id` through the injected API client. For rig reads, it resolves the `company_id`.

## Stored payload shape

```json
{
  "_id": "",
  "app_key": "corva.dysfunction_detection",
  "asset_id": 1,
  "company_id": 3,
  "rig_id": null,
  "data": {
    "settings": {
      "feature_enabled": true
    },
    "updated_by": "user@corva.ai",
    "updated_at": 1710000000,
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

## First-pass API

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
```

Supported write operations:

- `replace_settings`
- `patch_settings`
- `delete_keys`

`patch_settings` and `delete_keys` use dotted paths such as `alerts.threshold`.

## Expected API client surface

The library is designed around `corva_sdk`'s `Api` client. It uses:

```python
api.get_dataset(provider, dataset, query=..., sort=..., limit=..., skip=0)
api.insert_data(provider, dataset, [document])
api.get("/v2/assets/{asset_id}", params={"fields": ...})
api.post("/v2/assets/resolve?assets={parent_asset_id}")
```

The dataset methods come directly from the `corva-sdk` docs and repository:

- Docs: https://corva-ai.github.io/python-sdk/corva-sdk/2.1.1/index.html#api
- Repo: https://github.com/corva-ai/python-sdk

Asset and rig resolution uses raw platform requests through `Api.get(...)` and `Api.post(...)` because the SDK exposes generic HTTP methods but does not provide dedicated `get_asset` or `get_rig` helpers.

Current resolver behavior:

- `GET /v2/assets/{asset_id}?fields=*` to extract `company_id` and the associated rig when resolving asset-scoped settings
- `GET /v2/rigs/{rig_id}?fields=*` to extract the associated company when resolving rig-scoped settings

The company endpoint is not currently required for settings resolution because `company_id` is already present on the asset and rig payloads.

## Testing

Run:

```bash
uv run pytest
```
