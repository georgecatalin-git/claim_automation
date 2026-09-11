#!/usr/bin/env python3
"""
Interfata locala pentru pontaj_ibm.py

Porneste un server pe 127.0.0.1 (doar local, nu e expus in retea) si deschide
pagina in browserul implicit.

    python gui.py

Nu are dependinte in afara de Python standard library. Playwright e nevoie
doar cand apesi efectiv "Ponteaza".
"""

from __future__ import annotations

import json
import mimetypes
import queue
import socket
import sys
import threading
import webbrowser
from argparse import Namespace
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pontaj_ibm as P

HERE = Path(__file__).resolve().parent
UI_DIR = HERE / "ui"
HOST = "127.0.0.1"


# --------------------------------------------------------------------------
# Job runner - o singura rulare simultan
# --------------------------------------------------------------------------

class Job:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.exit_code: int | None = None

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def append(self, text: str) -> None:
        with self.lock:
            for line in text.splitlines():
                if line.strip():
                    self.lines.append(line)

    def snapshot(self, since: int) -> dict:
        with self.lock:
            return {
                "lines": self.lines[since:],
                "total": len(self.lines),
                "running": self.running,
                "exitCode": self.exit_code,
            }

    def start(self, args: Namespace) -> bool:
        if self.running:
            return False
        with self.lock:
            self.lines = []
            self.exit_code = None
        self.thread = threading.Thread(target=self._work, args=(args,), daemon=True)
        self.thread.start()
        return True

    def _work(self, args: Namespace) -> None:
        sink = _Sink(self.append)
        original = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = sink
        try:
            code = P.run(args)
        except Exception as exc:  # pragma: no cover
            self.append(f"[pontaj] EROARE NEASTEPTATA: {exc}")
            code = 1
        finally:
            sys.stdout, sys.stderr = original
        self.exit_code = code
        self.append(
            "[pontaj] Gata." if code == 0 else f"[pontaj] Terminat cu cod {code}."
        )


class _Sink:
    """Redirecteaza print-urile scriptului catre log-ul din interfata."""

    def __init__(self, emit) -> None:
        self.emit = emit
        self.buffer = ""

    def write(self, text: str) -> int:
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self.emit(line)
        return len(text)

    def flush(self) -> None:
        if self.buffer:
            self.emit(self.buffer)
            self.buffer = ""

    def isatty(self) -> bool:
        return False


JOB = Job()


# --------------------------------------------------------------------------
# Calcule pentru previzualizare
# --------------------------------------------------------------------------

def week_label(d: date) -> str:
    """Formatul folosit de aplicatie: 'September 18, 2026'."""
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def build_preview(payload: dict) -> dict:
    week_ending = date.fromisoformat(payload["weekEnding"])
    if week_ending.weekday() != 4:
        return {"error": "Saptamana trebuie sa se incheie vineri."}

    days = P.week_days(week_ending)

    oncall = None
    raw_oncall = (payload.get("oncall") or "").strip()
    if payload.get("mode") == "oncall":
        if not raw_oncall:
            return {"error": "Completeaza perioada de oncall."}
        try:
            oncall = P.parse_oncall(raw_oncall, week_ending)
        except ValueError as exc:
            return {"error": str(exc)}

    overtime: dict[date, str] = {}
    raw_overtime = (payload.get("overtime") or "").strip()
    if raw_overtime:
        try:
            overtime = P.parse_overtime(raw_overtime, days)
        except ValueError as exc:
            return {"error": str(exc)}

    try:
        absences = P.merge_absences(
            P.parse_days((payload.get("vacation") or "").strip(), days),
            P.parse_days((payload.get("holiday") or "").strip(), days),
            P.parse_days((payload.get("comp") or "").strip(), days),
        )
    except ValueError as exc:
        return {"error": str(exc)}

    plan = P.build_plan(days, oncall, overtime, absences)
    rows = []
    totals = {"regular": 0.0, "standby": 0.0, "overtime": 0.0, "absent": 0.0}
    for d in days:
        cell = plan[d]
        values = {
            "regular": cell[P.REGULAR_LABEL],
            "standby": cell[P.STANDBY_LABEL],
            "overtime": cell[P.OVERTIME_LABEL],
        }
        for key, value in values.items():
            totals[key] += float(value or 0)
        absent = ""
        absent_kind = ""
        for label in P.ABSENCE_LABELS:
            if cell.get(label):
                absent = cell[label]
                absent_kind = P.ABSENCE_SHORT[label]
                totals["absent"] += float(absent)
        rows.append(
            {
                "date": d.isoformat(),
                "dow": d.strftime("%a"),
                "day": d.day,
                "month": d.strftime("%b"),
                "weekend": d.weekday() >= 5,
                "absent": absent,
                "absentKind": absent_kind,
                **values,
            }
        )

    return {
        "weekLabel": week_label(week_ending),
        "rows": rows,
        "totals": {k: f"{v:g}" for k, v in totals.items()},
        "oncall": (
            f"{oncall[0].isoformat()} .. {oncall[1].isoformat()}" if oncall else None
        ),
        "needsWeekend": any(r["weekend"] and (r["standby"] or r["overtime"])
                            for r in rows),
        "extraWeeks": [
            f.strftime("%-d %b %Y") for f in P.weeks_touched(week_ending, oncall)
        ],
    }


def build_args(payload: dict) -> Namespace:
    return Namespace(
        week=week_label(date.fromisoformat(payload["weekEnding"])),
        simple=payload.get("mode") != "oncall",
        oncall=(payload.get("oncall") or "").strip()
        if payload.get("mode") == "oncall"
        else None,
        overtime=(payload.get("overtime") or "").strip() or None,
        no_overtime=not (payload.get("overtime") or "").strip(),
        vacation=(payload.get("vacation") or "").strip() or None,
        holiday=(payload.get("holiday") or "").strip() or None,
        comp=(payload.get("comp") or "").strip() or None,
        yes=True,
        login=False,
        submit=bool(payload.get("submit")),
        dry_run=bool(payload.get("dryRun")),
        no_sf=not payload.get("sf", True),
        debug=bool(payload.get("debug")),
        show=True,
    )


def login_args() -> Namespace:
    return Namespace(
        week=None, simple=True, oncall=None, overtime=None, no_overtime=True,
        vacation=None, holiday=None, comp=None,
        yes=True, login=True, submit=False, dry_run=False, no_sf=True,
        debug=False, show=True,
    )


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "Pontaj/1.0"

    def log_message(self, fmt, *a):  # liniste in consola
        pass

    # --- helpers ---------------------------------------------------------

    def send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # --- routes ----------------------------------------------------------

    def do_GET(self) -> None:
        path = self.path.split("?")[0]

        if path in ("/", "/index.html"):
            self.send_file(UI_DIR / "index.html")
        elif path == "/logo.png":
            logo = HERE / "logo.png"
            if logo.is_file():
                self.send_file(logo)
            else:
                self.send_error(404)
        elif path == "/api/init":
            self.send_json(
                {
                    "today": date.today().isoformat(),
                    "playwright": P.PLAYWRIGHT_OK,
                    "profile": str(P.PROFILE_DIR),
                }
            )
        elif path == "/api/status":
            since = 0
            if "?" in self.path:
                for part in self.path.split("?", 1)[1].split("&"):
                    if part.startswith("since="):
                        since = int(part[6:] or 0)
            self.send_json(JOB.snapshot(since))
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        try:
            payload = self.read_json()
        except Exception as exc:
            self.send_json({"error": f"Cerere invalida: {exc}"}, 400)
            return

        if path == "/api/preview":
            try:
                self.send_json(build_preview(payload))
            except Exception as exc:
                self.send_json({"error": str(exc)}, 200)

        elif path == "/api/run":
            if not P.PLAYWRIGHT_OK:
                self.send_json({"error": P.PLAYWRIGHT_HINT}, 200)
                return
            preview = build_preview(payload)
            if preview.get("error"):
                self.send_json({"error": preview["error"]}, 200)
                return
            started = JOB.start(build_args(payload))
            self.send_json(
                {"started": started}
                if started
                else {"error": "O rulare e deja in curs."}
            )

        elif path == "/api/login":
            if not P.PLAYWRIGHT_OK:
                self.send_json({"error": P.PLAYWRIGHT_HINT}, 200)
                return
            started = JOB.start(login_args())
            self.send_json(
                {"started": started}
                if started
                else {"error": "O rulare e deja in curs."}
            )

        else:
            self.send_error(404)


def free_port(preferred: int = 8765) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket() as s:
            try:
                s.bind((HOST, port))
                return port
            except OSError:
                continue
    raise RuntimeError("Nu am gasit un port liber.")


def main() -> int:
    if not (UI_DIR / "index.html").is_file():
        print(f"Lipseste {UI_DIR / 'index.html'}")
        return 1

    port = free_port()
    url = f"http://{HOST}:{port}/"
    server = ThreadingHTTPServer((HOST, port), Handler)

    print(f"Interfata pontaj: {url}")
    print("Inchide cu Ctrl+C.")
    if not P.PLAYWRIGHT_OK:
        print("\nAtentie: Playwright nu e instalat, pontarea efectiva nu va merge.")
        print(P.PLAYWRIGHT_HINT)

    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nInchis.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
