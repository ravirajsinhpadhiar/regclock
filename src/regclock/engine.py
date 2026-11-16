"""Deadline arithmetic. Rules live in rules.json; this module only does the maths.

Events an incident can carry (all timezone-aware datetimes):
    aware                   when the organisation became aware of / detected the incident
    classified              when it was classified as major (DORA)
    initial_submitted       when the initial notification was actually sent
    intermediate_submitted  when the latest intermediate report was actually sent
    notification_submitted  when the NIS2 incident notification was actually sent
"""
from __future__ import annotations

import calendar
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from importlib import resources
from typing import Any

EVENTS = ("aware", "classified", "initial_submitted", "intermediate_submitted", "notification_submitted")


def load_rules() -> dict[str, Any]:
    return json.loads(resources.files("regclock").joinpath("rules.json").read_text("utf-8"))


def regime_ids() -> list[str]:
    return [r["id"] for r in load_rules()["regimes"]]


def get_regime(regime_id: str) -> dict[str, Any]:
    for r in load_rules()["regimes"]:
        if r["id"] == regime_id.lower():
            return r
    raise KeyError(f"unknown regime '{regime_id}'. Known: {', '.join(regime_ids())}")


def parse_time(text: str) -> datetime:
    """ISO 8601 with an explicit offset, e.g. 2026-11-17T09:30+01:00 or ...Z."""
    dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(
            f"'{text}' has no timezone. Add an offset such as +05:30 or Z; "
            "a reporting deadline is meaningless without one."
        )
    return dt


def add_months(dt: datetime, months: int) -> datetime:
    """Same day-of-month N months on, clamped to the month's last day (31 Jan + 1 month = 28/29 Feb)."""
    index = dt.month - 1 + months
    year, month = dt.year + index // 12, index % 12 + 1
    return dt.replace(year=year, month=month, day=min(dt.day, calendar.monthrange(year, month)[1]))


@dataclass
class Deadline:
    regime: str
    regime_name: str
    obligation: str
    label: str
    due: datetime | None
    rule: str
    cite: str
    basis: str  # how `due` was derived, in words
    projected: bool = False  # True when it rests on a deadline, not on an actual submission
    missing: str | None = None  # event needed to compute it
    notes: list[str] = field(default_factory=list)

    def status(self, now: datetime) -> str:
        if self.due is None:
            return "needs input"
        left = self.due - now
        if left < timedelta(0):
            return "OVERDUE"
        if left <= timedelta(hours=4):
            return "due soon"
        return "open"

    def as_dict(self, now: datetime) -> dict[str, Any]:
        left = (self.due - now).total_seconds() / 3600 if self.due else None
        return {
            "regime": self.regime,
            "regime_name": self.regime_name,
            "obligation": self.obligation,
            "label": self.label,
            "due": self.due.isoformat() if self.due else None,
            "due_utc": self.due.astimezone(timezone.utc).isoformat() if self.due else None,
            "hours_left": round(left, 2) if left is not None else None,
            "status": self.status(now),
            "projected": self.projected,
            "basis": self.basis,
            "missing": self.missing,
            "rule": self.rule,
            "cite": self.cite,
            "notes": self.notes,
        }


def _offset(start: datetime, spec: dict[str, Any]) -> datetime:
    due = start
    if "hours" in spec:
        due += timedelta(hours=spec["hours"])
    if "then_days" in spec:
        due += timedelta(days=spec["then_days"])
    if "months" in spec:
        due = add_months(due, spec["months"])
    return due


def _span(spec: dict[str, Any]) -> str:
    parts = []
    if "hours" in spec:
        parts.append(f"{spec['hours']} h")
    if "then_days" in spec:
        parts.append(f"{spec['then_days']} days")
    if "months" in spec:
        parts.append(f"{spec['months']} month")
    return " + ".join(parts)


def compute(regime_id: str, events: dict[str, datetime]) -> list[Deadline]:
    regime = get_regime(regime_id)
    done: dict[str, Deadline] = {}
    out: list[Deadline] = []
    for ob in regime["obligations"]:
        after, cap = ob["after"], ob.get("cap")
        d = Deadline(
            regime=regime["id"], regime_name=regime["name"], obligation=ob["id"],
            label=ob["label"], due=None, rule=ob["rule"], cite=ob["cite"], basis="",
        )
        start = events.get(after["event"])
        if start is not None:
            d.due = _offset(start, after)
            d.basis = f"{after['event']} + {_span(after)}"
        elif after.get("else_obligation") and done[after["else_obligation"]].due is not None:
            # Not submitted yet: project from the latest moment the earlier report may be sent.
            prior = done[after["else_obligation"]]
            d.due = _offset(prior.due, after)
            d.projected = True
            d.basis = f"deadline of '{prior.label}' + {_span(after)}"
            d.notes.append(
                f"Projected: counts from the deadline of '{prior.label}'. It moves earlier "
                f"once you record the actual submission time ({after['event']})."
            )
        else:
            d.missing = after["event"]

        if cap is not None:
            cap_start = events.get(cap["event"])
            if cap_start is not None:
                cap_due = cap_start + timedelta(hours=cap["hours"])
                if d.due is None:
                    d.due, d.missing = cap_due, None
                    d.basis = f"{cap['event']} + {cap['hours']} h (outer limit)"
                    d.notes.append(
                        f"Outer limit only. Once '{after['event']}' is recorded the deadline "
                        f"becomes {_span(after)} after it, if that is earlier."
                    )
                elif cap_due < d.due:
                    d.due = cap_due
                    d.basis = f"{cap['event']} + {cap['hours']} h (outer limit, earlier than {d.basis})"
        done[ob["id"]] = d
        out.append(d)
    return out


def compute_all(regimes: list[str], events: dict[str, datetime]) -> list[Deadline]:
    deadlines = [d for r in regimes for d in compute(r, events)]
    far = datetime.max.replace(tzinfo=timezone.utc)
    return sorted(deadlines, key=lambda d: d.due or far)


def report(regimes: list[str], events: dict[str, datetime], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    rules = load_rules()
    return {
        "now": now.isoformat(),
        "events": {k: v.isoformat() for k, v in events.items()},
        "deadlines": [d.as_dict(now) for d in compute_all(regimes, events)],
        "caveats": {r: get_regime(r)["caveats"] for r in regimes},
        "sources": {r: get_regime(r)["sources"] for r in regimes},
        "rules_reviewed": rules["reviewed"],
        "disclaimer": "Deadline calculator, not legal advice. It does not decide whether an "
        "incident is reportable. Check the cited text and your regulator before relying on it.",
    }
