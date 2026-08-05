"""Collector_YahooDaily: läuft Mo-So 02:00-22:00 UTC alle 30 Minuten (siehe Workflow)."""
from collect_yahoo_common import run_collector
from run_log import write_pending_log

if __name__ == "__main__":
    added, errors = run_collector("Collector_YahooDaily", "Yahoo Finance (Daily)")
    status = "OK" if errors == 0 else "ERROR"
    detail = f"{errors} security(ies) failed" if errors else ""
    write_pending_log("Yahoo Daily", status, added, detail)
