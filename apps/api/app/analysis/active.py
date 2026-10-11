"""Jobs running in this process.

Embedding is marked running in the database before the model finishes. If the
API process stops, that row is left behind and the workspace keeps a spinner.
A read treats a running embedding this process does not own as stopped.
"""

from uuid import UUID

_active: set[str] = set()

STALE_EMBEDDING = "Embedding stopped because the API restarted. Rebuild to try again. Keyword search still works."


def mark_active(version_id: UUID) -> None:
    _active.add(str(version_id))


def clear_active(version_id: UUID) -> None:
    _active.discard(str(version_id))


def is_active(version_id: UUID) -> bool:
    return str(version_id) in _active
