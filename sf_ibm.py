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
OFFICE_ALLOWANCE = "Work @IBM Office"   # ziua de birou: o alocatie, doar in SF

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
    overtime_start: str | None = None,
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

    ot_start = overtime_start or (WORK_START if (weekend or off_day) else WORK_END)
    ot_end = add_hours(ot_start, float(overtime)) if overtime else None
    if overtime:
        entries.append((TYPE_OVERTIME, ot_start, ot_end))

    if standby:
        if weekend or holiday:
            blocks = [(MIDNIGHT, NOON), (NOON, MIDNIGHT)]
        else:
            blocks = [(MIDNIGHT, WORK_START), (WORK_END, MIDNIGHT)]
        # SF nu accepta doua inregistrari peste acelasi interval - nici nu
        # activeaza Save. Stand by-ul e restul zilei minus overtime-ul, ca in
        # regula HR pentru sarbatori (8 overtime + 16 stand by).
        if overtime:
            blocks = subtract_interval(blocks, (ot_start, ot_end))
        for a, b in blocks:
            entries.append((TYPE_STANDBY, a, b))
    return entries


def minutes_of(t: str, end: bool = False) -> int:
    """Minute de la miezul noptii; '12:00 AM' ca sfarsit inseamna 24:00."""
    tt = datetime.strptime(norm_time(t), "%I:%M %p")
    m = tt.hour * 60 + tt.minute
    return 24 * 60 if (end and m == 0) else m


def of_minutes(m: int) -> str:
    m %= 24 * 60
    return datetime(2000, 1, 1, m // 60, m % 60).strftime("%I:%M %p")


def subtract_interval(blocks: list[tuple[str, str]],
                      cut: tuple[str, str]) -> list[tuple[str, str]]:
    """Scoate intervalul `cut` din fiecare bloc; un bloc taiat la mijloc
    devine doua. Un overtime care trece de miezul noptii se taie la 24:00."""
    c0, c1 = minutes_of(cut[0]), minutes_of(cut[1], end=True)
    if c1 <= c0:
        c1 = 24 * 60
    out: list[tuple[str, str]] = []
    for a, b in blocks:
        b0, b1 = minutes_of(a), minutes_of(b, end=True)
        if c1 <= b0 or c0 >= b1:
            out.append((a, b))
            continue
        if b0 < c0:
            out.append((a, of_minutes(c0)))
        if c1 < b1:
            out.append((of_minutes(c1), b))
    return out


def fmt_entry(e: Entry) -> str:
    return f"{e[0]} {e[1]} - {e[2]}"


def entry_hours(entries: list[Entry]) -> dict[str, float]:
    """Orele pe tip din intervale; un sfarsit <= inceput trece de miezul noptii."""
    hours = {TYPE_STANDBY: 0.0, TYPE_OVERTIME: 0.0}
    for kind, a, b in entries:
        t0 = datetime.strptime(norm_time(a), "%I:%M %p")
        t1 = datetime.strptime(norm_time(b), "%I:%M %p")
        if t1 <= t0:
            t1 += timedelta(days=1)
        hours[kind] = hours.get(kind, 0.0) + (t1 - t0).total_seconds() / 3600
    return hours


def day_state(entries: list[Entry], absences: list[str]) -> dict:
    """Ce are ziua in SF, in aceleasi unitati ca Time@IBM: ore si un concediu."""
    h = entry_hours(entries)
    return {
        "standby": h[TYPE_STANDBY],
        "overtime": h[TYPE_OVERTIME],
        "vacation": any(ABSENCE_VACATION.lower() in a.lower() for a in absences),
    }


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
        page.wait_for_timeout(1_000)
        waited += 1
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


def signin_pending(page) -> bool:
    """
    SAP BTP deschide, cand ii expira sesiunea (separata de w3id), un dialog
    'Sign In' cu parola, peste foaia de pontaj. Poate aparea oricand, si in
    mijlocul unei zile. Il recunoastem dupa campul de parola vizibil.
    """
    for f in page.frames:
        try:
            box = f.locator("input[type='password']")
            if box.count() and box.first.is_visible():
                return True
        except Exception:
            continue
    return False


class Relogin(Exception):
    """SAP a cerut login si omul l-a facut; iframe-ul s-a reincarcat, deci
    orice referinta la el e moarta - ziua se reia de la capat."""


def current_frame(page):
    for f in page.frames:
        if SF_FRAME_URL in f.url:
            return f
    raise RuntimeError("Nu mai gasesc foaia de pontaj SF in pagina.")


def wait_signin(page, minutes: int = 5) -> None:
    """Daca SAP cere login, il face omul in fereastra; asteptam, apoi
    ridicam Relogin, pentru ca pagina de sub dialog s-a reincarcat."""
    if not signin_pending(page):
        return
    log("=" * 64)
    log("SAP cere login din nou (sesiunea BTP a expirat). Logheaza-te in")
    log("fereastra - poti bifa 'Keep me signed in' ca sa nu se repete azi.")
    log(f"Astept maxim {minutes} minute.")
    log("=" * 64)
    for _ in range(minutes * 60):
        page.wait_for_timeout(1_000)
        if not signin_pending(page):
            for _ in range(30):
                page.wait_for_timeout(1_000)
                try:
                    if "Time Sheet for" in frame_text(current_frame(page), 2_000):
                        break
                except Exception:
                    pass
            log("Login reusit; reiau ziua de la capat.")
            raise Relogin()
    raise RuntimeError("SAP a cerut login si nu s-a facut in timp util.")


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
        wait_signin(page)
        start, end = header_range(fr)
        if start <= day <= end:
            return
        btn = "navigateToPreviousSummaryBtn" if day < start else "navigateToNextSummaryBtn"
        before = (start, end)
        fr.locator(f"[id='{SUMMARY}{btn}']").click()
        for _ in range(60):
            page.wait_for_timeout(250)
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
    wait_signin(page)
    row.wait_for(state="visible", timeout=15_000)
    row.click()
    wanted = f"{day:%B} {day.day}, {day.year}"
    for _ in range(60):
        page.wait_for_timeout(250)
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
    panel = fr.locator(DAY_PANEL)

    combo = panel.locator("input[role='combobox']").first
    combo.wait_for(state="visible", timeout=10_000)
    # Campurile de ora se cauta in panoul acestei inregistrari, nu in toata
    # ziua: o inregistrare adaugata adineauri ramane deschisa si ar fi
    # gasita prima.
    entry_panel = combo.locator("xpath=ancestor::div[contains(@class,'sapMPanel')][1]")
    got = ""
    for delay in (40, 100):
        combo.click()
        combo.fill("")
        combo.type(kind, delay=delay)
        page.wait_for_timeout(200)
        combo.press("Enter")
        page.wait_for_timeout(150)
        got = combo.input_value().strip()
        if got == kind:
            break
    else:
        raise RuntimeError(f"Time Type: am cerut {kind!r}, a ramas {got!r}.")

    pickers = entry_panel.locator("input[placeholder^='e.g.']")
    for i, value in enumerate((start, end)):
        box = pickers.nth(i)
        # Camp cu masca: fill() e ignorat, tastele sunt intelese - dar
        # tastate prea repede se pierd ('05:30 PM' a iesit o data '3:00 AM').
        # Deci rar, verificat, si din nou mai rar daca nu a iesit.
        have = ""
        for delay in (60, 120, 200):
            box.click()
            box.press("Meta+a")
            box.press("Control+a")
            box.press("Backspace")
            page.wait_for_timeout(100)
            box.type(value, delay=delay)
            box.press("Tab")
            page.wait_for_timeout(250)
            have = box.input_value().replace("\u202f", " ").strip()
            try:
                if norm_time(have) == norm_time(value):
                    break
            except ValueError:
                pass
        else:
            raise RuntimeError(
                f"{'Start' if i == 0 else 'End'} Time: am scris {value!r}, "
                f"campul arata {have!r}."
            )
    page.wait_for_timeout(100)


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


def save_day(page, fr, added: bool) -> None:
    save = fr.locator(f"[id='{DAY}btnSaveTimeRecords']")
    # Dupa ce s-a adaugat ceva, Save se activeaza cu o mica intarziere; a-l
    # citi imediat il arata inca dezactivat. Asa s-au pierdut o data trei
    # zile de stand by: "nimic de salvat", browser inchis, inregistrari
    # duse. Cand s-a adaugat, asteptam sa se activeze; doar cand s-a
    # sters (se aplica pe loc) e normal sa ramana dezactivat.
    enabled = False
    for _ in range(40):
        if save.is_enabled():
            enabled = True
            break
        errors = validation_errors(fr)
        if errors:
            raise RuntimeError("SF a refuzat salvarea: " + " / ".join(errors))
        if not added:
            break
        page.wait_for_timeout(250)
    if not enabled:
        if added:
            have = ", ".join(map(fmt_entry, read_entries(fr))) or "nimic"
            raise RuntimeError(
                "Am adaugat inregistrari, dar butonul Save nu s-a activat; "
                f"nu salvez ceva ce nu pot verifica. Ziua arata: [{have}]. "
                "De obicei doua inregistrari se suprapun. Verifica pe pagina."
            )
        log("  nimic de salvat (stergerea s-a aplicat pe loc)")
        return
    save.click()
    page.wait_for_timeout(800)
    wait_signin(page)
    # O foaie deja aprobata cere confirmare: 'You need to submit the time
    # sheet again.' Omul o retrimite, ca la Submit-ul din Time@IBM.
    text = confirm_dialog(page, fr)
    if text:
        log(f"  SF: {text}")
        if "submit" in text.lower():
            log("  Foaia SF a fost aprobata inainte: trebuie retrimisa (Submit).")
    # Save e dezactivat cat timp nu exista modificari nesalvate - dar si
    # cand formularul are erori de validare. Asa ca butonul singur nu
    # spune ca s-a salvat: un camp marcat cu eroare inseamna refuz, si
    # mesajul lui e cel care ajunge in jurnal.
    for _ in range(100):
        page.wait_for_timeout(300)
        wait_signin(page)
        errors = validation_errors(fr)
        if errors:
            raise RuntimeError("SF a refuzat salvarea: " + " / ".join(errors))
        try:
            if save.is_disabled():
                page.wait_for_timeout(800)
                errors = validation_errors(fr)
                if errors:
                    raise RuntimeError("SF a refuzat salvarea: " + " / ".join(errors))
                return
        except RuntimeError:
            raise
        except Exception:
            pass
        text = confirm_dialog(page, fr)
        if text:
            log(f"  SF: {text}")
    raise RuntimeError("Save in SF nu s-a incheiat; verifica pe pagina.")


def validation_errors(fr) -> list[str]:
    """Mesajele campurilor marcate cu eroare in panoul zilei, fara dubluri."""
    panel = fr.locator(DAY_PANEL)
    if panel.locator(".sapMInputBaseContentWrapperError, [aria-invalid='true']").count() == 0:
        return []
    texts = fr.evaluate("""() => [...document.querySelectorAll(
        '[class*=MsgPopover] [class*=MessageItem], [class*=MessagePopover] li, [class*=MsgPopover] li, .sapMMessageItem')]
        .filter(b=>{const r=b.getBoundingClientRect();return r.width>0&&r.height>0})
        .map(b=>b.innerText.trim().replace(/\\s+/g,' '))""")
    seen: list[str] = []
    for t in texts:
        t = re.sub(r"\s*(Start Time|End Time|Time Type)$", "", t).strip()
        if t and t not in seen:
            seen.append(t)
    return seen or ["campuri marcate cu eroare (deschide Messages in SF)"]


def day_row_hours(fr, day: date) -> float | None:
    """
    'Recorded Overtime' de pe randul zilei din lista din stanga - include si
    stand by-ul - se actualizeaza doar dupa Save, spre deosebire de panoul
    zilei, care arata si ce nu e salvat. E verificarea de dupa Save.
    """
    row = fr.locator("tr[role='row']").filter(
        has_text=re.compile(rf"{day:%A}[\s\S]*{day:%b}\s+{day.day}")
    ).first
    try:
        text = row.inner_text().replace("\u202f", " ").replace("\u00a0", " ")
    except Exception:
        return None
    # '8 hr Emphasized 00 min': SAP strecoara text de accesibilitate intre
    # ore si minute, deci intre ele poate fi orice in afara de cifre.
    found = re.findall(r"(\d+)\s*hr\D{0,30}?(\d+)\s*min", text)
    if len(found) < 2:
        return None
    h, m = found[1]          # prima e Planned Time, a doua Recorded Overtime
    return int(h) + int(m) / 60


def sync_day(page, fr, day: date, wanted: list[Entry], dry_run: bool
             ) -> tuple[bool, dict]:
    """
    Aduce ziua la `wanted`. Returneaza (a schimbat ceva, starea zilei in SF
    la final - sau cea curenta, in dry run). Un re-login in mijlocul zilei
    reincarca iframe-ul; atunci ziua se reia cu un frame nou - citirea
    starii de la inceput face reluarea sigura.
    """
    for attempt in range(3):
        try:
            return _sync_day(page, fr, day, wanted, dry_run)
        except Relogin:
            fr = current_frame(page)
    raise RuntimeError(f"SAP a cerut login de prea multe ori pe {day:%a %d %b}.")


def _sync_day(page, fr, day: date, wanted: list[Entry], dry_run: bool
              ) -> tuple[bool, dict]:
    goto_week(page, fr, day)
    open_day(page, fr, day)
    wait_signin(page)
    have = read_entries(fr)
    absences = read_absences(fr)
    if sorted(have) == sorted(wanted):
        return False, day_state(have, absences)

    log(f"{day:%a %d %b}: SF are [{', '.join(map(fmt_entry, have)) or 'nimic'}]"
        f" -> vreau [{', '.join(map(fmt_entry, wanted)) or 'nimic'}]")
    if dry_run:
        return True, day_state(have, absences)

    if have:
        n = delete_entries(page, fr)
        log(f"  sterse {n} inregistrari")
    for e in wanted:
        add_entry(page, fr, e)
        log(f"  adaugat {fmt_entry(e)}")
    save_day(page, fr, added=bool(wanted))

    after = read_entries(fr)
    if sorted(after) != sorted(wanted):
        raise RuntimeError(
            f"Dupa Save, {day:%a %d %b} arata "
            f"[{', '.join(map(fmt_entry, after))}] in loc de "
            f"[{', '.join(map(fmt_entry, wanted))}]."
        )
    # Panoul arata si ce nu e salvat; randul zilei din lista, nu.
    expected = sum(entry_hours(wanted).values())
    for _ in range(20):
        wait_signin(page)
        got = day_row_hours(fr, day)
        if got is not None and abs(got - expected) < 0.01:
            break
        page.wait_for_timeout(500)
    else:
        raise RuntimeError(
            f"Dupa Save, randul zilei {day:%a %d %b} arata "
            f"{got if got is not None else '?'} ore in loc de {expected:g}. "
            "Salvarea nu s-a facut; verifica pe pagina."
        )
    log(f"  salvat: {day:%a %d %b} OK ({expected:g} ore pe randul zilei)")
    return True, day_state(after, absences)


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


def sync_vacation(page, fr, days: list[date], dry_run: bool,
                  states: dict[date, dict] | None = None) -> int:
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
            if states is not None:
                for k in range(i, j):
                    states.setdefault(days[k], {})["vacation"] = True
        changed += 1
        i = j
    return changed


def read_days(page, days: list[date]) -> dict[date, dict]:
    """Starea fiecarei zile in SF, doar citita - pentru verificari."""
    open_timesheet(page)
    states: dict[date, dict] = {}
    for day in sorted(days):
        for attempt in range(3):
            try:
                fr = current_frame(page)
                goto_week(page, fr, day)
                open_day(page, fr, day)
                wait_signin(page)
                states[day] = day_state(read_entries(fr), read_absences(fr))
                break
            except Relogin:
                continue
        else:
            raise RuntimeError(f"SAP a cerut login de prea multe ori pe {day:%a %d %b}.")
    return states


# --------------------------------------------------------------------------
# Ziua de birou: 'Allowances -> Record', doar in SF
# --------------------------------------------------------------------------

def read_allowances(fr) -> list[str]:
    """Alocatiile zilei deschise, dupa nume ('Work @IBM Office')."""
    text = frame_text(fr).replace("\u202f", " ").replace("\u00a0", " ")
    start = text.find("Allowances (")
    end = text.find("Absences (", start)
    if start < 0 or end < 0:
        raise RuntimeError("Nu gasesc sectiunea 'Allowances' in panoul zilei.")
    section = text[start:end]
    if "No allowances recorded" in section:
        return []
    return [p.strip() for p in section.split(" | ")[2:]
            if p.strip() and p.strip() not in ("Allowance Type", "Allowance Value")
            and not p.strip().replace(".", "").isdigit()]


def record_office(page, fr, day: date) -> None:
    """'Record' la Allowances: formularul vine gata cu 'Work @IBM Office'
    si 1.00; verificam, nu presupunem, apoi Save."""
    panel = fr.locator(DAY_PANEL)
    fr.locator(f"[id='{DAY}recordsAllowance--add']").click()
    combo = panel.locator("input[role='combobox']").first
    combo.wait_for(state="visible", timeout=10_000)
    page.wait_for_timeout(300)
    if combo.input_value().strip() != OFFICE_ALLOWANCE:
        combo.click()
        combo.fill("")
        combo.type(OFFICE_ALLOWANCE, delay=40)
        page.wait_for_timeout(300)
        combo.press("Enter")
        page.wait_for_timeout(200)
        if combo.input_value().strip() != OFFICE_ALLOWANCE:
            raise RuntimeError(
                f"Allowance Type: nu am putut alege {OFFICE_ALLOWANCE!r} "
                f"(a ramas {combo.input_value()!r})."
            )
    value = panel.locator("input[placeholder='Enter a number']").first
    if value.count():
        try:
            if abs(float(value.input_value().replace(",", ".") or "0") - 1) > 0.001:
                value.click()
                value.press("Meta+a")
                value.press("Control+a")
                value.type("1", delay=40)
                value.press("Tab")
                page.wait_for_timeout(200)
        except ValueError:
            pass
    save_day(page, fr, added=True)


def sync_office(page, days: list[date], dry_run: bool) -> int:
    """
    Pune alocatia de birou pe fiecare zi ceruta, daca nu e deja. Nu se
    sterge niciodata de aici: o zi de birou trecuta gresit se scoate de
    mana, e un click pe (x) in SF.
    """
    open_timesheet(page)
    changed = 0
    for day in sorted(days):
        for attempt in range(3):
            try:
                fr = current_frame(page)
                goto_week(page, fr, day)
                open_day(page, fr, day)
                wait_signin(page)
                have = read_allowances(fr)
                if any(OFFICE_ALLOWANCE.lower() in a.lower() for a in have):
                    log(f"{day:%a %d %b}: are deja ziua de birou in SF.")
                    break
                log(f"{day:%a %d %b}: SF are [{', '.join(have) or 'nimic'}] -> vreau "
                    f"{OFFICE_ALLOWANCE}")
                if dry_run:
                    changed += 1
                    break
                record_office(page, fr, day)
                after = read_allowances(fr)
                if not any(OFFICE_ALLOWANCE.lower() in a.lower() for a in after):
                    raise RuntimeError(
                        f"Dupa Save, {day:%a %d %b} tot nu are {OFFICE_ALLOWANCE} "
                        f"([{', '.join(after) or 'nimic'}])."
                    )
                log(f"  salvat: {day:%a %d %b} zi de birou OK")
                changed += 1
                break
            except Relogin:
                continue
        else:
            raise RuntimeError(f"SAP a cerut login de prea multe ori pe {day:%a %d %b}.")
    if dry_run:
        log(f"DRY RUN: {changed} zile de birou ar fi puse in SF.")
    else:
        log(f"{changed} zile de birou puse in SF. Submit-ul foii ramane pe seama ta.")
    return changed


def sync(page, days: list[date], plan_entries: dict[date, list[Entry]],
         dry_run: bool, vacation_days: list[date] | None = None
         ) -> dict[date, dict]:
    """
    Trece prin zilele date, in ordine, si aduce fiecare la inregistrarile
    cerute. Submit-ul foii SF ramane, ca la Time@IBM, pe seama omului.
    Returneaza starea fiecarei zile in SF, pentru verificarea cu Time@IBM.
    """
    open_timesheet(page)
    changed = 0
    states: dict[date, dict] = {}
    for d in sorted(days):
        did, states[d] = sync_day(page, current_frame(page), d,
                                  plan_entries.get(d, []), dry_run)
        changed += int(did)
    if vacation_days:
        for attempt in range(3):
            try:
                changed += sync_vacation(page, current_frame(page), vacation_days,
                                         dry_run, states)
                break
            except Relogin:
                continue
    if dry_run:
        log(f"DRY RUN: {changed} zile ar fi schimbate in SF.")
    else:
        log(f"{changed} zile schimbate in SF. Submit-ul foii ramane pe seama ta.")
    return states
