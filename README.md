# securitydatacollector

CSV-basierter Security Data Collector mit GitHub Actions Preis-Collectors,
HTML-Editoren und Dashboards. Läuft komplett auf GitHub (Repo + Actions +
GitHub Pages), keine externe Datenbank nötig.

## Struktur

```
data/
  security_master.csv     Stammdaten (1 Zeile pro Security)
  security_prices.csv     Preis-Historie (append-only, mehrere Zeilen/Tag)
scripts/
  collect_yahoo_common.py Gemeinsame Logik für Yahoo-Collectors
  collect_yahoo_weekday.py   Collector_YahooWeekday
  collect_yahoo_daily.py     Collector_YahooDaily
  collect_other.py          Collector_Other (Template, siehe unten)
  cleanup_old_prices.py      löscht Preise > 380 Tage
.github/workflows/
  yahoo_weekday.yml   Mo-Fr 02:00-22:00 UTC, alle 30 Min.
  yahoo_daily.yml     Mo-So 02:00-22:00 UTC, alle 30 Min.
  other_collector.yml gleiche Cadence wie yahoo_weekday
  cleanup_weekly.yml  So 03:00 UTC
index.html            Navigation
dashboard.html         Kursdashboard (gruppiert nach Instrument)
portfolio.html         Portfolio-Performance in CHF (Quantity × Preis × FX)
master_editor.html      Editor für security_master.csv
price_editor.html       Editor für security_prices.csv
assets/github-data.js   Gemeinsamer JS-Helper (GitHub Contents API, CSV, FX)
```

## Setup

1. Diesen Ordnerinhalt in dein Repo `securitydatacollector` pushen (Branch `main`).
2. **GitHub Pages aktivieren:** Settings → Pages → Source: `main` / `/ (root)`.
   Danach ist `index.html` z.B. unter `https://<user>.github.io/securitydatacollector/` erreichbar.
3. **Workflows brauchen keine Secrets** für die Yahoo-Collectors (yfinance ist
   quellen-offen). Der `GITHUB_TOKEN`, den Actions automatisch bereitstellt,
   reicht für den Commit/Push zurück ins Repo (`permissions: contents: write`
   ist in den Workflows bereits gesetzt).
4. **Editor-Seiten (master_editor.html / price_editor.html)** schreiben via
   GitHub Contents API direkt ins Repo. Dafür brauchst du beim ersten Öffnen
   einmalig ein **Personal Access Token** (Fine-grained, Scope: *Contents:
   Read and write* auf dieses Repo) unter „⚙ Repo/Token“ eintragen. Wird lokal
   im Browser (localStorage) gespeichert.

## Collector_Other erweitern

`scripts/collect_other.py` enthält eine `FETCHERS`-Registry
(`SecurityName -> Fetch-Funktion`). Für jede Security im Master mit
`DataCollector = Collector_Other` muss dort ein Eintrag existieren, der
`(price, currency)` zurückgibt. Ein Beispiel (SNB R10 RSS-Feed) ist bereits
enthalten; weitere Quellen (Raiffeisen-API, onvista, HTML-Scraping) lassen
sich nach demselben Muster wie im bestehenden `collect_others_prices.py`
ergänzen.

## Datenmodell / Konventionen

- **SecurityID** = interne, stabile ID (Referenz zwischen master und prices).
- **MainID** = externe Kennung (z.B. Ticker/ISIN), frei befüllbar.
- Preis-Historie wird **nie automatisch überschrieben** — jeder Collector-Lauf
  hängt neue Zeilen an. Einzige Löschung ist der wöchentliche Cleanup-Job
  (> 380 Tage).
- Zeitstempel-Format überall: `dd.mm.yyyy hh:mm:ss`, Zeitzone Europe/Zurich
  (CET/CEST) — siehe `nowZurichString()` in `assets/github-data.js` bzw.
  `now_zurich_str()` in `scripts/collect_yahoo_common.py`.

## Bekannte Vereinfachungen (Ausbaupunkte)

- Dashboard/Portfolio laden aktuell die komplette CSV clientseitig; bei sehr
  grossem Datenvolumen (>> 10-20k Preiszeilen) lohnt sich später ein
  serverseitiges Pre-Aggregat (z.B. `data/latest_prices.json`, von einem
  Workflow nach jedem Collector-Lauf erzeugt).
- `portfolio.html` nutzt live FX-Kurse von `frankfurter.app` (kostenlos, ohne
  Key). Für EUR/CHF, USD/CHF etc. ausreichend; für exotischere Währungen ggf.
  eigene Quelle ergänzen.
- Kein Chart (Kursverlauf) in `dashboard.html`/`portfolio.html` — bewusst
  kompakt gehalten. Kann bei Bedarf analog zu deinem bestehenden
  `index_html.txt`-Template (SVG-Chart-Funktionen) ergänzt werden.
