import datetime


def merge_labels(existing, add, clear):
    """Return the final label list after merge, or None if no API change needed.

    - clear=True  → wipe existing first, then add
    - clear=False → union of existing + add, preserving existing order
    - If result equals existing, return None to signal no-op.
    """
    if clear:
        result = []
        for label in add:
            if label not in result:
                result.append(label)
        return result if result != existing else None

    result = list(existing)
    for label in add:
        if label not in result:
            result.append(label)
    return result if result != existing else None


def parse_due(value):
    """Return ISO date string, or None to clear. Raise ValueError on invalid input."""
    if value == "none":
        return None
    if not value:
        raise ValueError("due must be YYYY-MM-DD or 'none'")
    try:
        datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"due must be YYYY-MM-DD or 'none', got {value!r}") from exc
    return value


_FORCE_GATED_FIELDS = {"summary", "description"}


def should_require_force(field, current, force):
    """Return True if this edit needs --force but force was not passed.

    Only 'summary' and 'description' are gated: they are free-form, potentially long,
    and a typo'd overwrite is painful. Whitespace-only existing values count as empty.
    """
    if force:
        return False
    if field not in _FORCE_GATED_FIELDS:
        return False
    if not current or not current.strip():
        return False
    return True
