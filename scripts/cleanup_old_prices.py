"""
Wöchentlicher Cleanup-Job: löscht Zeilen aus data/security_prices.csv,
deren PriceDate älter als 380 Tage ist. Läuft 1x pro Woche (siehe Workflow
cleanup_weekly.yml).
"""

import csv
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ZURICH = ZoneInfo("Europe/Zurich")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICES_PATH = os.path.join(REPO_ROOT, "data", "security_prices.csv")
MAX_AGE_DAYS = 380


def parse_price_date(s):
    try:
        return datetime.strptime(s.strip(), "%d.%m.%Y %H:%M:%S")
    except (ValueError, AttributeError):
        return None


def run():
    if not os.path.exists(PRICES_PATH):
        print("security_prices.csv nicht gefunden - nichts zu tun.")
        return

    with open(PRICES_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        rows = list(reader)

    cutoff = datetime.now(ZURICH).replace(tzinfo=None) - timedelta(days=MAX_AGE_DAYS)

    kept = []
    removed = 0
    for row in rows:
        dt = parse_price_date(row.get("PriceDate", ""))
        # Zeilen mit unparsbarem Datum werden sicherheitshalber behalten statt gelöscht
        if dt is None or dt >= cutoff:
            kept.append(row)
        else:
            removed += 1

    with open(PRICES_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(kept)

    print(f"Cleanup abgeschlossen: {removed} Zeile(n) älter als {MAX_AGE_DAYS} Tage gelöscht, {len(kept)} verbleiben.")


if __name__ == "__main__":
    run()
