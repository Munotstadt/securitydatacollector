"""
Wöchentlicher Cleanup-Job (läuft 1x pro Woche, siehe Workflow cleanup_weekly.yml).
Zwei Schritte, in dieser Reihenfolge:

1) KOMPAKTIERUNG (Zeilen älter als COMPACT_AFTER_DAYS Tage):
   Pro SecurityID + Kalendertag wird nur noch der zeitlich LETZTE Kurs des
   Tages behalten, alle anderen Beobachtungen dieses Tages werden gelöscht.
   Das begrenzt das langfristige Wachstum der Datei auf ~1 Zeile/Tag/Security,
   unabhängig davon, wie oft die Collectors an diesem Tag gelaufen sind.
   Die letzten COMPACT_AFTER_DAYS Tage bleiben in voller Granularität
   (mehrere Kurse/Tag) erhalten, damit der Intraday-Chart (10 Tage) auf
   security.html weiterhin sinnvoll aussieht.

2) LÖSCHUNG (Zeilen älter als MAX_AGE_DAYS Tage):
   Wird nach der Kompaktierung auf die dann bereits verdichteten Daten
   angewendet - unverändert wie bisher.
"""

import csv
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ZURICH = ZoneInfo("Europe/Zurich")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICES_PATH = os.path.join(REPO_ROOT, "data", "security_prices.csv")

COMPACT_AFTER_DAYS = 11
# 550 statt 380 Tage: der Analyser braucht für den rollierenden
# 180-Tage-Volatilitäts-Chart (über 360 Tage Verlauf) bis zu ~550 Tage
# FX-Historie (360 + 180 + Puffer) - bei 380 Tagen würde genau die Daten
# gelöscht, die dafür noch gebraucht werden.
MAX_AGE_DAYS = 550


def parse_price_date(s):
    try:
        return datetime.strptime(s.strip(), "%d.%m.%Y %H:%M:%S")
    except (ValueError, AttributeError):
        return None


def compact_rows(rows, cutoff_recent):
    """Für Zeilen mit PriceDate < cutoff_recent: nur die zeitlich letzte
    Zeile pro (SecurityID, Kalendertag) behalten. Zeilen >= cutoff_recent
    sowie Zeilen mit unparsbarem Datum bleiben unverändert erhalten."""
    old_by_key = {}  # (SecurityID, date) -> (dt, row)
    recent_or_unparsable = []
    compacted_away = 0

    for row in rows:
        dt = parse_price_date(row.get("PriceDate", ""))
        if dt is None or dt >= cutoff_recent:
            recent_or_unparsable.append(row)
            continue
        key = (row.get("SecurityID", ""), dt.date())
        existing = old_by_key.get(key)
        if existing is None or dt > existing[0]:
            if existing is not None:
                compacted_away += 1
            old_by_key[key] = (dt, row)
        else:
            compacted_away += 1

    compacted_rows = [row for _dt, row in old_by_key.values()]
    return recent_or_unparsable + compacted_rows, compacted_away


def delete_old_rows(rows, cutoff_expiry):
    kept, removed = [], 0
    for row in rows:
        dt = parse_price_date(row.get("PriceDate", ""))
        if dt is None or dt >= cutoff_expiry:
            kept.append(row)
        else:
            removed += 1
    return kept, removed


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
    cutoff_expiry = now - timedelta(days=MAX_AGE_DAYS)

    rows, compacted_away = compact_rows(rows, cutoff_recent)
    rows, removed = delete_old_rows(rows, cutoff_expiry)

    with open(PRICES_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"Cleanup abgeschlossen: {compacted_away} Zeile(n) älter als {COMPACT_AFTER_DAYS} Tage "
        f"auf 1 Kurs/Tag kompaktiert, zusätzlich {removed} Zeile(n) älter als {MAX_AGE_DAYS} Tage "
        f"gelöscht, {len(rows)} Zeile(n) verbleiben."
    )


if __name__ == "__main__":
    run()
