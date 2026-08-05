# securitydatacollector

CSV-basierter Security Data Collector mit GitHub Actions Preis-/Fundamentals-
Collectors, HTML-Editoren, Dashboard, Portfolio- und Analyser-Ansicht. Läuft
komplett auf GitHub (Repo + Actions + GitHub Pages), keine externe Datenbank
nötig.

## Struktur

```
data/
  security_master.csv            Stammdaten (1 Zeile pro Security)
  security_prices.csv            Preis-Historie (append-only)
  security_distributions.csv     Ausschüttungen (Dividenden)
  security_shares_fundamentals.csv  Market Cap/P-E/P-B/EPS/Analystendaten (Shares, wöchentlich)
  security_funds_fundamentals.csv   Net Assets/Expense Ratio/Sektor-Gewichtung (ETF/Funds, wöchentlich)
  security_fund_holdings.csv        Top-10-Holdings je Fonds (wöchentlich)
  collector_runs.csv             Lauf-Log aller Collectors (siehe unten) - für admin.html
  latest_prices.json             Pre-Aggregat: last + alle Perioden-Referenzpunkte
                                  (siehe "Perioden-Definitionen" unten) + 52W-Hoch/Tief
                                  pro Security, für Dashboard/Portfolio/Analyser

scripts/
  collect_yahoo_common.py     Gemeinsame Logik für Yahoo-Preis-Collectors
  collect_yahoo_weekday.py    Collector_YahooWeekday (Mo-Fr)
  collect_yahoo_daily.py      Collector_YahooDaily (täglich, z.B. FX, Krypto, Rohstoffe)
  collect_other.py            Collector_Other (FETCHERS-Registry, siehe unten)
  collect_shares_fundamentals.py  Market-/Bewertungskennzahlen für Instrument=Shares (wöchentlich, Montag)
  collect_funds_fundamentals.py   Fondskennzahlen + Top-Holdings für Instrument=ETF/Funds (wöchentlich, Dienstag)
  run_log.py                  Helper: jeder Collector schreibt am Ende einen
                               Eintrag für data/collector_runs.csv (Status,
                               Anzahl Datenpunkte, Trigger-Art, Run-ID)
  cleanup_old_prices.py       Wöchentliche 3-Stufen-Kompaktierung von
                               security_prices.csv (siehe unten) + kürzt
                               collector_runs.csv auf die letzten 100
                               Einträge pro Collector-Typ
  generate_latest_prices.py   Erzeugt data/latest_prices.json
  commit_and_push_prices.sh   Retry-sicheres Commit/Push (Weekday/Daily/Other Collector)
  commit_and_push_cleanup.sh  Retry-sicheres Commit/Push nach dem Cleanup-Job
  commit_and_push_shares_fundamentals.sh  dito für Shares-Fundamentals
  commit_and_push_funds_fundamentals.sh   dito für Funds-Fundamentals + Holdings

.github/workflows/
  yahoo_weekday.yml              Mo-Fr 02:00-22:00 UTC, alle 30 Min.
  yahoo_daily.yml                Mo-So 02:00-22:00 UTC, alle 30 Min.
  other_collector.yml            gleiche Cadence wie yahoo_weekday
  cleanup_weekly.yml             So 00:15 UTC (ausserhalb der Collector-Fenster)
  shares_fundamentals_weekly.yml Mo 04:00 UTC
  funds_fundamentals_weekly.yml  Di 04:00 UTC
  (alle sechs haben zusätzlich workflow_dispatch: - manuell auslösbar über
  die "Run Workflows"-Buttons in admin.html oder den GitHub Actions-Tab)

index.html                    Navigation / Übersichtskarten
dashboard.html                 Kursdashboard (gruppiert nach Instrument),
                              Perioden Day/WTD/MTD/YTD + Definitions-Block
portfolio.html                  Portfolio-Performance in CHF (Quantity × Preis × FX):
                              Summary-Kacheln (inkl. FX-Impact-Zeile) für
                              Day/WTD/10D/MTD/90D/360D, Pie-Charts nach
                              Währung/Instrument, Top-Bottom-Contributor
                              (Day/10D), klappbare Positionstabelle
                              (Shares/Bonds/Alternative, bis zu 3 Ebenen
                              Subgruppen), Definitions-Block
analyser.html                    FX-Exposure/-Risiko/-Performance: FX-Tabelle
                              (Day/10D/30D/90D/360D) mit FX Result/LC
                              Result/Total-Zerlegung, FX-Risks-Karten
                              (Volatilität annualisiert, Impact-Szenarien,
                              Kurs- + Rolling-Volatility-Charts pro
                              Fremdwährung), Market-Group-Tabellen
                              (Switzerland/USA je Index/Core/Growth)
security.html                    Detailansicht pro Security: Security-Switcher-
                              Dropdown, Price-/Dividend-Chart (beide gleichzeitig
                              sichtbar, eigene Zeiträume + Download-Button),
                              Performance-Tabelle (Day/WTD/10D/MTD/90D/360D,
                              LC/Cry/CHF), Yield + Yield-Change-Kacheln,
                              52W-Range-Slider, Stammdaten-Formular (inkl.
                              Industry/TER/URLFactsheet, nur bei passendem
                              Instrument aktiv), Fund-Details (Sektor-Pie
                              + Top-Holdings) bzw. Shares-Fundamentals
                              (Kennzahlen-Grid + Analyst-Targets-Chart) je
                              nach Instrument
master_editor.html               Editor für security_master.csv (sortierbar, Eye-Link
                              zu security.html, automatischer ID-Vorschlag,
                              Industry/TER/URLFactsheet nur bei passendem Instrument aktiv)
price_editor.html                Editor für security_prices.csv (SecurityID nicht editierbar)
distribution_editor.html          Editor für security_distributions.csv (SecurityID nicht
                              editierbar, Ex-/Pay-Date als reine Text-Eingabe)
admin.html                       CSV-Bulk-Upload für Preise, "Run Workflows"-Buttons
                              (löst Collector-Läufe manuell über die GitHub-API
                              aus), 30-Tage-Aktivitätstabelle, "Recent
                              Collector Runs"-Tabelle (letzte 5 Läufe pro
                              Collector-Typ inkl. OK/ERROR, Trigger, Run-Link)
assets/github-data.js            Gemeinsamer JS-Helper (GitHub Contents API,
                              CSV, Datum/Zeit, FX-Lookup mit Fallback,
                              ghDispatchWorkflow für manuelle Collector-Läufe)
assets/version.js                Zentrale Versionsangabe, bindet sich selbst
                              als Footer auf jeder Seite ein
```

Alle Seiten ausser der (bewusst deutschen) Top-Navigation sind auf Englisch.

## Setup

1. Diesen Ordnerinhalt in dein Repo `securitydatacollector` pushen (Branch `main`).
2. **GitHub Pages aktivieren:** Settings → Pages → Source: `main` / `/ (root)`.
   Danach ist `index.html` z.B. unter `https://<user>.github.io/securitydatacollector/` erreichbar.
3. **Workflows brauchen keine Secrets** (yfinance ist quellen-offen). Der
   `GITHUB_TOKEN`, den Actions automatisch bereitstellt, reicht für den
   Commit/Push zurück ins Repo (`permissions: contents: write` ist in den
   Workflows bereits gesetzt).
4. **Editor-Seiten** (master_editor.html / price_editor.html /
   distribution_editor.html / admin.html / security.html) schreiben via
   GitHub Contents API direkt ins Repo. Dafür brauchst du beim ersten
   Öffnen einmalig ein **Personal Access Token** unter „⚙ Repo/Token"
   eintragen. Für den reinen Datenzugriff genügt Scope *Contents: Read and
   write* (Fine-grained); für die "Run Workflows"-Buttons in `admin.html`
   zusätzlich **Actions: Read and write** (bzw. beim klassischen PAT den
   Scope `workflow`). Token wird lokal im Browser (localStorage) gespeichert.

## Collector_Other erweitern

`scripts/collect_other.py` enthält zwei Registries:

- **`FETCHERS`** (`SecurityName -> (Fetch-Funktion, Source-Label)`) — Standard-
  fall, gematcht über den exakten `SecurityName`.
- **`FETCHERS_BY_ID`** (`SecurityID -> (Fetch-Funktion, Source-Label)`) — hat
  Vorrang vor `FETCHERS`; sinnvoll für Securities, deren Name sich später
  ändern könnte, damit eine Umbenennung den Fetcher nicht stillschweigend
  "verwaisen" lässt.

Jede Fetch-Funktion liefert `(price, currency_or_None)`. Enthaltene Quellen:
SNB-RSS (Rendite Bundesobligationen), onvista (STOXX Europe 600), Raiffeisen-
API (Hypothekarzinsen), Raiffeisen-Börse-HTML-Scraping (Futura-II-Fonds, Gold
Vreneli), sowie ein generischer iShares-NAV-Export-Parser
(`_make_ishares_nav_fetcher`, sprachunabhängig — erkennt die NAV-Spalte über
den Header statt über einen festen Sheet-Namen, da iShares' Sheet-Namen je
nach Locale der Download-URL variieren, z.B. "Historisch" vs. "Historical").

## Fundamentals-Collectors

Zwei zusätzliche, bewusst **wöchentliche** (nicht 30-minütliche) Collectors,
da sich diese Kennzahlen selten ändern:

- **`collect_shares_fundamentals.py`** (Montag): für alle Securities mit
  `Instrument == 'Shares'` und gesetztem `YahooTicker` — Market Cap, P/E
  (trailing/forward), P/B, EPS (trailing/forward), Dividend Payout Ratio,
  Ex-Dividend Date, Earnings Date, Analystenkonsens + Kursziel. Bewusst
  **ohne** Zahlen aus dem Geschäftsbericht (Bilanz/Erfolgsrechnung/
  Geldflussrechnung).
- **`collect_funds_fundamentals.py`** (Dienstag): für alle Securities mit
  `Instrument == 'ETF/Funds'` — Net Assets, Expense Ratio, Kategorie,
  Anlageklassen (Equity/Bond/Cash, als Bruchzahl 0-1 von yfinance!) sowie 11
  Sektor-Gewichtungen (`Sector_realestate` … `Sector_healthcare`, ebenfalls
  Bruchzahlen), plus bis zu 10 Top-Holdings in einer separaten Tabelle.
  **Achtung bei den yfinance-Feldnamen:** `asset_classes` liefert die Keys
  camelCase (`stockPosition`/`bondPosition`/`cashPosition`), nicht
  snake_case — das hat den Collector einmal komplett stillschweigend leere
  Werte liefern lassen, bis es korrigiert wurde.

Beide schreiben ihre Ergebnisse als **Snapshot pro Lauf** (mehrere Zeilen pro
Security über die Zeit, wie bei den Preisen) — `security.html` und
`analyser.html` lesen dabei jeweils nur die **neueste** Zeile pro Security.

## Collector-Lauf-Log (`data/collector_runs.csv`)

Jeder der sechs Collectors (Weekday/Daily/Other/Weekly Cleanup/Shares
Fundamentals/Funds Fundamentals) schreibt über `scripts/run_log.py` am Ende
seines Laufs eine Zeile: `CollectorType, RunAt, Status (OK/ERROR),
DataPoints, Detail, Trigger (Scheduled/Manual, aus GITHUB_EVENT_NAME),
RunID, RunNumber` (RunID/RunNumber kommen aus `GITHUB_RUN_ID`/
`GITHUB_RUN_NUMBER` und lassen sich in `admin.html` zum exakten Actions-Lauf
verlinken). Der wöchentliche Cleanup-Job kürzt diese Datei bei jedem Lauf
auf die letzten **100 Einträge pro Collector-Typ**, damit sie nicht
unbegrenzt wächst — `admin.html` zeigt davon nur die letzten 5 pro Typ an.

## Perioden-Definitionen

Sitenweit einheitlich (Dashboard/Portfolio/Analyser/Security verwenden
Teilmengen derselben Definitionen, berechnet serverseitig in
`generate_latest_prices.py` bzw. clientseitig identisch nachgebaut in
`security.html`):

| Periode | Bedeutung |
|---|---|
| `day` | Vortag — bei `Collector_YahooWeekday`-Securities am Sa/So automatisch auf Do→Fr verschoben (kein Fr→Fr-Flat-Delta übers Wochenende) |
| `wtd` | Week-to-Date — vs. Schlusskurs **Sonntag** (7-Tage-Securities) bzw. **Freitag** (Weekday-Securities) der Vorwoche |
| `mtd` | Month-to-Date — vs. letztem Kurs des **Vormonats** (kalendarisch, z.B. 31.07. für August), NICHT rollierend |
| `ytd` | Year-to-Date — vs. letztem Kurs des **Vorjahres** (31.12.), kalendarisch |
| `ten_day` / `thirty_day` / `ninety_day` / `three_sixty_day` | rein rollierende Tage-Offsets (10/30/90/360) |

Welche Teilmenge wo verwendet wird: Dashboard = Day/WTD/MTD/YTD, Portfolio =
Day/WTD/10D/MTD/90D/360D, Analyser = Day/10D/30D/90D/360D, Security =
Day/WTD/10D/MTD/90D/360D (wie Portfolio).

## Datenmodell / Konventionen

- **SecurityID** = interne, stabile ID (Referenz zwischen master, prices,
  distributions, fundamentals). Im `master_editor.html`/`price_editor.html`/
  `distribution_editor.html` nicht editierbar; bei neuen Zeilen wird
  automatisch die nächste freie ID vorgeschlagen.
- **MainID** = externe Kennung (z.B. Ticker/ISIN/Valor), frei befüllbar.
- **Comment**, **MarketGroup** = zusätzliche freie Stammdatenfelder.
- **Industry** = Dropdown mit 13 festen Werten, nur editierbar/aktiv wenn
  `Instrument == 'Shares'` (sonst gesperrt, Wert wird auf `_not defined`
  zurückgesetzt).
- **TER**, **URLFactsheet** = nur editierbar/aktiv wenn
  `Instrument == 'ETF/Funds'`. `URLFactsheet` wird auf `security.html`
  zusätzlich als klickbarer Link angezeigt.
  Alle drei Felder (Industry/TER/URLFactsheet) werden beim Laden automatisch
  ins CSV-Schema nachgezogen, falls sie einer älteren Datei noch fehlen.
- Preis-Historie wird **nie direkt überschrieben** — jeder Collector-Lauf
  hängt neue Zeilen an. Der wöchentliche Cleanup-Job
  (`cleanup_old_prices.py`) arbeitet in **drei Stufen** nach Alter:
  1. **< 11 Tage**: unverändert, volle Intraday-Granularität (für den
     10-Tage-Intraday-Chart auf `security.html`).
  2. **11–550 Tage**: auf **1 Kurs/Tag** kompaktiert.
  3. **> 550 Tage**: auf **1 Kurs/Monat** kompaktiert — es wird ab hier
     **nichts mehr endgültig gelöscht** (früher: harte Löschung nach 380,
     dann 550 Tagen). 550 Tage deshalb, weil der Analyser für den
     rollierenden 180-Tage-Volatilitäts-Chart (über 360 Tage Verlauf) bis
     zu ~550 Tage volle FX-Historie braucht.
- Zeitstempel-Format überall: `dd.mm.yyyy hh:mm:ss` (bzw. `dd.mm.yyyy` ohne
  Zeit für ExDate/PayDate), Zeitzone Europe/Zurich (CET/CEST).
- **FX-Umrechnung** nutzt ausschliesslich selbst erfasste "XXX/CHF"-Securities
  aus `security_prices.csv` (kein externer API-Call). `fxRateOnDateWithFallback()`
  in `assets/github-data.js` nutzt bei fehlender Notierung am exakten
  Referenzdatum die älteste verfügbare Notierung als Näherung (mit `*`-Markierung
  in der UI) statt gar keinen Wert zu liefern. Referenz-Cutoffs laufen bewusst
  auf 23:59:59 des Zieltags, nicht auf die aktuelle Uhrzeit.
- **Rollierende 12-Monats-Dividendensumme** (Dividend-Chart auf
  `security.html`) läuft auf **Monatsgranularität**, nicht tagesgenau —
  verhindert einen künstlichen Doppelzähl-Spike, wenn zwei Dividenden knapp
  über/unter einem Jahr auseinanderliegen (z.B. 12.06. und 06.06. im
  Folgejahr wären tagesgenau für 6 Tage gleichzeitig im 365-Tage-Fenster).
- **Y-Achsen-Dezimalstellen** in Charts (`decideAxisDecimals()`): > 9'999 → 0
  Nachkommastellen, < 9.99 → 4, sonst 2.

## Bekannte Vereinfachungen (Ausbaupunkte)

- `admin.html`'s CSV-Bulk-Upload lädt die komplette Ziel-CSV bei jedem Upload
  neu hoch (GitHub Contents API hat kein "echtes" Append) — für die bisherige
  Grössenordnung unproblematisch, bei sehr grossen Dateien (>50 MB)
  irgendwann spürbar langsam.
- Manche Fonds haben auf Yahoo Finance unzuverlässige/veraltete Kurse für
  bestimmte Börsenplätze (beobachtet z.B. bei `SJPA.SW` und `CSUKX.SW`) — in
  solchen Fällen empfiehlt sich ein alternatives Listing (andere Börse) oder
  eine direkte Quelle wie der iShares-NAV-Export statt Yahoo.
- `analyser.html`'s FX-Risks-Sektion lädt für Volatilität/Rolling-Charts die
  **komplette** `security_prices.csv` (nicht nur das JSON-Pre-Aggregat), da
  volle Tageshistorie der FX-Paare gebraucht wird — bei sehr grossen
  Preisdateien könnte das spürbar langsamer werden.
- Kein automatisierter Test-Runner im Repo; Änderungen an den HTML-Editoren
  und Collector-Skripten werden bislang manuell (Browser-Konsole bzw. lokale
  Python-Ausführung) verifiziert.
