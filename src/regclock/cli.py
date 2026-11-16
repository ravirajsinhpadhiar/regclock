from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, engine, render


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="regclock",
        description="When is each incident report due? DORA, NIS2, GDPR, FINMA, Swiss ISA, CERT-In.",
    )
    p.add_argument("--version", action="version", version=f"regclock {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("regimes", help="list supported regimes")

    s = sub.add_parser("show", help="print one regime's rules, caveats and sources")
    s.add_argument("regime")

    s = sub.add_parser("deadlines", help="compute deadlines for an incident")
    s.add_argument("--regimes", "-r", default="all",
                   help="comma-separated ids (see 'regclock regimes'), default all")
    s.add_argument("--aware", required=True, metavar="TIME",
                   help="when you became aware of the incident, ISO 8601 with offset")
    s.add_argument("--classified", metavar="TIME", help="when it was classified as major (DORA)")
    s.add_argument("--initial-submitted", metavar="TIME", help="when the DORA initial notification was sent")
    s.add_argument("--intermediate-submitted", metavar="TIME",
                   help="when the latest DORA intermediate report was sent")
    s.add_argument("--notification-submitted", metavar="TIME",
                   help="when the NIS2 incident notification was sent")
    s.add_argument("--now", metavar="TIME", help="evaluate as of this time (default: current time)")
    s.add_argument("--json", action="store_true", help="JSON instead of a table")
    s.add_argument("--ics", metavar="FILE", help="also write the deadlines as a calendar file")

    sub.add_parser("mcp", help="run as an MCP server over stdio")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "mcp":
        from .mcp_server import run

        run()
        return 0

    if args.command == "regimes":
        for r in engine.load_rules()["regimes"]:
            print(f"{r['id']:<8} {r['jurisdiction']:<12} {r['name']}")
        return 0

    try:
        if args.command == "show":
            print(json.dumps(engine.get_regime(args.regime), indent=2, ensure_ascii=False))
            return 0

        regimes = engine.regime_ids() if args.regimes == "all" else [
            r.strip().lower() for r in args.regimes.split(",") if r.strip()
        ]
        events = {
            name: engine.parse_time(value)
            for name in engine.EVENTS
            if (value := getattr(args, name)) is not None
        }
        now = engine.parse_time(args.now) if args.now else None
        rep = engine.report(regimes, events, now)
    except (KeyError, ValueError) as exc:
        parser.exit(2, f"regclock: {exc.args[0] if exc.args else exc}\n")

    if args.ics:
        Path(args.ics).write_text(render.ics(rep), encoding="utf-8", newline="")
    print(json.dumps(rep, indent=2, ensure_ascii=False) if args.json else render.table(rep))
    if args.ics:
        print(f"\nCalendar written to {args.ics}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
