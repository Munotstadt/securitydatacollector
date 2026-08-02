"""
Wöchentlicher Collector für Funds-/ETF-Fundamentaldaten.

Liest data/security_master.csv, filtert auf Instrument == 'ETF/Funds' mit
gesetztem YahooTicker. Holt via yfinance (ticker.funds_data) Fondskennzahlen
(Net Assets, Expense Ratio, Kategorie, Anlageklassen-/Sektor-Gewichtung)
sowie die Top-10-Holdings.

Schreibt in ZWEI Dateien:
  - data/security_funds_fundamentals.csv   1 Zeile/Fonds/Lauf (Kennzahlen)
  - data/security_fund_holdings.csv         bis zu 10 Zeilen/Fonds/Lauf (Holdings)

Beide Append-only, analog zu den Preis-Collectors.
Zeitstempel-Format: dd.mm.yyyy hh:mm:ss, Zeitzone Europe/Zurich (CET/CEST).
"""

import csv
import os
from datetime import datetime
from zoneinfo import ZoneInfo

ZURICH = ZoneInfo("Europe/Zurich")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER_PATH = os.path.join(REPO_ROOT, "data", "security_master.csv")

# Standard-Sektorkategorien, wie sie yfinance/Morningstar für
# sector_weightings liefert - als feste Spalten geflacht, statt eine dritte
# Tabelle zu brauchen.
SECTOR_KEYS = [
    "realestate", "consumer_cyclical", "basic_materials", "consumer_defensive",
    "technology", "communication_services", "financial_services", "utilities",
    "industrials", "energy", "healthcare",
]

FUND_HEADER = [
    "SecurityID", "SecurityName", "Currency",
    "NetAssets", "ExpenseRatio", "Category",
    "EquityPct", "BondPct", "CashPct",
] + [f"Sector_{k}" for k in SECTOR_KEYS] + ["Source", "Created_at"]

HOLDINGS_HEADER = [
    "SecurityID", "SecurityName", "HoldingSymbol", "HoldingName", "HoldingPct",
    "Source", "Created_at",
]

PENDING_FUND_PATH = os.path.join(
    os.environ.get("RUNNER_TEMP", "/tmp"), "pending_funds_fundamentals.csv"
)
PENDING_HOLDINGS_PATH = os.path.join(
    os.environ.get("RUNNER_TEMP", "/tmp"), "pending_fund_holdings.csv"
)


def read_master():
    with open(MASTER_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def now_zurich_str():
    return datetime.now(ZURICH).strftime("%d.%m.%Y %H:%M:%S")


def write_pending(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _or_empty(x):
    """Wie 'x or {}', aber sicher für pandas Series/DataFrame - deren
    Wahrheitsgehalt ist bei mehr als einem Element nicht eindeutig
    bestimmbar ('The truth value of a DataFrame is ambiguous'), daher
    NIEMALS 'x or {}' direkt auf einem möglichen Series/DataFrame-Rückgabewert
    von yfinance verwenden."""
    return {} if x is None else x


def _safe_get(obj, *keys, default=""):
    """Wie obj.get(key, default), tolerant gegenüber Series/DataFrame/dict
    und mehreren möglichen Schlüssel-Schreibweisen. Gibt den ersten
    gefundenen, nicht-NaN/nicht-None Wert zurück."""
    for key in keys:
        try:
            val = obj.get(key)
        except AttributeError:
            continue
        if val is None:
            continue
        # pandas liefert bei fehlenden numerischen Werten oft NaN statt None
        try:
            import math
            if isinstance(val, float) and math.isnan(val):
                continue
        except TypeError:
            pass
        return val
    return default


def fetch_fund_data(ticker_symbol):
    import yfinance as yf  # lazy import, analog zu collect_yahoo_common.py
    t = yf.Ticker(ticker_symbol)
    fd = t.funds_data
    if fd is None:
        raise ValueError("Keine funds_data verfügbar (kein Fonds/ETF laut Yahoo?).")

    overview = _or_empty(fd.fund_overview)
    operations = _or_empty(fd.fund_operations)
    asset_classes = _or_empty(fd.asset_classes)
    sector_weightings = _or_empty(fd.sector_weightings)

    try:
        currency = yf.Ticker(ticker_symbol).fast_info.get("currency")
    except Exception:
        currency = None

    fund_row = {
        "Currency": currency or "",
        "NetAssets": _safe_get(operations, "Total Net Assets", "total net assets"),
        "ExpenseRatio": _safe_get(operations, "Annual Report Expense Ratio"),
        "Category": _safe_get(overview, "categoryName", "category"),
        "EquityPct": _safe_get(asset_classes, "stock_position", "stocks"),
        "BondPct": _safe_get(asset_classes, "bond_position", "bonds"),
        "CashPct": _safe_get(asset_classes, "cash_position", "cash"),
    }
    for key in SECTOR_KEYS:
        fund_row[f"Sector_{key}"] = _safe_get(sector_weightings, key)

    holdings = []
    top_holdings = fd.top_holdings
    if top_holdings is not None and not top_holdings.empty:
        for symbol, hrow in top_holdings.iterrows():
            holdings.append({
                "HoldingSymbol": symbol,
                "HoldingName": hrow.get("Name", ""),
                "HoldingPct": hrow.get("Holding Percent", ""),
            })

    return fund_row, holdings


def run():
    master = read_master()
    active = [
        r for r in master
        if (r.get("Instrument") or "").strip() == "ETF/Funds" and r.get("YahooTicker")
    ]
    print(f"{len(active)} Funds/ETFs mit gesetztem YahooTicker gefunden.")

    now_str = now_zurich_str()
    new_fund_rows = []
    new_holding_rows = []
    errors = 0

    for row in active:
        name = row["SecurityName"]
        ticker = row["YahooTicker"]
        sec_id = row["SecurityID"]
        try:
            fund_data, holdings = fetch_fund_data(ticker)
            new_fund_rows.append({
                "SecurityID": sec_id, "SecurityName": name, **fund_data,
                "Source": "Yahoo Finance (Fund Data)", "Created_at": now_str,
            })
            for h in holdings:
                new_holding_rows.append({
                    "SecurityID": sec_id, "SecurityName": name, **h,
                    "Source": "Yahoo Finance (Fund Data)", "Created_at": now_str,
                })
            print(f"[OK] {name} ({ticker}): {len(holdings)} Holdings, NetAssets={fund_data['NetAssets']}")
        except Exception as e:
            print(f"[ERROR] {name} (Ticker: {ticker}): {e}")
            errors += 1

    if new_fund_rows:
        write_pending(PENDING_FUND_PATH, FUND_HEADER, new_fund_rows)
        print(f"{len(new_fund_rows)} neue Fund-Fundamentaldaten-Zeile(n) vorbereitet.")
    if new_holding_rows:
        write_pending(PENDING_HOLDINGS_PATH, HOLDINGS_HEADER, new_holding_rows)
        print(f"{len(new_holding_rows)} neue Holdings-Zeile(n) vorbereitet.")
    if errors:
        print(f"{errors} von {len(active)} Securities konnten nicht abgerufen werden.")


if __name__ == "__main__":
    run()
