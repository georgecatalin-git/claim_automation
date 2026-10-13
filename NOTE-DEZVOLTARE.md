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
- **Save la fiecare rulare, Submit numai cu bifa.** Butoanele sunt mereu
  active pe site, deci apasarea nu spune nimic; "Salvat" inseamna ca a aparut
  bannerul "iERP labor for week ending ... was successfully saved" /
  "... was not changed". Submit inchide saptamana, deci e optiune, nu
  implicit - si e `submit_all`, la finalul rularii, nu langa fiecare Save.
  **Trei lucruri tin pasul asta la final:** zilele de birou se scriu in
  aceleasi foi SF *dupa* saptamani (o foaie trimisa si apoi scrisa e o foaie
  care trebuie retrimisa de mana); saptamanile atinse de oncall se ponteaza
  dupa prima; si verificarea `reconcile` e singurul lucru care stie daca
  cele doua sisteme coincid. **Cu diferente nu se trimite nimic** - o foaie
  trimisa cu diferente e exact luna platita incomplet pe care verificarea
  exista sa o prinda; `WeekRun.problems` le duce pana acolo.
- **O saptamana de pontaj inseamna doua foi SF.** IBM tine sambata-vineri,
  SAP luni-duminica, deci sambata si duminica sunt in foaia dinainte.
  `sf_weeks` grupeaza zilele scrise pe luni si se trimite fiecare foaie
  atinsa - "trimite saptamana" ar fi lasat weekendul netrimis.
- **"Not Submitted" contine "Submitted".** Statusul de dinainte de trimitere
  ar fi trecut drept confirmare, deci `submitted_marker` il scoate din text
  inainte sa caute. Confirmarea dupa click e ce spune foaia ("Pending
  Approval"), sau butonul care nu mai e activ; daca niciuna, jurnalul spune
  `ATENTIE`, nu "trimis". `confirm_dialog` a primit lista de butoane ca
  parametru anume ca "Submit" sa **nu** fie in lista implicita: un dialog
  aparut in timpul unui Save nu are voie sa trimita foaia.
- **Butoanele, citite de pe paginile reale (24 sep 2026), fara sa fie
  apasate.** Time@IBM: `btn-timesheet-submit`, **activ si in mijlocul
  saptamanii** - deci nu exista nicio plasa de siguranta acolo, bifa e
  singura. (README-ul sustinea contrariul, "dezactivat pana se incheie
  saptamana"; era fals.) SF: `...timeSheetSummaryView--submitTimeSheetBtn`,
  primul din `SUBMIT_BTN_IDS`, gasit de `submit_button`, iar
  `is_disabled()` citeste corect `sapMBtnDisabled` - foaia saptamanii era
  deja `Approved`, deci butonul inactiv, exact cazul in care nu trimitem.
- **Ce a ramas neverificat, si nu se poate altfel:** click-ul insusi si
  dialogul de dupa. `confirm_dialog` cauta `.sapMMessageBox` /
  `[role='alertdialog']`; daca confirmarea de Submit e un dialog obisnuit
  (cu un camp de comentariu), nu il va inchide, iar `submit_sheet` va
  incheia cu `ATENTIE: ... foaia nu confirma ca a plecat` in loc sa trimita.
  Fail-safe, dar de reparat cu ce se vede la prima trimitere adevarata.
  Pasul nu ridica exceptie niciodata - orele sunt deja salvate, si o foaie
  netrimisa se trimite de mana.
- **`submitted_marker` nu cauta "approved" anume.** Statusul unei cereri de
  concediu din aceeasi foaie e tot "Pending" / "Approved", deci cuvantul
  singur ar da fals pozitiv pe o foaie netrimisa. Confirmarea pe care ne
  bazam e "pending approval" sau butonul care nu mai e activ.
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
  colegi: instaleaza ce lipseste, ruleaza `update.py` si pornesc `gui.py`.
  **Orice push pe `main` ajunge la colegi la urmatoarea lor pornire** -
  `update.py` compara commit-ul de pe GitHub cu `.version` si inlocuieste
  fisierele din ZIP. Deci `main` trebuie sa fie mereu in stare de folosit;
  lucrul neterminat sta pe alt branch. Lansatoarele se inlocuiesc prin
  `.new` (un script nu se poate rescrie cat ruleaza). Python-ul de pe
  python.org nu are certificate SSL pe Mac: `fetch` cade pe `curl`.
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
- **Ce nu e cerut nu se sterge.** `preserved_labels(plan, columns, clear)`
  da randurile despre care formularul nu spune nimic in saptamana asta;
  `fill_row(..., preserve=True)` nu goleste o celula care are deja ore,
  `fill_project_row` nu scoate randul, iar in SF `merge_preserved` adauga
  inapoi inregistrarile de tipul pastrat. Bifa "Sterge ce nu mai e cerut"
  (`args.clear`) readuce comportamentul vechi. Motivul: o rulare facuta
  pentru altceva stergea oncall-ul pontat in avans.
- **Memoria saptamanilor** (`~/.ibm-pontaj-weeks.json`, `save_week` /
  `week_memory`): gui.py o scrie dupa o rulare reusita care a si scris
  (nu dry run), iar pagina o cere la `/api/week` cand se schimba data.
  Nota din hint e lipicioasa (`recallNote`) - altfel evenimentul `change`
  de dupa `input` o stergea.
- **Verificarea trimestriala** (`audit_quarter`) = ultimele 12 saptamani
  pana la ziua aleasa (`audit_weeks`, oprite la 1 ianuarie: Time@IBM nu
  tine alt an in selector). Citeste intai toate saptamanile din Time@IBM
  (`read_ibm_week_all`, insumat peste toate claim item-urile, fara
  configurare), apoi toate zilele din SF (`sf_ibm.read_days`), apoi
  `reconcile` pe fiecare saptamana. Nu scrie. Sarbatorile vin din randul
  XL0B00 al grilei. Selectorul de saptamana din Time@IBM e o lista
  virtualizata: saptamanile vechi se gasesc prin campul Search (al doilea
  input din overlay; primul e ascuns). Dialogul SAP Sign In poate incepe cu
  pasul de email, fara parola - `signin_pending` il recunoaste si pe acela.
- **Ziua de birou** e `sf_ibm.sync_office` / `pontaj_ibm.office_run`:
  doar SF, alocatia `Work @IBM Office` cu valoarea 1, formularul vine gata
  completat si se verifica, nu se presupune. Zilele se cauta in trei
  saptamani (cea de referinta, dinainte, de dupa) - fara numere de zi
  duplicate. Nu sterge niciodata alocatii.
- **Numaratoarea zilelor de birou** (`office_audit` -> `read_office_days`)
  deschide **fiecare zi** a anului. Masurat pe pagina reala inainte de a fi
  scrisa, pentru ca varianta rapida parea sa existe: cautarea lui
  `Work @IBM Office` in textul saptamanii raspundea `True` pe saptamanile
  potrivite - dar gasea **panoul zilei ramase deschise**, care face parte din
  acelasi frame, nu lista. Lista saptamanii are Planned Time, Recorded
  Overtime si un numar de inregistrari, din care o zi de birou nu se
  deosebeste de un stand by. O zi se deschide in ~0.3 s, deci un an costa
  vreo trei minute - cat verificarea trimestriala.
  **Drumul e inapoi**, de la ziua ceruta spre 1 ianuarie: foaia e deschisa
  pe saptamana curenta, deci prima zi e deja pe ecran si fiecare saptamana
  costa un click. Invers, primul lucru pe care il facea scanarea erau ~38
  de saptamani de navigat inapoi, tacut. `found` si `unread` se intorc
  sortate crescator: drumul e unul, raportul e altul.
  **Weekendurile se citesc si ele:** in datele reale exista o zi de birou
  pontata duminica, iar o scanare care le sare raporteaza mai putin fara sa
  spuna. **Si `Relogin` trebuie prins pe fiecare zi:** proba a nimerit o
  cerere de login SAP la mijloc si ziua aceea a disparut tacut din
  numaratoare. Ce tot nu se poate citi se numara separat si totalul se
  anunta ca minim, nu ca numar exact.
- `gui.py` ruleaza scriptul in acelasi proces: dupa o modificare in
  `pontaj_ibm.py` serverul trebuie repornit. Daca portul 8765 e ocupat,
  trece pe urmatorul liber si spune in consola pe care.
- Nu exista teste pe pagina reala; `python test_logica.py` acopera doar
  parsarea perioadelor si a orelor. O rulare cu "Doar verifica" bifat
  parcurge tot fluxul fara sa salveze si e verificarea de folosit.
