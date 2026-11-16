import json
from datetime import datetime, timedelta, timezone

import pytest

from regclock import engine, render
from regclock.cli import main

CET = timezone(timedelta(hours=1))
IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 11, 17, 9, 0, tzinfo=CET)


def by_id(deadlines):
    return {d.obligation: d for d in deadlines}


def test_dora_initial_is_four_hours_after_classification():
    d = by_id(engine.compute("dora", {"aware": T0, "classified": T0 + timedelta(hours=2)}))
    assert d["initial"].due == T0 + timedelta(hours=6)
    assert not d["initial"].projected


def test_dora_initial_capped_at_24h_from_awareness():
    d = by_id(engine.compute("dora", {"aware": T0, "classified": T0 + timedelta(hours=23)}))
    assert d["initial"].due == T0 + timedelta(hours=24)
    assert "outer limit" in d["initial"].basis


def test_dora_without_classification_shows_outer_limit_and_says_so():
    d = by_id(engine.compute("dora", {"aware": T0}))
    assert d["initial"].due == T0 + timedelta(hours=24)
    assert d["initial"].missing is None and d["initial"].notes


def test_dora_chain_is_projected_until_submissions_are_recorded():
    d = by_id(engine.compute("dora", {"aware": T0, "classified": T0}))
    assert d["intermediate"].projected and d["intermediate"].due == T0 + timedelta(hours=76)
    assert d["final"].projected and d["final"].due == engine.add_months(T0 + timedelta(hours=76), 1)

    sent = T0 + timedelta(hours=1)
    d = by_id(engine.compute("dora", {"aware": T0, "classified": T0, "initial_submitted": sent}))
    assert not d["intermediate"].projected and d["intermediate"].due == sent + timedelta(hours=72)

    inter = sent + timedelta(hours=50)
    d = by_id(engine.compute("dora", {"aware": T0, "classified": T0, "initial_submitted": sent,
                                      "intermediate_submitted": inter}))
    assert not d["final"].projected and d["final"].due == engine.add_months(inter, 1)


def test_nis2_deadlines():
    d = by_id(engine.compute("nis2", {"aware": T0}))
    assert d["early_warning"].due == T0 + timedelta(hours=24)
    assert d["notification"].due == T0 + timedelta(hours=72)
    assert d["final"].projected
    sent = T0 + timedelta(hours=30)
    d = by_id(engine.compute("nis2", {"aware": T0, "notification_submitted": sent}))
    assert d["final"].due == datetime(2026, 12, 18, 15, 0, tzinfo=CET)


def test_single_step_regimes():
    aware = datetime(2026, 11, 17, 22, 15, tzinfo=IST)
    assert engine.compute("cert-in", {"aware": aware})[0].due == datetime(2026, 11, 18, 4, 15, tzinfo=IST)
    assert engine.compute("gdpr", {"aware": T0})[0].due == T0 + timedelta(hours=72)
    finma = by_id(engine.compute("finma", {"aware": T0}))
    assert finma["initial"].due == T0 + timedelta(hours=24)
    assert finma["report"].due == T0 + timedelta(hours=72)
    isa = by_id(engine.compute("ch-isa", {"aware": T0}))
    assert isa["completion"].due == T0 + timedelta(hours=24) + timedelta(days=14)


@pytest.mark.parametrize("start,expected", [
    (datetime(2026, 1, 31, 10, tzinfo=timezone.utc), datetime(2026, 2, 28, 10, tzinfo=timezone.utc)),
    (datetime(2028, 1, 31, 10, tzinfo=timezone.utc), datetime(2028, 2, 29, 10, tzinfo=timezone.utc)),
    (datetime(2026, 12, 15, 10, tzinfo=timezone.utc), datetime(2027, 1, 15, 10, tzinfo=timezone.utc)),
])
def test_add_months_clamps_and_rolls_year(start, expected):
    assert engine.add_months(start, 1) == expected


def test_naive_time_is_rejected():
    with pytest.raises(ValueError, match="no timezone"):
        engine.parse_time("2026-11-17T09:00")
    assert engine.parse_time("2026-11-17T09:00Z").tzinfo is not None


def test_unknown_regime():
    with pytest.raises(KeyError):
        engine.compute("sox", {"aware": T0})


def test_report_sorts_across_regimes_and_flags_status():
    rep = engine.report(engine.regime_ids(), {"aware": T0}, now=T0 + timedelta(hours=7))
    dues = [d["due_utc"] for d in rep["deadlines"] if d["due_utc"]]
    assert dues == sorted(dues)
    first = rep["deadlines"][0]
    assert first["regime"] == "cert-in" and first["status"] == "OVERDUE" and first["hours_left"] == -1.0
    assert rep["sources"]["dora"][1]["url"].startswith("https://eur-lex.europa.eu/")


def test_every_rule_has_a_citation_and_source():
    for regime in engine.load_rules()["regimes"]:
        assert regime["sources"] and all(s["url"].startswith("https://") for s in regime["sources"])
        for ob in regime["obligations"]:
            assert ob["cite"] and ob["rule"]
            assert ob["after"]["event"] in engine.EVENTS


def test_table_and_ics_render(tmp_path):
    rep = engine.report(["dora", "cert-in"], {"aware": T0}, now=T0)
    text = render.table(rep)
    assert "Initial notification" in text and "*" in text and "not legal advice" in text
    cal = render.ics(rep)
    assert cal.count("BEGIN:VEVENT") == 4 and "DTSTART:20261117T140000Z" in cal
    assert all(len(line.encode()) <= 75 for line in cal.split("\r\n"))


def test_cli(capsys, tmp_path):
    ics = tmp_path / "incident.ics"
    assert main(["deadlines", "-r", "dora,nis2", "--aware", "2026-11-17T09:00+01:00",
                 "--now", "2026-11-17T10:00+01:00", "--json", "--ics", str(ics)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert {d["regime"] for d in out["deadlines"]} == {"dora", "nis2"}
    assert ics.read_text().startswith("BEGIN:VCALENDAR")
    with pytest.raises(SystemExit) as exc:
        main(["deadlines", "--aware", "2026-11-17T09:00"])
    assert exc.value.code == 2
