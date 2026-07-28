#!/usr/bin/env bash
# commit_and_push_prices.sh <commit-message>
#
# Hängt die in $PENDING_PATH (Default: $RUNNER_TEMP/pending_prices.csv,
# von collect_yahoo_common.write_pending_rows geschrieben) stehenden neuen
# Preiszeilen an data/security_prices.csv an und pusht.
#
# Warum keine "git pull --rebase"-Logik mehr? Bei mehreren zeitgleich
# laufenden Collector-Workflows (Weekday/Daily/Other), die alle dieselbe
# Datei anhängen, führt ein Rebase bei einem parallelen Schreibzugriff
# regelmässig zu einem echten Merge-Konflikt (zwei Commits hängen je eine
# Zeile ans Dateiende an) - das kann git nicht automatisch auflösen.
#
# Stattdessen: bei einem abgelehnten Push wird einfach hart auf den
# aktuellen origin-Stand zurückgesetzt und die (immer gleichen) neuen
# Zeilen erneut angehängt. Das kann nie einen Konflikt erzeugen, weil
# jeder Versuch von einem sauberen, aktuellen Stand ausgeht.

set -euo pipefail

COMMIT_MSG="${1:?Usage: commit_and_push_prices.sh <commit-message>}"
PENDING_PATH="${PENDING_PATH:-${RUNNER_TEMP:-/tmp}/pending_prices.csv}"
PRICES_PATH="data/security_prices.csv"
MAX_RETRIES=8
BRANCH="${GITHUB_REF_NAME:-main}"

if [ ! -s "$PENDING_PATH" ]; then
  echo "Keine neuen Preise vorhanden (pending file leer/fehlt) - nichts zu committen."
  exit 0
fi

git config user.name "securitydatacollector-bot"
git config user.email "actions@users.noreply.github.com"

for attempt in $(seq 1 "$MAX_RETRIES"); do
  echo "Versuch $attempt/$MAX_RETRIES: hole aktuellen Stand von origin/$BRANCH..."
  git fetch origin "$BRANCH"
  git reset --hard "origin/$BRANCH"

  # Pending-Zeilen (ohne Header) an die frisch geholte CSV anhängen.
  tail -n +2 "$PENDING_PATH" >> "$PRICES_PATH"

  # Pre-Aggregat neu generieren, damit dashboard.html/portfolio.html nicht
  # mehr die komplette CSV laden müssen (siehe generate_latest_prices.py).
  python scripts/generate_latest_prices.py

  git add "$PRICES_PATH" data/latest_prices.json
  if git diff --cached --quiet; then
    echo "Keine Änderungen nach dem Anhängen - fertig."
    exit 0
  fi
  git commit -q -m "$COMMIT_MSG"

  if git push origin "HEAD:$BRANCH"; then
    echo "Push erfolgreich (Versuch $attempt)."
    exit 0
  fi

  wait_s=$((attempt * 3))
  echo "Push abgelehnt (vermutlich zeitgleicher Collector-Lauf) - retry in ${wait_s}s..."
  sleep "$wait_s"
done

echo "Push nach $MAX_RETRIES Versuchen fehlgeschlagen." >&2
exit 1
