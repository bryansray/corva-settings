# Rollback And Version History

This document explains how append-only version history works and how `rollback_settings(...)` behaves.

## Version Model

Every write to a scope appends a new document version for that exact scope.

A scope is identified by:

- `app_key`
- `company_id`
- `asset_id`

Examples of writes that create a new version:

- `replace_settings(...)`
- `patch_settings(...)`
- `delete_keys(...)`
- `clear_settings(...)`
- `delete_scope(...)`
- `rollback_settings(...)`

The live state for a scope is the newest non-deleted document selected by:

1. highest `version`
2. highest `timestamp` as a secondary tiebreaker

Older documents remain in the dataset as immutable history.

## What A Version Looks Like

Example scope:

- `app_key = "corva.dysfunction_detection"`
- `company_id = 1`
- `asset_id = 49407322`

Version 1:

```json
{
  "app_key": "corva.dysfunction_detection",
  "company_id": 1,
  "asset_id": 49407322,
  "version": 1,
  "data": {
    "settings": {
      "dysfunction_detection": {
        "is_enabled": true,
        "wob_threshold": 10
      }
    },
    "updated_by": "user@corva.ai",
    "updated_at": 1710000000,
    "deleted": false
  },
  "timestamp": 1710000000
}
```

Version 2 after a threshold update:

```json
{
  "app_key": "corva.dysfunction_detection",
  "company_id": 1,
  "asset_id": 49407322,
  "version": 2,
  "data": {
    "settings": {
      "dysfunction_detection": {
        "is_enabled": true,
        "wob_threshold": 20
      }
    },
    "updated_by": "user@corva.ai",
    "updated_at": 1710000300,
    "deleted": false
  },
  "timestamp": 1710000300
}
```

Both versions remain stored. Version 2 is the live state because it is newer.

## Listing Versions

Use `list_versions(...)` to inspect append-only history for one concrete scope.

Example:

```python
versions = service.list_versions(
    "corva.dysfunction_detection",
    asset_id=49407322,
)
```

The result is ordered newest first:

```text
version=4
version=3
version=2
version=1
```

By default, deleted versions are included so you can inspect tombstones as part of the full history.

## Rollback Behavior

`rollback_settings(...)` does not modify older versions.

Instead, it:

1. looks up the requested earlier version for the same scope
2. copies that version's `settings`
3. appends a brand new latest version with those copied settings

This preserves immutable history.

Example:

Version history before rollback:

```text
version=1  wob_threshold=10
version=2  wob_threshold=20
version=3  wob_threshold=30
```

If you call:

```python
service.rollback_settings(
    "corva.dysfunction_detection",
    version=1,
    updated_by="user@corva.ai",
    asset_id=49407322,
)
```

the resulting history becomes:

```text
version=4  wob_threshold=10
version=3  wob_threshold=30
version=2  wob_threshold=20
version=1  wob_threshold=10
```

Important details:

- rollback creates a new head version
- the older target version stays in place
- no existing version is deleted or mutated

## Why Rollback Works This Way

This model preserves:

- immutability
- auditability
- chronological history
- the ability to inspect exactly what changed over time

If rollback rewrote older versions, the history would become less trustworthy.

## Rollback Limitations

Rollback only works for:

- an existing version
- a non-deleted version

You cannot roll back to:

- a version that does not exist
- a tombstone version created by `delete_scope(...)`

If you try, the service raises `ValueError`.

## Tombstones In Version History

`delete_scope(...)` appends a tombstone version:

```json
{
  "version": 5,
  "data": {
    "settings": {},
    "deleted": true
  }
}
```

That means:

- the scope no longer contributes settings to reads
- older active versions are still preserved in history
- `list_versions(...)` can still show the tombstone and the earlier active versions

If a later write is made to that same scope, it creates a new active version after the tombstone.

Example:

```text
version=5  deleted=true
version=4  active
version=3  active
```

After a new write:

```text
version=6  active
version=5  deleted=true
version=4  active
version=3  active
```

## Practical Rules

- every write creates a new version
- versions are append-only
- rollback creates a new version instead of changing old ones
- tombstones are part of version history
- `list_versions(...)` is the easiest way to inspect one scope's history
- `explain_settings(...)` is the easiest way to inspect which version is currently contributing to the effective result
