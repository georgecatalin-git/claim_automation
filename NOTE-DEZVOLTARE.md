# Pontaj automat IBM

Script Playwright + interfata locala care completeaza saptamana pe
`https://time.ibm.com/week`. Proiect de sine statator: nu are nicio legatura
cu Split sau cu find-clients, nu imparte cod, date sau conturi cu ele.

Ce face si cum se ruleaza: `README.md`. Pornire rapida: `PORNESTE.txt`.

## Ce nu se vede din cod

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
- `gui.py` ruleaza scriptul in acelasi proces: dupa o modificare in
  `pontaj_ibm.py` serverul trebuie repornit. Daca portul 8765 e ocupat,
  trece pe urmatorul liber si spune in consola pe care.
- Nu exista teste pe pagina reala; `python test_logica.py` acopera doar
  parsarea perioadelor si a orelor. O rulare cu "Doar verifica" bifat
  parcurge tot fluxul fara sa salveze si e verificarea de folosit.
