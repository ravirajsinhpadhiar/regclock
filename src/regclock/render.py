"""Human table and iCalendar output."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def _left(hours: float | None) -> str:
    if hours is None:
        return "-"
    sign, h = ("-" if hours < 0 else ""), abs(hours)
    if h >= 48:
        return f"{sign}{h / 24:.1f} d"
    return f"{sign}{int(h)} h {int(round((h - int(h)) * 60)):02d} m"


def table(rep: dict[str, Any]) -> str:
    rows = [("DUE (as entered offset)", "LEFT", "STATUS", "REGIME", "REPORT")]
    for d in rep["deadlines"]:
        due = d["due"][:16].replace("T", " ") + d["due"][-6:] if d["due"] else f"needs --{d['missing']}"
        if d["projected"]:
            due += " *"
        rows.append((due, _left(d["hours_left"]), d["status"], d["regime"], d["label"]))
    widths = [max(len(r[i]) for r in rows) for i in range(5)]
    lines = ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))
    out = [f"As of {rep['now'][:16].replace('T', ' ')}{rep['now'][-6:]}", "", *lines]
    if any(d["projected"] for d in rep["deadlines"]):
        out += ["", "* projected from an earlier deadline; record the actual submission time to firm it up"]
    out.append("")
    for regime, caveats in rep["caveats"].items():
        for c in caveats:
            out.append(f"[{regime}] {c}")
    out += ["", rep["disclaimer"]]
    return "\n".join(out)


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: lines over 75 octets are folded with CRLF + space."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, chunk = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(chunk) + len(b) > (75 if not parts else 74):
            parts.append(chunk.decode("utf-8"))
            chunk = b""
        chunk += b
    parts.append(chunk.decode("utf-8"))
    return "\r\n ".join(parts)


def ics(rep: dict[str, Any]) -> str:
    """One calendar event per computable deadline, with alarms 60 and 15 minutes before."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//regclock//EN", "CALSCALE:GREGORIAN"]
    for d in rep["deadlines"]:
        if not d["due_utc"]:
            continue
        due = datetime.fromisoformat(d["due_utc"]).strftime("%Y%m%dT%H%M%SZ")
        uid = hashlib.sha1(f"{d['regime']}{d['obligation']}{due}".encode()).hexdigest()[:20]
        summary = f"{d['regime'].upper()}: {d['label']} due" + (" (projected)" if d["projected"] else "")
        desc = f"{d['rule']}\nBasis: {d['basis']}\nSource: {d['cite']}\nNot legal advice."
        lines += [
            "BEGIN:VEVENT", f"UID:{uid}@regclock", f"DTSTAMP:{stamp}",
            f"DTSTART:{due}", f"DTEND:{due}",
            f"SUMMARY:{_ics_escape(summary)}", f"DESCRIPTION:{_ics_escape(desc)}",
        ]
        for minutes in (60, 15):
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_escape(summary)}",
                      f"TRIGGER:-PT{minutes}M", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
