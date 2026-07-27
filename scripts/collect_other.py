"""
Collector_Other: für Securities, die im Master mit DataCollector='Collector_Other'
geflaggt sind und deren Kurs nicht über Yahoo Finance bezogen werden kann
(z.B. SNB-Zinssätze, Bank-APIs, HTML-Scraping-Quellen).

Da diese Quellen sehr heterogen sind (unterschiedliche APIs/Formate je Security),
wird hier - analog zum bestehenden collect_others_prices.py Vorbild - pro
SecurityName eine eigene Fetch-Funktion registriert. Neue "Other"-Securities
im Master brauchen zusätzlich einen Eintrag in FETCHERS unten.

Läuft mit derselben Cadence wie der Weekday-Collector (siehe Workflow).
"""

import re
import urllib.request

from collect_yahoo_common import write_pending_rows, now_zurich_str, read_master

# ---------------------------------------------------------------------------
# Registry: SecurityName -> Funktion, die (price, currency_or_None) zurückgibt
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


# Beispiel-Registry - bei Bedarf um weitere Quellen ergänzen (Raiffeisen API,
# onvista, HTML-Scraping etc., siehe bestehendes collect_others_prices.py als Vorbild).
FETCHERS = {
    "Rendite Bundesobligationen Eidgenossenschaft 10 Jahre (%)": (fetch_snb_r10, "SNB"),
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
        entry = FETCHERS.get(name)
        if not entry:
            print(f"[WARN] Keine Fetch-Funktion registriert für '{name}' - bitte in collect_other.py ergänzen.")
            errors += 1
            continue
        fetch_fn, source_label = entry
        try:
            price, _currency = fetch_fn()
            new_rows.append({
                "SecurityID": sec_id, "SecurityName": name, "Price": price,
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
