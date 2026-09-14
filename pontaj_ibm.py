#!/usr/bin/env python3
"""
Pontaj automat IBM (time.ibm.com/week) - cu suport pentru oncall / stand by

Ce face:
  1. Deschide https://time.ibm.com/week intr-un profil persistent
     (login manual o singura data, sesiunea ramane salvata local).
  2. Citeste capul de tabel si afla EXACT ce data calendaristica e pe fiecare
     coloana. Nu presupune ordinea zilelor.
  3. Te intreaba daca e saptamana simpla sau cu oncall.
  4. Daca saptamana e goala -> "Copy from a previous week".
  5. Completeaza:
       Regular  = 8     Luni-Vineri
       Stand by = 15.5  Luni-Vineri din perioada de oncall
       Stand by = 24    Sambata/Duminica din perioada de oncall
  6. Apasa Save. NU apasa Submit decat cu --submit.

NU stocheaza si NU introduce parole.

Browserul e mereu vizibil. Daca IBM cere login, te loghezi tu in fereastra
(w3id + parola sau passkey + 2FA) si scriptul continua singur. w3id tine
sesiunea cateva ore, deci a doua rulare din aceeasi zi trece de obicei fara
sa tastezi nimic. Modul headless a fost scos: w3id refuza sesiunea acolo.

Exemple:
    python pontaj_ibm.py                            # interactiv, te intreaba
    python pontaj_ibm.py --simple                   # fara intrebari
    python pontaj_ibm.py --oncall "9-15" --yes
    python pontaj_ibm.py --week "September 18, 2026" --oncall 2026-09-09:2026-09-15
    python pontaj_ibm.py --dry-run
    python pontaj_ibm.py --login                    # doar login, fara pontaj
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import sf_ibm

try:
    from playwright.sync_api import (
        Locator,
        Page,
        TimeoutError as PlaywrightTimeout,
        sync_playwright,
    )
    PLAYWRIGHT_OK = True
except ImportError:  # GUI-ul poate importa modulul doar pentru calcule
    PLAYWRIGHT_OK = False
    sync_playwright = None

    class PlaywrightTimeout(Exception):
        pass

PLAYWRIGHT_HINT = (
    "Playwright nu e instalat.\n"
    "  pip install playwright\n"
    "  python -m playwright install chromium"
)

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

URL = "https://time.ibm.com/week"
PROFILE_DIR = Path.home() / ".ibm-pontaj-profile"
# Cookie-urile de sesiune, salvate la inchidere si puse la loc la pornire.
# Chrome le sterge cand se inchide - browserul de zi cu zi ramane logat doar
# pentru ca nu se inchide niciodata. Fisierul e echivalentul bazei de
# cookie-uri a browserului: doar al userului (0600), niciodata in repo.
SESSION_FILE = Path.home() / ".ibm-pontaj-session.json"

# Grila de pe time.ibm.com (ag-Grid)
GRID_ROWS = ".ag-center-cols-container [role='row']"
GRID_LABEL_CELL = "[col-id='data.claimItem.code']"
GRID_HOUR_HEADERS = ".ag-header-cell[col-id^='hours.']"

REGULAR_LABEL = "Regular"
STANDBY_LABEL = "Stand by"
OVERTIME_LABEL = "Overtime"

# Codurile de claim ale omului: ce claim item-uri are, cate ore Regular pe
# zi pe fiecare, si pe care merg stand by-ul si overtime-ul. Fiecare coleg
# ponteaza altfel - unul pe un singur cod, altul pe doua - asa ca asta e o
# configurare per persoana, pe calculatorul lui, facuta din interfata.
# Fara fisier: un singur claim item in grila inseamna 8 ore pe zi pe el, cu
# stand by si overtime tot acolo; mai multe inseamna "configureaza".
CONFIG_FILE = Path.home() / ".ibm-pontaj-config.json"
WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri")

REGULAR_HOURS = "8"
STANDBY_WEEKDAY = "15.5"
STANDBY_WEEKEND = "24"

# Zile libere: concediu, sarbatoare legala, zi de compensatie. Toate se
# ponteaza cu 8 ore pe claim item-ul M.00556, fiecare pe task-ul ei, iar in
# ziua aceea rândul Regular al proiectului ramane gol. Regulile vin din
# emailul HR pentru 1 Dec 2025 si sunt scrise in build_plan.
ABSENCE_CLAIM_CODE = "M.00556"
ABSENCE_HOURS = "8"
VACATION_LABEL = "Vacation"              # XL0A00 - concediu
HOLIDAY_LABEL = "Designated Holiday"     # XL0B00 - sarbatoare legala
COMP_LABEL = "Optional Holiday"          # XL0C00 - zi libera in compensatie
ABSENCE_TASKS = {
    VACATION_LABEL: "XL0A00",
    HOLIDAY_LABEL: "XL0B00",
    COMP_LABEL: "XL0C00",
}
ABSENCE_LABELS = tuple(ABSENCE_TASKS)
# Stand by intr-o sarbatoare legala lucrata: Time@IBM vrea 24 de ore in
# total pe zi, din care 8 sunt deja pe XL0B00.
STANDBY_HOLIDAY_WITH_OVERTIME = "8"      # 8 liber + 8 overtime + 8 stand by
STANDBY_HOLIDAY = "16"                   # 8 liber + 16 stand by
MAX_SANE_OVERTIME = 12.0   # peste atat doar avertizam, nu blocam

DECIMAL_SEP = "."          # schimba in "," daca aplicatia cere virgula
BLANK = ""                 # ce scriem intr-o casuta care trebuie golita

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# zilele saptamanii, EN si RO (0 = luni). Atentie: "mar" e si martie, si marti;
# in contextul zilelor il tratam ca marti.
WEEKDAY_NAMES = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
    "lun": 0, "mar": 1, "mie": 2, "joi": 3, "vin": 4, "sam": 5, "dum": 6,
    "marti": 1, "miercuri": 2, "vineri": 4, "sambata": 5, "duminica": 6,
    "luni": 0, "sâm": 5, "dum.": 6,
}


def log(msg: str) -> None:
    print(f"[pontaj] {msg}", flush=True)


def month_num(text: str) -> int | None:
    return MONTHS.get(text.strip().lower()[:3])


def fmt_num(value: str) -> str:
    return value.replace(".", DECIMAL_SEP)


# --------------------------------------------------------------------------
# Locatori generici
# --------------------------------------------------------------------------

def click_by_text(page: Page, text: str, timeout: int = 9_000) -> bool:
    candidates = [
        page.get_by_role("button", name=text, exact=False),
        page.get_by_role("link", name=text, exact=False),
        page.get_by_text(text, exact=False),
    ]
    per_try = max(timeout // len(candidates), 1_500)
    for loc in candidates:
        try:
            el = loc.first
            el.wait_for(state="visible", timeout=per_try)
            el.click()
            return True
        except Exception:
            continue
    return False


def find_row(page: Page, label: str, wait_ms: int = 8_000) -> Locator | None:
    """
    Randul din grila care contine exact eticheta data (ex: 'Stand by').
    `wait_ms` e cat asteptam sa apara: mult dupa o actiune care il creeaza,
    putin cand grila e deja pe ecran si intrebam doar daca exista - altfel
    fiecare rand lipsa costa 8 secunde.
    """
    try:
        text = page.get_by_text(label, exact=True).first
        text.wait_for(state="visible", timeout=wait_ms)
    except PlaywrightTimeout:
        return None

    # time.ibm.com e un ag-Grid: randurile sunt div[role=row] in containerul
    # central, iar eticheta sta in prima coloana. Filtram pe coloana, nu pe
    # tot randul, ca 'Total' sa nu prinda randul cu totalul de pe coloana.
    # Rândurile de zile libere de pe M.00556 au si ele un 'Regular'; cele
    # ale proiectului sunt toate celelalte.
    try:
        row = page.locator(
            f"{GRID_ROWS}:not([row-id^='{ABSENCE_CLAIM_CODE}|'])"
        ).filter(
            has=page.locator(GRID_LABEL_CELL).get_by_text(label, exact=True)
        ).first
        if row.count() > 0 and row.is_visible():
            return row
    except Exception:
        pass

    for selector in ("tr", "[role='row']", "div[class*='row']"):
        try:
            row = page.locator(selector).filter(has=text).first
            if row.count() > 0 and row.is_visible():
                return row
        except Exception:
            continue
    return None


# --------------------------------------------------------------------------
# Codurile de claim
# --------------------------------------------------------------------------

def load_config() -> dict:
    try:
        cfg = json.loads(CONFIG_FILE.read_text())
    except FileNotFoundError:
        return {"projects": []}
    except Exception as exc:
        raise RuntimeError(f"Nu pot citi {CONFIG_FILE}: {exc}")
    cfg.setdefault("projects", [])
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))


def project_key(p: dict) -> str:
    return f"{p['account']}|{p['task']}"


def project_title(p: dict) -> str:
    name = p.get("name") or ""
    return f"{p['task']} – {name}" if name else f"{p['account']} / {p['task']}"


def read_projects(page: Page) -> list[dict]:
    """
    Claim item-urile din grila saptamanii deschise. Randul unui claim item
    are row-id 'cont|task|nume|bill|' (bill e 'no-bc' cand nu are), iar
    randurile lui de ore continua cu '|1reg|0|' etc. M.00556 e al zilelor
    libere si nu e un proiect.
    """
    rows = page.evaluate(
        "(sel) => [...document.querySelectorAll(sel)].map(r => r.getAttribute('row-id') || '')",
        GRID_ROWS,
    )
    found: list[dict] = []
    for rid in rows:
        parts = rid.split("|")
        if len(parts) != 5 or parts[4] != "" or not parts[1]:
            continue
        if parts[0] == ABSENCE_CLAIM_CODE:
            continue
        found.append({"account": parts[0], "task": parts[1],
                      "name": parts[2], "bill": parts[3]})
    return found


def default_project(found: dict) -> dict:
    return {**found, "regular": {k: REGULAR_HOURS for k in WEEKDAY_KEYS},
            "standby": True, "overtime": True}


def claim_row(page: Page, p: dict) -> Locator | None:
    rid = f"{p['account']}|{p['task']}|{p['name']}|{p['bill']}|"
    row = page.locator(f"{GRID_ROWS}[row-id='{rid}']").first
    return row if row.count() else None


def project_row(page: Page, p: dict, label: str, wait_ms: int = 500) -> Locator | None:
    """Randul Regular / Stand by / Overtime al unui claim item anume."""
    row = page.locator(f"{GRID_ROWS}[row-id^='{project_key(p)}|']").filter(
        has=page.locator(GRID_LABEL_CELL).get_by_text(label, exact=True)
    ).first
    try:
        row.wait_for(state="visible", timeout=wait_ms)
        return row
    except PlaywrightTimeout:
        return None


def resolve_projects(page: Page, cfg: dict, dry_run: bool) -> list[dict]:
    """
    Proiectele pe care se ponteaza saptamana asta. Din configurare, cu
    claim item-urile lipsa adaugate; fara configurare, singurul claim item
    din grila, cu 8 pe zi si tot pe el - sau, daca sunt mai multe, refuz:
    nu ghicim cum imparte omul orele.
    """
    found = read_projects(page)
    by_key = {project_key(f): f for f in found}
    projects: list[dict] = []
    if not cfg.get("projects"):
        if len(found) == 1:
            projects.append(default_project(found[0]))
        elif not found:
            raise RuntimeError(
                "Saptamana nu are niciun claim item si nu exista o configurare "
                "de coduri. Configureaza codurile de claim in interfata."
            )
        else:
            raise RuntimeError(
                "Saptamana are mai multe claim item-uri ("
                + ", ".join(project_title(f) for f in found)
                + ") si nu stiu cum imparti orele. Configureaza codurile de "
                "claim in interfata."
            )
    else:
        for cp in cfg["projects"]:
            key = f"{cp['account']}|{cp['task']}"
            if key in by_key:
                projects.append({**cp, **by_key[key]})
                continue
            if dry_run:
                log(f"DRY RUN: as adauga claim item-ul {cp['account']} -> {cp['task']}.")
                projects.append({**cp, "name": cp.get("name", ""), "bill": "no-bc",
                                 "_missing": True})
                continue
            add_claim_item(page, cp["account"], cp["task"])
            by_key = {project_key(f): f for f in read_projects(page)}
            if key not in by_key:
                raise RuntimeError(
                    f"Am adaugat {cp['account']} -> {cp['task']}, dar nu il "
                    "gasesc in grila."
                )
            projects.append({**cp, **by_key[key]})
    extra = [f for f in found if project_key(f) not in {project_key(p) for p in projects}]
    for f in extra:
        log(f"ATENTIE: claim item-ul {project_title(f)} e in saptamana, dar nu "
            "e in configurare; nu il ating.")
    return projects


def split_plan(
    plan: dict[date, dict[str, str]], projects: list[dict], columns: list[date]
) -> dict[str, dict[date, dict[str, str]]]:
    """
    Planul zilei, impartit pe claim item-uri: Regular dupa orele din
    configurare (gol in weekend si in zilele libere, ca in plan), stand by
    si overtime pe proiectul bifat pentru fiecare.
    """
    out: dict[str, dict[date, dict[str, str]]] = {}
    for p in projects:
        rows: dict[date, dict[str, str]] = {}
        for d in columns:
            regular = BLANK
            if plan[d][REGULAR_LABEL]:
                hours = str(p.get("regular", {}).get(d.strftime("%a").lower(), "")).strip()
                regular = "" if hours in ("", "0", "0.0") else hours
            rows[d] = {
                REGULAR_LABEL: regular,
                STANDBY_LABEL: plan[d][STANDBY_LABEL] if p.get("standby") else BLANK,
                OVERTIME_LABEL: plan[d][OVERTIME_LABEL] if p.get("overtime") else BLANK,
            }
        out[project_key(p)] = rows
    return out


def print_projects(projects: list[dict], per_project: dict, columns: list[date]) -> None:
    if len(projects) == 1 and not CONFIG_FILE.exists():
        log(f"Claim item: {project_title(projects[0])} (singurul din grila)")
        return
    log("Coduri de claim:")
    for p in projects:
        rows = per_project[project_key(p)]
        reg = "/".join((rows[d][REGULAR_LABEL] or "-") for d in sorted(columns)
                       if d.weekday() < 5)
        carries = [n for n, k in (("stand by", "standby"), ("overtime", "overtime"))
                   if p.get(k)]
        log(f"    {project_title(p):<40} Regular L-V: {reg}"
            + (f"  + {', '.join(carries)}" if carries else "")
            + ("  (se adauga)" if p.get("_missing") else ""))


def row_inputs(row: Locator) -> list[Locator]:
    boxes = row.locator("input:not([type='hidden']):not([type='checkbox'])")
    return [boxes.nth(i) for i in range(boxes.count())]


def expand_claim_items(page: Page) -> None:
    """
    Claim item-ul vine de obicei restrans, cu randurile Regular / Stand by
    ascunse. 'Expand all' din toolbar le scoate la vedere; fara el, randurile
    nu exista in pagina si nu au cum sa fie gasite.
    """
    if page.get_by_text(REGULAR_LABEL, exact=True).count() > 0:
        return
    btn = page.get_by_role("button", name="Expand all", exact=True).first
    try:
        btn.wait_for(state="visible", timeout=5_000)
        btn.click()
        page.get_by_text(REGULAR_LABEL, exact=True).first.wait_for(
            state="visible", timeout=5_000
        )
        log("Am expandat claim item-ele.")
    except Exception:
        log("Nu am gasit butonul 'Expand all'; incerc randurile asa cum sunt.")


def read_column_ids(page: Page, week_ending: date) -> dict[date, str]:
    """
    Capul de tabel al grilei: fiecare coloana de ore are un col-id
    ('hours.mon', 'hours.sat', ...) si un text 'Mon Sep 7'. Legam data de
    col-id, ca scrierea sa mearga pe coloana cu data aceea, nu pe pozitie.
    """
    pattern = re.compile(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\b")
    ids: dict[date, str] = {}
    headers = page.locator(GRID_HOUR_HEADERS)
    for i in range(headers.count()):
        h = headers.nth(i)
        col_id = h.get_attribute("col-id") or ""
        m = pattern.search(h.inner_text() or "")
        if not col_id or not m:
            continue
        mon = month_num(m.group(1))
        if not mon:
            continue
        year = week_ending.year
        if mon == 12 and week_ending.month == 1:
            year -= 1
        elif mon == 1 and week_ending.month == 12:
            year += 1
        try:
            d = date(year, mon, int(m.group(2)))
        except ValueError:
            continue
        if abs((d - week_ending).days) <= 10:
            ids.setdefault(d, col_id)
    return ids


def cell_value(cell: Locator) -> str:
    return (cell.inner_text() or "").strip()


def set_cell(page: Page, cell: Locator, value: str) -> None:
    """
    O celula ag-Grid nu are input pana nu intri in editare: dublu-click
    deschide editorul, Enter comite. Golul se scrie tot asa, cu un fill('').
    """
    cell.dblclick()
    box = cell.locator("input").first
    box.wait_for(state="visible", timeout=5_000)
    box.fill(value)
    box.press("Enter")
    page.wait_for_timeout(300)
    got = cell_value(cell)
    if got != value:
        raise RuntimeError(
            f"Celula nu a retinut valoarea: am scris {value!r}, arata {got!r}."
        )


# --------------------------------------------------------------------------
# Citirea saptamanii din pagina
# --------------------------------------------------------------------------

def read_week_ending(page: Page) -> date:
    """Citeste 'Week ending: September 18, 2026'."""
    raw = ""
    try:
        combo = page.get_by_role("combobox").first
        raw = (combo.input_value() or "").strip()
        if not raw:
            raw = combo.inner_text()
    except Exception:
        pass

    if not re.search(r"[A-Za-z]+\s+\d{1,2}", raw or ""):
        body = page.locator("body").inner_text()
        m = re.search(r"Week ending:?\s*([A-Za-z]+ \d{1,2},? \d{4})", body)
        raw = m.group(1) if m else raw

    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})", raw or "")
    if not m:
        raise RuntimeError(f"Nu pot citi 'week ending' din: {raw!r}")

    mon = month_num(m.group(1))
    if not mon:
        raise RuntimeError(f"Luna necunoscuta: {m.group(1)}")
    return date(int(m.group(3)), mon, int(m.group(2)))


def read_columns(page: Page, week_ending: date) -> list[date]:
    """
    Citeste capul de tabel ('Mon Sep 14', 'Sat Sep 12', ...) si returneaza
    datele calendaristice IN ORDINEA IN CARE APAR pe ecran.
    """
    pattern = re.compile(
        r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\s*[\s\n]*"
        r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\b"
    )

    header_text = ""
    for sel in ("thead", "[role='rowgroup']", "table", "body"):
        try:
            node = page.locator(sel).first
            if node.count():
                candidate = node.inner_text()
                if pattern.search(candidate):
                    header_text = candidate
                    break
        except Exception:
            continue

    found: list[date] = []
    for mon_txt, day_txt in pattern.findall(header_text):
        mon = month_num(mon_txt)
        if not mon:
            continue
        year = week_ending.year
        if mon == 12 and week_ending.month == 1:
            year -= 1
        elif mon == 1 and week_ending.month == 12:
            year += 1
        try:
            d = date(year, mon, int(day_txt))
        except ValueError:
            continue
        if abs((d - week_ending).days) <= 10 and d not in found:
            found.append(d)

    if not found:
        raise RuntimeError(
            "Nu am putut citi datele din capul de tabel. "
            "Ruleaza cu --debug si uita-te la pagina."
        )
    return found


def weekend_visible(columns: list[date]) -> bool:
    return any(d.weekday() >= 5 for d in columns)


def toggle_weekend(page: Page, show: bool) -> bool:
    label = "Show weekend" if show else "Hide weekend"
    log(f"Comut: '{label}'")
    if click_by_text(page, label, timeout=6_000):
        try:
            page.locator(GRID_HOUR_HEADERS + "[col-id='hours.sat'], "
                         + GRID_HOUR_HEADERS + "[col-id='hours.sun']").first.wait_for(
                state="visible" if show else "hidden", timeout=5_000
            )
        except PlaywrightTimeout:
            page.wait_for_timeout(1_000)
        return True
    log(f"Nu am gasit butonul '{label}'.")
    return False


def week_days(week_ending: date) -> list[date]:
    """Cele 7 zile ale saptamanii care se incheie la week_ending."""
    return [week_ending - timedelta(days=i) for i in range(6, -1, -1)]


# --------------------------------------------------------------------------
# Perioada de oncall
# --------------------------------------------------------------------------

def nearest_date(day: int, month: int | None, ref: date) -> date:
    """Alege luna/anul care cad cel mai aproape de saptamana de referinta."""
    candidates: list[date] = []
    for delta in (-1, 0, 1):
        total = (ref.year * 12 + ref.month - 1) + delta
        y, m = divmod(total, 12)
        m += 1
        if month is not None:
            m = month
        try:
            candidates.append(date(y, m, day))
        except ValueError:
            continue
    if not candidates:
        raise ValueError(f"Data invalida: ziua {day}")
    return min(candidates, key=lambda d: abs((d - ref).days))


def parse_oncall(text: str, ref: date) -> tuple[date, date]:
    """
    Accepta:
      "9-15"                      -> zile, luna dedusa din saptamana curenta
      "9 sep - 15 sep" / "sep 9 - sep 15"
      "2026-09-09:2026-09-15"
    """
    cleaned = text.strip().lower().replace(" to ", "-")

    iso = re.findall(r"(\d{4})-(\d{1,2})-(\d{1,2})", cleaned)
    if len(iso) >= 2:
        a = date(int(iso[0][0]), int(iso[0][1]), int(iso[0][2]))
        b = date(int(iso[1][0]), int(iso[1][1]), int(iso[1][2]))
        return (a, b) if a <= b else (b, a)

    parts = re.split(r"\s*[-–:]\s*", cleaned)
    parts = [p for p in parts if p.strip()]
    if len(parts) != 2:
        raise ValueError(f"Nu inteleg perioada: {text!r}")

    def one(part: str, anchor: date) -> date:
        mon_m = re.search(r"[a-z]{3,9}", part)
        day_m = re.search(r"\d{1,2}", part)
        if not day_m:
            raise ValueError(f"Lipseste ziua in {part!r}")
        mon = month_num(mon_m.group(0)) if mon_m else None
        return nearest_date(int(day_m.group(0)), mon, anchor)

    start = one(parts[0], ref)
    end = one(parts[1], start)
    if end < start:
        end = nearest_date(end.day, end.month, start + timedelta(days=7))
    if end < start:
        raise ValueError("Sfarsitul perioadei e inaintea inceputului.")
    return start, end


def norm_start(text: str) -> str:
    """'20:00', '20', '8pm', '8:30 pm', '20.30' -> '08:00 PM' / '08:30 PM'."""
    t = text.strip().lower().replace(".", ":")
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", t)
    if not m:
        raise ValueError(f"Ora de inceput neinteleasa: {text!r}. Ex: '@20:00'.")
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ampm:
        if hour < 1 or hour > 12:
            raise ValueError(f"Ora invalida: {text!r}")
        hour = hour % 12 + (12 if ampm == "pm" else 0)
    if hour > 23 or minute > 59:
        raise ValueError(f"Ora invalida: {text!r}")
    return datetime(2000, 1, 1, hour, minute).strftime("%I:%M %p")


def parse_overtime(text: str, week: list[date]) -> dict[date, str]:
    """Orele suplimentare pe zi; vezi parse_overtime_full."""
    return {d: h for d, (h, _) in parse_overtime_full(text, week).items()}


def parse_overtime_starts(text: str, week: list[date]) -> dict[date, str]:
    """Doar zilele pentru care s-a dat si ora de inceput ('@20:00')."""
    return {d: st for d, (_, st) in parse_overtime_full(text, week).items()
            if st}


def parse_overtime_full(
    text: str, week: list[date]
) -> dict[date, tuple[str, str | None]]:
    """
    Ore suplimentare pe zile anume din saptamana afisata.

    Accepta, separate prin virgula sau punct si virgula:
      "16=3"          -> ziua 16 a lunii, 3 ore
      "wed=2.5"       -> miercuri, 2.5 ore
      "mie 2"         -> miercuri, 2 ore
      "16=3, joi=1.5"
      "16=3@20:00"    -> 3 ore incepand de la 20:00 (conteaza doar in
                         SuccessFactors, care vrea interval; implicit
                         17:30 in zi lucratoare, 09:00 in weekend / zi libera)
    """
    result: dict[date, tuple[str, str | None]] = {}
    if not text or not text.strip():
        return result

    by_day = {d.day: d for d in week}
    by_weekday = {d.weekday(): d for d in week}

    # Separam pe ';' si pe virgulele care chiar despart zile, nu pe virgula
    # zecimala din "1,5". O virgula e separator daca dupa ea urmeaza o litera
    # sau o zi urmata de '=' / ':' / spatiu.
    chunks = re.split(
        r";|,(?=\s*(?:[a-zăâîșț]|\d{1,2}\s*[=: ]))",
        text,
        flags=re.IGNORECASE,
    )
    for chunk in chunks:
        chunk = chunk.strip().lower()
        if not chunk:
            continue

        m = re.match(
            r"^\s*([a-zăâîșț\.]+|\d{1,2})\s*[=: ]\s*(\d+(?:[.,]\d+)?)"
            r"\s*(?:@\s*([0-9:. ]*[0-9](?:\s*[ap]m)?))?\s*$",
            chunk,
        )
        if not m:
            raise ValueError(f"Nu inteleg {chunk!r}. Foloseste 'zi=ore', ex: '16=3'.")

        key, hours_txt = m.group(1), m.group(2).replace(",", ".")
        start = norm_start(m.group(3)) if m.group(3) else None
        hours = float(hours_txt)
        if hours <= 0:
            raise ValueError(f"Ore invalide in {chunk!r}.")

        if key.isdigit():
            day = by_day.get(int(key))
            if day is None:
                raise ValueError(
                    f"Ziua {key} nu e in saptamana afisata "
                    f"({week[0]:%d %b} - {week[-1]:%d %b})."
                )
        else:
            wd = WEEKDAY_NAMES.get(key[:3]) 
            if wd is None:
                wd = WEEKDAY_NAMES.get(key)
            if wd is None:
                raise ValueError(f"Zi necunoscuta: {key!r}")
            day = by_weekday[wd]

        if hours > MAX_SANE_OVERTIME:
            log(f"ATENTIE: {hours} ore suplimentare pe {day:%a %d %b} "
                f"par multe. Verifica inainte de confirmare.")

        # normalizam "3.0" -> "3"
        result[day] = (f"{hours:g}", start)

    return result


def resolve_day(key: str, week: list[date]) -> date:
    """'16' -> ziua 16 a lunii; 'wed', 'mie', 'miercuri' -> ziua saptamanii."""
    key = key.strip().lower().rstrip(".")
    if key.isdigit():
        by_day = {d.day: d for d in week}
        day = by_day.get(int(key))
        if day is None:
            raise ValueError(
                f"Ziua {key} nu e in saptamana afisata "
                f"({week[0]:%d %b} - {week[-1]:%d %b})."
            )
        return day
    wd = WEEKDAY_NAMES.get(key[:3])
    if wd is None:
        wd = WEEKDAY_NAMES.get(key)
    if wd is None:
        raise ValueError(f"Zi necunoscuta: {key!r}")
    return {d.weekday(): d for d in week}[wd]


def parse_days(text: str, week: list[date]) -> list[date]:
    """
    Zile din saptamana afisata, pentru concediu / liber legal / compensatie.

    Accepta, separate prin virgula sau punct si virgula:
      "15"            -> ziua 15 a lunii
      "14-16"         -> 14, 15 si 16
      "luni, marti"   -> zilele saptamanii
      "wed"           -> miercuri
    """
    result: list[date] = []
    if not text or not text.strip():
        return result
    for chunk in re.split(r"[;,]", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(r"^(\d{1,2})\s*[-–]\s*(\d{1,2})$", chunk)
        if m:
            first, last = resolve_day(m.group(1), week), resolve_day(m.group(2), week)
            if last < first:
                raise ValueError(f"Interval invers: {chunk!r}.")
            days = [d for d in week if first <= d <= last]
        else:
            days = [resolve_day(chunk, week)]
        for d in days:
            if d.weekday() >= 5:
                raise ValueError(
                    f"{d:%a %d %b} e in weekend; zilele libere se ponteaza "
                    "doar Luni-Vineri."
                )
            if d not in result:
                result.append(d)
    return result


def merge_absences(
    vacation: list[date], holiday: list[date], comp: list[date]
) -> dict[date, str]:
    """O zi e ori concediu, ori sarbatoare, ori compensatie - niciodata doua."""
    absences: dict[date, str] = {}
    for label, days in ((VACATION_LABEL, vacation), (HOLIDAY_LABEL, holiday),
                        (COMP_LABEL, comp)):
        for d in days:
            if d in absences:
                raise ValueError(
                    f"{d:%a %d %b} e trecuta si la {absences[d]} si la {label}."
                )
            absences[d] = label
    return absences


# --------------------------------------------------------------------------
# Planul de pontaj
# --------------------------------------------------------------------------

def build_plan(
    columns: list[date],
    oncall: tuple[date, date] | None,
    overtime: dict[date, str] | None = None,
    absences: dict[date, str] | None = None,
) -> dict[date, dict[str, str]]:
    """
    Ce trebuie sa scrie in fiecare celula. Zilele libere urmeaza emailul HR:

      - zi libera (concediu / sarbatoare / compensatie): 8 pe task-ul ei de pe
        M.00556, Regular gol - altfel ziua ar avea 16 ore;
      - sarbatoare lucrata: overtime-ul cerut se pune pe proiect, ca de obicei;
      - sarbatoare cu oncall: stand by 8 daca e si overtime, 16 daca nu, ca
        ziua sa insumeze 24 in Time@IBM (diferenta fata de SAP o factureaza
        PMO manual - nu e treaba scriptului);
      - concediu sau compensatie cu oncall: fara stand by. SuccessFactors
        refuza orice inregistrare intr-o zi cu absenta de o zi intreaga
        ("A full day absence exists for the same period"), iar cele doua
        sisteme trebuie sa coincida - si cine e in concediu nu e de garda.
    """
    overtime = overtime or {}
    absences = absences or {}
    plan: dict[date, dict[str, str]] = {}
    for d in columns:
        is_weekend = d.weekday() >= 5
        absence = absences.get(d)
        standby = BLANK
        if oncall and oncall[0] <= d <= oncall[1]:
            if absence == HOLIDAY_LABEL:
                standby = (STANDBY_HOLIDAY_WITH_OVERTIME if overtime.get(d)
                           else STANDBY_HOLIDAY)
            elif absence:
                standby = BLANK
            else:
                standby = STANDBY_WEEKEND if is_weekend else STANDBY_WEEKDAY
        row = {
            REGULAR_LABEL: BLANK if (is_weekend or absence) else REGULAR_HOURS,
            STANDBY_LABEL: standby,
            OVERTIME_LABEL: overtime.get(d, BLANK),
        }
        for label in ABSENCE_LABELS:
            row[label] = ABSENCE_HOURS if absence == label else BLANK
        plan[d] = row
    return plan


ABSENCE_SHORT = {VACATION_LABEL: "concediu", HOLIDAY_LABEL: "liber legal",
                 COMP_LABEL: "compensatie"}


def print_plan(plan: dict[date, dict[str, str]]) -> None:
    log("Plan de pontaj:")
    log(f"    {'Zi':<12} {'Regular':>9} {'Stand by':>9} {'Overtime':>9}  Zi libera")
    totals = {REGULAR_LABEL: 0.0, STANDBY_LABEL: 0.0, OVERTIME_LABEL: 0.0}
    absent = 0.0
    for d in sorted(plan):
        cells = []
        for label in (REGULAR_LABEL, STANDBY_LABEL, OVERTIME_LABEL):
            value = plan[d].get(label, BLANK)
            totals[label] += float(value or 0)
            cells.append(f"{value or '-':>9}")
        free = ""
        for label in ABSENCE_LABELS:
            if plan[d].get(label):
                free = f"{plan[d][label]} {ABSENCE_SHORT[label]}"
                absent += float(plan[d][label])
        log(f"    {d.strftime('%a %d %b'):<12} " + " ".join(cells)
            + (f"  {free}" if free else ""))
    log(f"    {'TOTAL':<12} "
        + " ".join(f"{totals[l]:>9g}"
                   for l in (REGULAR_LABEL, STANDBY_LABEL, OVERTIME_LABEL))
        + (f"  {absent:g} libere" if absent else ""))


def ask_absences(args: argparse.Namespace, week_ending: date) -> dict[date, str]:
    week = week_days(week_ending)
    return merge_absences(
        parse_days(getattr(args, "vacation", None) or "", week),
        parse_days(getattr(args, "holiday", None) or "", week),
        parse_days(getattr(args, "comp", None) or "", week),
    )


def ask_oncall(
    args: argparse.Namespace, week_ending: date
) -> tuple[date, date] | None:
    if args.oncall:
        return parse_oncall(args.oncall, week_ending)
    if args.simple or not sys.stdin.isatty():
        return None

    print()
    print(f"  Saptamana care se incheie vineri {week_ending:%d %b %Y}")
    print("  1) Saptamana simpla  - doar 8h Regular, Luni-Vineri")
    print("  2) Saptamana cu oncall / stand by")
    while True:
        choice = input("  Alege [1/2]: ").strip()
        if choice == "1":
            return None
        if choice == "2":
            break
        print("  Raspunde cu 1 sau 2.")

    while True:
        raw = input('  Perioada oncall (ex: "9-15" sau "2026-09-09:2026-09-15"): ')
        try:
            start, end = parse_oncall(raw, week_ending)
        except ValueError as exc:
            print(f"  {exc}")
            continue
        print(f"  -> oncall {start:%d %b %Y} ... {end:%d %b %Y}")
        return start, end


def ask_overtime(
    args: argparse.Namespace, week_ending: date
) -> dict[date, str]:
    week = week_days(week_ending)

    if args.no_overtime:
        return {}
    if args.overtime:
        return parse_overtime(args.overtime, week)
    if args.simple or not sys.stdin.isatty():
        return {}

    print()
    answer = input("  Ai ore suplimentare (overtime) saptamana asta? [y/N]: ")
    if answer.strip().lower() not in ("y", "yes", "da", "d"):
        return {}

    print("  Format: zi=ore, separate prin virgula.")
    print("  Ex: '16=3'  sau  'wed=2.5, joi=1'  sau  '16=3, 17=2'")
    print(f"  Zile disponibile: {week[0]:%a %d} ... {week[-1]:%a %d}")
    while True:
        raw = input("  Overtime: ")
        try:
            result = parse_overtime(raw, week)
        except ValueError as exc:
            print(f"  {exc}")
            continue
        if not result:
            return {}
        for d, h in sorted(result.items()):
            print(f"  -> {d:%a %d %b}: {h}h")
        return result


# --------------------------------------------------------------------------
# Pasii pe pagina
# --------------------------------------------------------------------------

def ensure_logged_in(page: Page, minutes: int = 5) -> None:
    log(f"Deschid {URL}")
    page.goto(URL, wait_until="domcontentloaded")
    marker = page.get_by_text("Week ending", exact=False).first
    # Redirect-ul prin w3id dureaza si cand sesiunea e valida; 15 s erau prea
    # putin si anuntau "nu esti logat" exact inainte sa se logheze singur.
    try:
        marker.wait_for(state="visible", timeout=45_000)
        log("Sesiune activa.")
        return
    except PlaywrightTimeout:
        pass

    log("=" * 64)
    log("Logheaza-te in fereastra deschisa: w3id + parola sau passkey + 2FA.")
    log(f"Astept maxim {minutes} minute, apoi continui singur.")
    log("=" * 64)
    marker.wait_for(state="visible", timeout=minutes * 60_000)
    log("Login reusit.")


def select_week(page: Page, week_label: str | None) -> None:
    """
    Selectorul 'Week ending' e un mat-select Angular: valoarea curenta sta
    in trigger, optiunile apar intr-un overlay. Daca saptamana ceruta e
    deja cea afisata, nu e nimic de facut - si cautarea dupa text ar nimeri
    trigger-ul, nu optiunea.
    """
    if not week_label:
        return
    log(f"Selectez saptamana: {week_label}")
    combo = page.get_by_role("combobox").first
    try:
        current = (combo.inner_text() or "").strip()
    except Exception:
        current = ""
    if week_label in current:
        log("Saptamana e deja selectata.")
        return
    try:
        combo.select_option(label=week_label, timeout=5_000)
    except Exception:
        combo.click()
        option = page.locator("mat-option, [role='option']").filter(
            has_text=week_label
        ).first
        option.wait_for(state="visible", timeout=10_000)
        option.click()
    for _ in range(40):
        page.wait_for_timeout(150)
        try:
            if week_label in (combo.inner_text() or ""):
                page.wait_for_timeout(500)   # grila se reincarca dupa
                return
        except Exception:
            pass


def week_is_empty(page: Page) -> bool:
    """
    'No labor data found' sau grila cu randuri - oricare apare prima. Sa
    astepti doar mesajul inseamna 5 secunde pierdute la fiecare saptamana
    care are deja date. Sondam, pentru ca grila goala are si ea randuri
    (nevizibile) si un 'or' de locatoare ar nimeri-o pe aceea.
    """
    empty = page.get_by_text("No labor data found", exact=False).first
    rows = page.locator(f"{GRID_ROWS}[row-id*='|']")
    for _ in range(50):
        try:
            if empty.is_visible():
                return True
            if rows.count() and rows.first.is_visible():
                return False
        except Exception:
            pass
        page.wait_for_timeout(200)
    return False


def copy_from_previous_week(page: Page) -> None:
    log("Saptamana e goala -> 'Copy from a previous week'")
    if not click_by_text(page, "Copy from a previous week"):
        raise RuntimeError("Nu am gasit 'Copy from a previous week'.")
    page.wait_for_timeout(1_500)

    for confirm in ("Copy", "Continue", "OK", "Apply", "Confirm"):
        dialog = page.get_by_role("dialog")
        if dialog.count() == 0:
            break
        try:
            btn = dialog.get_by_role("button", name=confirm, exact=False).first
            if btn.is_visible():
                log(f"Confirm modalul cu '{confirm}'")
                btn.click()
                page.wait_for_timeout(1_500)
                break
        except Exception:
            continue

    # Orice claim item, al oricui: asteptam un rand de claim item (row-id
    # 'cont|task|...'). Nu "primul rand" - acela e randul Total, row-id '0',
    # care sta ascuns si a tinut asteptarea pana la timeout.
    page.locator(f"{GRID_ROWS}[row-id*='|']").first.wait_for(
        state="visible", timeout=20_000
    )
    log("Claim item copiat.")


def ensure_task_row(page: Page, project: dict, label: str) -> bool:
    """
    Se asigura ca exista randul cerut (Stand by, Overtime) sub claim
    item-ul dat. Daca lipseste, il adauga din meniul 'Action menu' al
    claim item-ului, unde optiunea se numeste 'Add <rand>'. Returneaza
    True daca randul exista la final.
    """
    if project_row(page, project, label) is not None:
        return True

    log(f"Adaug randul '{label}' din meniul lui '{project_title(project)}'")
    parent = claim_row(page, project)
    if parent is None:
        log(f"Nu am gasit randul claim item-ului '{project_title(project)}'.")
        return False
    parent.get_by_role("button", name="Action menu").first.click()

    item = page.get_by_role("menuitem", name=f"Add {label}", exact=True).first
    try:
        item.wait_for(state="visible", timeout=5_000)
    except PlaywrightTimeout:
        page.keyboard.press("Escape")
        log(f"Meniul nu are optiunea 'Add {label}'.")
        return False
    item.click()
    page.wait_for_timeout(1_500)

    # Unele versiuni cer confirmare intr-un modal
    for confirm in ("Add", "OK", "Save", "Apply", "Confirm"):
        dialog = page.get_by_role("dialog")
        if dialog.count() == 0:
            break
        try:
            btn = dialog.get_by_role("button", name=confirm, exact=False).first
            if btn.is_visible():
                btn.click()
                page.wait_for_timeout(1_500)
                break
        except Exception:
            continue

    ok = project_row(page, project, label, wait_ms=8_000) is not None
    log(f"Rand '{label}' adaugat." if ok else f"Randul '{label}' tot nu apare.")
    return ok


def fill_project_row(
    page: Page,
    project: dict,
    label: str,
    columns: list[date],
    column_ids: dict[date, str],
    plan: dict[date, dict[str, str]],
    dry_run: bool,
) -> int:
    """
    Un rand al unui claim item: Regular exista mereu; Stand by si Overtime
    se adauga doar cand planul are ore pe ele. Un rand care exista si nu
    mai are ore se goleste, nu se sterge.
    """
    tag = f"{label} [{project['task']}]"
    wanted = any(plan[d][label] for d in columns)
    row = None if project.get("_missing") else project_row(page, project, label)
    if row is None and wanted:
        if dry_run:
            log(f"DRY RUN: as adauga randul '{tag}'.")
            n = 0
            for d in columns:
                if plan[d][label]:
                    log(f"  {tag} {d:%a %d %b}: {plan[d][label]}")
                    n += 1
            return n
        if not ensure_task_row(page, project, label):
            raise RuntimeError(
                f"Nu am putut adauga randul {tag}. Adauga-l manual "
                "din meniul cu 3 puncte si reruleaza."
            )
        row = project_row(page, project, label)
    if row is None:
        return 0
    return fill_row(page, tag, columns, column_ids,
                    {d: {tag: plan[d][label]} for d in columns}, dry_run, row)


def fill_row(
    page: Page,
    label: str,
    columns: list[date],
    column_ids: dict[date, str],
    plan: dict[date, dict[str, str]],
    dry_run: bool,
    row: Locator | None = None,
) -> int:
    if row is None:
        row = find_row(page, label, wait_ms=500)
    if row is None:
        if any(plan[d][label] for d in columns):
            raise RuntimeError(
                f"Nu am gasit randul '{label}', dar am ore de pus acolo. "
                "Verifica manual claim item-ul."
            )
        log(f"Randul '{label}' lipseste si nu am nevoie de el. Sar peste.")
        return 0

    missing = [d for d in columns if d not in column_ids]
    if missing:
        raise RuntimeError(
            f"Nu gasesc coloana din grila pentru "
            + ", ".join(f"{d:%a %d %b}" for d in missing)
            + ". Opresc ca sa nu pontez gresit."
        )

    changed = 0
    for d in columns:
        cell = row.locator(f"[col-id='{column_ids[d]}']").first
        if cell.count() == 0:
            raise RuntimeError(
                f"Randul '{label}' nu are celula pentru {d:%a %d %b}."
            )
        want = fmt_num(plan[d][label])
        have = cell_value(cell)
        if have == want:
            continue

        shown = want or "(gol)"
        if dry_run:
            log(f"  {label} {d:%a %d %b}: '{have or 'gol'}' -> {shown}")
            changed += 1
            continue

        set_cell(page, cell, want)
        log(f"  {label} {d:%a %d %b}: {shown}")
        changed += 1

    return changed


def absence_row(page: Page, label: str) -> Locator | None:
    """
    Randul editabil al unei zile libere: sub M.00556 -> task-ul ei sta un
    'Regular' cu row-id 'M.00556|XL0B00|Designated Holiday|...|1reg|...'.
    """
    code = ABSENCE_TASKS[label]
    rows = page.locator(
        f"{GRID_ROWS}[row-id^='{ABSENCE_CLAIM_CODE}|{code}|']"
    ).filter(
        has=page.locator(GRID_LABEL_CELL).get_by_text(REGULAR_LABEL, exact=True)
    )
    try:
        if rows.count() > 0 and rows.first.is_visible():
            return rows.first
    except Exception:
        pass
    return None


def add_claim_item(page: Page, account: str, task: str) -> None:
    """
    'New claim item' -> cauta contul -> bifeaza WBS-ul -> bifeaza task-ul
    -> Add. Pasii sunt cei pe care ii face omul, in ordinea in care pagina
    ii deschide. Un cod care cere si Bill Code e refuzat cu mesaj: nu
    stim ce ar alege omul, deci il adauga el o data si scriptul il
    refoloseste.
    """
    log(f"Adaug claim item {account} -> {task}")
    # Buton pe o saptamana cu date, cartonas cu text pe una goala.
    if not click_by_text(page, "New claim item"):
        raise RuntimeError("Nu am gasit 'New claim item'.")

    box = page.get_by_placeholder(re.compile(r"^Search by account", re.I)).first
    box.wait_for(state="visible", timeout=10_000)
    box.fill(account)
    box.press("Enter")

    wbs = page.locator("input[type='radio'][aria-label='radio-wbs']").first
    try:
        wbs.wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeout:
        raise RuntimeError(f"Cautarea nu a gasit contul {account!r}.")
    wbs.check(force=True)

    task_row = page.locator("tr, [role='row']").filter(has_text=task).filter(
        has=page.locator("input[type='radio'][aria-label='radio-taskLevel']")
    ).first
    try:
        task_row.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeout:
        raise RuntimeError(f"Contul {account} nu are task-ul {task!r}.")
    task_row.locator("input[type='radio']").first.check(force=True)
    page.wait_for_timeout(500)

    others = page.locator("input[type='radio']:not([aria-label='radio-wbs'])"
                          ":not([aria-label='radio-taskLevel'])")
    if others.count() > 0:
        page.get_by_role("button", name="Cancel", exact=True).first.click()
        raise RuntimeError(
            f"Claim item-ul {account} -> {task} cere si un Bill Code. Adauga-l "
            "o data manual, cu Bill Code-ul potrivit; dupa aceea scriptul il "
            "gaseste in saptamana si il foloseste."
        )

    page.get_by_role("button", name="Add", exact=True).first.click()
    page.wait_for_timeout(2_000)
    expand_claim_items(page)


def add_absence_claim_item(page: Page, label: str) -> Locator:
    """M.00556 -> XL0A00 / XL0B00 / XL0C00, pentru zilele libere."""
    code = ABSENCE_TASKS[label]
    add_claim_item(page, ABSENCE_CLAIM_CODE, code)

    row = absence_row(page, label)
    if row is None:
        raise RuntimeError(
            f"Am apasat Add pentru {ABSENCE_CLAIM_CODE} -> {code}, dar randul "
            "nu a aparut in grila. Verifica pe site."
        )
    log("Claim item adaugat.")
    return row


def fill_absences(
    page: Page,
    columns: list[date],
    column_ids: dict[date, str],
    plan: dict[date, dict[str, str]],
    dry_run: bool,
) -> int:
    """
    Cate un rand pe fel de zi libera. Randul se adauga doar daca planul are
    ore pe el; unul deja existent (copiat din saptamana trecuta) se
    completeaza sau se goleste ca oricare altul.
    """
    changed = 0
    for label in ABSENCE_LABELS:
        wanted = any(plan[d][label] for d in columns)
        row = absence_row(page, label)
        if row is None:
            if not wanted:
                continue
            if dry_run:
                log(f"DRY RUN: as adauga claim item-ul "
                    f"{ABSENCE_CLAIM_CODE} -> {ABSENCE_TASKS[label]} ({label}).")
                for d in columns:
                    if plan[d][label]:
                        log(f"  {label} {d:%a %d %b}: {plan[d][label]}")
                        changed += 1
                continue
            row = add_absence_claim_item(page, label)
        changed += fill_row(page, label, columns, column_ids, plan, dry_run, row)
    return changed


def read_ibm_state(page: Page, columns: list[date], column_ids: dict[date, str],
                   projects: list[dict]) -> dict[date, dict]:
    """Ce are Time@IBM pe fiecare zi: stand by si overtime insumate peste
    toate claim item-urile, plus concediul - citit din grila, nu din plan,
    ca verificarea sa compare ce e salvat."""
    rows: list[tuple[str, Locator]] = []
    for p in projects:
        if p.get("_missing"):
            continue
        for key, label in (("standby", STANDBY_LABEL), ("overtime", OVERTIME_LABEL)):
            r = project_row(page, p, label, wait_ms=300)
            if r is not None:
                rows.append((key, r))
    vac = absence_row(page, VACATION_LABEL)
    if vac is not None:
        rows.append(("vacation", vac))

    def num(row: Locator, d: date) -> float:
        cell = row.locator(f"[col-id='{column_ids[d]}']").first
        if not cell.count():
            return 0.0
        txt = cell_value(cell).replace(",", ".")
        try:
            return float(txt) if txt else 0.0
        except ValueError:
            return 0.0

    state: dict[date, dict] = {}
    for d in columns:
        entry = {"standby": 0.0, "overtime": 0.0, "vacation": 0.0}
        for key, row in rows:
            entry[key] += num(row, d)
        entry["vacation"] = entry["vacation"] > 0
        state[d] = entry
    return state


def reconcile(columns: list[date], ibm: dict[date, dict], sf: dict[date, dict],
              absences: dict[date, str], dry_run: bool) -> int:
    """
    Verificarea de la final: Time@IBM si SuccessFactors, zi cu zi, pe stand
    by, overtime si concediu. Sarbatoarea legala se pune doar in Time@IBM,
    deci nu se compara; stand by-ul ei difera prin regula HR (SF are cu 8
    mai mult, diferenta o factureaza PMO) si e doar semnalat ca asteptat.
    Returneaza numarul de diferente reale.
    """
    log("Verificare Time@IBM <-> SuccessFactors"
        + (" (starea curenta, fara modificari - dry run)" if dry_run else "") + ":")
    log(f"    {'Zi':<12} {'stand by':>15} {'overtime':>15} {'concediu':>13}")
    problems: list[str] = []
    for d in sorted(columns):
        a = ibm.get(d, {"standby": 0.0, "overtime": 0.0, "vacation": False})
        b = sf.get(d)
        if b is None:
            log(f"    {d.strftime('%a %d %b'):<12} {'necitit din SF':>45}")
            problems.append(f"{d:%a %d %b}: nu am putut citi ziua din SF")
            continue
        holiday = absences.get(d) == HOLIDAY_LABEL
        marks = []

        def pair(x: float, y: float) -> str:
            fx = f"{x:g}" if x else "-"
            fy = f"{y:g}" if y else "-"
            return f"{fx:>6} / {fy:<6}"

        sb_ok = abs(a["standby"] - b["standby"]) < 0.01
        sb_expected = holiday and a["standby"] and abs(b["standby"] - a["standby"] - 8) < 0.01
        if not sb_ok and not sb_expected:
            marks.append(f"stand by {a['standby']:g} in Time@IBM, {b['standby']:g} in SF")
        ot_ok = abs(a["overtime"] - b["overtime"]) < 0.01
        if not ot_ok:
            marks.append(f"overtime {a['overtime']:g} in Time@IBM, {b['overtime']:g} in SF")
        vac_ok = bool(a["vacation"]) == bool(b["vacation"])
        if not vac_ok:
            marks.append("concediu " + ("in Time@IBM, dar nu in SF" if a["vacation"]
                                        else "in SF, dar nu in Time@IBM"))
        vac = f"{'da' if a['vacation'] else '-':>4} / {'da' if b['vacation'] else '-':<4}"
        flag = "  !!" if marks else ("  (regula HR)" if sb_expected else "")
        log(f"    {d.strftime('%a %d %b'):<12} {pair(a['standby'], b['standby']):>15} "
            f"{pair(a['overtime'], b['overtime']):>15} {vac:>13}{flag}")
        for m in marks:
            problems.append(f"{d:%a %d %b}: {m}")

    if problems:
        log(f"ATENTIE: {len(problems)} diferente intre Time@IBM si SuccessFactors:")
        for m in problems:
            log(f"    - {m}")
    else:
        log("Verificare reusita: Time@IBM si SuccessFactors coincid.")
    return len(problems)


def save(page: Page, dry_run: bool) -> None:
    """
    Save se apasa la fiecare rulare, cu sau fara modificari: orele scrise in
    grila nu raman fara el, si o saptamana nesalvata trebuie refacuta de la
    'Copy from a previous week' data urmatoare.

    Butonul e mereu activ, deci apasarea lui nu spune nimic. Ce spune ceva
    e bannerul cu care raspunde pagina - 'iERP labor for week ending ... was
    saved' sau '... was not changed' - si pe el asteptam. Fara banner nu
    raportam "salvat", pentru ca exact asta e problema pe care o rezolvam.
    """
    if dry_run:
        log("DRY RUN: nu apas Save.")
        return
    btn = page.get_by_role("button", name="Save", exact=True).first
    try:
        btn.wait_for(state="visible", timeout=8_000)
    except PlaywrightTimeout:
        raise RuntimeError("Nu am gasit butonul Save.")
    btn.click()

    banner = page.get_by_text(
        re.compile(r"labor for week ending", re.I), exact=False
    ).first
    try:
        banner.wait_for(state="visible", timeout=20_000)
    except PlaywrightTimeout:
        raise RuntimeError(
            "Am apasat Save, dar pagina nu a confirmat salvarea. "
            "Verifica pe site inainte sa inchizi."
        )
    text = " ".join((banner.inner_text() or "").split())
    if re.search(r"error|fail|could not|unable|invalid", text, re.I):
        raise RuntimeError(f"Salvarea a fost refuzata: {text}")
    log(f"Salvat. Site-ul spune: {text}")


def try_submit(page: Page) -> None:
    try:
        btn = page.get_by_role("button", name="Submit", exact=False).first
        if not btn.is_visible():
            log("Submit nu e vizibil.")
            return
        if btn.is_disabled():
            log("Submit e inca greyed out (saptamana nu s-a incheiat). "
                "Datele raman salvate.")
            return
        btn.click()
        page.wait_for_timeout(3_000)
        log("Submit trimis.")
    except Exception as exc:
        log(f"Nu am putut apasa Submit: {exc}")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def launch_browser(pw, slow_mo: int = 0):
    """
    Google Chrome-ul instalat, nu Chromium-ul care vine cu Playwright.

    Diferenta conteaza la login: Chromium ("Chrome for Testing") nu are
    integrarea macOS cu passkey-urile din iCloud Keychain, asa ca w3id
    ofera acolo doar parola - exact ce IBM incearca sa elimine. In Chrome,
    aceeasi pagina arata butonul de passkey si Touch ID-ul merge.

    Profilul ramane al scriptului (PROFILE_DIR), nu cel personal din Chrome:
    Chrome refuza sa fie automatizat pe profilul deschis, iar sesiunea w3id
    oricum e de ajuns acolo.
    """
    other = profile_in_use()
    if other:
        raise RuntimeError(
            "O alta fereastra de pontaj e deja deschisa (alta rulare, sau "
            f"login-ul) - {other}. Inchide-o sau asteapta sa termine, apoi "
            "incearca din nou."
        )
    kwargs = dict(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
        slow_mo=slow_mo,
        viewport={"width": 1600, "height": 1000},
        # Google Chrome-ul adevarat afiseaza o bara galbena "unsupported
        # command-line flag" pentru orice flag neobisnuit: --no-sandbox (pe
        # care Playwright il pune implicit) si --disable-blink-features=
        # AutomationControlled (pe care il puneam noi). Sandbox-ul merge
        # normal pe Mac/Windows, iar w3id, Time@IBM si SuccessFactors nu se
        # uita daca browserul e automatizat - verificat fara flag.
        chromium_sandbox=True,
    )
    try:
        ctx = pw.chromium.launch_persistent_context(channel="chrome", **kwargs)
    except Exception as exc:
        log("Nu am putut porni Google Chrome; folosesc Chromium-ul lui "
            "Playwright. Login-ul cu passkey nu va merge acolo, doar cu parola.")
        log(f"  ({str(exc).strip().splitlines()[0][:120]})")
        ctx = pw.chromium.launch_persistent_context(**kwargs)
    restore_session(ctx)
    return ctx


def profile_in_use() -> str | None:
    """
    Chrome tine 'SingletonLock' in profil cat timp ruleaza - un symlink
    catre 'host-pid'. Doua instante pe acelasi profil nu pot exista: a doua
    se inchide instant, iar de aici vedeam doar 'Target page ... has been
    closed'. Un lock ramas de la un proces mort nu conteaza.
    """
    lock = PROFILE_DIR / "SingletonLock"
    try:
        target = os.readlink(lock)
    except OSError:
        return None
    pid_txt = target.rsplit("-", 1)[-1]
    if not pid_txt.isdigit():
        return f"lock {target!r}"
    pid = int(pid_txt)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        pass
    return f"proces Chrome {pid}"


def restore_session(ctx) -> None:
    """Pune la loc cookie-urile salvate la ultima inchidere, inainte de
    prima navigare. Cele expirate intre timp se sar."""
    try:
        cookies = json.loads(SESSION_FILE.read_text()).get("cookies", [])
    except FileNotFoundError:
        return
    except Exception as exc:
        log(f"Nu pot citi sesiunea salvata ({exc}); pornesc fara ea.")
        return
    now = time.time()
    live = [c for c in cookies if c.get("expires", -1) in (-1, None)
            or c["expires"] > now]
    if not live:
        return
    try:
        ctx.add_cookies(live)
        log(f"Sesiune restaurata ({len(live)} cookie-uri).")
    except Exception as exc:
        log(f"Nu am putut restaura sesiunea: {exc}")


def close_browser(ctx) -> None:
    """Salveaza cookie-urile (inclusiv cele de sesiune, pe care Chrome le-ar
    arunca) si abia apoi inchide browserul."""
    try:
        state = ctx.storage_state()
        SESSION_FILE.write_text(json.dumps({"cookies": state.get("cookies", [])}))
        os.chmod(SESSION_FILE, 0o600)
    except Exception as exc:
        log(f"Nu am putut salva sesiunea: {exc}")
    ctx.close()


def week_label(d: date) -> str:
    """Formatul din selectorul Time@IBM: 'September 18, 2026'."""
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def friday_of(d: date) -> date:
    """Vinerea care incheie saptamana IBM in care cade ziua."""
    return d + timedelta(days=(4 - d.weekday()) % 7)


def weeks_touched(week_ending: date, oncall: tuple[date, date] | None) -> list[date]:
    """
    Saptamanile pe care le atinge perioada de oncall, in afara celei alese.
    Un oncall de marti pana marti cade in doua saptamani de pontaj; scriptul
    le ponteaza pe amandoua, ca omul sa nu ruleze de doua ori.
    """
    if not oncall:
        return []
    extra: list[date] = []
    d = oncall[0]
    while d <= oncall[1]:
        f = friday_of(d)
        if f != week_ending and f not in extra:
            extra.append(f)
        d += timedelta(days=1)
    return extra


def process_week(page, args: argparse.Namespace, week: str | None,
                 oncall_only: tuple[date, date] | None = None,
                 ) -> tuple[date, tuple[date, date] | None]:
    """
    O saptamana, cap-coada: Time@IBM apoi SuccessFactors. Returneaza
    vinerea saptamanii si perioada de oncall, ca sa se stie ce alte
    saptamani mai trebuie pontate. `oncall_only` e pentru acelea: doar
    stand by, fara overtime si zile libere, care se dau relativ la
    saptamana aleasa.
    """
    ensure_logged_in(page)
    select_week(page, week)
    week_ending = read_week_ending(page)
    log(f"Week ending: {week_ending:%A %d %B %Y}")

    # Pentru saptamanile suplimentare perioada e deja stiuta; altfel s-ar
    # cere inca o data de la tastatura.
    oncall = oncall_only if oncall_only else ask_oncall(args, week_ending)
    if oncall:
        log(f"Oncall: {oncall[0]:%d %b} ... {oncall[1]:%d %b}")

    if oncall_only:
        overtime, overtime_starts, absences = {}, {}, {}
    else:
        overtime = ask_overtime(args, week_ending)
        overtime_starts = (parse_overtime_starts(args.overtime, week_days(week_ending))
                           if args.overtime else {})
        if overtime:
            log("Overtime: " + ", ".join(
                f"{d:%a %d}={h}" + (f"@{overtime_starts[d]}" if d in overtime_starts else "")
                for d, h in sorted(overtime.items())))

        absences = ask_absences(args, week_ending)
        if absences:
            log("Zile libere: " + ", ".join(
                f"{d:%a %d} {ABSENCE_SHORT[l]}"
                for d, l in sorted(absences.items())))

    if week_is_empty(page):
        copy_from_previous_week(page)
    else:
        log("Saptamana are deja date, nu copiez.")
    expand_claim_items(page)

    columns = read_columns(page, week_ending)
    log("Coloane: " + ", ".join(f"{d:%a %d}" for d in columns))

    need_weekend = any(
        d.weekday() >= 5
        and ((oncall and oncall[0] <= d <= oncall[1]) or d in overtime)
        for d in week_days(week_ending)
    )
    if need_weekend and not weekend_visible(columns):
        if toggle_weekend(page, show=True):
            columns = read_columns(page, week_ending)
            log("Coloane dupa Show weekend: "
                + ", ".join(f"{d:%a %d}" for d in columns))

    missing = [d for d in overtime if d not in columns]
    if missing:
        raise RuntimeError(
            "Overtime cerut pe zile care nu sunt afisate: "
            + ", ".join(f"{d:%a %d %b}" for d in missing)
        )

    missing = [d for d in absences if d not in columns]
    if missing:
        raise RuntimeError(
            "Zile libere cerute pe zile care nu sunt afisate: "
            + ", ".join(f"{d:%a %d %b}" for d in missing)
        )

    plan = build_plan(columns, oncall, overtime, absences)
    print_plan(plan)

    projects = resolve_projects(page, load_config(), args.dry_run)
    per_project = split_plan(plan, projects, columns)
    print_projects(projects, per_project, columns)

    column_ids = read_column_ids(page, week_ending)

    if not args.yes and not args.dry_run and sys.stdin.isatty():
        answer = input("  Confirmi? [y/N]: ").strip().lower()
        if answer not in ("y", "yes", "da", "d"):
            raise RuntimeError("Anulat. Nu am salvat nimic.")

    changed = 0
    for p in projects:
        for label in (REGULAR_LABEL, STANDBY_LABEL, OVERTIME_LABEL):
            changed += fill_project_row(
                page, p, label, columns, column_ids,
                per_project[project_key(p)], args.dry_run
            )

    changed += fill_absences(page, columns, column_ids, plan, args.dry_run)

    log(f"{changed} casute modificate.")

    save(page, args.dry_run)

    # Submit e deliberat pe seama omului: inchide saptamana si nu se
    # mai poate corecta din script. Butonul e activ tot timpul pe
    # site, deci nu exista o plasa de siguranta acolo.
    if args.submit and not args.dry_run:
        try_submit(page)
    else:
        log("Submit lasat pe seama ta.")

    # SuccessFactors: aceleasi ore de stand by si overtime, in forma
    # lui. HR cere ca cele doua sa fie identice.
    if not getattr(args, "no_sf", False):
        sf_entries = {
            d: sf_ibm.desired_entries(
                d, plan[d],
                standby_label=STANDBY_LABEL,
                overtime_label=OVERTIME_LABEL,
                holiday=absences.get(d) == HOLIDAY_LABEL,
                off_day=d in absences,
                overtime_start=overtime_starts.get(d),
            )
            for d in columns
        }
        # Citit din grila inainte de a pleca de pe Time@IBM, dupa Save.
        ibm_state = read_ibm_state(page, columns, column_ids, projects)
        sf_state = sf_ibm.sync(
            page, columns, sf_entries, args.dry_run,
            vacation_days=[d for d in columns
                           if absences.get(d) == VACATION_LABEL],
        )
        reconcile(columns, ibm_state, sf_state, absences, args.dry_run)
    return week_ending, oncall


def scan_projects(week: str | None = None) -> list[dict]:
    """
    Deschide Time@IBM si citeste claim item-urile saptamanii - pentru
    panoul de configurare din interfata, unde omul spune apoi cum imparte
    orele. Nu scrie nimic.
    """
    if not PLAYWRIGHT_OK:
        raise RuntimeError(PLAYWRIGHT_HINT)
    other = profile_in_use()
    if other:
        raise RuntimeError(
            f"O alta fereastra de pontaj e deja deschisa - {other}. Inchide-o "
            "si incearca din nou."
        )
    with sync_playwright() as pw:
        ctx = launch_browser(pw)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(20_000)
        try:
            ensure_logged_in(page)
            select_week(page, week)
            week_ending = read_week_ending(page)
            log(f"Week ending: {week_ending:%A %d %B %Y}")
            if week_is_empty(page):
                log("Saptamana e goala; ma uit in cea dinainte.")
                page.get_by_role("button", name="Previous", exact=False).first.click()
                page.wait_for_timeout(2_000)
                if week_is_empty(page):
                    log("Nici aceea nu are claim item-uri.")
                    return []
            expand_claim_items(page)
            found = read_projects(page)
            for f in found:
                log(f"Claim item: {project_title(f)}  ({f['account']})")
            if not found:
                log("Nu am gasit niciun claim item.")
            return found
        finally:
            close_browser(ctx)


def run(args: argparse.Namespace) -> int:
    if not PLAYWRIGHT_OK:
        log(PLAYWRIGHT_HINT)
        return 2
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    other = profile_in_use()
    if other:
        log("EROARE: O alta fereastra de pontaj e deja deschisa (alta rulare, "
            f"sau login-ul) - {other}. Inchide-o sau asteapta sa termine, apoi "
            "incearca din nou.")
        return 1
    # Mereu vizibil: w3id refuza sesiunea din headless, iar login-ul este
    # oricum al omului - parola sau passkey-ul se pun in fereastra IBM,
    # niciodata in script.
    with sync_playwright() as pw:
        ctx = launch_browser(pw, slow_mo=300 if args.debug else 0)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(20_000)

        try:
            if args.login:
                ensure_logged_in(page)
                log("Login salvat. Poti rula scriptul normal de acum.")
                return 0

            week_ending, oncall = process_week(page, args, args.week)

            extra = weeks_touched(week_ending, oncall)
            if extra:
                log("Oncall-ul atinge si saptamana "
                    + ", ".join(f"{f:%d %b}" for f in extra)
                    + " - o pontez si pe aceea (doar stand by).")
                for f in extra:
                    log("-" * 64)
                    process_week(page, args, week_label(f), oncall_only=oncall)

            if args.debug:
                input("[pontaj] Enter ca sa inchid browserul...")
            return 0

        except Exception as exc:
            msg = str(exc)
            if "has been closed" in msg or "Target closed" in msg:
                msg = ("Fereastra Chrome s-a inchis inainte sa termin. Ori ai "
                       "inchis-o tu, ori alta rulare a pornit pe acelasi profil "
                       "in acelasi timp. Porneste din nou, o singura data.")
            log(f"EROARE: {msg}")
            shot = Path.cwd() / "pontaj_eroare.png"
            try:
                page.screenshot(path=str(shot), full_page=True)
                log(f"Screenshot: {shot}")
            except Exception:
                pass
            if args.debug:
                input("[pontaj] Enter ca sa inchid browserul...")
            return 1
        finally:
            close_browser(ctx)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pontaj automat IBM cu oncall")
    p.add_argument("--week", help='ex: "September 18, 2026"')
    p.add_argument("--simple", action="store_true",
                   help="saptamana fara oncall, fara intrebari")
    p.add_argument("--oncall", metavar="PERIOADA",
                   help='ex: "9-15" sau "2026-09-09:2026-09-15"')
    p.add_argument("--overtime", metavar="ZI=ORE[@ORA]",
                   help='ex: "16=3" sau "wed=2.5, joi=1"')
    p.add_argument("--vacation", metavar="ZILE",
                   help='concediu, ex: "14-16" sau "luni, marti"')
    p.add_argument("--holiday", metavar="ZILE",
                   help='sarbatoare legala, ex: "15"')
    p.add_argument("--comp", metavar="ZILE",
                   help='zi libera in compensatie (XL0C00), ex: "18"')
    p.add_argument("--no-overtime", action="store_true",
                   help="sari peste intrebarea de overtime")
    p.add_argument("--yes", action="store_true", help="nu cere confirmare")
    p.add_argument("--login", action="store_true",
                   help="doar deschide pagina si asteapta login-ul, fara pontaj")
    p.add_argument("--submit", action="store_true", help="incearca si Submit")
    p.add_argument("--no-sf", action="store_true",
                   help="nu scrie si in SuccessFactors")
    p.add_argument("--dry-run", action="store_true", help="nu salveaza nimic")
    p.add_argument("--debug", action="store_true", help="browser vizibil, incet")
    p.add_argument("--show", action="store_true",
                   help="(pastrat pentru compatibilitate; browserul e mereu vizibil)")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(run(parse_args()))
