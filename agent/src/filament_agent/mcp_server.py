"""MCP server exposing a user's spools and prints as tools.

The agent connects to it in-process, but it is a normal MCP server: run
``ft-mcp`` (stdio) and point Claude Desktop or any other MCP client at it.

Tool annotations matter here: the agent treats every tool that is not
``readOnlyHint=True`` as a write and asks the user before running it.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .models import Feasibility, PrintList, Spool, SpoolList, UsageSummary, WriteResult
from .repository import FilamentService, FixtureBackend

F = TypeVar("F", bound=Callable[..., Any])

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
CORRECT = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)

INSTRUCTIONS = """\
Tools over one user's 3D-printing filament data from Filament Tracker.
Weights are grams. Print weights are slicer estimates, so tracked remaining
grams drift from reality; check_print_feasibility adds a safety margin.
Only loaded (active) spools are used for feasibility checks."""


def _friendly(fn: F) -> F:
    """Turn expected errors into ToolError so the model sees a useful message."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except (LookupError, ValueError) as e:
            raise ToolError(str(e)) from e

    return wrapper  # type: ignore[return-value]


def build_server(service: FilamentService) -> MCPServer:
    # WARNING: MCPServer configures root logging, and INFO would print every HTTP request.
    server = MCPServer("filament-tracker", instructions=INSTRUCTIONS, version="0.1.0", log_level="WARNING")

    @server.tool(annotations=READ)
    @_friendly
    def list_spools(include_archived: bool = False) -> SpoolList:
        """List the user's spools with remaining grams. Loaded spools only unless include_archived."""
        return service.list_spools(include_archived)

    @server.tool(annotations=READ)
    @_friendly
    def get_spool(spool_id: int) -> Spool:
        """Get one spool (loaded or archived) by id."""
        return service.get_spool(spool_id)

    @server.tool(annotations=READ)
    @_friendly
    def list_prints(
        limit: int = 20, spool_id: int | None = None, days: int | None = None, include_ignored: bool = False
    ) -> PrintList:
        """Recent print jobs, newest first. Filter by spool or by the last N days.
        Ignored (failed or excluded) prints are hidden unless include_ignored."""
        return service.list_prints(limit, spool_id, days, include_ignored)

    @server.tool(annotations=READ)
    @_friendly
    def usage_summary(days: int = 30) -> UsageSummary:
        """Grams used over the last N days, by material and per loaded spool,
        with average grams/day and estimated days until each spool runs out."""
        return service.usage_summary(days)

    @server.tool(annotations=READ)
    @_friendly
    def check_print_feasibility(
        grams: float,
        material: str | None = None,
        color: str | None = None,
        spool_id: int | None = None,
        safety_margin_pct: float = 10.0,
    ) -> Feasibility:
        """Check whether a print needing `grams` fits on a loaded spool.
        Filter by material (e.g. PETG), colour name (e.g. black) or a specific spool.
        Verdicts: yes (fits with the safety margin), tight (fits only without it), no."""
        return service.check_feasibility(grams, material, color, spool_id, safety_margin_pct)

    @server.tool(annotations=WRITE)
    @_friendly
    def log_print(title: str, grams: float, slot: int) -> WriteResult:
        """Record a print that Bambu Cloud didn't capture, charged to the spool loaded in `slot`.
        Changes the user's data."""
        return service.log_print(title, grams, slot)

    @server.tool(annotations=CORRECT)
    @_friendly
    def correct_spool_weight(spool_id: int, measured_g: float, note: str = "corrected via agent") -> WriteResult:
        """Set a spool's remaining filament to a weighed value (filament only, without the empty spool).
        Changes the user's data."""
        return service.correct_spool(spool_id, measured_g, note)

    return server


def service_from_env() -> FilamentService:
    """FT_FIXTURE=<path> for demo data; otherwise the signed-in Supabase user."""
    fixture = os.environ.get("FT_FIXTURE")
    if fixture:
        return FilamentService(FixtureBackend.from_file(fixture))
    from .auth import supabase_backend

    return FilamentService(supabase_backend())


def main() -> None:
    build_server(service_from_env()).run("stdio")


if __name__ == "__main__":
    main()
