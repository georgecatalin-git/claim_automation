"""Teste pentru logica de date/plan (fara browser)."""
import re
from datetime import date

import pontaj_ibm as P


def sub(row):
    """Doar Regular + Stand by, pentru asertii mai vechi."""
    return {k: v for k, v in row.items() if k in ("Regular", "Stand by")}


def test_parse_header():
    header = ("Sat\nSep 12  Sun\nSep 13  Mon\nSep 14  Tue\nSep 15  "
              "Wed\nSep 16  Thu\nSep 17  Fri\nSep 18  Total  Action")
    pattern = re.compile(
        r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\s*[\s\n]*"
        r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\b"
    )
    days = [int(d) for _, d in pattern.findall(header)]
    assert days == [12, 13, 14, 15, 16, 17, 18], days
    print("header parsing OK ->", days)


def test_oncall_parsing():
    ref18 = date(2026, 9, 18)
    cases = {
        "9-15": (date(2026, 9, 9), date(2026, 9, 15)),
        "2026-09-09:2026-09-15": (date(2026, 9, 9), date(2026, 9, 15)),
        "sep 9 - sep 15": (date(2026, 9, 9), date(2026, 9, 15)),
        "9 sep - 15 sep": (date(2026, 9, 9), date(2026, 9, 15)),
    }
    for text, expected in cases.items():
        got = P.parse_oncall(text, ref18)
        assert got == expected, f"{text}: {got} != {expected}"
        print(f"oncall {text!r:28} -> {got[0]} .. {got[1]}")

    # trecere peste luni: 28 sep - 4 oct, saptamana care se incheie 2 oct
    got = P.parse_oncall("28-4", date(2026, 10, 2))
    print("oncall '28-4' (week ending 2 Oct) ->", got)
    assert got[0] < got[1]


def test_plan_week_sep18():
    we = date(2026, 9, 18)
    cols = P.week_days(we)
    assert cols[0] == date(2026, 9, 12) and cols[-1] == we
    plan = P.build_plan(cols, (date(2026, 9, 9), date(2026, 9, 15)))
    P.print_plan(plan)

    assert sub(plan[date(2026, 9, 12)]) == {"Regular": "", "Stand by": "24"}
    assert sub(plan[date(2026, 9, 13)]) == {"Regular": "", "Stand by": "24"}
    assert sub(plan[date(2026, 9, 14)]) == {"Regular": "8", "Stand by": "15.5"}
    assert sub(plan[date(2026, 9, 15)]) == {"Regular": "8", "Stand by": "15.5"}
    assert sub(plan[date(2026, 9, 16)]) == {"Regular": "8", "Stand by": ""}
    assert sub(plan[date(2026, 9, 18)]) == {"Regular": "8", "Stand by": ""}


def test_plan_week_sep11():
    we = date(2026, 9, 11)
    cols = P.week_days(we)
    plan = P.build_plan(cols, (date(2026, 9, 9), date(2026, 9, 15)))
    P.print_plan(plan)
    assert plan[date(2026, 9, 9)]["Stand by"] == "15.5"
    assert plan[date(2026, 9, 11)]["Stand by"] == "15.5"
    assert plan[date(2026, 9, 7)]["Stand by"] == ""
    assert sub(plan[date(2026, 9, 5)]) == {"Regular": "", "Stand by": ""}


def test_simple_week():
    plan = P.build_plan(P.week_days(date(2026, 9, 25)), None)
    total = sum(float(v["Regular"] or 0) for v in plan.values())
    assert total == 40, total
    assert all(v["Stand by"] == "" for v in plan.values())
    print("saptamana simpla -> 40h Regular, 0 stand by")


if __name__ == "__main__":
    test_parse_header()
    print()
    test_oncall_parsing()
    print("\n--- Week ending 18 Sep 2026 (oncall 9-15) ---")
    test_plan_week_sep18()
    print("\n--- Week ending 11 Sep 2026 (oncall 9-15) ---")
    test_plan_week_sep11()
    print()
    test_simple_week()
    print("\nTOATE TESTELE AU TRECUT")


# ---- teste overtime -------------------------------------------------------

def test_overtime_parsing():
    week = P.week_days(date(2026, 9, 18))   # Sat 12 .. Fri 18
    cases = {
        "16=3": {date(2026, 9, 16): "3"},
        "wed=2.5": {date(2026, 9, 16): "2.5"},
        "mie 2": {date(2026, 9, 16): "2"},
        "16=3, 17=2": {date(2026, 9, 16): "3", date(2026, 9, 17): "2"},
        "joi=1,5": {date(2026, 9, 17): "1.5"},
        "sun=4": {date(2026, 9, 13): "4"},
        "": {},
    }
    for text, expected in cases.items():
        got = P.parse_overtime(text, week)
        assert got == expected, f"{text!r}: {got} != {expected}"
        print(f"overtime {text!r:20} -> "
              + (", ".join(f"{d:%a %d}={h}" for d, h in sorted(got.items()))
                 or "(nimic)"))

    for bad in ("16", "99=3", "16=0", "abc=2"):
        try:
            P.parse_overtime(bad, week)
        except ValueError as exc:
            print(f"respins corect {bad!r}: {exc}")
        else:
            raise AssertionError(f"{bad!r} ar fi trebuit respins")


def test_plan_with_overtime():
    week = P.week_days(date(2026, 9, 18))
    plan = P.build_plan(
        week,
        (date(2026, 9, 9), date(2026, 9, 15)),
        P.parse_overtime("16=3, 17=2", week),
    )
    P.print_plan(plan)
    assert plan[date(2026, 9, 16)]["Overtime"] == "3"
    assert plan[date(2026, 9, 17)]["Overtime"] == "2"
    assert plan[date(2026, 9, 18)]["Overtime"] == ""
    assert plan[date(2026, 9, 14)]["Stand by"] == "15.5"
    assert plan[date(2026, 9, 12)]["Stand by"] == "24"


if True:
    print()
    test_overtime_parsing()
    print("\n--- Week ending 18 Sep: oncall 9-15 + overtime 16=3, 17=2 ---")
    test_plan_with_overtime()
    print("\nTESTELE DE OVERTIME AU TRECUT")


def test_decimal_comma():
    week = P.week_days(date(2026, 9, 18))
    checks = {
        "joi=1,5": {date(2026, 9, 17): "1.5"},
        "joi=1,5, mie=2": {date(2026, 9, 17): "1.5", date(2026, 9, 16): "2"},
        "16=3,17=2": {date(2026, 9, 16): "3", date(2026, 9, 17): "2"},
        "16=2,5; 17=1": {date(2026, 9, 16): "2.5", date(2026, 9, 17): "1"},
    }
    for text, expected in checks.items():
        got = P.parse_overtime(text, week)
        assert got == expected, f"{text!r}: {got} != {expected}"
        print(f"virgula zecimala {text!r:18} -> "
              + ", ".join(f"{d:%a %d}={h}" for d, h in sorted(got.items())))
    print("virgula zecimala OK")

test_decimal_comma()


# ---- teste zile libere ----------------------------------------------------

def test_absences():
    """Regulile din emailul HR pentru sarbatoarea legala din 1 Dec 2025."""
    week_ending = date(2025, 12, 5)
    week = P.week_days(week_ending)
    mon = date(2025, 12, 1)
    weekdays = [d for d in week if d.weekday() < 5]

    assert P.parse_days("1", week) == [mon]
    assert P.parse_days("luni, marti", week) == [mon, date(2025, 12, 2)]
    assert P.parse_days("1-3", week) == [mon, date(2025, 12, 2), date(2025, 12, 3)]
    for bad in ("29", "sam"):
        try:
            P.parse_days(bad, week)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad!r} trebuia refuzat")
    try:
        P.merge_absences([mon], [mon], [])
    except ValueError:
        pass
    else:
        raise AssertionError("aceeasi zi la concediu si liber trebuia refuzata")

    holiday = {mon: P.HOLIDAY_LABEL}

    # 1. nu lucrezi: 8 pe XL0B00, Regular gol
    plan = P.build_plan(weekdays, None, {}, holiday)
    assert plan[mon][P.REGULAR_LABEL] == ""
    assert plan[mon][P.HOLIDAY_LABEL] == "8"
    assert plan[mon][P.STANDBY_LABEL] == ""
    assert plan[date(2025, 12, 2)][P.REGULAR_LABEL] == "8"
    assert plan[date(2025, 12, 2)][P.HOLIDAY_LABEL] == ""

    # 2a. overtime: 8 pe XL0B00 + 8 overtime
    plan = P.build_plan(weekdays, None, {mon: "8"}, holiday)
    assert plan[mon][P.OVERTIME_LABEL] == "8" and plan[mon][P.REGULAR_LABEL] == ""

    # 2b. overtime + oncall: + 8 stand by
    plan = P.build_plan(weekdays, (mon, mon), {mon: "8"}, holiday)
    assert plan[mon][P.STANDBY_LABEL] == "8", plan[mon]

    # 2c. doar oncall: 16 stand by
    plan = P.build_plan(weekdays, (mon, mon), {}, holiday)
    assert plan[mon][P.STANDBY_LABEL] == "16", plan[mon]
    # ... iar restul saptamanii de oncall ramane la 15.5
    plan = P.build_plan(weekdays, (mon, date(2025, 12, 3)), {}, holiday)
    assert plan[date(2025, 12, 2)][P.STANDBY_LABEL] == "15.5"

    # 2d. compensatie in alta zi: 8 pe XL0C00, Regular gol acolo
    thu = date(2025, 12, 4)
    plan = P.build_plan(weekdays, None, {mon: "8"},
                        P.merge_absences([], [mon], [thu]))
    assert plan[thu][P.COMP_LABEL] == "8" and plan[thu][P.REGULAR_LABEL] == ""

    # concediu: 8 pe XL0A00, Regular gol, stand by neschimbat
    plan = P.build_plan(weekdays, (mon, mon), {}, {mon: P.VACATION_LABEL})
    assert plan[mon][P.VACATION_LABEL] == "8"
    assert plan[mon][P.REGULAR_LABEL] == ""
    assert plan[mon][P.STANDBY_LABEL] == "15.5"
    print("zile libere OK")


print()
test_absences()
