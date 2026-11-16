"""MCP server so an AI agent can answer 'when is this report due?' from rules, not from memory."""
from __future__ import annotations

from typing import Any

from . import engine

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

server = _Server("regclock")


@server.tool()
def list_regimes() -> list[dict[str, str]]:
    """List the incident-reporting regimes regclock knows, with jurisdiction and scope."""
    return [
        {"id": r["id"], "name": r["name"], "jurisdiction": r["jurisdiction"],
         "authority": r["authority"], "applies_to": r["applies_to"]}
        for r in engine.load_rules()["regimes"]
    ]


@server.tool()
def regime_rules(regime: str) -> dict[str, Any]:
    """Full rules for one regime: each report, its time limit, the legal citation,
    caveats and source links."""
    return engine.get_regime(regime)


@server.tool()
def incident_deadlines(
    aware: str,
    regimes: list[str] | None = None,
    classified: str | None = None,
    initial_submitted: str | None = None,
    intermediate_submitted: str | None = None,
    notification_submitted: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Compute report deadlines for an incident.

    All times are ISO 8601 with a UTC offset (2026-11-17T09:30+01:00).
    `aware` is when the organisation became aware of the incident. `classified`
    is when it was classified as major (DORA). The *_submitted times are when
    reports were actually sent; without them later deadlines are projected and
    marked as such. `regimes` defaults to all. This does not decide whether the
    incident is reportable.
    """
    given = {
        "aware": aware, "classified": classified, "initial_submitted": initial_submitted,
        "intermediate_submitted": intermediate_submitted,
        "notification_submitted": notification_submitted,
    }
    events = {k: engine.parse_time(v) for k, v in given.items() if v}
    return engine.report(regimes or engine.regime_ids(), events, engine.parse_time(now) if now else None)


def run() -> None:
    server.run()
