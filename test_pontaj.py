"""
Teste de regresie pentru tot ce se poate verifica fara browser.

    python3 -m unittest -v          # sau: python3 test_pontaj.py

Ce acopera: parsarea a tot ce scrie omul (perioade, ore, zile), regulile de
plan (oncall, overtime, sarbatori, concediu - cele din emailul HR),
saptamanile atinse, impartirea pe coduri de claim, ce trimite interfata
scriptului (inclusiv ziua de birou cu "Ponteaza saptamana"), forma
intrarilor din SuccessFactors si cititul textelor SAP (antete, randuri,
sectiuni) cu texte luate de pe pagina reala, verificarea Time@IBM <-> SF, si
actualizarea automata. Ce nu se poate verifica aici - pagina insasi - se
verifica cu "Doar verifica" din interfata.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

import gui
import pontaj_ibm as P
import sf_ibm as S
import update

WE = date(2026, 9, 18)                       # vineri, saptamana 12-18 Sep 2026
WEEK = P.week_days(WE)
SAT, SUN, MON, TUE, WED, THU, FRI = WEEK


def capture(fn, *args, **kwargs):
    """Ruleaza fn si intoarce (rezultat, textul scris in jurnal)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*args, **kwargs)
    return result, buf.getvalue()


class FakeFrame:
    """Un iframe SF redus la textul lui, pentru functiile care doar citesc."""

    def __init__(self, text: str) -> None:
        self.text = text

    def locator(self, *_a, **_k):
        return self

    def filter(self, *_a, **_k):
        return self

    @property
    def first(self):
        return self

    def inner_text(self) -> str:
        return self.text


# --------------------------------------------------------------------------
# Ce scrie omul
# --------------------------------------------------------------------------

class ParseOncall(unittest.TestCase):
    def test_formats(self):
        for raw in ("16-22", "16 - 22", "16–22", "16 22", "sep 16 - sep 22",
                    "16 sep - 22 sep", "2026-09-16:2026-09-22"):
            self.assertEqual(P.parse_oncall(raw, WE), (WED, date(2026, 9, 22)), raw)

    def test_nearest_month(self):
        # "28-3" de pe o saptamana din septembrie e 28 Aug - 3 Sep
        self.assertEqual(P.parse_oncall("28-3", date(2026, 9, 4)),
                         (date(2026, 8, 28), date(2026, 9, 3)))

    def test_refuses_garbage(self):
        for raw in ("", "abc", "16..22"):
            with self.assertRaises(ValueError):
                P.parse_oncall(raw, WE)


class ParseOvertime(unittest.TestCase):
    def test_days_and_hours(self):
        got = P.parse_overtime("12=4, joi=1.5; mie 2", WEEK)
        self.assertEqual(got, {SAT: "4", THU: "1.5", WED: "2"})

    def test_decimal_comma(self):
        self.assertEqual(P.parse_overtime("16=2,5; 17=1", WEEK), {WED: "2.5", THU: "1"})

    def test_start_time(self):
        full = P.parse_overtime_full("12=4@20:00, 13=4, 16=2@8pm, 17=1.5@7:30", WEEK)
        self.assertEqual(full[SAT], ("4", "08:00 PM"))
        self.assertEqual(full[SUN], ("4", None))
        self.assertEqual(full[WED], ("2", "08:00 PM"))
        self.assertEqual(full[THU], ("1.5", "07:30 AM"))
        self.assertEqual(P.parse_overtime_starts("12=4@20:00, 13=4", WEEK), {SAT: "08:00 PM"})

    def test_refuses(self):
        for raw in ("12=0", "40=3", "12=4@25:00", "12=4@abc", "luni"):
            with self.assertRaises(ValueError):
                P.parse_overtime_full(raw, WEEK)

    def test_empty(self):
        self.assertEqual(P.parse_overtime("", WEEK), {})


class ParseDays(unittest.TestCase):
    def test_single_range_names(self):
        self.assertEqual(P.parse_days("15", WEEK), [TUE])
        self.assertEqual(P.parse_days("14-16", WEEK), [MON, TUE, WED])
        self.assertEqual(P.parse_days("luni, marti", WEEK), [MON, TUE])
        self.assertEqual(P.parse_days("wed", WEEK), [WED])

    def test_weekend(self):
        with self.assertRaises(ValueError):
            P.parse_days("19", WEEK, P.absence_window(WE))     # sambata singura: refuzata
        days = P.parse_days("17-23", WEEK, P.absence_window(WE))
        self.assertEqual([d.day for d in days], [17, 18, 21, 22, 23])   # in interval: sarita

    def test_window(self):
        with self.assertRaises(ValueError):
            P.parse_days("23", WEEK)                              # fara fereastra
        self.assertEqual(P.parse_days("23", WEEK, P.absence_window(WE)), [date(2026, 9, 23)])

    def test_merge_conflict(self):
        with self.assertRaises(ValueError):
            P.merge_absences([MON], [MON], [])
        self.assertEqual(P.merge_absences([MON], [TUE], [WED]),
                         {MON: P.VACATION_LABEL, TUE: P.HOLIDAY_LABEL, WED: P.COMP_LABEL})


class OfficeDays(unittest.TestCase):
    def test_three_week_window(self):
        self.assertEqual(P.office_days("17", WE), [THU])
        self.assertEqual(P.office_days("luni, 11, 22", WE),
                         [date(2026, 9, 11), MON, date(2026, 9, 22)])

    def test_weekend_refused(self):
        with self.assertRaises(ValueError):
            P.office_days("19", WE)


# --------------------------------------------------------------------------
# Planul
# --------------------------------------------------------------------------

class BuildPlan(unittest.TestCase):
    def test_simple_week(self):
        plan = P.build_plan(WEEK, None)
        for d in (MON, TUE, WED, THU, FRI):
            self.assertEqual(plan[d][P.REGULAR_LABEL], "8")
            self.assertEqual(plan[d][P.STANDBY_LABEL], "")
        for d in (SAT, SUN):
            self.assertEqual(plan[d][P.REGULAR_LABEL], "")

    def test_oncall(self):
        plan = P.build_plan(WEEK, (SAT, WED))
        self.assertEqual(plan[SAT][P.STANDBY_LABEL], "24")
        self.assertEqual(plan[SUN][P.STANDBY_LABEL], "24")
        self.assertEqual(plan[MON][P.STANDBY_LABEL], "15.5")
        self.assertEqual(plan[WED][P.STANDBY_LABEL], "15.5")
        self.assertEqual(plan[THU][P.STANDBY_LABEL], "")

    def test_standby_minus_overtime(self):
        plan = P.build_plan(WEEK, (SAT, FRI), {THU: "3", SAT: "4"})
        self.assertEqual(plan[THU][P.STANDBY_LABEL], "12.5")
        self.assertEqual(plan[SAT][P.STANDBY_LABEL], "20")
        self.assertEqual(plan[THU][P.OVERTIME_LABEL], "3")

    def test_holiday_hr_cases(self):
        hol = {MON: P.HOLIDAY_LABEL}
        # 1. nu lucrezi
        plan = P.build_plan(WEEK, None, {}, hol)
        self.assertEqual((plan[MON][P.REGULAR_LABEL], plan[MON][P.HOLIDAY_LABEL],
                          plan[MON][P.STANDBY_LABEL]), ("", "8", ""))
        # 2a. overtime
        plan = P.build_plan(WEEK, None, {MON: "8"}, hol)
        self.assertEqual(plan[MON][P.OVERTIME_LABEL], "8")
        # 2b. overtime + oncall -> 8 stand by
        plan = P.build_plan(WEEK, (MON, MON), {MON: "8"}, hol)
        self.assertEqual(plan[MON][P.STANDBY_LABEL], "8")
        # 2c. doar oncall -> 16 stand by, restul saptamanii 15.5
        plan = P.build_plan(WEEK, (MON, WED), {}, hol)
        self.assertEqual(plan[MON][P.STANDBY_LABEL], "16")
        self.assertEqual(plan[TUE][P.STANDBY_LABEL], "15.5")
        # 2d. compensatie in alta zi
        plan = P.build_plan(WEEK, None, {MON: "8"}, P.merge_absences([], [MON], [THU]))
        self.assertEqual((plan[THU][P.COMP_LABEL], plan[THU][P.REGULAR_LABEL]), ("8", ""))

    def test_vacation_no_standby(self):
        plan = P.build_plan(WEEK, (MON, TUE), {}, {MON: P.VACATION_LABEL})
        self.assertEqual((plan[MON][P.VACATION_LABEL], plan[MON][P.REGULAR_LABEL],
                          plan[MON][P.STANDBY_LABEL]), ("8", "", ""))
        self.assertEqual(plan[TUE][P.STANDBY_LABEL], "15.5")


class Weeks(unittest.TestCase):
    def test_friday_of(self):
        self.assertEqual(P.friday_of(SAT), WE)          # sambata e in saptamana urmatoare
        self.assertEqual(P.friday_of(FRI), WE)
        self.assertEqual(P.friday_of(date(2026, 9, 11)), date(2026, 9, 11))

    def test_weeks_touched(self):
        self.assertEqual(P.weeks_touched(WE, (date(2026, 9, 16), date(2026, 9, 22))), [date(2026, 9, 25)])
        self.assertEqual(P.weeks_touched(WE, (date(2026, 9, 10), WE)), [date(2026, 9, 11)])
        self.assertEqual(P.weeks_touched(WE, (WED, FRI)), [])
        self.assertEqual(P.weeks_touched(WE, None, {date(2026, 9, 23): P.VACATION_LABEL}),
                         [date(2026, 9, 25)])

    def test_audit_weeks(self):
        w = P.audit_weeks(WE)
        self.assertEqual(len(w), 12)
        self.assertEqual((w[0], w[-1]), (date(2026, 7, 3), WE))
        w = P.audit_weeks(date(2026, 2, 10))
        self.assertTrue(all(f.year == 2026 for f in w))
        self.assertEqual(w[0], date(2026, 1, 2))

    def test_week_label(self):
        self.assertEqual(P.week_label(WE), "September 18, 2026")
        self.assertEqual(P.week_label(date(2026, 10, 2)), "October 2, 2026")


class ClaimCodes(unittest.TestCase):
    A = {"account": "C.1", "task": "GB0020", "name": "A", "bill": "no-bc"}

    def test_default_project(self):
        p = P.default_project(self.A)
        self.assertEqual(p["regular"], {k: "8" for k in P.WEEKDAY_KEYS})
        self.assertTrue(p["standby"] and p["overtime"])
        self.assertEqual(P.project_key(p), "C.1|GB0020")
        self.assertEqual(P.project_title(p), "GB0020 – A")

    def test_split_two_codes(self):
        plan = P.build_plan(WEEK, (WED, FRI), {SAT: "4"}, {TUE: P.VACATION_LABEL})
        a = {**self.A, "regular": {"mon": "3", "tue": "3", "wed": "3", "thu": "0", "fri": ""},
             "standby": True, "overtime": False}
        b = {"account": "C.2", "task": "GB0010", "name": "B", "bill": "no-bc",
             "regular": {"mon": "5", "tue": "5", "wed": "5", "thu": "8", "fri": "8"},
             "standby": False, "overtime": True}
        sp = P.split_plan(plan, [a, b], WEEK)
        self.assertEqual(sp["C.1|GB0020"][MON][P.REGULAR_LABEL], "3")
        self.assertEqual(sp["C.2|GB0010"][MON][P.REGULAR_LABEL], "5")
        self.assertEqual(sp["C.1|GB0020"][THU][P.REGULAR_LABEL], "")
        self.assertEqual(sp["C.2|GB0010"][THU][P.REGULAR_LABEL], "8")
        self.assertEqual(sp["C.1|GB0020"][WED][P.STANDBY_LABEL], "15.5")
        self.assertEqual(sp["C.2|GB0010"][WED][P.STANDBY_LABEL], "")
        self.assertEqual(sp["C.2|GB0010"][SAT][P.OVERTIME_LABEL], "4")
        self.assertEqual(sp["C.1|GB0020"][TUE][P.REGULAR_LABEL], "")   # concediu: gol peste tot
        self.assertEqual(sp["C.2|GB0010"][TUE][P.REGULAR_LABEL], "")

    def test_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = P.CONFIG_FILE
            P.CONFIG_FILE = Path(tmp) / "cfg.json"
            try:
                self.assertEqual(P.load_config(), {"projects": []})
                cfg = gui.validate_config({"projects": [
                    {"account": "C.1", "task": "GB0020", "name": "A",
                     "regular": {"mon": "4", "tue": "4,5"}, "standby": True, "overtime": True}]})
                self.assertEqual(cfg["projects"][0]["regular"]["tue"], "4.5")
                P.save_config(cfg)
                self.assertEqual(P.load_config(), cfg)
            finally:
                P.CONFIG_FILE = old

    def test_validate_refuses(self):
        with self.assertRaises(ValueError):       # doua coduri pentru stand by
            gui.validate_config({"projects": [
                {"account": "C.1", "task": "A", "standby": True, "overtime": True},
                {"account": "C.2", "task": "B", "standby": True, "overtime": False}]})
        with self.assertRaises(ValueError):       # fara task
            gui.validate_config({"projects": [{"account": "C.1", "task": ""}]})
        with self.assertRaises(ValueError):       # ore imposibile
            gui.validate_config({"projects": [
                {"account": "C.1", "task": "A", "regular": {"mon": "30"}, "standby": True, "overtime": True}]})


# --------------------------------------------------------------------------
# Interfata -> script
# --------------------------------------------------------------------------

class Preview(unittest.TestCase):
    def test_basic(self):
        r = gui.build_preview({"weekEnding": "2026-09-18", "mode": "oncall", "oncall": "16-22",
                               "overtime": "12=4@20:00", "holiday": "14", "office": "17"})
        self.assertIsNone(r.get("error"))
        self.assertEqual(r["totals"], {"regular": "32", "standby": "46.5", "overtime": "4", "absent": "8"})
        self.assertEqual(r["extraWeeks"], ["25 Sep 2026"])
        self.assertEqual(r["office"], ["Thu 17 Sep"])
        self.assertTrue(r["needsWeekend"])

    def test_errors_are_human(self):
        self.assertIn("calendar", gui.build_preview({"weekEnding": ""})["error"])
        self.assertIn("calendar", gui.build_preview({"weekEnding": "NaN-NaN-NaN"})["error"])
        self.assertIn("oncall", gui.build_preview({"weekEnding": "2026-09-18", "mode": "oncall", "oncall": ""})["error"])
        self.assertIn("weekend", gui.build_preview({"weekEnding": "2026-09-18", "office": "19"})["error"])

    def test_carried_absences(self):
        r = gui.build_preview({"weekEnding": "2026-09-18", "mode": "simple", "vacation": "17-23"})
        self.assertEqual(r["carried"], ["Mon 21 Sep concediu", "Tue 22 Sep concediu", "Wed 23 Sep concediu"])
        self.assertEqual(r["totals"]["absent"], "16")


class Args(unittest.TestCase):
    def test_week_run_carries_office(self):
        """'Ponteaza saptamana' ponteaza si zilele de birou scrise."""
        a = gui.build_args({"weekEnding": "2026-09-18", "mode": "simple", "office": "17"})
        self.assertEqual(a.office, "17")
        self.assertEqual(a.week, "September 18, 2026")
        self.assertTrue(a.simple and a.yes and not a.dry_run and not a.no_sf)

    def test_empty_office_stays_off(self):
        a = gui.build_args({"weekEnding": "2026-09-18", "mode": "simple", "office": "  "})
        self.assertIsNone(a.office)

    def test_flags(self):
        a = gui.build_args({"weekEnding": "2026-09-18", "mode": "oncall", "oncall": "16-18",
                            "dryRun": True, "sf": False, "submit": True})
        self.assertEqual(a.oncall, "16-18")
        self.assertTrue(a.dry_run and a.no_sf and a.submit and not a.simple)

    def test_cli(self):
        import sys
        old = sys.argv
        try:
            sys.argv = ["x", "--office-only", "18", "--dry-run"]
            a = P.parse_args()
            self.assertEqual(a.office_only, "18")
            sys.argv = ["x", "--audit", "--week", "March 31, 2026"]
            a = P.parse_args()
            self.assertTrue(a.audit)
        finally:
            sys.argv = old


# --------------------------------------------------------------------------
# SuccessFactors: forma intrarilor si cititul textelor SAP
# --------------------------------------------------------------------------

class SFEntries(unittest.TestCase):
    KW = dict(standby_label=P.STANDBY_LABEL, overtime_label=P.OVERTIME_LABEL)

    def entries(self, d, standby, overtime, holiday=False, off=False, start=None):
        row = {P.STANDBY_LABEL: standby, P.OVERTIME_LABEL: overtime}
        return S.desired_entries(d, row, holiday=holiday, off_day=off, overtime_start=start, **self.KW)

    def test_weekday_standby(self):
        self.assertEqual(self.entries(WED, "15.5", ""),
                         [("Standby", "12:00 AM", "09:00 AM"), ("Standby", "05:30 PM", "12:00 AM")])

    def test_weekend_standby(self):
        self.assertEqual(self.entries(SAT, "24", ""),
                         [("Standby", "12:00 AM", "12:00 PM"), ("Standby", "12:00 PM", "12:00 AM")])

    def test_overtime_defaults(self):
        self.assertEqual(self.entries(WED, "", "2"), [("Overtime", "05:30 PM", "07:30 PM")])
        self.assertEqual(self.entries(SAT, "", "4"), [("Overtime", "09:00 AM", "01:00 PM")])
        self.assertEqual(self.entries(SAT, "", "4", start="08:00 PM"), [("Overtime", "08:00 PM", "12:00 AM")])

    def test_overtime_carved_out_of_standby(self):
        self.assertEqual(self.entries(WED, "12.5", "3", start="08:00 PM"),
                         [("Overtime", "08:00 PM", "11:00 PM"), ("Standby", "12:00 AM", "09:00 AM"),
                          ("Standby", "05:30 PM", "08:00 PM"), ("Standby", "11:00 PM", "12:00 AM")])
        hours = S.entry_hours(self.entries(WED, "12.5", "3", start="08:00 PM"))
        self.assertEqual(hours, {"Standby": 12.5, "Overtime": 3.0})

    def test_holiday_hr(self):
        self.assertEqual(S.entry_hours(self.entries(MON, "16", "", holiday=True, off=True)),
                         {"Standby": 24.0, "Overtime": 0.0})
        self.assertEqual(S.entry_hours(self.entries(MON, "8", "8", holiday=True, off=True)),
                         {"Standby": 16.0, "Overtime": 8.0})

    def test_time_helpers(self):
        self.assertEqual(S.norm_time("9:00 AM"), "09:00 AM")
        self.assertEqual(S.norm_time(" 5:30 pm"), "05:30 PM")
        self.assertEqual(S.add_hours("05:30 PM", 8), "01:30 AM")
        self.assertEqual(S.subtract_interval([("12:00 AM", "09:00 AM"), ("05:30 PM", "12:00 AM")],
                                             ("10:00 PM", "02:00 AM")),
                         [("12:00 AM", "09:00 AM"), ("05:30 PM", "10:00 PM")])
        with self.assertRaises(ValueError):
            S.norm_time("25:00")

    def test_day_state(self):
        st = S.day_state([("Standby", "12:00 AM", "09:00 AM")], ["Vacation", "9:00 AM - 5:30 PM", "Pending"])
        self.assertEqual(st, {"standby": 9.0, "overtime": 0.0, "vacation": True})


class SFReading(unittest.TestCase):
    """Texte luate de pe pagina reala, cu spatiile speciale ale SAP."""

    def test_header_range(self):
        for text, want in (
            ("Time Sheet for Sep 7 - 13, 2026 | x", (date(2026, 9, 7), date(2026, 9, 13))),
            ("Time Sheet for Aug 31 – Sep 6, 2026 | x", (date(2026, 8, 31), date(2026, 9, 6))),
            ("Time Sheet for Dec 29, 2025 – Jan 4, 2026 | x", (date(2025, 12, 29), date(2026, 1, 4))),
        ):
            self.assertEqual(S.header_range(FakeFrame(text)), want, text)

    def test_day_row_hours(self):
        row = "Wednesday\nSep 16\n\t\n8 hr\nEmphasized\n00 min\nEmphasized\n\t\n15 hr\nEmphasized\n30 min\nEmphasized\n2"
        self.assertEqual(S.day_row_hours(FakeFrame(row), WED), 15.5)

    def test_entries_absences_allowances(self):
        text = ("Wed, August 19, 2026\nPlanned Working Time\nRecorded Overtime\n15 hr 30 min\n"
                "Working Times (2)\nRecord\nStandby\n12:00 AM - 9:00 AM\nStandby\n5:30 PM - 12:00 AM (+1 day)\n"
                "Allowances (1)\nRecord\nWork @IBM Office\n1\nAllowance Type\nAllowance Value\n"
                "Absences (1)\nCreate\nVacation\n9:00 AM - 5:30 PM\nPending\nObject Status\n"
                "Save\nCancel")
        fr = FakeFrame(text)
        self.assertEqual(S.read_entries(fr), [("Standby", "12:00 AM", "09:00 AM"), ("Standby", "05:30 PM", "12:00 AM")])
        self.assertEqual(S.read_allowances(fr), ["Work @IBM Office"])
        self.assertIn("Vacation", S.read_absences(fr)[0])

    def test_empty_sections(self):
        text = ("Working Times (0)\nRecord\nNo working times recorded\nAllowances (0)\nRecord\n"
                "No allowances recorded\nAbsences (0)\nCreate\nNo absences recorded\nSave\nCancel")
        fr = FakeFrame(text)
        self.assertEqual(S.read_entries(fr), [])
        self.assertEqual(S.read_allowances(fr), [])
        self.assertEqual(S.read_absences(fr), [])


# --------------------------------------------------------------------------
# Verificarea Time@IBM <-> SF
# --------------------------------------------------------------------------

class Reconcile(unittest.TestCase):
    def state(self, standby=0.0, overtime=0.0, vacation=False):
        return {"standby": standby, "overtime": overtime, "vacation": vacation}

    def test_all_good(self):
        ibm = {d: self.state() for d in WEEK}
        sf = {d: self.state() for d in WEEK}
        ibm[WED] = sf[WED] = self.state(15.5)
        ibm[SAT] = sf[SAT] = self.state(overtime=4)
        n, out = capture(P.reconcile, WEEK, ibm, sf, {}, False)
        self.assertEqual(n, 0)
        self.assertIn("coincid", out)
        self.assertNotIn("!!", out)

    def test_differences_named(self):
        ibm = {d: self.state() for d in WEEK}
        sf = {d: self.state() for d in WEEK}
        ibm[THU] = self.state(15.5)                 # lipseste in SF
        ibm[TUE] = self.state(vacation=True)        # concediu doar in Time@IBM
        n, out = capture(P.reconcile, WEEK, ibm, sf, {}, False)
        self.assertEqual(n, 2)
        self.assertIn("ATENTIE: 2 diferente", out)
        self.assertIn("Thu 17 Sep: stand by 15.5 in Time@IBM, 0 in SF", out)
        self.assertIn("concediu in Time@IBM, dar nu in SF", out)

    def test_holiday_rule_is_expected(self):
        ibm = {d: self.state() for d in WEEK}
        sf = {d: self.state() for d in WEEK}
        ibm[MON] = self.state(16); sf[MON] = self.state(24)
        n, out = capture(P.reconcile, WEEK, ibm, sf, {MON: P.HOLIDAY_LABEL}, False)
        self.assertEqual(n, 0)
        self.assertIn("(regula HR)", out)

    def test_missing_sf_day(self):
        ibm = {d: self.state() for d in WEEK}
        n, out = capture(P.reconcile, WEEK, ibm, {}, {}, False)
        self.assertEqual(n, 7)


# --------------------------------------------------------------------------
# Actualizarea automata
# --------------------------------------------------------------------------

class Updater(unittest.TestCase):
    def test_apply_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            here = Path(tmp)
            old = update.HERE
            update.HERE = here
            try:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as zf:
                    zf.writestr("claim_automation-main/gui.py", "print('nou')\n")
                    zf.writestr("claim_automation-main/ui/index.html", "<p>nou</p>")
                    zf.writestr("claim_automation-main/Pontaj.command", "#!/bin/bash\necho nou\n")
                    zf.writestr("claim_automation-main/Pontaj.bat", "@echo nou\n")
                    zf.writestr("claim_automation-main/.git/config", "nu")
                n = update.apply(zipfile.ZipFile(io.BytesIO(buf.getvalue())))
                self.assertEqual(n, 4)
                self.assertEqual((here / "gui.py").read_text(), "print('nou')\n")
                self.assertEqual((here / "ui" / "index.html").read_text(), "<p>nou</p>")
                # lansatoarele nu se suprascriu cat ruleaza: stau in .new
                self.assertTrue((here / "Pontaj.command.new").exists())
                self.assertTrue((here / "Pontaj.bat.new").exists())
                self.assertFalse((here / "Pontaj.command").exists())
                self.assertFalse((here / ".git").exists())
            finally:
                update.HERE = old

    def test_local_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = update.VERSION_FILE
            update.VERSION_FILE = Path(tmp) / ".version"
            try:
                self.assertEqual(update.local_sha(), "")
                update.VERSION_FILE.write_text("abc123\n")
                self.assertEqual(update.local_sha(), "abc123")
            finally:
                update.VERSION_FILE = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
