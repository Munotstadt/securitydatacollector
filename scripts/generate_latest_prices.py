"""
Erzeugt data/latest_prices.json: ein kompaktes Pre-Aggregat mit den
Referenzpunkten, die dashboard.html, portfolio.html und analyser.html für
ihre "Last + Delta"-Ansichten brauchen, pro SecurityID. Damit müssen diese
Seiten nicht mehr die komplette security_prices.csv laden und parsen - das
bleibt nur für die Detail-Charts (security.html) und die Editoren nötig.

PERIODEN-DEFINITIONEN (Stand: präzisiert, siehe Kommentare unten):
  day            Vortag - letzter Kurs vor dem heutigen Handelstag
  wtd            Week-to-Date - vs. Schlusskurs des Wochenendes davor
                 (Sonntag bei 7-Tage-Securities, Freitag bei
                 Collector_YahooWeekday-Securities)
  ten_day        10 Days - rollierend, 10 Kalendertage zurück
  mtd            Month-to-Date - vs. letztem verfügbaren Kurs des VORMONATS
                 (kalendarisch, z.B. 31.07. für August), nicht rollierend
  thirty_day     30 Days - rollierend, 30 Kalendertage zurück
  ninety_day     90 Days - rollierend, 90 Kalendertage zurück
  ytd            Year-to-Date - vs. letztem Kurs des VORJAHRES (31.12.),
                 kalendarisch, nicht rollierend
  three_sixty_day 360 Days - rollierend, 360 Kalendertage zurück

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

# Rein rollierende Perioden (fixer Tage-Offset, "vor N Kalendertagen").
ROLLING_OFFSETS_DAYS = {
    "ten_day": 10,
    "thirty_day": 30,
    "ninety_day": 90,
    "three_sixty_day": 360,
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


def wtd_cutoff(now, is_weekday_only):
    """Week-to-Date-Referenzpunkt: der Schlusskurs des Wochenendes VOR der
    aktuellen (kalendarischen, Montag-startenden) Woche - Sonntag für
    7-Tage-Securities (FX/Krypto/Rohstoffe), Freitag für
    Collector_YahooWeekday-Securities (da dort übers Wochenende ohnehin
    keine neuen Kurse entstehen)."""
    monday_this_week = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    boundary = monday_this_week - timedelta(days=3 if is_weekday_only else 1)
    return end_of_day(boundary)


def mtd_cutoff(now):
    """Month-to-Date-Referenzpunkt: letzter verfügbarer Kurs des
    VORMONATS (kalendarisch, z.B. 31.07. für einen Cutoff im August) -
    nicht rollierend (kein fixer 30-Tage-Offset)."""
    first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    return end_of_day(last_of_prev_month)


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

    entry["wtd"] = obs_to_json(find_on_or_before(observations, wtd_cutoff(now, is_weekday_only)))
    entry["mtd"] = obs_to_json(find_on_or_before(observations, mtd_cutoff(now)))

    for key, offset_days in ROLLING_OFFSETS_DAYS.items():
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
