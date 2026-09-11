"""
SuccessFactors ("Record Your Time"): aceleasi ore de stand by si overtime ca
in Time@IBM, in foaia de pontaj SAP.

HR cere ca cele doua sa fie identice - o luna cu discrepante se plateste
incomplet - asa ca acest modul scrie in SF exact ce s-a scris in Time@IBM,
in forma pe care SF o cere: intervale de ore, nu numere de ore.

Modelele (citite de pe foi de pontaj deja aprobate):

  Stand by, zi lucratoare, 15.5 h  = 12:00 AM - 09:00 AM  +  05:30 PM - 12:00 AM
  Stand by, weekend, 24 h          = 12:00 AM - 12:00 PM  +  12:00 PM - 12:00 AM
  Overtime, N ore                  = o inregistrare, inceput -> inceput + N

Overtime-ul incepe implicit la 05:30 PM intr-o zi lucratoare (dupa programul
09:00-17:30) si la 09:00 AM in weekend sau intr-o zi libera.

Sarbatoare legala cu oncall (emailul HR): SF vrea 24 h stand by fara
overtime, sau overtime + 16 h stand by cu - adica toata ziua mai putin
intervalul de overtime.

Pagina e SAP Fiori: foaia de pontaj sta intr-un iframe (hcm41.sapsf.com),
saptamana ei e luni-duminica (nu sambata-vineri ca la IBM), iar controalele
au id-uri stabile cu prefixul 'sap.sf.attendancerecording.timesheets---'.
Campurile unei inregistrari noi au id-uri generate (__box11, __picker0), asa
ca se gasesc dupa rol si placeholder, in panoul zilei.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

SF_URL = (
    "https://sf-wz-prd-p2-4snxii8t.workzonehr.cfapps.us10.hana.ondemand.com/"
    "site#IBMTIME-Show?sap-app-origin-hint="
    "&sap-ui-app-id-hint=417571ad-34c5-4d04-8590-089eed813e58"
)
SF_FRAME_URL = "sapsf.com/sf/timesheet"
V = "sap.sf.attendancerecording.timesheets---"
SUMMARY = V + "timeSheetSummaryView--"
DAY = V + "timeRecordingView--"
DAY_PANEL = f"[id='{DAY}timeRecordingPage']"

TYPE_STANDBY = "Standby"
TYPE_OVERTIME = "Overtime"
SF_TYPES = (TYPE_STANDBY, TYPE_OVERTIME)
ABSENCE_VACATION = "Vacation"      # concediul; sarbatoarea legala nu se pune in SF

MIDNIGHT = "12:00 AM"
NOON = "12:00 PM"
WORK_START = "09:00 AM"
WORK_END = "05:30 PM"

Entry = tuple[str, str, str]   # (tip, inceput, sfarsit) in format "hh:mm AM"


def log(msg: str) -> None:
    print(f"[sf] {msg}", flush=True)


# --------------------------------------------------------------------------
# Ore
# --------------------------------------------------------------------------

def norm_time(text: str) -> str:
    """'9:00 AM', '09:00 AM', '9:00AM' -> '09:00 AM'."""
    t = text.replace(" ", " ").replace(" ", " ").strip().upper()
    m = re.match(r"^(\d{1,2}):(\d{2})\s*([AP]M)$", t)
    if not m:
        raise ValueError(f"Ora neinteleasa: {text!r}")
    return f"{int(m.group(1)):02d}:{m.group(2)} {m.group(3)}"


def add_hours(start: str, hours: float) -> str:
    t = datetime.strptime(norm_time(start), "%I:%M %p") + timedelta(hours=hours)
    return t.strftime("%I:%M %p")


def desired_entries(
    d: date,
    row: dict[str, str],
    *,
    standby_label: str,
    overtime_label: str,
    holiday: bool,
    off_day: bool,
) -> list[Entry]:
    """
    Ce inregistrari trebuie sa aiba ziua in SF, din randul ei de plan.
    `holiday` = sarbatoare legala; `off_day` = orice zi libera (concediu,
    sarbatoare, compensatie), unde overtime-ul incepe dimineata.
    """
    entries: list[Entry] = []
    standby = row.get(standby_label, "")
    overtime = row.get(overtime_label, "")
    weekend = d.weekday() >= 5

    ot_start = WORK_START if (weekend or off_day) else WORK_END
    ot_end = add_hours(ot_start, float(overtime)) if overtime else None
    if overtime:
        entries.append((TYPE_OVERTIME, ot_start, ot_end))

    if standby:
        if holiday and overtime:
            # toata ziua mai putin overtime-ul: 16 h la 8 h de overtime
            entries.append((TYPE_STANDBY, MIDNIGHT, ot_start))
            entries.append((TYPE_STANDBY, ot_end, MIDNIGHT))
        elif weekend or holiday:
            entries.append((TYPE_STANDBY, MIDNIGHT, NOON))
            entries.append((TYPE_STANDBY, NOON, MIDNIGHT))
        else:
            entries.append((TYPE_STANDBY, MIDNIGHT, WORK_START))
            entries.append((TYPE_STANDBY, WORK_END, MIDNIGHT))
    return entries


def fmt_entry(e: Entry) -> str:
    return f"{e[0]} {e[1]} - {e[2]}"


# --------------------------------------------------------------------------
# Pagina
# --------------------------------------------------------------------------

def frame_text(fr, limit: int = 30_000) -> str:
    raw = fr.locator("body").inner_text()
    return " | ".join(l.strip() for l in raw.splitlines() if l.strip())[:limit]


def open_timesheet(page, minutes: int = 5):
    """
    Deschide SF si asteapta foaia de pontaj. Login-ul (passkey) e al omului;
    asteptam pana la `minutes` minute sa apara foaia.
    """
    log("Deschid SuccessFactors.")
    try:
        page.goto(SF_URL, wait_until="domcontentloaded")
    except Exception as exc:
        # Un redirect SSO pornit in timpul incarcarii intrerupe navigarea
        # (net::ERR_ABORTED), dar pagina merge mai departe; asteptam foaia.
        log(f"  (navigarea a fost intrerupta de un redirect: "
            f"{str(exc).splitlines()[0][:80]})")
    told = False
    deadline = minutes * 60
    waited = 0
    while waited < deadline:
        page.wait_for_timeout(3_000)
        waited += 3
        for f in page.frames:
            if SF_FRAME_URL in f.url:
                try:
                    if "Time Sheet for" in frame_text(f, 2_000):
                        page.wait_for_timeout(1_500)
                        log("Foaia de pontaj SF e deschisa.")
                        return f
                except Exception:
                    pass
        if not told and waited >= 20:
            told = True
            log("=" * 64)
            log("Daca SF cere login, fa-l in fereastra (passkey / Touch ID).")
            log(f"Astept maxim {minutes} minute.")
            log("=" * 64)
    raise RuntimeError("Nu am ajuns la foaia de pontaj din SuccessFactors.")


MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def header_range(fr) -> tuple[date, date]:
    """'Time Sheet for Aug 31 – Sep 6, 2026' / 'Dec 29, 2025 – Jan 4, 2026'."""
    m = re.search(r"Time Sheet for ([^|]+?) \|", frame_text(fr, 1_500))
    if not m:
        raise RuntimeError("Nu gasesc antetul 'Time Sheet for ...'.")
    # SAP pune spatii subtiri (U+2009) si linii lungi in jurul cratimei.
    text = re.sub(r"[\u2009\u202f\u00a0]", " ", m.group(1))
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    parts = [p.strip() for p in text.split("-")]
    if len(parts) != 2:
        raise RuntimeError(f"Antet neinteles: {text!r}")

    def parse(p: str, default_month: int | None, default_year: int | None):
        m2 = re.match(r"^(?:([A-Za-z]{3})\w*\s+)?(\d{1,2})(?:,\s*(\d{4}))?$", p)
        if not m2:
            raise RuntimeError(f"Data neinteleasa in antet: {p!r}")
        mon = MONTHS[m2.group(1)[:3]] if m2.group(1) else default_month
        year = int(m2.group(3)) if m2.group(3) else default_year
        return mon, int(m2.group(2)), year

    # Trei forme: 'Sep 7 - 13, 2026', 'Aug 31 - Sep 6, 2026',
    # 'Dec 29, 2025 - Jan 4, 2026'. Luna lipsa se ia de la cealalta parte.
    m_start, d_start, y_start = parse(parts[0], None, None)
    m_end, d_end, y_end = parse(parts[1], None, None)
    if m_end is None:
        m_end = m_start
    if m_start is None or y_end is None:
        raise RuntimeError(f"Antet neinteles: {text!r}")
    if y_start is None:
        y_start = y_end - 1 if m_start > m_end else y_end
    return date(y_start, m_start, d_start), date(y_end, m_end, d_end)


def goto_week(page, fr, day: date) -> None:
    for _ in range(60):
        start, end = header_range(fr)
        if start <= day <= end:
            return
        btn = "navigateToPreviousSummaryBtn" if day < start else "navigateToNextSummaryBtn"
        before = (start, end)
        fr.locator(f"[id='{SUMMARY}{btn}']").click()
        for _ in range(30):
            page.wait_for_timeout(500)
            try:
                if header_range(fr) != before:
                    break
            except Exception:
                pass
    raise RuntimeError(f"Nu am ajuns la saptamana lui {day:%d %b %Y} in SF.")


def open_day(page, fr, day: date) -> None:
    # Randul zilei, dupa numele ei si data ('Saturday ... Sep 12'; azi are
    # virgula: 'Friday, Sep 11'). Click pe mijlocul randului: stanga e bifa
    # de selectie, dreapta e sageata.
    row = fr.locator("tr[role='row']").filter(
        # O singura zi cu numele asta pe saptamana, iar goto_week a verificat
        # deja saptamana. \s si nu spatiu: SAP pune spatii speciale intre
        # luna si zi; fara \b sau lookahead: has_text nu le traduce.
        has_text=re.compile(rf"{day:%A}[\s\S]*{day:%b}\s+{day.day}")
    ).first
    row.wait_for(state="visible", timeout=15_000)
    row.click()
    wanted = f"{day:%B} {day.day}, {day.year}"
    for _ in range(30):
        page.wait_for_timeout(500)
        if wanted in frame_text(fr).replace(" ", " "):
            return
    raise RuntimeError(f"Panoul zilei {day:%a %d %b} nu s-a deschis in SF.")


def read_entries(fr) -> list[Entry]:
    """Inregistrarile din 'Working Times' ale zilei deschise."""
    text = frame_text(fr).replace(" ", " ").replace(" ", " ")
    start = text.find("Working Times (")
    end = text.find("Allowances (", start)
    if start < 0 or end < 0:
        raise RuntimeError("Nu gasesc sectiunea 'Working Times' in panoul zilei.")
    section = text[start:end]
    found: list[Entry] = []
    for kind, a, b in re.findall(
        r"(Standby|Overtime) \| (\d{1,2}:\d{2} [AP]M) - (\d{1,2}:\d{2} [AP]M)",
        section,
    ):
        found.append((kind, norm_time(a), norm_time(b)))
    return found


def delete_entries(page, fr) -> int:
    """Sterge toate inregistrarile Standby/Overtime ale zilei deschise."""
    panel = fr.locator(DAY_PANEL)
    deleted = 0
    for _ in range(20):
        btn = panel.get_by_role("button", name="Delete", exact=True).first
        if btn.count() == 0:
            break
        btn.click()
        page.wait_for_timeout(600)
        confirm_dialog(page, fr)
        deleted += 1
    return deleted


def add_entry(page, fr, entry: Entry) -> None:
    """'Record' -> tip, inceput, sfarsit. Inregistrarea noua apare prima."""
    kind, start, end = entry
    fr.locator(f"[id='{DAY}attendancesClock--add']").click()
    page.wait_for_timeout(1_200)
    panel = fr.locator(DAY_PANEL)

    combo = panel.locator("input[role='combobox']").first
    combo.wait_for(state="visible", timeout=10_000)
    # Campurile de ora se cauta in panoul acestei inregistrari, nu in toata
    # ziua: o inregistrare adaugata adineauri ramane deschisa si ar fi
    # gasita prima.
    entry_panel = combo.locator("xpath=ancestor::div[contains(@class,'sapMPanel')][1]")
    combo.click()
    combo.fill("")
    combo.type(kind, delay=30)
    page.wait_for_timeout(400)
    combo.press("Enter")
    page.wait_for_timeout(300)
    got = combo.input_value().strip()
    if got != kind:
        raise RuntimeError(f"Time Type: am cerut {kind!r}, a ramas {got!r}.")

    pickers = entry_panel.locator("input[placeholder^='e.g.']")
    for i, value in enumerate((start, end)):
        box = pickers.nth(i)
        # Camp cu masca: fill() e ignorat, tastele sunt intelese.
        box.click()
        box.press("Meta+a")
        box.press("Control+a")
        box.press("Backspace")
        box.type(value, delay=40)
        box.press("Tab")
        page.wait_for_timeout(400)
        have = box.input_value().replace(" ", " ").strip()
        try:
            ok = norm_time(have) == norm_time(value)
        except ValueError:
            ok = False
        if not ok:
            raise RuntimeError(
                f"{'Start' if i == 0 else 'End'} Time: am scris {value!r}, "
                f"campul arata {have!r}."
            )
    page.wait_for_timeout(300)


def confirm_dialog(page, fr) -> str | None:
    """Confirma un dialog SAP daca a aparut; returneaza textul lui."""
    # MessageBox-ul SAP e 'alertdialog', nu 'dialog'; popover-ele de ajutor
    # ('Changing Your Time Clock Format') au si ele butoane si nu ne privesc.
    dialog = fr.locator(".sapMMessageBox, [role='alertdialog']")
    if dialog.count() == 0 or not dialog.first.is_visible():
        return None
    text = " ".join(dialog.first.inner_text().split())
    for name in ("OK", "Yes", "Delete", "Continue"):
        b = dialog.first.get_by_role("button", name=name, exact=True)
        if b.count():
            b.first.click()
            page.wait_for_timeout(800)
            return text
    return text


def save_day(page, fr) -> None:
    save = fr.locator(f"[id='{DAY}btnSaveTimeRecords']")
    save.click()
    page.wait_for_timeout(800)
    # O foaie deja aprobata cere confirmare: 'You need to submit the time
    # sheet again.' Omul o retrimite, ca la Submit-ul din Time@IBM.
    text = confirm_dialog(page, fr)
    if text:
        log(f"  SF: {text}")
        if "submit" in text.lower():
            log("  Foaia SF a fost aprobata inainte: trebuie retrimisa (Submit).")
    # Save e dezactivat cat timp nu exista modificari nesalvate; cand
    # redevine asa, salvarea s-a incheiat.
    for _ in range(60):
        page.wait_for_timeout(500)
        try:
            if save.is_disabled():
                page.wait_for_timeout(800)
                return
        except Exception:
            pass
        text = confirm_dialog(page, fr)
        if text:
            log(f"  SF: {text}")
    raise RuntimeError("Save in SF nu s-a incheiat; verifica pe pagina.")


def sync_day(page, fr, day: date, wanted: list[Entry], dry_run: bool) -> bool:
    """Aduce ziua la `wanted`. Returneaza True daca a schimbat ceva."""
    goto_week(page, fr, day)
    open_day(page, fr, day)
    have = read_entries(fr)
    if sorted(have) == sorted(wanted):
        return False

    log(f"{day:%a %d %b}: SF are [{', '.join(map(fmt_entry, have)) or 'nimic'}]"
        f" -> vreau [{', '.join(map(fmt_entry, wanted)) or 'nimic'}]")
    if dry_run:
        return True

    if have:
        n = delete_entries(page, fr)
        log(f"  sterse {n} inregistrari")
    for e in wanted:
        add_entry(page, fr, e)
        log(f"  adaugat {fmt_entry(e)}")
    save_day(page, fr)

    after = read_entries(fr)
    if sorted(after) != sorted(wanted):
        raise RuntimeError(
            f"Dupa Save, {day:%a %d %b} arata "
            f"[{', '.join(map(fmt_entry, after))}] in loc de "
            f"[{', '.join(map(fmt_entry, wanted))}]."
        )
    log(f"  salvat: {day:%a %d %b} OK")
    return True


# --------------------------------------------------------------------------
# Concediu: 'Absences -> Create' e o cerere de concediu, cu Submit
# --------------------------------------------------------------------------

def read_absences(fr) -> list[str]:
    """Absentele zilei deschise, ca text ('Vacation ...')."""
    text = frame_text(fr).replace("\u202f", " ").replace("\u00a0", " ")
    start = text.find("Absences (")
    if start < 0:
        raise RuntimeError("Nu gasesc sectiunea 'Absences' in panoul zilei.")
    end = text.find("| Save |", start)
    section = text[start:end if end > 0 else None]
    if "No absences recorded" in section:
        return []
    return [p.strip() for p in section.split(" | ")[2:] if p.strip()]


def fmt_date(d: date) -> str:
    return f"{d:%b} {d.day:02d}, {d.year}"


def set_text(page, box, value: str) -> None:
    box.click()
    box.press("Meta+a")
    box.press("Control+a")
    box.press("Backspace")
    box.type(value, delay=30)


def create_vacation(page, fr, first: date, last: date) -> None:
    """
    Deschide dialogul de pe ziua `first`, il completeaza pentru intervalul
    first..last si apasa Submit - o cerere de concediu, ca cea facuta de om.
    """
    fr.locator(f"[id='{DAY}recordsAbsence--add']").click()
    dlg = fr.locator(".sapMDialog").filter(has_text="Create Absence").first
    dlg.wait_for(state="visible", timeout=30_000)
    combos = dlg.locator("input[role='combobox']")
    combos.first.wait_for(state="visible", timeout=30_000)
    page.wait_for_timeout(800)

    kind = combos.nth(0)
    if kind.input_value().strip() != ABSENCE_VACATION:
        set_text(page, kind, ABSENCE_VACATION)
        kind.press("Enter")
        page.wait_for_timeout(500)
    if kind.input_value().strip() != ABSENCE_VACATION:
        raise RuntimeError(f"Time Type: nu am putut alege {ABSENCE_VACATION!r}.")

    duration = combos.nth(1)
    if duration.input_value().strip() != "Full Day":
        set_text(page, duration, "Full Day")
        duration.press("Enter")
        page.wait_for_timeout(500)

    dates = dlg.locator("input[placeholder='MMM dd, yyyy']")
    for i, d in enumerate((first, last)):
        box = dates.nth(i)
        if box.input_value().replace("\u202f", " ").strip() == fmt_date(d):
            continue
        set_text(page, box, fmt_date(d))
        box.press("Enter")
        page.wait_for_timeout(500)
        have = box.input_value().replace("\u202f", " ").strip()
        if have != fmt_date(d):
            raise RuntimeError(
                f"{'Start' if i == 0 else 'End'} Date: am scris {fmt_date(d)!r}, "
                f"campul arata {have!r}."
            )

    dlg.get_by_role("button", name="Submit", exact=True).first.click()
    for _ in range(60):
        page.wait_for_timeout(500)
        text = confirm_dialog(page, fr)
        if text:
            log(f"  SF: {text}")
            if re.search(r"error|cannot|not allowed|invalid", text, re.I):
                raise RuntimeError(f"SF a refuzat cererea de concediu: {text}")
        if dlg.count() == 0 or not dlg.is_visible():
            page.wait_for_timeout(1_500)
            return
    raise RuntimeError("Dialogul 'Create Absence' nu s-a inchis dupa Submit.")


def sync_vacation(page, fr, days: list[date], dry_run: bool) -> int:
    """
    Zilele de concediu, grupate pe intervale consecutive (asa cum face si
    omul o cerere). O zi care are deja concediu in SF e lasata in pace; un
    concediu din SF care nu e in plan e doar semnalat - anularea unei cereri
    e treaba omului si a HR-ului.
    """
    days = sorted(days)
    changed = 0
    i = 0
    while i < len(days):
        first = days[i]
        goto_week(page, fr, first)
        open_day(page, fr, first)
        have = read_absences(fr)
        if any(ABSENCE_VACATION.lower() in a.lower() for a in have):
            log(f"{first:%a %d %b}: SF are deja concediu ({have[0]}).")
            i += 1
            continue
        # cat de departe merge intervalul consecutiv (in aceeasi saptamana SF)
        last = first
        j = i + 1
        while j < len(days) and (days[j] - last).days == 1:
            last = days[j]
            j += 1
        log(f"{first:%a %d %b}: SF are [{', '.join(have) or 'nimic'}] -> vreau "
            f"concediu {fmt_date(first)}"
            + (f" - {fmt_date(last)}" if last != first else ""))
        if not dry_run:
            create_vacation(page, fr, first, last)
            open_day(page, fr, first)
            after = read_absences(fr)
            if not any(ABSENCE_VACATION.lower() in a.lower() for a in after):
                raise RuntimeError(
                    f"Dupa Submit, {first:%a %d %b} tot nu are concediu in SF "
                    f"([{', '.join(after) or 'nimic'}])."
                )
            log(f"  trimis: concediu {fmt_date(first)} - {fmt_date(last)} OK")
        changed += 1
        i = j
    return changed


def sync(page, days: list[date], plan_entries: dict[date, list[Entry]],
         dry_run: bool, vacation_days: list[date] | None = None) -> int:
    """
    Trece prin zilele date, in ordine, si aduce fiecare la inregistrarile
    cerute. Submit-ul foii SF ramane, ca la Time@IBM, pe seama omului.
    """
    fr = open_timesheet(page)
    changed = 0
    for d in sorted(days):
        if sync_day(page, fr, d, plan_entries.get(d, []), dry_run):
            changed += 1
    if vacation_days:
        changed += sync_vacation(page, fr, vacation_days, dry_run)
    if dry_run:
        log(f"DRY RUN: {changed} zile ar fi schimbate in SF.")
    else:
        log(f"{changed} zile schimbate in SF. Submit-ul foii ramane pe seama ta.")
    return changed
