# Pontaj automat IBM

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
- `gui.py` ruleaza scriptul in acelasi proces: dupa o modificare in
  `pontaj_ibm.py` serverul trebuie repornit. Daca portul 8765 e ocupat,
  trece pe urmatorul liber si spune in consola pe care.
- Nu exista teste pe pagina reala; `python test_logica.py` acopera doar
  parsarea perioadelor si a orelor. O rulare cu "Doar verifica" bifat
  parcurge tot fluxul fara sa salveze si e verificarea de folosit.
