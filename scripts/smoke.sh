#!/bin/sh
# Copyright 2026 Tauric Research
# SPDX-License-Identifier: Apache-2.0
# Checks a built executable as CI and the release workflow run it: sh scripts/smoke.sh <executable> <scratch dir>
#
# - it carries React's production build;
# - it prints its version and help, and answers one question (-p) from an OpenAI-compatible server, here a
#   stub this script starts with Node;
# - it reads no .env or bunfig.toml where it runs (a loaded .env would turn sync on; a loaded bunfig.toml
#   would print first).
set -eu
bin=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
scratch=$2
mkdir -p "$scratch"

if grep -aq _debugStack "$bin"; then
	echo "the executable carries React's development build" >&2
	exit 1
fi

"$bin" --version | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+'
"$bin" --help | grep -q 'tradingagents -p'

# A server that answers every chat request with one fixed sentence, streamed as chat completions are.
rm -f "$scratch/port"
node -e '
const reply = (res, chunk) => res.write(`data: ${JSON.stringify({ id: "s", object: "chat.completion.chunk", created: 0, model: "stub", ...chunk })}\n\n`);
const server = require("node:http").createServer((req, res) => {
  req.resume();
  req.on("end", () => {
    if (req.method === "GET") return res.end(JSON.stringify({ object: "list", data: [{ id: "stub", object: "model" }] }));
    res.writeHead(200, { "content-type": "text/event-stream" });
    reply(res, { choices: [{ index: 0, delta: { role: "assistant", content: "The smoke answer." }, finish_reason: null }] });
    reply(res, { choices: [{ index: 0, delta: {}, finish_reason: "stop" }], usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 } });
    res.end("data: [DONE]\n\n");
  });
});
server.listen(0, "127.0.0.1", () => require("node:fs").writeFileSync(process.argv[1], String(server.address().port)));
' "$scratch/port" &
stub=$!
trap 'kill "$stub" 2>/dev/null || true' EXIT
for _ in 1 2 3 4 5 6 7 8 9 10; do [ -s "$scratch/port" ] && break; sleep 1; done
answer=$(TRADINGAGENTS_HOME="$scratch/home" TRADINGAGENTS_BASE_URL="http://127.0.0.1:$(cat "$scratch/port")/v1" \
	TRADINGAGENTS_MODEL=stub TRADINGAGENTS_SYNC=off TRADINGAGENTS_NO_UPDATE_CHECK=1 "$bin" -p "Say the smoke answer.")
case $answer in
*"The smoke answer."*) ;;
*)
	printf '%s\n' "$answer" >&2
	exit 1
	;;
esac

dir="$scratch/cwd"
mkdir -p "$dir"
cd "$dir"
echo TRADINGAGENTS_SYNC=on >.env
echo 'preload = ["./preload.js"]' >bunfig.toml
echo 'console.log("preloaded")' >preload.js
out=$(TRADINGAGENTS_HOME="$dir/home" "$bin" sync status)
case $out in
"Sync is not set"*) ;;
*)
	printf '%s\n' "$out" >&2
	exit 1
	;;
esac
echo "smoke: $bin"
