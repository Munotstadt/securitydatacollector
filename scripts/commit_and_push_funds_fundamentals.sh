# commit_and_push_funds_fundamentals.sh
#
# Hängt die in collect_funds_fundamentals.py ermittelten Zeilen an
# data/security_funds_fundamentals.csv UND data/security_fund_holdings.csv
# an (beide zusammen in einem Commit, damit sie nie auseinanderlaufen).
# Retry-Pattern identisch zu commit_and_push_prices.sh.

set -euo pipefail

MAX_RETRIES=8
BRANCH="${GITHUB_REF_NAME:-main}"
PENDING_FUND_PATH="${RUNNER_TEMP:-/tmp}/pending_funds_fundamentals.csv"
PENDING_HOLDINGS_PATH="${RUNNER_TEMP:-/tmp}/pending_fund_holdings.csv"
FUND_DATA_PATH="data/security_funds_fundamentals.csv"
HOLDINGS_DATA_PATH="data/security_fund_holdings.csv"
COMMIT_MSG="${1:-Funds Fundamentals Collector: Update}"

git config user.name "securitydatacollector-bot"
git config user.email "actions@users.noreply.github.com"

if [ ! -f "$PENDING_FUND_PATH" ] && [ ! -f "$PENDING_HOLDINGS_PATH" ]; then
  echo "Keine Pending-Dateien gefunden - nichts zu committen."
  exit 0
fi

for attempt in $(seq 1 "$MAX_RETRIES"); do
  echo "Versuch $attempt/$MAX_RETRIES: hole aktuellen Stand von origin/$BRANCH..."
  git fetch origin "$BRANCH"
  git reset --hard "origin/$BRANCH"

  if [ -f "$PENDING_FUND_PATH" ]; then
    if [ ! -f "$FUND_DATA_PATH" ]; then
      head -n 1 "$PENDING_FUND_PATH" > "$FUND_DATA_PATH"
    fi
    tail -n +2 "$PENDING_FUND_PATH" >> "$FUND_DATA_PATH"
    git add "$FUND_DATA_PATH"
  fi

  if [ -f "$PENDING_HOLDINGS_PATH" ]; then
    if [ ! -f "$HOLDINGS_DATA_PATH" ]; then
      head -n 1 "$PENDING_HOLDINGS_PATH" > "$HOLDINGS_DATA_PATH"
    fi
    tail -n +2 "$PENDING_HOLDINGS_PATH" >> "$HOLDINGS_DATA_PATH"
    git add "$HOLDINGS_DATA_PATH"
  fi

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
