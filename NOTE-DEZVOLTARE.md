# Pontaj automat IBM - note de dezvoltare

Script Playwright + interfata locala care completeaza saptamana pe
`https://time.ibm.com/week`. Proiect de sine statator: nu are nicio legatura
cu Split sau cu find-clients, nu imparte cod, date sau conturi cu ele.

Ce face si cum se ruleaza: `README.md`. Pornire rapida: `PORNESTE.txt`.

## Ce nu se vede din cod

- **Browserul e Google Chrome-ul instalat** (`channel="chrome"`), cu
  profilul scriptului. Chromium-ul lui Playwright nu vede passkey-urile din
  iCloud Keychain si w3id cere parola acolo; Chrome arata Touch ID-ul.
- **Sesiunea se salveaza la inchidere** (`~/.ibm-pontaj-session.json`,
  cookie-uri, 0600) si se restaureaza la pornire, pentru ca Chrome arunca
  cookie-urile de sesiune cand se inchide. `close_browser()` in loc de
  `ctx.close()`, altfel urmatoarea rulare cere login.
- **Browserul e mereu vizibil, login-ul e al omului.** w3id refuza sesiunea
  din headless si cere din nou parola; a fost incercat si scos. Scriptul nu
  cere, nu stocheaza si nu tasteaza nicio parola. Profilul din
  `~/.ibm-pontaj-profile` pastreaza doar cookie-ul de sesiune w3id, care tine
  cateva ore.
- **Grila e un ag-Grid.** Claim item-ul vine restrans ("Expand all" il
  deschide), celulele sunt text pana la dublu-click, Enter comite. Coloanele
  se identifica dupa `col-id` (`hours.mon` ...), nu dupa pozitie.
- **Save la fiecare rulare, Submit niciodata automat.** Butoanele sunt mereu
  active pe site, deci apasarea nu spune nimic; "Salvat" inseamna ca a aparut
  bannerul "iERP labor for week ending ... was successfully saved" /
  "... was not changed". Submit inchide saptamana si ramane pe mana omului.
- **Zilele libere stau pe M.00556**, cate un task pe fel (XL0A00 concediu,
  XL0B00 sarbatoare, XL0C00 compensatie), fiecare cu un rand "Regular" al
  lui. De aceea `find_row` exclude `row-id`-urile care incep cu `M.00556|`:
  altfel un 8 de concediu ar ateriza pe proiect. Regulile HR pentru o
  sarbatoare lucrata (stand by 8 sau 16) sunt in `build_plan` si in
  `test_logica.py`.
- **SuccessFactors e in `sf_ibm.py`**, apelat din `run()` dupa Save-ul din
  Time@IBM. E SAP Fiori intr-un iframe (`hcm41.sapsf.com/sf/timesheet`):
  id-uri stabile cu prefixul `sap.sf.attendancerecording.timesheets---`,
  campuri de ora cu masca (doar `type()`, `fill()` e ignorat), spatii
  speciale (U+2009/U+202F) in antete si ore, MessageBox cu rol
  `alertdialog`, si `has_text` din Playwright nu intelege `\b` sau
  lookahead. Saptamana SF e luni-duminica. Fiecare zi e recitita dupa Save.
  Concediul e o cerere (dialog "Create Absence", buton Submit), nu o
  inregistrare: se adauga cand lipseste, nu se sterge niciodata.
  **"Salvat" in SF inseamna doar ce spune randul zilei din lista din
  stanga** (coloana Recorded Overtime, care include stand by-ul): panoul
  zilei arata si inregistrarile nesalvate, iar butonul Save se activeaza cu
  intarziere dupa adaugare - amandoua au dat o data "salvat OK" cu SF gol.
  Textul rândului are "Emphasized" (accesibilitate) intre ore si minute.
  Dialogul SAP "Sign In" (sesiunea BTP) poate aparea oricand; dupa login
  iframe-ul se reincarca si orice Frame vechi e mort - `Relogin` reia ziua
  cu `current_frame(page)`. **Save-ul
  SF dezactiveaza butonul si cand formularul are erori** - `save_day`
  verifica campurile marcate cu eroare si ridica mesajul lor; fara asta,
  inregistrarile nesalvate din panou treceau drept salvate.
- **O rulare = saptamana aleasa + saptamanile atinse de oncall** (`run()`
  -> `process_week()` de mai multe ori, cu `oncall_only` pentru celelalte).
  Overtime-ul si zilele libere se dau relativ la saptamana aleasa, deci
  celelalte primesc doar stand by. `select_week` trebuie sa recunoasca
  saptamana deja afisata: dupa `page.goto` Time@IBM se deschide pe cea
  curenta, iar cautarea dupa text nimerea trigger-ul, nu optiunea.
- `Pontaj.command` / `Pontaj.bat` sunt lansatoarele pe dublu-click pentru
  colegi: instaleaza Playwright daca lipseste si pornesc `gui.py`.
- **Verificarea de la final** (`reconcile`) compara ce e *citit inapoi* din
  cele doua sisteme, nu planul: `read_ibm_state` din grila Time@IBM
  inainte de a pleca de pe pagina, starile din `sf_ibm.sync`. Stand by,
  overtime, concediu; sarbatoarea nu; `ATENTIE` la diferente, ca interfata
  sa le coloreze rosu.
- **O singura fereastra de pontaj o data.** Chrome tine `SingletonLock` in
  profil; a doua instanta pe acelasi profil se inchide instant si se vedea
  doar "Target page ... has been closed". `profile_in_use()` refuza rularea
  cu un mesaj clar, iar `gui.py` nu porneste un al doilea server daca
  interfata ruleaza deja (deschide pagina existenta).
- **Codurile de claim sunt configurare per persoana**
  (`~/.ibm-pontaj-config.json`, panoul din interfata). Un proiect e
  `cont|task` - exact prefixul `row-id`-ului din ag-Grid, iar randul claim
  item-ului e `cont|task|nume|bill|` (bill = `no-bc`). `resolve_projects`
  face lista (fara fisier: singurul din grila, cu 8/zi; mai multe fara
  fisier: refuz), `split_plan` imparte planul zilei pe proiecte,
  `add_claim_item` e generalizarea celui de la M.00556. Nimic din cod nu mai
  presupune "General Billable". Pe o saptamana goala "New claim item" e un
  cartonas cu text, nu un buton.
- `gui.py` ruleaza scriptul in acelasi proces: dupa o modificare in
  `pontaj_ibm.py` serverul trebuie repornit. Daca portul 8765 e ocupat,
  trece pe urmatorul liber si spune in consola pe care.
- Nu exista teste pe pagina reala; `python test_logica.py` acopera doar
  parsarea perioadelor si a orelor. O rulare cu "Doar verifica" bifat
  parcurge tot fluxul fara sa salveze si e verificarea de folosit.
