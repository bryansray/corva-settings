# Deleting Keys

This document explains how `delete_keys(...)` behaves for scoped settings.

## What `delete_keys(...)` Does

`delete_keys(...)` removes one or more dotted-path keys from the current scope's latest active settings document.

It does not:

- delete older versions
- modify parent scopes
- physically remove dataset rows

Instead, it appends a new version for the same scope with the requested keys removed from that scope's settings payload.

## Basic Behavior

Assume `Company 1` has these settings:

```json
{
  "dysfunction_detection": {
    "is_enabled": true,
    "wob_threshold": 10
  },
  "notifications": {
    "is_enabled": true
  }
}
```

And `Well 1` has:

```json
{
  "dysfunction_detection": {
    "wob_threshold": 20
  },
  "well_label": "Primary"
}
```

The effective settings for `Well 1` are:

```json
{
  "dysfunction_detection": {
    "is_enabled": true,
    "wob_threshold": 20
  },
  "notifications": {
    "is_enabled": true
  },
  "well_label": "Primary"
}
```

If you call:

```python
service.delete_keys(
    "corva.dysfunction_detection",
    ["dysfunction_detection.wob_threshold"],
    updated_by="user@corva.ai",
    asset_id=well_1_id,
)
```

then the newest `Well 1` document no longer contains `dysfunction_detection.wob_threshold`.

The resulting effective settings become:

```json
{
  "dysfunction_detection": {
    "is_enabled": true,
    "wob_threshold": 10
  },
  "notifications": {
    "is_enabled": true
  },
  "well_label": "Primary"
}
```

What happened:

- the key was removed from the `Well 1` scope
- the company value became visible again through inheritance

## Deleting A Key That Exists Only At The Current Scope

If `Well 1` has:

```json
{
  "well_label": "Primary"
}
```

and no parent scope defines `well_label`, then deleting it removes it from the effective result entirely.

Before:

```json
{
  "well_label": "Primary"
}
```

After deleting `well_label`:

```json
{}
```

## Deleting A Nested Object Key

Assume the current scope has:

```json
{
  "dysfunction_detection": {
    "parameters": {
      "wob_threshold": 20,
      "rpm_threshold": 140
    }
  }
}
```

If you delete:

```python
["dysfunction_detection.parameters.rpm_threshold"]
```

then only that nested key is removed.

Result:

```json
{
  "dysfunction_detection": {
    "parameters": {
      "wob_threshold": 20
    }
  }
}
```

## Deleting Multiple Keys

You can delete more than one dotted path in a single operation.

Example:

```python
service.delete_keys(
    "corva.dysfunction_detection",
    [
        "dysfunction_detection.wob_threshold",
        "notifications.is_enabled",
        "well_label",
    ],
    updated_by="user@corva.ai",
    asset_id=well_1_id,
)
```

Each path is removed from the current scope before the new version is written.

## Important Distinction From `clear_settings(...)`

- `delete_keys(...)` removes only selected paths from the current scope
- `clear_settings(...)` writes an empty active settings document for the current scope

Use `delete_keys(...)` when only part of the current scope should fall back to inherited values.

Use `clear_settings(...)` when the whole scope should stop contributing active settings.

## Important Distinction From `delete_scope(...)`

- `delete_keys(...)` keeps the scope active
- `delete_scope(...)` writes a tombstone version for the scope

After `delete_scope(...)`, the scope no longer contributes any settings at all until a later non-deleted version is written.

## Practical Rules

- `delete_keys(...)` affects only the requested scope
- parent scopes are never modified
- inheritance can make a deleted key appear to "come back" if an ancestor defines it
- the operation is append-only and creates a new version for the scope
- use `explain_settings(...)` if you need to confirm where the resulting value now comes from
