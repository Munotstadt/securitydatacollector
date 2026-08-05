"""
Wöchentlicher Cleanup-Job (läuft 1x pro Woche, siehe Workflow cleanup_weekly.yml).
Drei Stufen, nach Alter der PriceDate-Zeile:

1) VOLLE GRANULARITÄT (Zeilen jünger als COMPACT_AFTER_DAYS Tage):
   Bleiben unverändert - mehrere Kurse/Tag pro Security, damit der
   Intraday-Chart (10 Tage) auf security.html weiterhin sinnvoll aussieht.

2) TAGES-KOMPAKTIERUNG (COMPACT_AFTER_DAYS bis MONTHLY_AFTER_DAYS Tage alt):
   Pro SecurityID + Kalendertag wird nur noch der zeitlich LETZTE Kurs des
   Tages behalten, alle anderen Beobachtungen dieses Tages werden gelöscht.

3) MONATS-KOMPAKTIERUNG (älter als MONTHLY_AFTER_DAYS Tage):
   Pro SecurityID + Kalendermonat wird nur noch der zeitlich LETZTE Kurs
   des Monats behalten. Es wird ab hier NICHTS mehr endgültig gelöscht -
   die Langzeit-Historie bleibt auf Monatsbasis für immer erhalten, statt
   wie früher komplett zu verfallen.
"""

import csv
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from run_log import trigger_label

ZURICH = ZoneInfo("Europe/Zurich")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICES_PATH = os.path.join(REPO_ROOT, "data", "security_prices.csv")
RUN_LOG_PATH = os.path.join(REPO_ROOT, "data", "collector_runs.csv")
RUN_LOG_HEADER = ["CollectorType", "RunAt", "Status", "DataPoints", "Detail", "Trigger", "RunID", "RunNumber"]
# Wie viele Läufe PRO Collector-Typ maximal behalten werden - admin.html
# zeigt nur die letzten 5, dieser Puffer ist grosszügiger, damit zwischen
# zwei Cleanup-Läufen (wöchentlich) nichts vorzeitig fehlt.
TRIM_KEEP_PER_TYPE = 100

COMPACT_AFTER_DAYS = 11
# Ab hier wird nicht mehr gelöscht, sondern nur noch weiter auf 1 Kurs/Monat
# verdichtet (vorher: MAX_AGE_DAYS, ab dem komplett gelöscht wurde). 550
# Tage, weil der Analyser für den rollierenden 180-Tage-Volatilitäts-Chart
# (über 360 Tage Verlauf) bis zu ~550 Tage volle FX-Historie braucht
# (360+180+Puffer) - erst danach ist gröbere Auflösung unproblematisch.
MONTHLY_AFTER_DAYS = 550


def now_zurich_str():
    return datetime.now(ZURICH).strftime("%d.%m.%Y %H:%M:%S")


def append_and_trim_run_log(new_row):
    """Hängt new_row an data/collector_runs.csv an und kürzt die Datei
    danach auf die letzten TRIM_KEEP_PER_TYPE Einträge PRO Collector-Typ
    (nicht nur für den Cleanup-Job selbst, sondern für ALLE Typen, die sich
    seit dem letzten Cleanup-Lauf angesammelt haben - andere Collectors
    hängen nur an, ohne selbst zu kürzen)."""
    rows = []
    if os.path.exists(RUN_LOG_PATH):
        with open(RUN_LOG_PATH, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    rows.append(new_row)

    def parse_dt(r):
        try:
            return datetime.strptime(r.get("RunAt", ""), "%d.%m.%Y %H:%M:%S")
        except ValueError:
            return datetime.min

    by_type = {}
    for r in rows:
        by_type.setdefault(r.get("CollectorType", ""), []).append(r)

    trimmed = []
    for entries in by_type.values():
        entries.sort(key=parse_dt, reverse=True)
        trimmed.extend(entries[:TRIM_KEEP_PER_TYPE])
    trimmed.sort(key=parse_dt, reverse=True)

    with open(RUN_LOG_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RUN_LOG_HEADER)
        writer.writeheader()
        writer.writerows(trimmed)


def parse_price_date(s):
    try:
        return datetime.strptime(s.strip(), "%d.%m.%Y %H:%M:%S")
    except (ValueError, AttributeError):
        return None


def compact_by_key(rows, key_fn):
    """Generische Kompaktierung: pro key_fn(row) wird nur die Zeile mit dem
    zeitlich spätesten PriceDate behalten. Erwartet, dass ALLE übergebenen
    Zeilen bereits ein parsbares Datum haben (Aufrufer filtert vorher)."""
    latest_by_key = {}  # key -> (dt, row)
    compacted_away = 0

    for row in rows:
        dt = parse_price_date(row["PriceDate"])
        key = key_fn(row, dt)
        existing = latest_by_key.get(key)
        if existing is None or dt > existing[0]:
            if existing is not None:
                compacted_away += 1
            latest_by_key[key] = (dt, row)
        else:
            compacted_away += 1

    return [row for _dt, row in latest_by_key.values()], compacted_away


def run():
    if not os.path.exists(PRICES_PATH):
        print("security_prices.csv nicht gefunden - nichts zu tun.")
        return

    with open(PRICES_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        rows = list(reader)

    now = datetime.now(ZURICH).replace(tzinfo=None)
    cutoff_recent = now - timedelta(days=COMPACT_AFTER_DAYS)
    cutoff_monthly = now - timedelta(days=MONTHLY_AFTER_DAYS)

    # In drei Alters-Buckets aufteilen. Zeilen mit unparsbarem Datum werden
    # sicherheitshalber wie "aktuell" behandelt (nicht verändert/gelöscht).
    recent, daily_zone, monthly_zone = [], [], []
    for row in rows:
        dt = parse_price_date(row.get("PriceDate", ""))
        if dt is None or dt >= cutoff_recent:
            recent.append(row)
        elif dt >= cutoff_monthly:
            daily_zone.append(row)
        else:
            monthly_zone.append(row)

    daily_compacted, compacted_away = compact_by_key(
        daily_zone, lambda row, dt: (row.get("SecurityID", ""), dt.date())
    )
    monthly_compacted, monthly_compacted_away = compact_by_key(
        monthly_zone, lambda row, dt: (row.get("SecurityID", ""), dt.year, dt.month)
    )

    rows = recent + daily_compacted + monthly_compacted

    with open(PRICES_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"Cleanup abgeschlossen: {compacted_away} Zeile(n) ({COMPACT_AFTER_DAYS}-{MONTHLY_AFTER_DAYS} Tage alt) "
        f"auf 1 Kurs/Tag kompaktiert, zusätzlich {monthly_compacted_away} Zeile(n) (älter als "
        f"{MONTHLY_AFTER_DAYS} Tage) auf 1 Kurs/Monat kompaktiert (keine endgültige Löschung mehr), "
        f"{len(rows)} Zeile(n) verbleiben."
    )

    append_and_trim_run_log({
        "CollectorType": "Weekly Cleanup",
        "RunAt": now_zurich_str(),
        "Status": "OK",
        "DataPoints": f"-{compacted_away} daily-compacted / -{monthly_compacted_away} monthly-compacted",
        "Detail": f"{len(rows)} remaining",
        "Trigger": trigger_label(),
        "RunID": os.environ.get("GITHUB_RUN_ID", ""),
        "RunNumber": os.environ.get("GITHUB_RUN_NUMBER", ""),
    })


if __name__ == "__main__":
    run()
