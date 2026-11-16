# regclock

When is each incident report due? `regclock` takes the times of an incident and returns every regulatory reporting deadline, sorted, with the legal citation beside each one.

```console
$ regclock deadlines -r dora,finma,cert-in --aware 2026-11-17T09:00+01:00 --classified 2026-11-17T10:30+01:00
```

It is a deadline calculator. It does not decide whether an incident is reportable, and it is not legal advice.

## Regimes

| Id | Regime | Reports tracked |
|---|---|---|
| `dora` | EU DORA, major ICT-related incident | Initial 4 h after classification (24 h cap), intermediate 72 h, final 1 month |
| `nis2` | EU NIS2, significant incident | Early warning 24 h, notification 72 h, final report 1 month |
| `gdpr` | EU GDPR, personal data breach | Supervisory authority 72 h |
| `finma` | Switzerland, FINMA cyber attack report | Initial 24 h, full report 72 h |
| `ch-isa` | Switzerland, Information Security Act (NCSC) | Initial 24 h, completion 14 days |
| `cert-in` | India, CERT-In Directions 2022 | Report 6 h |

Every rule sits in one data file, [`src/regclock/rules.json`](src/regclock/rules.json), with its article and a link to the official text. Rules were last reviewed on 17 November 2026. `regclock show dora` prints a regime's rules, caveats and sources.

## Install

```bash
pip install git+https://github.com/ravirajsinhpadhiar/regclock
```

Python 3.10 or newer, no dependencies. For the MCP server: `pip install "regclock[mcp] @ git+https://github.com/ravirajsinhpadhiar/regclock"`.

## Use

```bash
regclock regimes
regclock deadlines --aware 2026-11-17T09:00+01:00                    # all regimes
regclock deadlines -r dora --aware 2026-11-17T09:00+01:00 \
    --classified 2026-11-17T10:30+01:00 \
    --initial-submitted 2026-11-17T13:00+01:00                       # firm up later reports
regclock deadlines -r dora,nis2 --aware 2026-11-17T09:00+01:00 --ics incident.ics
regclock deadlines -r cert-in --aware 2026-11-17T22:15+05:30 --json
```

Times must carry a UTC offset (`+01:00`, `+05:30`, `Z`). A time without one is rejected, because the deadline would be ambiguous.

`--ics` writes a calendar file with one event per deadline and reminders 60 and 15 minutes before; import it into Outlook, Google Calendar or Apple Calendar.

## How the clock works

- **Chained reports.** Under DORA the intermediate report is due 72 hours after the initial notification *was submitted*. Until you pass `--initial-submitted`, regclock projects from the initial deadline and marks the result with `*`. Recording the real submission time moves the later deadlines earlier.
- **Caps.** The DORA initial notification is due 4 hours after classification but never later than 24 hours after awareness. regclock shows whichever comes first and says which rule set the time.
- **One month** means the same day of the next month, clamped to the month's last day.
- **Conservative where rules allow extensions.** DORA's weekend and public-holiday relief and FINMA's bank-working-day counting are not applied. The time shown is never later than the legal deadline under those reliefs; the caveats printed with each run explain this.

## Use from an AI agent (MCP)

```bash
regclock mcp
claude mcp add regclock -- regclock mcp     # Claude Code
```

Tools: `list_regimes`, `regime_rules`, `incident_deadlines`. The point is that the agent reads deadlines from cited rules instead of recalling them.

## Develop

```bash
git clone https://github.com/ravirajsinhpadhiar/regclock && cd regclock
pip install -e ".[dev]"
pytest
```

## Adding or correcting a rule

Edit `rules.json`. An obligation needs a `rule` in words, a `cite`, and an `after` block naming the event the clock runs from. A test checks that every rule has a citation and an `https` source. Corrections with a link to the official text are welcome.

## Limits

- NIS2 is a directive: the binding deadlines are in each Member State's transposition.
- Sector rules not yet covered include RBI and SEBI (India), SEC Form 8-K Item 1.05 (US) and MAS (Singapore).
- FINMA's root cause analysis has no fixed hour limit in the guidance, so it is not scheduled.

## Licence

MIT.
