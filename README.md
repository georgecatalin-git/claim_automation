# Pontaj automat IBM (cu oncall / stand by)

Completeaza saptamana in **Time@IBM** si pune aceleasi ore de stand by,
overtime si concediu in **SuccessFactors**, apoi verifica ca cele doua
coincid. Tu doar spui ce s-a intamplat saptamana asta; login-ul si Submit-ul
raman ale tale.

## Pentru colegi: start in 3 pasi

1. **Descarca**: [ZIP-ul proiectului](https://github.com/georgecatalin-git/claim_automation/archive/refs/heads/main.zip),
   dezarhiveaza-l unde vrei.
2. **Ai nevoie de**: [Python 3](https://www.python.org/downloads/) (pe Windows
   bifeaza "Add python.exe to PATH" la instalare) si Google Chrome, pentru
   login-ul cu passkey.
3. **Porneste**: dublu-click pe `Pontaj.command` (Mac) sau `Pontaj.bat`
   (Windows). Verifica pe rand Python, Playwright si Google Chrome si
   instaleaza ce lipseste (Python si Chrome pot cere parola calculatorului),
   apoi deschide interfata in browser. A doua oara trece direct.

   **Pe Mac, prima data**, macOS va spune *"Pontaj.command" Not Opened - Apple
   could not verify...*: e Gatekeeper, care blocheaza orice script descarcat
   din internet si nesemnat de Apple. Apasa **Done** (nu "Move to Bin"), apoi
   una din variantele de mai jos, o singura data:
   - **System Settings → Privacy & Security**, deruleaza jos pana la
     *"Pontaj.command" was blocked* → **Open Anyway**, apoi dublu-click din nou;
   - sau click dreapta pe `Pontaj.command` → **Open** → **Open** (merge pe
     macOS-urile mai vechi);
   - sau, in Terminal, in folderul dezarhivat: `xattr -dr com.apple.quarantine .`
     (scoate marcajul de "descarcat din internet" de pe toate fisierele).

   Pe Windows, echivalentul e ecranul albastru *SmartScreen*: **More info →
   Run anyway**, tot o singura data.

In interfata: alegi o zi din saptamana, spui daca ai avut oncall (si
perioada), ore suplimentare, zile libere, apoi **Ponteaza saptamana**. Se
deschide Chrome; daca IBM sau SuccessFactors cer login, il faci tu acolo
(passkey / Touch ID) si scriptul continua singur. La final vezi in jurnal
ce a scris si o verificare Time@IBM <-> SuccessFactors, zi cu zi.

Bine de stiut inainte de prima rulare:

- **"Doar verifica"** parcurge tot fara sa salveze nimic - bun pentru prima
  data, si ca sa verifici o saptamana deja pontata.
- **Concediul trimite o cerere reala la manager** in SuccessFactors. Nu e de
  testat; folosesc-l doar cand chiar pleci.
- **Submit** nu se apasa niciodata automat, in niciunul din sisteme. Il dai
  tu, cand esti sigur.
- Scriptul nu cere si nu stocheaza parole. Sesiunea ramane pe calculatorul
  tau, ca in browser.

Restul acestui fisier e pentru cine vrea sa stie cum functioneaza sau sa
ruleze din linia de comanda.

---

Script Playwright pentru `https://time.ibm.com/week`:
copiaza claim item-ul din saptamana precedenta si completeaza orele.

| Rand | Luni-Vineri | Sambata/Duminica |
|------|-------------|------------------|
| Regular | 8 | gol |
| Stand by (doar in perioada de oncall) | 15.5 | 24 |

## Instalare (o singura data)

Dublu-click pe **`Pontaj.command`** (Mac) sau **`Pontaj.bat`** (Windows).
Lansatorul verifica, in ordine, si instaleaza ce lipseste:

| | Mac | Windows |
|---|---|---|
| Python 3.9+ | Homebrew, altfel instalatorul python.org (cere parola) | winget, altfel instalatorul python.org, silentios, cu PATH |
| Playwright | pip | pip |
| Google Chrome | Homebrew, altfel dmg-ul oficial Google | winget, altfel instalatorul oficial Google |

Fara Google Chrome se foloseste Chromium-ul lui Playwright, unde login-ul
merge doar cu parola, nu cu passkey. Stub-urile care se dau drept Python
(cel al Apple fara Command Line Tools, cel din Microsoft Store) sunt
recunoscute si sarite.

Din terminal:

```bash
pip install playwright
python -m playwright install chromium   # doar daca nu ai Google Chrome
```

## Login

Login-ul e al tau, de fiecare data cand IBM il cere. Browserul se deschide
mereu la vedere; daca ajunge pe pagina w3id, te loghezi acolo (w3id + parola
sau passkey + 2FA) si scriptul continua singur cand apare saptamana.

**Scriptul nu cere, nu stocheaza si nu tasteaza nicio parola.** Profilul din
`~/.ibm-pontaj-profile` pastreaza doar ce ar pastra orice browser: emailul
precompletat si cookie-urile de sesiune.

**Sesiunea ramane logata intre rulari**, ca in browserul de zi cu zi. Acela
ramane logat pentru ca nu se inchide niciodata; scriptul inchide Chrome la
sfarsitul fiecarei rulari, iar Chrome arunca atunci cookie-urile de sesiune.
De aceea le salveaza inainte, in `~/.ibm-pontaj-session.json` (doar al tau,
0600), si le pune la loc la pornire. Login-ul se cere din nou doar cand
expira sesiunea pe partea IBM.

Fereastra e **Google Chrome-ul instalat**, nu Chromium-ul care vine cu
Playwright. Diferenta se vede la login: Chromium ("Chrome for Testing") nu
are integrarea macOS cu passkey-urile din iCloud Keychain, asa ca w3id ofera
acolo doar parola; in Chrome apare butonul de passkey si Touch ID-ul merge,
ca in browserul de zi cu zi. Profilul ramane cel al scriptului, nu cel
personal - Chrome refuza sa fie automatizat pe profilul deschis. Fara Chrome
instalat, scriptul cade inapoi pe Chromium si spune ca passkey-ul nu va merge.

Nu exista mod headless. A fost incercat: w3id refuza sesiunea din browserul
fara fereastra si cere din nou parola, pe care nu are cine sa o scrie.
`python pontaj_ibm.py --login` deschide pagina si asteapta login-ul fara sa
ponteze nimic, daca vrei sa te loghezi inainte.

## Rulare

```bash
# interactiv - te intreaba daca e saptamana simpla sau cu oncall
python pontaj_ibm.py

# fara intrebari
python pontaj_ibm.py --simple --yes
python pontaj_ibm.py --oncall "9-15" --yes

# o saptamana anume
python pontaj_ibm.py --week "September 18, 2026" --oncall "9-15"

# vezi ce ar face, fara sa salveze
python pontaj_ibm.py --oncall "9-15" --dry-run
```

Formate acceptate pentru `--oncall`: `9-15`, `sep 9 - sep 15`,
`9 sep - 15 sep`, `2026-09-09:2026-09-15`.

**Un oncall care atinge doua saptamani de pontaj le ponteaza pe amandoua**
dintr-o rulare: cea aleasa cu tot ce s-a cerut, cealalta doar cu stand by
(overtime-ul si zilele libere se dau relativ la saptamana aleasa). Interfata
spune dinainte ce a doua saptamana va fi atinsa.

**`--overtime "12=4@20:00"`** spune si de cand a inceput overtime-ul.
Time@IBM vrea doar numarul de ore; SuccessFactors vrea interval, si fara
`@ora` ia 17:30 in zi lucratoare si 09:00 in weekend sau zi libera. Merg
`@20`, `@20:00`, `@8pm`, `@8:30 pm`.

## Coduri de claim: fiecare ponteaza altfel

Unii ponteaza pe un singur claim item, altii pe doua, cu orele impartite in
felul lor. De aceea impartirea e o **configurare per persoana**, facuta din
panoul "Coduri de claim" al interfetei si tinuta pe calculatorul fiecaruia
(`~/.ibm-pontaj-config.json`):

1. **Citeste codurile din Time@IBM** deschide Chrome, citeste claim item-urile
   din saptamana curenta (cont, task, nume) si le pune in lista. Un cod care
   nu e inca in nicio saptamana se poate adauga si manual, dupa cont si task.
2. Pentru fiecare cod scrii **orele Regular pe zi**, Luni-Vineri - `8` peste
   tot, `4` si `4`, luni-miercuri pe unul si joi-vineri pe celalalt, orice
   combinatie - si bifezi **pe care merge stand by-ul** si **pe care merge
   overtime-ul** (cate unul singur).
3. **Salveaza.** De acum fiecare rulare imparte orele asa; jurnalul arata
   impartirea inainte sa scrie. Se poate schimba oricand.

Un cod din configurare care lipseste din saptamana se adauga singur, prin
"New claim item" dupa cont si task - acelasi mecanism ca la M.00556. Daca
codul cere si un Bill Code, scriptul se opreste si spune sa il adaugi o data
manual; dupa aceea il gaseste in saptamana si il foloseste.

**Fara configurare**, ca pana acum: singurul claim item din grila primeste 8
pe zi, cu stand by si overtime pe el. Mai multe claim item-uri fara
configurare inseamna un mesaj clar ("configureaza codurile"), nu o ghiceala.
Un claim item care e in saptamana dar nu e in configurare e lasat in pace si
semnalat.

Verificarea de la final insumeaza stand by-ul si overtime-ul peste toate
codurile, pentru ca SuccessFactors nu are coduri.

## SuccessFactors: aceleasi ore, a doua oara

HR cere ca stand by-ul si overtime-ul sa fie identice in Time@IBM si in
SuccessFactors ("Record Your Time"); o luna cu discrepante se plateste
incomplet. Dupa Save-ul din Time@IBM, scriptul deschide foaia de pontaj SF
si aduce fiecare zi a saptamanii la aceleasi ore, in forma pe care SF o
cere - intervale, nu numere:

| Time@IBM | SuccessFactors |
|---|---|
| Stand by 15.5 (zi lucratoare) | Standby 12:00 AM - 9:00 AM + Standby 5:30 PM - 12:00 AM |
| Stand by 24 (weekend) | Standby 12:00 AM - 12:00 PM + Standby 12:00 PM - 12:00 AM |
| Overtime N ore | Overtime de la 5:30 PM (zi lucratoare) sau 9:00 AM (weekend / zi libera), N ore |
| Sarbatoare cu oncall | 24 h Standby, sau Overtime + Standby pe restul zilei (16 h la 8 h overtime) |

Modelele sunt citite de pe foi de pontaj deja aprobate. O zi care are deja
exact aceste inregistrari e lasata in pace; altfel inregistrarile de Standby
si Overtime ale zilei se sterg si se scriu cele corecte, apoi Save. Dupa
Save, ziua e recitita si comparata - "salvat" inseamna ca SF arata ce trebuie.
Un refuz al SF-ului (camp marcat cu eroare, de exemplu "Ensure only one entry
exists..." sau "A full day absence exists...") opreste rularea cu mesajul lui;
butonul Save singur nu spune nimic, pentru ca SAP il dezactiveaza si cand
formularul are erori.
O foaie deja aprobata cere confirmarea "You need to submit the time sheet
again"; scriptul confirma si spune in jurnal ca foaia trebuie retrimisa.
**Submit-ul foii SF ramane pe seama ta**, ca la Time@IBM.

**Concediul** merge prin "Absences -> Create", care e o cerere de concediu:
Time Type `Vacation`, Full Day, Start/End Date, apoi **Submit** - cererea
pleaca la aprobare si apare pe zi ca "Vacation, Pending". Zilele consecutive
de concediu din saptamana devin o singura cerere, cum ar face-o si omul. O
zi care are deja concediu in SF e lasata in pace; un concediu din SF care nu
e in plan e doar semnalat, pentru ca anularea unei cereri e treaba omului si
a HR-ului. Sarbatoarea legala nu se pune in SF (emailul HR).

**La final, verificarea.** Dupa ce a scris in amandoua, scriptul reciteste
din grila Time@IBM si din foaia SF ce e efectiv salvat si le pune fata in
fata, zi cu zi, pe stand by, overtime si concediu:

```
Verificare Time@IBM <-> SuccessFactors:
    Zi                  stand by        overtime      concediu
    Sat 12 Sep        - / -           4 / 4           - / -
    Wed 16 Sep     15.5 / 15.5        - / -           - / -
    ...
Verificare reusita: Time@IBM si SuccessFactors coincid.
```

O diferenta e marcata cu `!!` pe rand si insumata la final intr-un
`ATENTIE: N diferente ...` cu fiecare caz numit - in interfata apare cu
rosu, ca erorile. Sarbatoarea legala nu se compara (se pune doar in
Time@IBM), iar stand by-ul ei, care in SF e cu 8 ore mai mare prin regula
HR, e marcat `(regula HR)` si nu conteaza ca diferenta. In dry run
verificarea compara starea curenta, fara modificari.

`--no-sf` sare peste SF (in interfata: bifa "Ponteaza si in SuccessFactors").
Login-ul in SF e tot al tau (passkey), iar sesiunea se pastreaza la fel ca
cea de Time@IBM.

## Zile libere: concediu, sarbatoare legala, compensatie

```bash
python pontaj_ibm.py --vacation "14-16"            # concediu
python pontaj_ibm.py --holiday "15"                # sarbatoare legala
python pontaj_ibm.py --holiday "1" --overtime "1=8" --comp "4"
```

Toate se ponteaza cu 8 ore pe claim item-ul `M.00556 - WW TimeAway`, fiecare
pe task-ul ei: `XL0A00 Vacation`, `XL0B00 Designated Holiday`, `XL0C00
Optional Holiday` (ziua libera luata in compensatie). Daca claim item-ul nu
exista pe saptamana, scriptul il adauga singur: New claim item -> cauta
`M.00556` -> bifeaza WBS-ul si task-ul -> Add. In ziua aceea randul Regular
al proiectului ramane gol.

Regulile pentru o sarbatoare legala sunt cele din emailul HR:

| Situatie | Time@IBM |
|---|---|
| nu lucrezi | 8 pe XL0B00 |
| overtime | 8 pe XL0B00 + overtime pe proiect (`--overtime "1=8"`) |
| overtime + oncall | ... + **8** stand by |
| doar oncall | 8 pe XL0B00 + **16** stand by |
| overtime, dar vrei alta zi libera | ca la overtime, plus 8 pe XL0C00 in ziua aleasa (`--comp`) |

Stand by-ul de 8 sau 16 iese singur din `--oncall` si `--overtime`; diferenta
fata de SAP o factureaza PMO manual si nu e treaba scriptului. **Concediul si
compensatia nu primesc stand by nici in oncall**: SuccessFactors refuza orice
inregistrare intr-o zi cu absenta de o zi intreaga, iar cele doua sisteme
trebuie sa coincida. Zilele se
scriu ca la overtime: numar din luna, nume de zi sau interval (`14-16`).
Weekend-ul e refuzat, si la fel o zi trecuta la doua feluri de liber.

## Cum trateaza saptamanile

Saptamana IBM se incheie vineri, deci **weekend-ul e la inceputul ei**.
Saptamana care se incheie vineri 18 Sep 2026 contine Sat 12, Sun 13, apoi
Mon 14 ... Fri 18.

Din cauza asta, o perioada de oncall aproape sigur se imparte in doua
saptamani de pontaj. Pentru oncall 9-15 Sep 2026:

```
Week ending 11 Sep          Week ending 18 Sep
  Wed 09  Regular 8 / SB 15.5    Sat 12  SB 24
  Thu 10  Regular 8 / SB 15.5    Sun 13  SB 24
  Fri 11  Regular 8 / SB 15.5    Mon 14  Regular 8 / SB 15.5
                                 Tue 15  Regular 8 / SB 15.5
                                 Wed-Fri Regular 8
  SB total: 46.5                 SB total: 79
```

Rulezi scriptul de doua ori, cu acelasi `--oncall "9-15"`, o data pe fiecare
saptamana. El decide singur ce zile pica in interval.

Scriptul **nu presupune** ordinea coloanelor: citeste datele din capul de
tabel si completeaza pe data calendaristica. Daca numarul de coloane din
header nu se potriveste cu numarul de casute din rand, se opreste cu eroare
in loc sa ponteze pe zi gresita.

"Show weekend" se apasa automat, dar numai cand exista oncall in weekend-ul
saptamanii respective.

## Verificare inainte de salvare

Inainte sa scrie ceva, scriptul afiseaza planul si cere confirmare:

```
[pontaj]     Zi             Regular  Stand by
[pontaj]     Sat 12 Sep           -        24
[pontaj]     Sun 13 Sep           -        24
[pontaj]     Mon 14 Sep           8      15.5
...
  Confirmi? [y/N]:
```

Sari peste confirmare cu `--yes` (necesar pentru cron).

## Daca ceva nu merge

`python pontaj_ibm.py --debug` - browser vizibil, incetinit, pauza la final.
La orice eroare se salveaza `pontaj_eroare.png` in directorul curent.

Puncte sensibile:

- **Etichetele randurilor.** Scriptul cauta exact `Regular` si `Stand by`.
  Daca in aplicatia ta scrie altfel (`Standby`, `On call`), modifica
  `REGULAR_LABEL` / `STANDBY_LABEL` la inceputul fisierului.
- **Modalul dupa "Copy from a previous week".** Nu stiu cum arata la tine.
  Scriptul incearca butoane "Copy", "Continue", "OK", "Apply", "Confirm".
  Ruleaza o data cu `--debug` si adauga butonul corect daca lipseste.
- **Separatorul zecimal.** Daca aplicatia refuza `15.5`, schimba
  `DECIMAL_SEP = "."` in `DECIMAL_SEP = ","`.
- **Randul Stand by lipseste.** Apare doar daca claim item-ul copiat il are.
  Daca ai oncall si randul nu exista, scriptul se opreste si te anunta -
  adauga-l manual o data, apoi copierea din saptamana precedenta il aduce.

## Teste

`python test_logica.py` verifica parsarea datelor si generarea planului,
fara browser. Util dupa orice modificare a orelor sau a logicii.

## Programare automata

Vineri la 17:00 (Linux/macOS):

```
0 17 * * 5 cd /cale/catre/pontaj && /usr/bin/python3 pontaj_ibm.py --simple --yes >> pontaj.log 2>&1
```

Saptamanile cu oncall nu le lasa pe cron - ruleaza-le manual cu `--oncall`,
ca sa vezi planul inainte de confirmare.

## Submit

Scriptul se opreste la Save. Butonul Submit e oricum dezactivat pana se
incheie saptamana, iar orele raman declaratia ta - merita o privire inainte
de trimitere, mai ales in saptamanile cu concediu sau sarbatori legale.

Cu `--submit` incearca si trimiterea; daca butonul e greyed out, te anunta
si iese curat.

## Ore suplimentare (Overtime)

Randul `Overtime` nu exista implicit. Se adauga din meniul cu 3 puncte al
randului `General Billable`. Scriptul face asta singur, dar doar cand chiar
ai overtime de pus.

```bash
# interactiv: te intreaba dupa oncall
python pontaj_ibm.py

# direct
python pontaj_ibm.py --overtime "16=3"
python pontaj_ibm.py --oncall "9-15" --overtime "wed=2.5, joi=1"
python pontaj_ibm.py --simple --no-overtime --yes   # pentru cron
```

Formate acceptate pentru `--overtime` (separate prin virgula sau `;`):

| Scriere | Inseamna |
|---------|----------|
| `16=3` | ziua 16 a lunii, 3 ore |
| `wed=2.5` / `mie=2.5` | miercuri, 2.5 ore |
| `joi 1` | joi, 1 ora |
| `joi=1,5` | joi, 1.5 ore (virgula zecimala merge) |
| `16=3, 17=2` | doua zile deodata |

Zilele se valideaza fata de saptamana afisata: daca ceri overtime pe o zi
care nu e in saptamana, scriptul se opreste cu eroare in loc sa ghiceasca.
Peste 12 ore intr-o zi primesti o avertizare, dar nu te blocheaza.

Daca optiunea din meniul cu 3 puncte se numeste altfel la tine, modifica
`OVERTIME_MENU_WORDS` de la inceputul scriptului. Randul-parinte din care se
deschide meniul e `PARENT_ROW_LABEL = "General Billable"`.


## Interfata grafica

```bash
python gui.py
```

Porneste un server local pe `127.0.0.1` si deschide pagina in browser. Nu e
expus in retea si nu are dependinte in afara de Python standard.

Ce face interfata:

- alegi orice zi din calendar; saptamana IBM care o contine (sambata - vineri)
  se incheie in vinerea afisata sub camp
- comuti intre saptamana obisnuita si una cu oncall
- scrii perioada de oncall si orele suplimentare in aceleasi formate ca la
  linia de comanda
- vezi imediat cum va arata saptamana, inainte sa se atinga ceva pe site
- la fiecare rulare se apasa Save, pentru ca orele scrise in grila nu raman
  fara el; "Doar verifica" e optional si parcurge tot fluxul fara sa salveze
- Submit nu se apasa niciodata implicit: inchide saptamana si nu mai poate fi
  corectata din script, iar butonul e activ tot timpul pe site, deci nu e nimic
  care sa te apere de un click in plus
- jurnalul rularii apare live in partea de jos

Butonul "Deschide login-ul IBM" deschide doar pagina, ca sa te loghezi
inainte de pontaj. Nu e obligatoriu: daca sesiunea a expirat, fereastra care
se deschide la "Ponteaza" te lasa sa te loghezi si continua singura.

Grila de pe time.ibm.com e un ag-Grid: claim item-ul vine restrans si scriptul
apasa singur "Expand all", iar orele se scriu cu dublu-click pe celula si
Enter, pe coloana cu data respectiva (dupa `col-id`, nu dupa pozitie).

### Logo

Interfata foloseste stilul Carbon (font IBM Plex, culorile si geometria
aplicatiei), dar cu un semn propriu, nu cu logo-ul IBM &mdash; acela e marca
inregistrata si nu poate fi recreat.

Daca vrei logo-ul oficial, ia fisierul de pe w3 si pune-l ca `logo.png`
langa `gui.py`. Interfata il detecteaza singura la incarcare si il foloseste
in locul semnului implicit. Ramane pe calculatorul tau, nu se distribuie
nicaieri.
