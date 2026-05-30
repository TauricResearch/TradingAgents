#!/bin/bash
# Hook: block server kill/restart if analysis jobs are active.
# Receives tool input JSON on stdin.

INPUT=$(cat)
CMD=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('command',''))" 2>/dev/null)

# Only care about commands that would kill or restart uvicorn
if ! echo "$CMD" | grep -qE "kill.*8000|kill.*uvicorn|lsof.*8000|pkill.*uvicorn"; then
  exit 0
fi

# Check for active jobs
JOBS=$(curl -s --max-time 3 http://localhost:8000/api/jobs 2>/dev/null)
COUNT=$(echo "$JOBS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count',0))" 2>/dev/null)

if [ "$COUNT" -gt 0 ] 2>/dev/null; then
  echo "BLOCKED: $COUNT active analysis job(s) running. Wait for them to finish before restarting the server." >&2
  echo "Active jobs: $JOBS" >&2
  exit 1
fi

exit 0
