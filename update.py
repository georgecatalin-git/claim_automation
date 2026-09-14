#!/usr/bin/env python3
"""
Actualizare automata, rulata de lansatoare inainte de a porni interfata.

Colegii au descarcat un ZIP; fara asta, fiecare modificare ar insemna
"descarca din nou". Aici: intrebam GitHub care e ultimul commit de pe main,
il comparam cu cel notat local in `.version`, si daca difera descarcam
ZIP-ul si inlocuim fisierele aplicatiei. Ce e al omului nu e in folder
(configurarea si sesiunea stau in home), deci nu are ce se pierde.

Fara internet, cu GitHub indisponibil sau cu orice eroare: pornim cu ce
avem si spunem de ce. O copie de dezvoltare (are `.git`) nu se atinge -
acolo se lucreaza cu git, nu cu ZIP-uri.

Lansatorul care ruleaza nu poate fi suprascris in timp ce ruleaza (bash si
cmd citesc scriptul pe masura ce il executa), asa ca versiunea lui noua
se lasa langa el, cu `.new`, si o pune el la loc cand se inchide.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = "georgecatalin-git/claim_automation"
BRANCH = "main"
API = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"
ZIP = f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"
HERE = Path(__file__).resolve().parent
VERSION_FILE = HERE / ".version"
LAUNCHERS = ("Pontaj.command", "Pontaj.bat")
TIMEOUT = 8


def say(msg: str) -> None:
    print(f"[update] {msg}", flush=True)


def fetch(url: str, timeout: int) -> bytes:
    """
    urllib, si daca nu poate, curl. Python-ul de pe python.org nu are, pe
    Mac, certificatele SSL de sistem pana nu rulezi "Install Certificates";
    curl le are, si exista pe Mac si pe Windows 10+.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "pontaj-update"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as exc:
        first = exc
    try:
        return subprocess.run(
            ["curl", "-fsSL", "--max-time", str(timeout), "-A", "pontaj-update", url],
            capture_output=True, check=True,
        ).stdout
    except Exception:
        raise first


def remote_sha() -> str | None:
    return json.loads(fetch(API, TIMEOUT)).get("sha")


def local_sha() -> str:
    try:
        return VERSION_FILE.read_text().strip()
    except FileNotFoundError:
        return ""


def download_zip() -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(fetch(ZIP, 120)))


def apply(zf: zipfile.ZipFile) -> int:
    """Copiaza fisierele din arhiva peste cele de aici. Returneaza cate."""
    count = 0
    for info in zf.infolist():
        parts = Path(info.filename).parts
        if len(parts) < 2 or info.is_dir():
            continue                      # primul segment e folderul radacina
        rel = Path(*parts[1:])
        if rel.parts[0] in (".git", ".github"):
            continue
        target = HERE / rel
        if rel.name in LAUNCHERS:
            target = target.with_name(rel.name + ".new")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
        if rel.name in LAUNCHERS or rel.suffix in (".command", ".sh"):
            try:
                target.chmod(0o755)
            except OSError:
                pass
        count += 1
    return count


def main() -> int:
    if (HERE / ".git").exists():
        say("copie de dezvoltare (.git); nu actualizez.")
        return 0
    try:
        remote = remote_sha()
    except Exception as exc:
        say(f"nu pot verifica actualizarile ({type(exc).__name__}); pornesc cu ce am.")
        return 0
    if not remote:
        say("GitHub nu a raspuns cu un commit; pornesc cu ce am.")
        return 0
    local = local_sha()
    if local == remote:
        say(f"la zi ({remote[:7]}).")
        return 0
    say("versiune noua pe GitHub" + (f" ({local[:7]} -> {remote[:7]})" if local else "")
        + "; descarc...")
    try:
        n = apply(download_zip())
    except Exception as exc:
        say(f"actualizarea a esuat ({type(exc).__name__}: {exc}); pornesc cu ce am.")
        return 0
    VERSION_FILE.write_text(remote + "\n")
    say(f"actualizat: {n} fisiere. Lansatorul isi ia versiunea noua la urmatoarea pornire.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
