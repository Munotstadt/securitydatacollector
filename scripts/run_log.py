"""
Kleiner Helper, den jeder Collector am Ende seines Laufs aufruft, um einen
Eintrag für data/collector_runs.csv vorzubereiten (Pending-Datei, analog zum
Muster der übrigen Collector-Skripte). admin.html liest diese Datei und
zeigt pro Collector-Typ die letzten 5 Läufe inkl. Status (OK/ERROR) und
Anzahl neuer/gelöschter Datenpunkte.

Wächst NICHT unbegrenzt: der wöchentliche Cleanup-Job
(cleanup_old_prices.py) kürzt data/collector_runs.csv jede Woche auf die
letzten TRIM_KEEP_PER_TYPE Einträge PRO Collector-Typ (siehe dort).
"""

import csv
import os
from datetime import datetime
from zoneinfo import ZoneInfo

ZURICH = ZoneInfo("Europe/Zurich")
LOG_HEADER = ["CollectorType", "RunAt", "Status", "DataPoints", "Detail"]
PENDING_LOG_PATH = os.path.join(
    os.environ.get("RUNNER_TEMP", "/tmp"), "pending_collector_run.csv"
)


def now_zurich_str():
    return datetime.now(ZURICH).strftime("%d.%m.%Y %H:%M:%S")


def write_pending_log(collector_type, status, data_points, detail=""):
    """Schreibt EINE Pending-Zeile (Header + 1 Datenzeile). Das jeweilige
    commit_and_push-Skript hängt diese Zeile zusammen mit den eigentlichen
    Collector-Daten an data/collector_runs.csv an."""
    with open(PENDING_LOG_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(LOG_HEADER)
        writer.writerow([collector_type, now_zurich_str(), status, data_points, detail])
