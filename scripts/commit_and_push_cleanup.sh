#!/usr/bin/env bash
# commit_and_push_cleanup.sh
#
# Führt scripts/cleanup_old_prices.py aus und pusht das Ergebnis. Bei einem
# abgelehnten Push (paralleler Collector-Lauf hat zwischenzeitlich neue
# Zeilen angehängt) wird auf den aktuellen origin-Stand zurückgesetzt und
# der Cleanup deterministisch neu berechnet (die 380-Tage-Grenze ändert
# sich innerhalb weniger Sekunden praktisch nicht) - dadurch nie ein
# Merge-Konflikt.

set -euo pipefail

MAX_RETRIES=5
BRANCH="${GITHUB_REF_NAME:-main}"

git config user.name "securitydatacollector-bot"
git config user.email "actions@users.noreply.github.com"

for attempt in $(seq 1 "$MAX_RETRIES"); do
  echo "Versuch $attempt/$MAX_RETRIES: hole aktuellen Stand von origin/$BRANCH..."
  git fetch origin "$BRANCH"
  git reset --hard "origin/$BRANCH"

  python scripts/cleanup_old_prices.py

  git add data/security_prices.csv
  if git diff --cached --quiet; then
    echo "Keine Änderungen - fertig."
    exit 0
  fi
  git commit -q -m "Weekly Cleanup: Preise >380 Tage entfernt $(date -u +'%Y-%m-%d')"

  if git push origin "HEAD:$BRANCH"; then
    echo "Push erfolgreich (Versuch $attempt)."
    exit 0
  fi

  wait_s=$((attempt * 3))
  echo "Push abgelehnt - retry in ${wait_s}s..."
  sleep "$wait_s"
done

echo "Push nach $MAX_RETRIES Versuchen fehlgeschlagen." >&2
exit 1
