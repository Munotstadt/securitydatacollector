"""
Erzeugt data/latest_prices.json: ein kompaktes Pre-Aggregat mit den
Referenzpunkten, die dashboard.html und portfolio.html für ihre "Last +
Delta"-Ansicht brauchen (Tag/Woche/10 Tage/Monat sowie 52-Wochen-Hoch/Tief),
pro SecurityID. Damit müssen diese Seiten nicht mehr die komplette
security_prices.csv laden und parsen - das bleibt nur für die
Detail-Charts (security.html) und die Editoren nötig.

Wird nach jedem Collector-Lauf und nach dem wöchentlichen Cleanup neu
generiert (siehe commit_and_push_prices.sh / commit_and_push_cleanup.sh),
damit es nie veraltet.
"""

import csv
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ZURICH = ZoneInfo("Europe/Zurich")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICES_PATH = os.path.join(REPO_ROOT, "data", "security_prices.csv")
MASTER_PATH = os.path.join(REPO_ROOT, "data", "security_master.csv")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "latest_prices.json")

# Referenzpunkte, wie sie bisher clientseitig in dashboard.html/portfolio.html
# berechnet wurden (daysAgo(now, N) + "letzter Kurs auf oder vor diesem Datum").
# "day" ist NICHT hier drin - der Offset für "day" hängt vom Wochentag und
# vom Collector-Typ ab, siehe day_offset_for().
REFERENCE_OFFSETS_DAYS = {
    "week": 7,
    "ten_day": 10,
    "month": 30,
    "year": 365,
}


def day_offset_for(now, is_weekday_only):
    """Normalerweise ist 'Vortag' schlicht 1 Tag zurück. Für Securities, die
    nur an Wochentagen erfasst werden (Collector_YahooWeekday), würde das am
    Samstag/Sonntag aber fälschlich Freitag mit Freitag vergleichen (da über
    das Wochenende keine neuen Kurse dazukommen) und einen irreführenden
    Flat-0%-Delta erzeugen. Deshalb wird an diesen beiden Tagen für solche
    Securities weiter zurückgegangen, bis der Cutoff wieder auf Donnerstag
    fällt - damit wird korrekt der letzte ECHTE Tagesvergleich (Do->Fr)
    gezeigt, wie es einem "Vortag" an einem Handelstag entspricht."""
    if is_weekday_only:
        weekday = now.weekday()  # Mo=0 .. So=6
        if weekday == 5:  # Samstag -> Donnerstag (2 Tage zurück)
            return 2
        if weekday == 6:  # Sonntag -> Donnerstag (3 Tage zurück)
            return 3
    return 1


def parse_price_date(s):
    try:
        return datetime.strptime(s.strip(), "%d.%m.%Y %H:%M:%S")
    except (ValueError, AttributeError):
        return None


def read_weekday_only_flags():
    """SecurityID -> True, falls DataCollector == 'Collector_YahooWeekday'."""
    if not os.path.exists(MASTER_PATH):
        return {}
    flags = {}
    with open(MASTER_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            flags[row.get("SecurityID", "")] = (
                row.get("DataCollector", "").strip() == "Collector_YahooWeekday"
            )
    return flags


def read_prices_by_security():
    if not os.path.exists(PRICES_PATH):
        return {}
    by_security = {}
    with open(PRICES_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            dt = parse_price_date(row.get("PriceDate", ""))
            try:
                price = float(row.get("Price", ""))
            except (ValueError, TypeError):
                price = None
            if dt is None or price is None:
                continue
            sec_id = row.get("SecurityID", "")
            by_security.setdefault(sec_id, []).append(
                {"dt": dt, "price": price, "source": row.get("Source", "")}
            )
    for sec_id in by_security:
        by_security[sec_id].sort(key=lambda r: r["dt"])
    return by_security


def find_on_or_before(observations, cutoff):
    """Letzte Beobachtung mit dt <= cutoff, oder None."""
    best = None
    for obs in observations:
        if obs["dt"] <= cutoff:
            if best is None or obs["dt"] > best["dt"]:
                best = obs
        else:
            break  # observations ist aufsteigend sortiert
    return best


def obs_to_json(obs):
    if obs is None:
        return None
    return {"price": obs["price"], "date": obs["dt"].isoformat(), "source": obs["source"]}


def end_of_day(d):
    """23:59:59.999999 desselben Kalendertags - stellt sicher, dass 'letzter
    Kurs von diesem Tag' gefunden wird, unabhängig davon, zu welcher Uhrzeit
    der Generator gerade läuft. Ohne das würde ein FX-Kurs, der später am
    selben Tag erfasst wurde als der Cutoff-Zeitpunkt, fälschlich als 'nicht
    vorhanden' gelten."""
    return d.replace(hour=23, minute=59, second=59, microsecond=999999)


def build_entry(observations, now, is_weekday_only):
    last = observations[-1] if observations else None
    entry = {"last": obs_to_json(last)}

    day_cutoff = end_of_day(now - timedelta(days=day_offset_for(now, is_weekday_only)))
    entry["day"] = obs_to_json(find_on_or_before(observations, day_cutoff))

    for key, offset_days in REFERENCE_OFFSETS_DAYS.items():
        cutoff = end_of_day(now - timedelta(days=offset_days))
        entry[key] = obs_to_json(find_on_or_before(observations, cutoff))

    # YTD: letzter Kurs des VORJAHRES (31.12., 23:59:59), nicht ein
    # Tage-Offset - kalendarisch, nicht rollierend.
    ytd_cutoff = end_of_day(datetime(now.year - 1, 12, 31))
    entry["ytd"] = obs_to_json(find_on_or_before(observations, ytd_cutoff))

    last_365d = [o for o in observations if o["dt"] >= now - timedelta(days=365)]
    if last_365d:
        high = max(last_365d, key=lambda o: o["price"])
        low = min(last_365d, key=lambda o: o["price"])
        entry["high_52w"] = obs_to_json(high)
        entry["low_52w"] = obs_to_json(low)
    else:
        entry["high_52w"] = None
        entry["low_52w"] = None

    return entry


def run():
    now = datetime.now(ZURICH).replace(tzinfo=None)
    by_security = read_prices_by_security()
    weekday_only_flags = read_weekday_only_flags()

    result = {
        "generated_at": now.isoformat(),
        "securities": {
            sec_id: build_entry(observations, now, weekday_only_flags.get(sec_id, False))
            for sec_id, observations in by_security.items()
        },
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

    print(f"latest_prices.json geschrieben: {len(result['securities'])} Securities.")


if __name__ == "__main__":
    run()
