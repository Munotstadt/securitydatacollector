"""
Collector_Other: für Securities, die im Master mit DataCollector='Collector_Other'
geflaggt sind und deren Kurs nicht über Yahoo Finance bezogen werden kann
(z.B. SNB-Zinssätze, Bank-APIs, HTML-Scraping-Quellen).

Da diese Quellen sehr heterogen sind (unterschiedliche APIs/Formate je Security),
wird hier pro SecurityName eine eigene Fetch-Funktion registriert. Neue
"Other"-Securities im Master brauchen zusätzlich einen Eintrag in FETCHERS unten.

Läuft mit derselben Cadence wie der Weekday-Collector (siehe Workflow).
"""

import json
import re
import urllib.request
from datetime import datetime

from collect_yahoo_common import write_pending_rows, now_zurich_str, read_master

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


def strip_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


# ---------------------------------------------------------------------------
# Quelle 1: SNB RSS-Feed (R10 - Rendite Bundesobligationen 10J)
# ---------------------------------------------------------------------------

def fetch_snb_r10():
    url = "https://www.snb.ch/public/de/rss/interestRates"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        xml = resp.read().decode("utf-8", errors="replace")
    for item in re.findall(r"<item>(.*?)</item>", xml, re.DOTALL):
        if re.search(r"<cb:rateName>\s*R10\s*</cb:rateName>", item):
            value = float(re.search(r"<cb:value>\s*([\d,.\-]+)\s*</cb:value>", item).group(1).replace(",", "."))
            return value, None
    raise ValueError("R10 nicht im SNB RSS-Feed gefunden")


# ---------------------------------------------------------------------------
# Quelle 2: Raiffeisen API (Hypothekarzinsen Winterthur)
# ---------------------------------------------------------------------------

RAIFFEISEN_API_URL = "https://api.raiffeisen.ch/loan-product-service/v1/products"
RAIFFEISEN_BANK_CODE = "1485"

RAIFFEISEN_DURATION_MAP = {
    12: "Raiffeisen Winterthur Hypothek 1 Jahr Zinssatz",
    60: "Raiffeisen Winterthur Hypothek 5 Jahr Zinssatz",
    120: "Raiffeisen Winterthur Hypothek 10 Jahr Zinssatz",
    180: "Raiffeisen Winterthur Hypothek 15 Jahr Zinssatz",
}

_raiffeisen_rates_cache = None  # Cache pro Skript-Lauf: 1 API-Call statt 4


def _get_raiffeisen_rates():
    global _raiffeisen_rates_cache
    if _raiffeisen_rates_cache is not None:
        return _raiffeisen_rates_cache
    req = urllib.request.Request(RAIFFEISEN_API_URL, headers={
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-rai-bankcode": RAIFFEISEN_BANK_CODE,
        "x-rai-channel": "INFORMATION",
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.raiffeisen.ch/winterthur/de/privatkunden/"
                   "wohnen-und-hypotheken/hypothekarzinsen.html",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    fixed = next(p for p in data if p.get("type") == "FIXED")
    rates_by_months = {
        v["durationInMonths"]: v["rate"]
        for v in fixed["variants"]
        if v["durationInMonths"] in RAIFFEISEN_DURATION_MAP
    }
    _raiffeisen_rates_cache = {
        name: rates_by_months[months]
        for months, name in RAIFFEISEN_DURATION_MAP.items()
        if months in rates_by_months
    }
    return _raiffeisen_rates_cache


def _make_raiffeisen_rate_fetcher(security_name):
    def _fetch():
        rates = _get_raiffeisen_rates()
        if security_name not in rates:
            raise ValueError(f"'{security_name}' nicht in Raiffeisen-API-Antwort enthalten")
        return rates[security_name], None
    return _fetch


# ---------------------------------------------------------------------------
# Quelle 3: onvista (STOXX Europe 600 EUR NR)
# ---------------------------------------------------------------------------

ONVISTA_API_URL = "https://api.onvista.de/api/v1/instruments/INDEX/1544657/quote?idNotation=&range=D1"


def fetch_onvista_stoxx():
    req = urllib.request.Request(ONVISTA_API_URL, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read())
    price = float(d.get("last") or d.get("previousLast"))
    return price, "EUR"


# ---------------------------------------------------------------------------
# Quelle 4: Raiffeisen Futura II Fonds (boerse.raiffeisen.ch, HTML-Scraping)
# ---------------------------------------------------------------------------
# CAUTION: kein dokumentiertes JSON-API für diese Fonds - die Seite rendert
# NAV direkt im HTML. Falls Raiffeisen das Seitenlayout ändert, muss der
# Regex unten evtl. angepasst werden.

def _make_raiffeisen_futura_fetcher(fund_id):
    def _fetch():
        url = f"https://boerse.raiffeisen.ch/fonds/detail/{fund_id}?exchangeid=393"
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        text = strip_html(html)

        # Preis: direkt nach der "CHF"-Überschrift am Seitenanfang, z.B.
        # "CHF\n\n135.30\n\n+0.84% (+1.13) 24.06.2026"
        price_match = re.search(r"\bCHF\s*\n+\s*([\d']+[.,]\d+)", text)
        if not price_match:
            raise ValueError(
                f"Preis-Muster auf der Raiffeisen-Fondsseite (fund_id={fund_id}) "
                "nicht gefunden - Seitenlayout hat sich evtl. geändert."
            )
        price = float(price_match.group(1).replace("'", "").replace(",", "."))
        if price <= 0:
            raise ValueError(f"Unplausibler Preis für fund_id={fund_id}.")
        return price, "CHF"
    return _fetch


# ---------------------------------------------------------------------------
# Quelle 5: Raiffeisen Börse - Goldvreneli 20 Fr. (Ankaufspreis)
# ---------------------------------------------------------------------------
# CAUTION: Münzen-Übersichtsseite ohne eigene IDs/API - reines HTML-Scraping.

RAIFFEISEN_EDELMETALLE_URL = "https://boerse.raiffeisen.ch/edelmetalle"


def fetch_raiffeisen_vreneli_ankauf():
    req = urllib.request.Request(RAIFFEISEN_EDELMETALLE_URL, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    text = strip_html(html)

    # Nach "20 Fr. Vreneli" folgen (nicht-gierig, über Zeilenumbrüche hinweg)
    # zwei Preise: Ankauf, dann Verkauf.
    match = re.search(
        r"20 Fr\.\s*Vreneli.*?([\d']+[.,]\d+)\s*\n+\s*([\d']+[.,]\d+)",
        text, re.DOTALL,
    )
    if not match:
        raise ValueError(
            "Preis-Muster für '20 Fr. Vreneli' auf boerse.raiffeisen.ch/edelmetalle "
            "nicht gefunden - Seitenlayout hat sich evtl. geändert."
        )
    ankauf = float(match.group(1).replace("'", "").replace(",", "."))
    if ankauf <= 0:
        raise ValueError("Unplausibler Ankaufspreis - Extraktion vermutlich fehlgeschlagen.")
    return ankauf, "CHF"


# ---------------------------------------------------------------------------
# Quelle 6: iShares NAV-Export (offizieller "Download"-Link auf der
# Produktseite, liefert eine SpreadsheetML-"xls"-Datei mit u.a. dem Sheet
# "Historisch" - Spalten: per (Datum), Währung, NAV, ...).
# Nützlich für Fonds, bei denen der Yahoo-Kurs unzuverlässig/veraltet ist
# (z.B. CSUKX.SW, wo Yahoo einen stark abweichenden Wert zeigte).
#
# Die Download-URL ist pro Fonds fix (enthält eine produktspezifische, nicht
# herleitbare ID) - sie muss einmalig von der jeweiligen iShares-Produktseite
# über den "Download"-Link unter "Literature" kopiert werden.
# ---------------------------------------------------------------------------

ISHARES_MONTHS = {
    "Jan.": 1, "Feb.": 2, "März": 3, "Apr.": 4, "Mai": 5, "Juni": 6,
    "Juli": 7, "Aug.": 8, "Sept.": 9, "Okt.": 10, "Nov.": 11, "Dez.": 12,
}


def _make_ishares_nav_fetcher(download_url):
    def _fetch():
        req = urllib.request.Request(download_url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8-sig", errors="replace")

        m = re.search(r'<ss:Worksheet ss:Name="Historisch".*?</ss:Worksheet>', content, re.DOTALL)
        if not m:
            raise ValueError("Sheet 'Historisch' nicht im iShares-Export gefunden.")
        rows = re.findall(r"<ss:Row>(.*?)</ss:Row>", m.group(0), re.DOTALL)
        if len(rows) < 2:
            raise ValueError("Keine Datenzeilen im 'Historisch'-Sheet gefunden.")

        # Erste Datenzeile (nach dem Header) = jeweils der aktuellste Eintrag.
        cells = re.findall(r'<ss:Data ss:Type="(String|Number)">([^<]*)</ss:Data>', rows[1])
        if len(cells) < 3:
            raise ValueError("Unerwartete Zeilenstruktur im 'Historisch'-Sheet.")
        currency = cells[1][1].strip() or None
        try:
            nav = float(cells[2][1])
        except ValueError:
            raise ValueError(f"NAV-Wert nicht numerisch: {cells[2][1]!r}")
        return nav, currency
    return _fetch


# ---------------------------------------------------------------------------
# Registry: SecurityName -> (Fetch-Funktion, Source-Label)
# Fetch-Funktion liefert (price, currency_or_None).
# ---------------------------------------------------------------------------

FETCHERS = {
    "Rendite Bundesobligationen Eidgenossenschaft 10 Jahre (%)": (fetch_snb_r10, "SNB"),
    "STOXX Europe 600 EUR NR": (fetch_onvista_stoxx, "onvista"),
    "Raiffeisen Winterthur Hypothek 1 Jahr Zinssatz": (
        _make_raiffeisen_rate_fetcher("Raiffeisen Winterthur Hypothek 1 Jahr Zinssatz"), "RB Winterthur"),
    "Raiffeisen Winterthur Hypothek 5 Jahr Zinssatz": (
        _make_raiffeisen_rate_fetcher("Raiffeisen Winterthur Hypothek 5 Jahr Zinssatz"), "RB Winterthur"),
    "Raiffeisen Winterthur Hypothek 10 Jahr Zinssatz": (
        _make_raiffeisen_rate_fetcher("Raiffeisen Winterthur Hypothek 10 Jahr Zinssatz"), "RB Winterthur"),
    "Raiffeisen Winterthur Hypothek 15 Jahr Zinssatz": (
        _make_raiffeisen_rate_fetcher("Raiffeisen Winterthur Hypothek 15 Jahr Zinssatz"), "RB Winterthur"),
    "Raiffeisen Futura II - Systematic Invest Equity (Vorsorge)": (
        _make_raiffeisen_futura_fetcher("114426954"), "Raiffeisen Börse"),
    "Raiffeisen Futura II - Systematic Invest Equity B (Samantha)": (
        _make_raiffeisen_futura_fetcher("114426952"), "Raiffeisen Börse"),
    "Gold Vreneli (CHF 20)": (fetch_raiffeisen_vreneli_ankauf, "Raiffeisen Börse"),
}

# ---------------------------------------------------------------------------
# Registry (per SecurityID statt Name): für Securities, bei denen der Name
# in security_master.csv sich ändern könnte oder wo eine exakte Namens-
# Übereinstimmung nicht garantiert werden soll. Wird VOR der namens-basierten
# FETCHERS-Registry geprüft.
# ---------------------------------------------------------------------------

FETCHERS_BY_ID = {
    "33": (
        _make_ishares_nav_fetcher(
            "https://www.ishares.com/ch/individual/en/products/253716/ishares-ftse-100-ucits-etf-acc-fund/"
            "1535604580403.ajax?fileType=xls&fileName=iShares-Core-FTSE-100-UCITS-ETF-GBP-Acc_fund&dataType=fund"
        ),
        "iShares (NAV)",
    ),
}


def run():
    master = read_master()
    active = [r for r in master if r.get("DataCollector") == "Collector_Other"]
    print(f"{len(active)} Securities mit Flag 'Collector_Other' gefunden.")

    now_str = now_zurich_str()
    new_rows = []
    errors = 0

    for row in active:
        name = row["SecurityName"]
        sec_id = row["SecurityID"]
        # SecurityID-Lookup hat Vorrang: kein Risiko, dass eine spätere
        # Umbenennung in security_master.csv den Fetcher stillschweigend
        # "verwaist" (die namens-basierte FETCHERS-Registry bräuchte sonst
        # eine exakte String-Übereinstimmung).
        entry = FETCHERS_BY_ID.get(sec_id) or FETCHERS.get(name)
        if not entry:
            print(f"[WARN] Keine Fetch-Funktion registriert für '{name}' (SecurityID {sec_id}) - bitte in collect_other.py ergänzen.")
            errors += 1
            continue
        fetch_fn, source_label = entry
        try:
            price, _currency = fetch_fn()
            new_rows.append({
                "SecurityID": sec_id, "SecurityName": name, "Price": round(price, 5),
                "PriceDate": now_str, "Source": source_label, "Created_at": now_str,
            })
            print(f"[OK] {name}: {price}")
        except Exception as e:
            print(f"[ERROR] {name}: {e}")
            errors += 1

    if new_rows:
        write_pending_rows(new_rows)
        print(f"{len(new_rows)} neue Preiszeile(n) für den Commit vorbereitet.")
    if errors:
        print(f"{errors} Quelle(n) konnten nicht abgerufen werden.")


if __name__ == "__main__":
    run()
