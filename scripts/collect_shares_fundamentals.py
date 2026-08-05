"""
Wöchentlicher Collector für Shares-Fundamentaldaten (Einzelaktien).

Liest data/security_master.csv, filtert auf Instrument == 'Shares' mit
gesetztem YahooTicker (unabhängig vom DataCollector-Flag, das ist für die
Kurs-Collectors reserviert - dieser Collector läuft komplett separat,
wöchentlich statt alle 30 Minuten).

Holt pro Security via yfinance NUR Markt-/Bewertungskennzahlen und
Termine (Market Cap, P/E, P/B, EPS, Ex-Dividend-/Earnings-Datum, Payout
Ratio, Analystenkonsens + Kursziel) - BEWUSST OHNE Zahlen aus dem
Geschäftsbericht (Bilanz/Erfolgsrechnung/Geldflussrechnung), die sich
ohnehin nur quartalsweise ändern und für dieses Projekt nicht relevant sind.

Schreibt EINE Zeile pro Security pro Lauf nach
data/security_shares_fundamentals.csv (Append - so entsteht über die Zeit
eine Historie dieser Kennzahlen, analog zu den Preis-Collectors).

Zeitstempel-Format: dd.mm.yyyy hh:mm:ss, Zeitzone Europe/Zurich (CET/CEST).
"""

import csv
import os
from datetime import datetime
from zoneinfo import ZoneInfo

ZURICH = ZoneInfo("Europe/Zurich")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER_PATH = os.path.join(REPO_ROOT, "data", "security_master.csv")

HEADER = [
    "SecurityID", "SecurityName", "Currency",
    "MarketCap", "PE_Trailing", "PE_Forward", "PB_Ratio",
    "EPS_Trailing", "EPS_Forward", "DividendPayoutRatio",
    "ExDividendDate", "EarningsDate",
    "RecommendationMean", "RecommendationKey", "NumberOfAnalysts",
    "PriceTargetLow", "PriceTargetMean", "PriceTargetHigh", "PriceTargetMedian",
    "Source", "Created_at",
]

PENDING_PATH = os.path.join(
    os.environ.get("RUNNER_TEMP", "/tmp"), "pending_shares_fundamentals.csv"
)


def read_master():
    with open(MASTER_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def now_zurich_str():
    return datetime.now(ZURICH).strftime("%d.%m.%Y %H:%M:%S")


def write_pending_rows(rows):
    with open(PENDING_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def fmt_date(epoch_ts):
    """Unix-Timestamp (wie von yfinance für exDividendDate geliefert) ->
    dd.mm.yyyy. None/0 -> leer."""
    if not epoch_ts:
        return ""
    try:
        return datetime.fromtimestamp(int(epoch_ts), tz=ZURICH).strftime("%d.%m.%Y")
    except (ValueError, OSError, OverflowError):
        return ""


def fmt_earnings_date(calendar):
    """ticker.calendar liefert i.d.R. {'Earnings Date': [date, date2]} -
    ein Zeitfenster, kein exaktes Datum. Wir nehmen das erste (frühere)
    Datum als Näherung."""
    if not calendar:
        return ""
    dates = calendar.get("Earnings Date")
    if not dates:
        return ""
    try:
        d = dates[0]
        return d.strftime("%d.%m.%Y") if hasattr(d, "strftime") else str(d)
    except Exception:
        return ""


def fetch_fundamentals(ticker_symbol):
    import yfinance as yf  # lazy import, analog zu collect_yahoo_common.py
    t = yf.Ticker(ticker_symbol)
    info = t.info or {}

    try:
        calendar = t.calendar
    except Exception:
        calendar = None

    return {
        "Currency": info.get("currency") or "",
        "MarketCap": info.get("marketCap") or "",
        "PE_Trailing": info.get("trailingPE") or "",
        "PE_Forward": info.get("forwardPE") or "",
        "PB_Ratio": info.get("priceToBook") or "",
        "EPS_Trailing": info.get("trailingEps") or "",
        "EPS_Forward": info.get("forwardEps") or "",
        "DividendPayoutRatio": info.get("payoutRatio") or "",
        "ExDividendDate": fmt_date(info.get("exDividendDate")),
        "EarningsDate": fmt_earnings_date(calendar),
        "RecommendationMean": info.get("recommendationMean") or "",
        "RecommendationKey": info.get("recommendationKey") or "",
        "NumberOfAnalysts": info.get("numberOfAnalystOpinions") or "",
        "PriceTargetLow": info.get("targetLowPrice") or "",
        "PriceTargetMean": info.get("targetMeanPrice") or "",
        "PriceTargetHigh": info.get("targetHighPrice") or "",
        "PriceTargetMedian": info.get("targetMedianPrice") or "",
    }


def run():
    master = read_master()
    active = [
        r for r in master
        if (r.get("Instrument") or "").strip() == "Shares" and r.get("YahooTicker")
    ]
    print(f"{len(active)} Shares mit gesetztem YahooTicker gefunden.")

    now_str = now_zurich_str()
    new_rows = []
    errors = 0

    for row in active:
        name = row["SecurityName"]
        ticker = row["YahooTicker"]
        sec_id = row["SecurityID"]
        try:
            data = fetch_fundamentals(ticker)
            new_rows.append({
                "SecurityID": sec_id,
                "SecurityName": name,
                **data,
                "Source": "Yahoo Finance (Fundamentals)",
                "Created_at": now_str,
            })
            print(f"[OK] {name} ({ticker}): MarketCap={data['MarketCap']} PE={data['PE_Trailing']}")
        except Exception as e:
            print(f"[ERROR] {name} (Ticker: {ticker}): {e}")
            errors += 1

    if new_rows:
        write_pending_rows(new_rows)
        print(f"{len(new_rows)} neue Fundamentaldaten-Zeile(n) für den Commit vorbereitet.")
    if errors:
        print(f"{errors} von {len(active)} Securities konnten nicht abgerufen werden.")

    return len(new_rows), errors


if __name__ == "__main__":
    from run_log import write_pending_log
    added, errors = run()
    status = "OK" if errors == 0 else "ERROR"
    detail = f"{errors} security(ies) failed" if errors else ""
    write_pending_log("Shares Fundamentals", status, added, detail)
