"""
Gemeinsame Logik für die Yahoo-Collectors (Weekday + Daily).
Liest data/security_master.csv, filtert nach DataCollector-Flag,
holt aktuellen Kurs via yfinance und hängt eine Zeile pro Security
an data/security_prices.csv an (Append, es wird nichts gelöscht/überschrieben -
so werden pro Tag mehrere Kurse gesammelt).

Zeitstempel-Format (Vorgabe): dd.mm.yyyy hh:mm:ss, Zeitzone Europe/Zurich (CET/CEST).
"""

import csv
import os
from datetime import datetime
from zoneinfo import ZoneInfo

ZURICH = ZoneInfo("Europe/Zurich")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER_PATH = os.path.join(REPO_ROOT, "data", "security_master.csv")
PRICES_PATH = os.path.join(REPO_ROOT, "data", "security_prices.csv")
PRICES_HEADER = ["SecurityID", "SecurityName", "Price", "PriceDate", "Source", "Created_at"]

# Ablage für neu ermittelte Preiszeilen dieses Laufs. Bewusst AUSSERHALB des
# Repos (RUNNER_TEMP bzw. /tmp), damit git status sauber bleibt. Das
# Commit/Push-Skript (commit_and_push_prices.sh) liest diese Datei und hängt
# die Zeilen mit Retry-Logik an - siehe dort für den Grund (Vermeidung von
# Merge-Konflikten bei zeitgleich laufenden Collectors).
PENDING_PATH = os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), "pending_prices.csv")


def read_master():
    with open(MASTER_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def now_zurich_str():
    return datetime.now(ZURICH).strftime("%d.%m.%Y %H:%M:%S")


def write_pending_rows(new_rows):
    """Schreibt neu ermittelte Preiszeilen in eine temporäre Datei (nicht ins
    Repo!). Das eigentliche Anhängen an security_prices.csv + Commit/Push
    übernimmt scripts/commit_and_push_prices.sh mit Retry-Logik, um
    Merge-Konflikte bei zeitgleich laufenden Collector-Workflows zu vermeiden."""
    with open(PENDING_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PRICES_HEADER)
        writer.writeheader()
        for row in new_rows:
            writer.writerow(row)


def get_price_and_currency(ticker_symbol):
    import yfinance as yf  # lazy import: nur Weekday/Daily-Collector brauchen yfinance,
                            # Other-Collector soll ohne diese Abhängigkeit laufen können
    t = yf.Ticker(ticker_symbol)
    data = t.history(period="1d", interval="1m")
    if data.empty:
        data = t.history(period="5d")
    if data.empty:
        return None, None
    last = data.iloc[-1]
    price = float(last["Close"])
    currency = None
    try:
        currency = t.fast_info.get("currency")
    except Exception:
        pass
    return price, currency


def run_collector(flag_value, source_label):
    """
    flag_value: z.B. 'Collector_YahooWeekday' oder 'Collector_YahooDaily'
    source_label: Wert für die Source-Spalte in security_prices.csv
    """
    master = read_master()
    active = [r for r in master if r.get("DataCollector") == flag_value and r.get("YahooTicker")]
    print(f"{len(active)} Securities mit Flag '{flag_value}' und gesetztem YahooTicker gefunden.")

    now_str = now_zurich_str()
    new_rows = []
    errors = 0

    for row in active:
        name = row["SecurityName"]
        ticker = row["YahooTicker"]
        sec_id = row["SecurityID"]
        try:
            price, currency = get_price_and_currency(ticker)
            if price is None:
                print(f"[WARN] Keine Kursdaten für '{name}' (Ticker: {ticker})")
                errors += 1
                continue
            new_rows.append({
                "SecurityID": sec_id,
                "SecurityName": name,
                "Price": price,
                "PriceDate": now_str,
                "Source": source_label,
                "Created_at": now_str,
            })
            print(f"[OK] {name} ({ticker}): {price} {currency or ''}")
        except Exception as e:
            print(f"[ERROR] {name} (Ticker: {ticker}): {e}")
            errors += 1

    if new_rows:
        write_pending_rows(new_rows)
        print(f"{len(new_rows)} neue Preiszeile(n) für den Commit vorbereitet ({PENDING_PATH}).")

    if errors:
        print(f"{errors} von {len(active)} Securities konnten nicht abgerufen werden.")

    return len(new_rows), errors
