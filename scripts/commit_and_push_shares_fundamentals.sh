# commit_and_push_shares_fundamentals.sh
#
# Hängt die in collect_shares_fundamentals.py ermittelten Zeilen an
# data/security_shares_fundamentals.csv an. Retry-Pattern identisch zu
# commit_and_push_prices.sh: bei einem zeitgleichen Push eines anderen
# Collectors wird auf den frischen origin-Stand zurückgesetzt und die
# Pending-Zeilen erneut angehängt - dadurch nie ein Merge-Konflikt.

set -euo pipefail

MAX_RETRIES=8
BRANCH="${GITHUB_REF_NAME:-main}"
PENDING_PATH="${RUNNER_TEMP:-/tmp}/pending_shares_fundamentals.csv"
PENDING_LOG_PATH="${RUNNER_TEMP:-/tmp}/pending_collector_run.csv"
DATA_PATH="data/security_shares_fundamentals.csv"
RUN_LOG_PATH="data/collector_runs.csv"
COMMIT_MSG="${1:-Shares Fundamentals Collector: Update}"

git config user.name "securitydatacollector-bot"
git config user.email "actions@users.noreply.github.com"

if [ ! -f "$PENDING_PATH" ]; then
  echo "Keine Pending-Datei gefunden ($PENDING_PATH) - nichts zu committen."
  exit 0
fi

for attempt in $(seq 1 "$MAX_RETRIES"); do
  echo "Versuch $attempt/$MAX_RETRIES: hole aktuellen Stand von origin/$BRANCH..."
  git fetch origin "$BRANCH"
  git reset --hard "origin/$BRANCH"

  if [ ! -f "$DATA_PATH" ]; then
    head -n 1 "$PENDING_PATH" > "$DATA_PATH"
  fi
  tail -n +2 "$PENDING_PATH" >> "$DATA_PATH"

  if [ -s "$PENDING_LOG_PATH" ]; then
    if [ ! -f "$RUN_LOG_PATH" ]; then
      head -n 1 "$PENDING_LOG_PATH" > "$RUN_LOG_PATH"
    fi
    tail -n +2 "$PENDING_LOG_PATH" >> "$RUN_LOG_PATH"
  fi

  git add "$DATA_PATH"
  [ -f "$RUN_LOG_PATH" ] && git add "$RUN_LOG_PATH"
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
  echo "Push abgelehnt - retry in ${wait_s}s..."
  sleep "$wait_s"
done

echo "Push nach $MAX_RETRIES Versuchen fehlgeschlagen." >&2
exit 1
