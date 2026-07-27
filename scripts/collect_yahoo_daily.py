"""Collector_YahooDaily: läuft Mo-So 02:00-22:00 UTC alle 30 Minuten (siehe Workflow)."""
from collect_yahoo_common import run_collector

if __name__ == "__main__":
    run_collector("Collector_YahooDaily", "Yahoo Finance (Daily)")
