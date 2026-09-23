"""Handler registration — importing this package registers all @router handlers."""

from __future__ import annotations

from app import forcejoin  # noqa: F401 — registers the join: callback handler
from app.handlers import (  # noqa: F401
    delete,
    expire,
    help_cmd,
    list_files,
    ping,
    start,
    stats,
    upload,
)
