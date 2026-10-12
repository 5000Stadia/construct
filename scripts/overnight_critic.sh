#!/bin/bash
# Founder-directed overnight live critic runs (2026-07-09). SERIAL (Codex rate
# limit = one consumer). Each run: a critic-primed agent plays a world, files
# /feedback to dev_inbox on anything less than exceptional live fiction. Uses a
# separate 'critic' slot — never touches the real players' saves. One failure
# never stops the chain.
cd "${CONSTRUCT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
export PYTHONPATH=.
run() {
  echo "=== $(date '+%H:%M:%S') START $1 ($2) ==="
  timeout 1800 .venv/bin/python scripts/critic_harness.py "$1" "$2" \
    >> logs/overnight-critic.log 2>&1 || echo "=== $1 ($2) ended: exit $? ==="
  echo "=== $(date '+%H:%M:%S') DONE $1 ==="
  sleep 20   # let the Codex budget breathe between runs
}
echo "###### OVERNIGHT CRITIC CAMPAIGN $(date) ######" >> logs/overnight-critic.log
# priority: the live worlds (newest features + highest fidelity scores), then the
# flagship regression, then the other shipped worlds. Live worlds are named by player
# ids, so they come from CONSTRUCT_LIVE_WORLDS (space-separated), never from source.
for w in ${CONSTRUCT_LIVE_WORLDS:-}; do
  run "$w" standard
done
run bodycase offpath                      # flagship regression + adversarial off-path
run thedeep standard                      # survival (severity 11)
run emberroad standard                    # the fragmentation exemplar
echo "###### CAMPAIGN COMPLETE $(date) ######" >> logs/overnight-critic.log
