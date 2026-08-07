#!/usr/bin/env bash
# Inspect or conditionally release a stale collector deployment lock. This is a
# recovery tool only: reconcile Fly and prove no deployment can still complete
# before supplying the exact remote owner SHA to `release`.

set +x
set -Eeuo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

mode=${1:-}
app=${2:-tradagent}
expected_owner=${3:-}
if [[ $mode == inspect ]]; then
  if (( $# > 2 )); then
    echo "usage: scripts/unlock_collector_deploy.sh inspect [app]" >&2
    exit 64
  fi
elif [[ $mode == release ]]; then
  if (( $# != 3 )) || ! [[ $expected_owner =~ ^[0-9a-f]{40}$ ]]; then
    echo "usage: scripts/unlock_collector_deploy.sh release [app] <exact-owner-sha>" >&2
    exit 64
  fi
else
  echo "usage: scripts/unlock_collector_deploy.sh {inspect [app]|release [app] <exact-owner-sha>}" >&2
  exit 64
fi

configured_app=$(awk -F '"' '/^app[[:space:]]*=[[:space:]]*"/ { print $2; exit }' fly.toml)
if [[ -z $configured_app || $app != "$configured_app" ]] \
  || ! [[ $app =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
  echo "collector unlock target must exactly match fly.toml app" >&2
  exit 64
fi
for command_name in git ps tr; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "collector unlock requires $command_name" >&2
    exit 69
  fi
done

safe_git_transport() {
  GIT_TERMINAL_PROMPT=0 \
  GIT_TRACE=0 \
  GIT_TRACE_PACK_ACCESS=0 \
  GIT_TRACE_PACKET=0 \
  GIT_TRACE_PERFORMANCE=0 \
  GIT_TRACE_SETUP=0 \
  GIT_TRACE_SHALLOW=0 \
  GIT_TRACE_CURL=0 \
  GIT_CURL_VERBOSE=0 \
  GIT_TRACE2=0 \
  GIT_TRACE2_EVENT=0 \
  GIT_TRACE2_PERF=0 \
  GIT_TRACE_REDACT=1 \
  GIT_HTTP_LOW_SPEED_LIMIT=1 \
  GIT_HTTP_LOW_SPEED_TIME=30 \
    git "$@"
}

lock_remote=${COLLECTOR_DEPLOY_LOCK_REMOTE:-fork}
lock_repository_identity=github.com/clarkipeng/tradingagents
lock_ref="refs/heads/tradingagents-deploy-lock/${app}"
lock_transport=
lock_dir="${TMPDIR:-/tmp}/tradingagents-${app}.deploy.lock"
local_lock_present=false
local_lock_pid=
local_lock_revision=

resolve_lock_transport() {
  local remote_url identity owner repo
  if ! [[ $lock_remote =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] \
    || ! remote_url=$(safe_git_transport remote get-url --push --all \
      "$lock_remote" 2>/dev/null) \
    || [[ -z $remote_url || $remote_url == *$'\n'* ]]; then
    echo "collector unlock remote is unavailable or has multiple push URLs" >&2
    return 1
  fi
  if [[ $remote_url =~ ^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$ ]]; then
    owner=${BASH_REMATCH[1]}
    repo=${BASH_REMATCH[2]%.git}
  elif [[ $remote_url =~ ^git@github\.com:([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$ ]]; then
    owner=${BASH_REMATCH[1]}
    repo=${BASH_REMATCH[2]%.git}
  elif [[ $remote_url =~ ^ssh://git@github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$ ]]; then
    owner=${BASH_REMATCH[1]}
    repo=${BASH_REMATCH[2]%.git}
  else
    echo "collector unlock remote is not the reviewed credential-free GitHub repository" >&2
    return 1
  fi
  identity=$(printf 'github.com/%s/%s' "$owner" "$repo" | \
    LC_ALL=C tr '[:upper:]' '[:lower:]')
  if [[ $identity != "$lock_repository_identity" ]]; then
    echo "collector unlock remote resolves to the wrong repository" >&2
    return 1
  fi
  lock_transport=$remote_url
}

read_remote_lock() {
  local output sha observed_ref extra
  if ! output=$(safe_git_transport ls-remote --refs \
    "$lock_transport" "$lock_ref" 2>/dev/null); then
    return 1
  fi
  if [[ -z $output ]]; then
    printf '%s\n' absent
    return 0
  fi
  [[ $output != *$'\n'* ]] || return 1
  IFS=$'\t' read -r sha observed_ref extra <<< "$output"
  [[ $sha =~ ^[0-9a-f]{40}$ \
    && $observed_ref == "$lock_ref" \
    && $output == "${sha}"$'\t'"${observed_ref}" \
    && -z ${extra:-} ]] || return 1
  printf '%s\n' "$sha"
}

inspect_local_lock() {
  local owner_file owner_record
  local -a entries
  [[ -e $lock_dir ]] || return 0
  if [[ ! -d $lock_dir || -L $lock_dir ]]; then
    echo "local collector lock is not a safe directory" >&2
    return 1
  fi
  owner_file="$lock_dir/owner"
  shopt -s nullglob dotglob
  entries=("$lock_dir"/*)
  shopt -u nullglob dotglob
  if (( ${#entries[@]} != 1 )) \
    || [[ ${entries[0]} != "$owner_file" || ! -f $owner_file || -L $owner_file ]]; then
    echo "local collector lock contents are ambiguous" >&2
    return 1
  fi
  owner_record=$(<"$owner_file")
  if [[ $owner_record == *$'\n'* ]] \
    || ! [[ $owner_record =~ ^pid=([1-9][0-9]*)\ revision=([0-9a-f]{40})$ ]]; then
    echo "local collector lock owner is malformed" >&2
    return 1
  fi
  local_lock_present=true
  local_lock_pid=${BASH_REMATCH[1]}
  local_lock_revision=${BASH_REMATCH[2]}
}

local_owner_is_alive() {
  [[ $local_lock_present == true ]] || return 1
  kill -0 "$local_lock_pid" >/dev/null 2>&1 \
    || ps -p "$local_lock_pid" -o pid= >/dev/null 2>&1
}

remove_dead_local_lock() {
  [[ $local_lock_present == true ]] || return 0
  if local_owner_is_alive; then
    echo "local collector lock owner PID is still alive; refusing release" >&2
    return 1
  fi
  if ! rm -- "$lock_dir/owner" || ! rmdir -- "$lock_dir"; then
    echo "remote lock was reconciled, but dead local lock cleanup failed" >&2
    return 1
  fi
  local_lock_present=false
}

resolve_lock_transport || exit 69
inspect_local_lock || exit 75
if ! observed=$(read_remote_lock); then
  echo "collector remote lock state is unreadable or malformed" >&2
  exit 75
fi

if [[ $mode == inspect ]]; then
  if [[ $observed == absent ]]; then
    echo "collector remote deploy lock is absent"
  else
    echo "collector remote deploy lock owner: ${observed}"
  fi
  if [[ $local_lock_present == true ]]; then
    echo "collector local deploy lock owner: pid=${local_lock_pid} revision=${local_lock_revision}"
  else
    echo "collector local deploy lock is absent"
  fi
  exit 0
fi

if local_owner_is_alive; then
  echo "local collector lock owner PID is still alive; refusing release" >&2
  exit 75
fi
if [[ $observed == absent ]]; then
  if ! remove_dead_local_lock; then
    exit 75
  fi
  echo "collector remote deploy lock was already absent; dead local lock reconciled"
  exit 0
fi
if [[ $observed != "$expected_owner" ]]; then
  echo "collector remote deploy lock owner changed; refusing release" >&2
  exit 75
fi

safe_git_transport push --no-verify \
  --force-with-lease="${lock_ref}:${expected_owner}" \
  "$lock_transport" ":${lock_ref}" >/dev/null 2>&1 || true
if ! after=$(read_remote_lock); then
  echo "collector remote lock release is ambiguous; preserve local lock" >&2
  exit 75
fi
if [[ $after == "$expected_owner" ]]; then
  echo "collector remote deploy lock was not released" >&2
  exit 75
fi
if ! remove_dead_local_lock; then
  exit 75
fi
if [[ $after == absent ]]; then
  echo "collector stale deploy lock released"
  exit 0
fi
echo "prior stale lock is gone, but a newer remote owner is active" >&2
exit 75
