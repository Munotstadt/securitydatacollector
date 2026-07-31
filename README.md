# securitydatacollector

CSV-basierter Security Data Collector mit GitHub Actions Preis-Collectors,
HTML-Editoren, Dashboards und Portfolio-Ansicht. Läuft komplett auf GitHub
(Repo + Actions + GitHub Pages), keine externe Datenbank nötig.

## Struktur

```
data/
  security_master.csv         Stammdaten (1 Zeile pro Security)
  security_prices.csv         Preis-Historie (append-only, mehrere Zeilen/Tag)
  security_distributions.csv  Ausschüttungen (Dividenden)
  latest_prices.json          Pre-Aggregat: last/day/week/ten_day/month/year +
                               52W-Hoch/Tief pro Security, für Dashboard/
                               Portfolio (spart das Laden der vollen CSV)

scripts/
  collect_yahoo_common.py     Gemeinsame Logik für Yahoo-Collectors
  collect_yahoo_weekday.py    Collector_YahooWeekday (Mo-Fr)
  collect_yahoo_daily.py      Collector_YahooDaily (täglich, z.B. FX, Krypto, Rohstoffe)
  collect_other.py            Collector_Other (FETCHERS-Registry, siehe unten)
  cleanup_old_prices.py       Kompaktiert Preise >35 Tage auf 1/Tag,
                               löscht Preise >380 Tage
  generate_latest_prices.py   Erzeugt data/latest_prices.json
  commit_and_push_prices.sh   Retry-sicheres Commit/Push nach Collector-Läufen
  commit_and_push_cleanup.sh  Retry-sicheres Commit/Push nach dem Cleanup-Job

.github/workflows/
  yahoo_weekday.yml   Mo-Fr 02:00-22:00 UTC, alle 30 Min.
  yahoo_daily.yml     Mo-So 02:00-22:00 UTC, alle 30 Min.
  other_collector.yml gleiche Cadence wie yahoo_weekday
  cleanup_weekly.yml  So 00:15 UTC (ausserhalb der Collector-Fenster)

index.html                    Navigation / Übersichtskarten
dashboard.html                 Kursdashboard (gruppiert nach Instrument)
portfolio.html                  Portfolio-Performance in CHF (Quantity × Preis × FX),
                               Pie-Chart nach Währung, Top/Bottom Contributor
security.html                    Detailansicht pro Security: Kurs-/Dividenden-Chart
                               (interaktive Tooltips), Performance-Tabelle
                               (LC/Cry/CHF), 52W-Range-Slider, Stammdaten-Formular
master_editor.html               Editor für security_master.csv (sortierbar, Eye-Link
                               zu security.html, automatischer ID-Vorschlag)
price_editor.html                Editor für security_prices.csv
distribution_editor.html          Editor für security_distributions.csv
admin.html                       CSV-Bulk-Upload für Preise, Kennzahlen-Kacheln,
                               30-Tage-Aktivitätstabelle
assets/github-data.js            Gemeinsamer JS-Helper (GitHub Contents API, CSV,
                               Datum/Zeit, FX-Lookup mit Fallback)
```

Alle Seiten ausser der (bewusst deutschen) Top-Navigation sind auf Englisch.

## Setup

1. Diesen Ordnerinhalt in dein Repo `securitydatacollector` pushen (Branch `main`).
2. **GitHub Pages aktivieren:** Settings → Pages → Source: `main` / `/ (root)`.
   Danach ist `index.html` z.B. unter `https://<user>.github.io/securitydatacollector/` erreichbar.
3. **Workflows brauchen keine Secrets** für die Yahoo-Collectors (yfinance ist
   quellen-offen). Der `GITHUB_TOKEN`, den Actions automatisch bereitstellt,
   reicht für den Commit/Push zurück ins Repo (`permissions: contents: write`
   ist in den Workflows bereits gesetzt).
4. **Editor-Seiten** (master_editor.html / price_editor.html /
   distribution_editor.html / admin.html) schreiben via GitHub Contents API
   direkt ins Repo. Dafür brauchst du beim ersten Öffnen einmalig ein
   **Personal Access Token** (Fine-grained, Scope: *Contents: Read and write*
   auf dieses Repo) unter „⚙ Repo/Token" eintragen. Wird lokal im Browser
   (localStorage) gespeichert.

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

## Datenmodell / Konventionen

- **SecurityID** = interne, stabile ID (Referenz zwischen master, prices und
  distributions). Im `master_editor.html` nicht editierbar; bei neuen Zeilen
  wird automatisch die nächste freie ID vorgeschlagen.
- **MainID** = externe Kennung (z.B. Ticker/ISIN/Valor), frei befüllbar.
- **Comment**, **MarketGroup** = zusätzliche freie Stammdatenfelder (Schema
  wird beim Laden automatisch erweitert, falls eine ältere CSV diese Spalten
  noch nicht hat).
- Preis-Historie wird **nie direkt überschrieben** — jeder Collector-Lauf
  hängt neue Zeilen an. Der wöchentliche Cleanup-Job (`cleanup_old_prices.py`)
  macht zwei Dinge:
  1. Zeilen **älter als 35 Tage** werden auf **1 Kurs/Tag** kompaktiert (der
     zeitlich letzte Kurs dieses Tages bleibt erhalten).
  2. Zeilen **älter als 380 Tage** werden komplett gelöscht.
- Zeitstempel-Format überall: `dd.mm.yyyy hh:mm:ss` (bzw. `dd.mm.yyyy` ohne
  Zeit für ExDate/PayDate), Zeitzone Europe/Zurich (CET/CEST) — siehe
  `nowZurichString()` in `assets/github-data.js` bzw. `now_zurich_str()` in
  `scripts/collect_yahoo_common.py`.
- **FX-Umrechnung** nutzt ausschliesslich selbst erfasste "XXX/CHF"-Securities
  aus `security_prices.csv` (kein externer API-Call). `fxRateOnDateWithFallback()`
  in `assets/github-data.js` nutzt bei fehlender Notierung am exakten
  Referenzdatum die älteste verfügbare Notierung als Näherung (mit `*`-Markierung
  in der UI) statt gar keinen Wert zu liefern. Referenz-Cutoffs für Perioden
  (Tag/Woche/Monat/YTD/1 Jahr) laufen bewusst auf 23:59:59 des Zieltags, nicht
  auf die aktuelle Uhrzeit — sonst könnte ein später am selben Tag erfasster
  FX-Kurs fälschlich als "nicht vorhanden" gelten.
- **Y-Achsen-Dezimalstellen** in Charts (`decideAxisDecimals()`): > 9'999 → 0
  Nachkommastellen, < 9.99 → 4, sonst 2.

## Bekannte Vereinfachungen (Ausbaupunkte)

- `admin.html`'s CSV-Bulk-Upload lädt die komplette Ziel-CSV bei jedem Upload
  neu hoch (GitHub Contents API hat kein "echtes" Append) — für die bisherige
  Grössenordnung (einige hundert bis wenige tausend Zeilen) unproblematisch,
  bei sehr grossen Dateien (>50 MB) irgendwann spürbar langsam.
- Manche Fonds haben auf Yahoo Finance unzuverlässige/veraltete Kurse für
  bestimmte Börsenplätze (beobachtet z.B. bei `SJPA.SW` und `CSUKX.SW`) — in
  solchen Fällen empfiehlt sich ein alternatives Listing (andere Börse) oder
  eine direkte Quelle wie der iShares-NAV-Export statt Yahoo.
- Kein automatisierter Test-Runner im Repo; Änderungen an den HTML-Editoren
  und Collector-Skripten werden bislang manuell (Browser-Konsole bzw. lokale
  Python-Ausführung) verifiziert.
