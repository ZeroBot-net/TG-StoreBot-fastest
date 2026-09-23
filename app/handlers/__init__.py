"""Handler registration — importing this package registers all @router.message handlers."""

from __future__ import annotations

from app.handlers import (  # noqa: F401
    delete,
    help_cmd,
    list_files,
    ping,
    start,
    stats,
    upload,
)
