#!/usr/bin/env bash
# Deploy one reviewed collector commit as a transaction. The prior image and
# deployed Fly configuration are captured together before any remote mutation.

# Never allow caller/inherited xtrace to render Fly tokens or command arguments.
set +x
set -Eeuo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

app=${1:-tradagent}
if (( $# > 1 )); then
  echo "usage: scripts/deploy_collector.sh [app]" >&2
  exit 64
fi

configured_app=$(awk -F '"' '/^app[[:space:]]*=[[:space:]]*"/ { print $2; exit }' fly.toml)
if [[ -z $configured_app || $app != "$configured_app" ]]; then
  echo "collector deploy target must exactly match fly.toml app (${configured_app:-missing})" >&2
  exit 64
fi
if ! [[ $app =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
  echo "collector Fly app name is invalid" >&2
  exit 64
fi

timeout_seconds=${COLLECTOR_HEALTH_TIMEOUT_SECONDS:-600}
poll_seconds=${COLLECTOR_HEALTH_POLL_SECONDS:-15}
rollback_timeout_seconds=${COLLECTOR_ROLLBACK_TIMEOUT_SECONDS:-90}
for value_name in timeout_seconds poll_seconds rollback_timeout_seconds; do
  value=${!value_name}
  if ! [[ $value =~ ^[0-9]+$ ]] || (( value < 1 )); then
    echo "$value_name must be a positive integer" >&2
    exit 64
  fi
done
if (( rollback_timeout_seconds < 3 )); then
  echo "COLLECTOR_ROLLBACK_TIMEOUT_SECONDS must be at least 3" >&2
  exit 64
fi

allow_unmerged=${COLLECTOR_DEPLOY_ALLOW_UNMERGED:-false}
case $allow_unmerged in
  1|true|TRUE|yes|YES|on|ON) allow_unmerged=true ;;
  0|false|FALSE|no|NO|off|OFF) allow_unmerged=false ;;
  *)
    echo "COLLECTOR_DEPLOY_ALLOW_UNMERGED must be an explicit boolean" >&2
    exit 64
    ;;
esac

allow_unhealthy_baseline=${COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE:-false}
case $allow_unhealthy_baseline in
  1|true|TRUE|yes|YES|on|ON) allow_unhealthy_baseline=true ;;
  0|false|FALSE|no|NO|off|OFF) allow_unhealthy_baseline=false ;;
  *)
    echo "COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE must be an explicit boolean" >&2
    exit 64
    ;;
esac

for command_name in fly git python3; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "collector deploy requires $command_name" >&2
    exit 69
  fi
done
if [[ -n $(git status --porcelain) ]]; then
  echo "collector deploy requires a clean committed worktree" >&2
  exit 65
fi

revision=$(git rev-parse --verify HEAD)
if ! [[ $revision =~ ^[0-9a-f]{40}$ ]]; then
  echo "collector deploy requires a full lowercase Git revision" >&2
  exit 65
fi
target_ref=${COLLECTOR_DEPLOY_TARGET_REF:-origin/main}

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

read_exact_remote_ref() {
  local remote=$1
  local ref=$2
  local output sha observed_ref extra
  if ! output=$(safe_git_transport ls-remote --exit-code --refs \
    "$remote" "$ref" 2>/dev/null); then
    return 1
  fi
  # One exact ref must produce one exact SHA/ref record. Never forward remote
  # output: transport errors can contain credential-bearing remote URLs.
  [[ -n $output && $output != *$'\n'* ]] || return 1
  IFS=$'\t' read -r sha observed_ref extra <<< "$output"
  [[ $sha =~ ^[0-9a-f]{40}$ \
    && $observed_ref == "$ref" \
    && $output == "${sha}"$'\t'"${observed_ref}" \
    && -z ${extra:-} ]] || return 1
  printf '%s\n' "$sha"
}

read_remote_target_revision() {
  read_exact_remote_ref "$target_remote" "refs/heads/${target_branch}"
}

verify_remote_target() {
  local observed_revision
  if ! observed_revision=$(read_remote_target_revision); then
    echo "collector deploy cannot authenticate and resolve its configured remote branch" >&2
    return 1
  fi
  if [[ $observed_revision != "$revision" ]]; then
    echo "collector deploy requires HEAD to exactly match the configured remote branch" >&2
    return 1
  fi
}

if [[ $allow_unmerged != true ]]; then
  if [[ $target_ref != */* ]]; then
    echo "COLLECTOR_DEPLOY_TARGET_REF must name a configured remote and branch" >&2
    exit 64
  fi
  target_remote=${target_ref%%/*}
  target_branch=${target_ref#*/}
  if ! [[ $target_remote =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] \
    || ! git check-ref-format "refs/heads/${target_branch}" >/dev/null 2>&1; then
    echo "COLLECTOR_DEPLOY_TARGET_REF must name a valid configured remote branch" >&2
    exit 64
  fi
  if ! verify_remote_target; then
    echo "set COLLECTOR_DEPLOY_ALLOW_UNMERGED=true only for an explicitly reviewed exceptional rollout" >&2
    exit 65
  fi
fi

lock_dir="${TMPDIR:-/tmp}/tradingagents-${app}.deploy.lock"
if ! mkdir "$lock_dir" 2>/dev/null; then
  echo "another collector deploy owns ${lock_dir}" >&2
  exit 73
fi
printf '%s\n' "pid=$$ revision=$revision" > "$lock_dir/owner"

temp_dir=
remote_lock_owned=false
preserve_remote_lock=false
remote_lock_release_permitted=true
lock_remote=${COLLECTOR_DEPLOY_LOCK_REMOTE:-fork}
lock_repository_identity=github.com/clarkipeng/tradingagents
lock_transport=
lock_ref="refs/heads/tradingagents-deploy-lock/${app}"
lock_commit=

read_remote_deploy_lock() {
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

release_remote_deploy_lock() {
  local observed after
  [[ $remote_lock_owned == true ]] || return 0
  if [[ $preserve_remote_lock == true \
    || $remote_lock_release_permitted != true ]]; then
    echo "collector remote deploy lock was intentionally preserved for manual reconciliation" >&2
    return 1
  fi
  if ! observed=$(read_remote_deploy_lock); then
    echo "collector remote deploy lock cleanup is ambiguous; manual reconciliation is required" >&2
    return 1
  fi
  if [[ $observed == absent ]]; then
    remote_lock_owned=false
    return 0
  fi
  if [[ $observed != "$lock_commit" ]]; then
    remote_lock_owned=false
    echo "collector remote deploy lock changed owners before cleanup; the newer owner was preserved" >&2
    return 1
  fi
  safe_git_transport push --no-verify \
    --force-with-lease="${lock_ref}:${lock_commit}" \
    "$lock_transport" ":${lock_ref}" >/dev/null 2>&1 || true
  if ! after=$(read_remote_deploy_lock); then
    echo "collector remote deploy lock cleanup is ambiguous; manual reconciliation is required" >&2
    return 1
  fi
  if [[ $after == absent || $after != "$lock_commit" ]]; then
    remote_lock_owned=false
    return 0
  fi
  echo "collector remote deploy lock was not released; remove it only if ${lock_ref} still equals ${lock_commit}" >&2
  return 1
}

cleanup() {
  local cleanup_failed=false
  if ! release_remote_deploy_lock; then
    cleanup_failed=true
  fi
  [[ -z $temp_dir ]] || rm -rf "$temp_dir"
  rm -rf "$lock_dir"
  [[ $cleanup_failed == false ]]
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

temp_dir=$(mktemp -d "${TMPDIR:-/tmp}/tradingagents-deploy.XXXXXX")
previous_config="$temp_dir/fly.previous.toml"
previous_status_before="$temp_dir/status.previous-before.json"
previous_status="$temp_dir/status.previous.json"
current_status="$temp_dir/status.current.json"
current_releases="$temp_dir/releases.current.json"

deploy_invoked=false
deployment_verified=false
rollback_attempted=false
superseded=false
mutation_active=false
mutation_ambiguous=false
mutation_pid=
previous_id=
previous_instance=
previous_image=
previous_digest=
previous_release=
previous_release_version=
previous_rollback_from_version=0
previous_rollback_to_version=0
previous_config_fingerprint=
target_id=
target_instance=
deployment_nonce=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
if ! [[ $deployment_nonce =~ ^[0-9a-f]{32}$ ]]; then
  echo "collector deploy could not create a unique deployment nonce" >&2
  exit 70
fi
target_image="registry.fly.io/${app}:git-${revision}-${deployment_nonce}"
target_digest=
target_release=
target_release_version=
target_rollback_from_version=0
target_rollback_to_version=0
target_config_fingerprint=
legacy_bare_baseline=false
baseline_health_passes=false

validate_runtime_image_identity() {
  local image_ref=$1
  local image_digest=${2:-}
  local expected_revision=${3:-}
  python3 - "$app" "$image_ref" "$image_digest" "$expected_revision" \
    >/dev/null 2>&1 <<'PY'
import re
import sys

from tradingagents.research_protocol import runtime_build_manifest

app, image_ref, image_digest, expected_revision = sys.argv[1:]
if image_digest:
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest) is None:
        raise SystemExit(1)
    if "@" in image_ref:
        if not image_ref.endswith("@" + image_digest):
            raise SystemExit(1)
    else:
        image_ref += "@" + image_digest

tag_ref = image_ref.partition("@")[0]
embedded_revision = ""
marker = ":git-"
if marker in tag_ref:
    embedded_revision = tag_ref.partition(marker)[2][:40]
revision = expected_revision or embedded_revision
env = {
    "FLY_APP_NAME": app,
    "FLY_MACHINE_ID": "deploy-preflight",
    "FLY_IMAGE_REF": image_ref,
}
if revision:
    env["GIT_REVISION"] = revision
manifest = runtime_build_manifest(env)
if (
    manifest is None
    or manifest.get("schema_version") != 1
    or manifest.get("platform") != "fly"
    or manifest.get("app_name") != app
    or manifest.get("image_ref") != image_ref
    or (expected_revision and manifest.get("git_revision") != expected_revision)
):
    raise SystemExit(1)
PY
}

# Keep the deployer's content-addressed image tag and the runtime's authenticated
# build-identity parser in one fail-closed contract. This executes before any Fly
# mutation, so a future tag-format change cannot strand a release command or
# replace the existing worker.
if ! validate_runtime_image_identity "$target_image" "" "$revision"; then
  echo "collector deploy image tag is incompatible with runtime build identity" >&2
  exit 65
fi

if ! validate_runtime_image_identity \
  "$target_image" "sha256:$(printf '0%.0s' {1..64})" "$revision"; then
  echo "collector deploy digest pin is incompatible with runtime build identity" >&2
  exit 65
fi

run_mutating_command() {
  local mutation_status
  mutation_active=true
  "$@" &
  mutation_pid=$!
  if wait "$mutation_pid"; then
    mutation_status=0
  else
    mutation_status=$?
  fi
  mutation_pid=
  mutation_active=false
  return "$mutation_status"
}

verify_remote_deploy_lock() {
  local observed
  [[ $remote_lock_owned == true ]] || return 1
  if ! observed=$(read_remote_deploy_lock); then
    return 1
  fi
  [[ $observed == "$lock_commit" ]]
}

acquire_remote_deploy_lock() {
  local lock_message lock_remote_url lock_identity lock_owner lock_repo
  local empty_tree observed push_status=0 started_at
  if ! [[ $lock_remote =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] \
    || ! git check-ref-format "$lock_ref" >/dev/null 2>&1 \
    || ! lock_remote_url=$(safe_git_transport remote get-url --push --all \
      "$lock_remote" 2>/dev/null) \
    || [[ -z $lock_remote_url || $lock_remote_url == *$'\n'* ]]; then
    echo "COLLECTOR_DEPLOY_LOCK_REMOTE must name the shared writable deployment remote" >&2
    return 64
  fi
  if [[ $lock_remote_url =~ ^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$ ]]; then
    lock_owner=${BASH_REMATCH[1]}
    lock_repo=${BASH_REMATCH[2]%.git}
  elif [[ $lock_remote_url =~ ^git@github\.com:([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$ ]]; then
    lock_owner=${BASH_REMATCH[1]}
    lock_repo=${BASH_REMATCH[2]%.git}
  elif [[ $lock_remote_url =~ ^ssh://git@github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$ ]]; then
    lock_owner=${BASH_REMATCH[1]}
    lock_repo=${BASH_REMATCH[2]%.git}
  else
    echo "collector deploy lock remote URL is not the reviewed credential-free GitHub repository" >&2
    return 64
  fi
  lock_identity=$(printf 'github.com/%s/%s' "$lock_owner" "$lock_repo" | \
    LC_ALL=C tr '[:upper:]' '[:lower:]')
  if [[ $lock_identity != "$lock_repository_identity" ]]; then
    echo "collector deploy lock remote resolves to the wrong repository" >&2
    return 64
  fi
  lock_transport=$lock_remote_url
  if ! observed=$(read_remote_deploy_lock); then
    echo "collector deploy cannot authenticate the remote lock state" >&2
    return 75
  fi
  if [[ $observed != absent ]]; then
    echo "another host owns the collector remote deploy lock; refusing to inspect or mutate Fly" >&2
    return 73
  fi
  if ! empty_tree=$(git mktree </dev/null 2>/dev/null) \
    || ! [[ $empty_tree =~ ^[0-9a-f]{40}$ ]]; then
    echo "collector deploy could not create its remote lock tree" >&2
    return 70
  fi
  started_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  lock_message="schema=v1 app=${app} revision=${revision} nonce=${deployment_nonce} started_at=${started_at}"
  if ! lock_commit=$(printf '%s\n' "$lock_message" | \
    GIT_AUTHOR_NAME=TradingAgents \
    GIT_AUTHOR_EMAIL=deploy-lock@localhost \
    GIT_COMMITTER_NAME=TradingAgents \
    GIT_COMMITTER_EMAIL=deploy-lock@localhost \
    git commit-tree "$empty_tree" 2>/dev/null); then
    echo "collector deploy could not create its remote lock object" >&2
    return 70
  fi
  if ! [[ $lock_commit =~ ^[0-9a-f]{40}$ ]]; then
    echo "collector deploy created a malformed remote lock object" >&2
    return 70
  fi
  # A parentless commit with a random nonce cannot fast-forward an existing lock.
  # The non-forced create is therefore an atomic acquire on the Git server.
  safe_git_transport push --no-verify "$lock_transport" \
    "${lock_commit}:${lock_ref}" >/dev/null 2>&1 || push_status=$?
  if ! observed=$(read_remote_deploy_lock); then
    echo "collector remote deploy lock acquisition is ambiguous; inspect the remote ref before retrying" >&2
    return 75
  fi
  if [[ $observed == absent ]]; then
    echo "collector remote deploy lock was not acquired; refusing to inspect or mutate Fly" >&2
    return 75
  fi
  if [[ $observed != "$lock_commit" ]]; then
    echo "another host owns the collector remote deploy lock; refusing to inspect or mutate Fly" >&2
    return 73
  fi
  remote_lock_owned=true
  if (( push_status != 0 )); then
    echo "collector deploy reconciled an acknowledged remote lock from server state" >&2
  fi
}

run_bounded_command() {
  local command_timeout=$1
  shift
  python3 - "$command_timeout" "$@" <<'PY'
import os
import signal
import subprocess
import sys

try:
    timeout = int(sys.argv[1])
except (TypeError, ValueError):
    raise SystemExit(64)
if timeout < 1 or len(sys.argv) < 3:
    raise SystemExit(64)

process = subprocess.Popen(
    sys.argv[2:],
    stdin=subprocess.DEVNULL,
    start_new_session=True,
)
try:
    status = process.wait(timeout=timeout)
except subprocess.TimeoutExpired:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    raise SystemExit(124)
raise SystemExit(status if status >= 0 else 128 - status)
PY
}

capture_status() {
  local output_file=$1
  fly status -a "$app" --json > "$output_file"
}

capture_status_bounded() {
  local output_file=$1
  local command_timeout=$2
  run_bounded_command "$command_timeout" \
    fly status -a "$app" --json > "$output_file"
}

started_app_machine_summary() {
  local status_file=$1
  python3 - "$status_file" <<'PY'
import hashlib
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)

machines = []
for machine in payload.get("Machines") or []:
    config = machine.get("config") or {}
    metadata = config.get("metadata") or {}
    env = config.get("env") or {}
    process_group = metadata.get("fly_process_group") or env.get("FLY_PROCESS_GROUP")
    if process_group == "app":
        machines.append(machine)
if len(machines) != 1 or machines[0].get("state") != "started":
    raise SystemExit(2)

machine = machines[0]
config = machine.get("config") or {}
metadata = config.get("metadata") or {}
semantic_config = {
    key: value
    for key, value in config.items()
    if key not in {"image", "metadata"}
}
fingerprint = hashlib.sha256(
    json.dumps(semantic_config, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
image_ref = machine.get("image_ref") or {}
rollback_from = metadata.get(
    "tradingagents_fenced_rollback_from_release_version"
) or "0"
rollback_to = metadata.get(
    "tradingagents_fenced_rollback_to_release_version"
) or "0"
if any(
    not isinstance(value, str) or not value.isascii() or not value.isdecimal()
    for value in (rollback_from, rollback_to)
):
    raise SystemExit(2)
fields = (
    machine.get("id") or "",
    machine.get("instance_id") or "",
    config.get("image") or "",
    image_ref.get("digest") or "",
    metadata.get("fly_release_id") or "",
    metadata.get("fly_release_version") or "",
    rollback_from,
    rollback_to,
    fingerprint,
)
if not all(fields):
    raise SystemExit(2)
print("\t".join(fields))
PY
}

read_started_app_machine() {
  local status_file=$1
  local summary
  if ! summary=$(started_app_machine_summary "$status_file"); then
    return 1
  fi
  IFS=$'\t' read -r machine_id machine_instance machine_image machine_digest \
    machine_release machine_release_version machine_rollback_from_version \
    machine_rollback_to_version machine_config_fingerprint <<< "$summary"
}

status_relation() {
  local status_file=$1
  python3 - "$status_file" \
    "$previous_id" "$previous_instance" "$previous_image" "$previous_digest" \
    "$previous_release" "$previous_release_version" \
    "$previous_rollback_from_version" "$previous_rollback_to_version" \
    "$previous_config_fingerprint" \
    "$target_id" "$target_instance" "$target_image" "$target_digest" \
    "$target_release" "$target_release_version" \
    "$target_rollback_from_version" "$target_rollback_to_version" \
    "$target_config_fingerprint" <<'PY'
import hashlib
import json
import sys

(
    path,
    previous_id,
    previous_instance,
    previous_image,
    previous_digest,
    previous_release,
    previous_release_version,
    previous_rollback_from_version,
    previous_rollback_to_version,
    previous_fingerprint,
    target_id,
    target_instance,
    target_image,
    target_digest,
    target_release,
    target_release_version,
    target_rollback_from_version,
    target_rollback_to_version,
    target_fingerprint,
) = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)

machines = []
for machine in payload.get("Machines") or []:
    config = machine.get("config") or {}
    metadata = config.get("metadata") or {}
    env = config.get("env") or {}
    if (metadata.get("fly_process_group") or env.get("FLY_PROCESS_GROUP")) == "app":
        machines.append(machine)

if len(machines) == 1 and machines[0].get("state") == "started":
    machine = machines[0]
    config = machine.get("config") or {}
    semantic_config = {
        key: value for key, value in config.items()
        if key not in {"image", "metadata"}
    }
    fingerprint = hashlib.sha256(
        json.dumps(semantic_config, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    digest = (machine.get("image_ref") or {}).get("digest") or ""
    metadata = config.get("metadata") or {}
    release = metadata.get("fly_release_id") or ""
    identity = (
        machine.get("id") or "",
        machine.get("instance_id") or "",
        config.get("image") or "",
        digest,
        release,
        metadata.get("fly_release_version") or "",
        metadata.get("tradingagents_fenced_rollback_from_release_version") or "0",
        metadata.get("tradingagents_fenced_rollback_to_release_version") or "0",
        fingerprint,
    )
    previous = (
        previous_id,
        previous_instance,
        previous_image,
        previous_digest,
        previous_release,
        previous_release_version,
        previous_rollback_from_version,
        previous_rollback_to_version,
        previous_fingerprint,
    )
    target = (
        target_id,
        target_instance,
        target_image,
        target_digest,
        target_release,
        target_release_version,
        target_rollback_from_version,
        target_rollback_to_version,
        target_fingerprint,
    )
    if all(previous) and identity == previous:
        print("previous")
        raise SystemExit
    if all(target) and identity == target:
        print("owned")
        raise SystemExit

print("superseded")
PY
}

bind_target_from_status() {
  local status_file=$1
  [[ -z $target_release ]] || return 0
  if ! read_started_app_machine "$status_file" \
    || [[ $machine_image != "$target_image" ]]; then
    return 1
  fi
  target_id=$machine_id
  target_instance=$machine_instance
  target_digest=$machine_digest
  target_release=$machine_release
  target_release_version=$machine_release_version
  target_rollback_from_version=$machine_rollback_from_version
  target_rollback_to_version=$machine_rollback_to_version
  target_config_fingerprint=$machine_config_fingerprint
}

bound_target_matches_status() {
  local status_file=$1
  [[ -n $target_id && -n $target_instance && -n $target_digest \
    && -n $target_release \
    && -n $target_release_version \
    && -n $target_config_fingerprint ]] \
    && read_started_app_machine "$status_file" \
    && [[ $machine_id == "$target_id" \
      && $machine_instance == "$target_instance" \
      && $machine_image == "$target_image" \
      && $machine_digest == "$target_digest" \
      && $machine_release == "$target_release" \
      && $machine_release_version == "$target_release_version" \
      && $machine_rollback_from_version == "$target_rollback_from_version" \
      && $machine_rollback_to_version == "$target_rollback_to_version" \
      && $machine_config_fingerprint == "$target_config_fingerprint" ]]
}

candidate_predecessor_is_baseline() {
  [[ $target_release_version =~ ^[1-9][0-9]*$ \
    && $previous_release_version =~ ^[1-9][0-9]*$ ]] || return 1
  if ! fly releases -a "$app" --json > "$current_releases" 2>/dev/null; then
    return 1
  fi
  python3 - "$current_releases" \
    "$target_release_version" "$previous_release_version" \
    "$previous_rollback_from_version" "$previous_rollback_to_version" <<'PY'
import json
import sys

path, target_raw, baseline_raw, rollback_from_raw, rollback_to_raw = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)
if not isinstance(payload, list):
    raise SystemExit(2)

def exact_version(value):
    if isinstance(value, bool):
        raise ValueError
    rendered = str(value)
    if not rendered.isascii() or not rendered.isdecimal() or rendered.startswith("0"):
        raise ValueError
    return int(rendered)

try:
    target = exact_version(target_raw)
    baseline = exact_version(baseline_raw)
    rollback_from = exact_version(rollback_from_raw) if rollback_from_raw != "0" else 0
    rollback_to = exact_version(rollback_to_raw) if rollback_to_raw != "0" else 0
    rows = []
    seen = set()
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError
        version = exact_version(item.get("Version"))
        if version in seen:
            raise ValueError
        seen.add(version)
        status = item.get("Status")
        if not isinstance(status, str):
            raise ValueError
        rows.append((version, status.lower()))
except (TypeError, ValueError):
    raise SystemExit(2)

if target not in seen or baseline >= target:
    raise SystemExit(2)
prior_complete = next(
    (version for version, status in sorted(rows, reverse=True)
     if version < target and status == "complete"),
    None,
)
accepted_predecessors = {baseline}
if rollback_to == baseline and baseline < rollback_from < target:
    accepted_predecessors.add(rollback_from)
raise SystemExit(0 if prior_complete in accepted_predecessors else 2)
PY
}

machine_check_passes() {
  local machine_id=$1
  fly checks list -a "$app" --json 2>/dev/null |
    python3 -c '
import json, sys
machine_id = sys.argv[1]
payload = json.load(sys.stdin)
items = payload.get(machine_id) or []
target = [
    item for item in items
    if (item.get("name") or item.get("Name")) == "collector_health"
]
statuses = {
    str(item.get("status") or item.get("Status") or "").lower()
    for item in target
}
raise SystemExit(0 if target and statuses <= {"passing", "pass"} else 1)
' "$machine_id"
}

target_revision_matches() {
  local machine_id=$1
  fly ssh console -a "$app" --machine "$machine_id" --pty=false \
    -C "grep -Fxq '$revision' /opt/tradingagents/REVISION" >/dev/null
}

target_alert_delivers() {
  local machine_id=$1
  fly ssh console -a "$app" --machine "$machine_id" --pty=false \
    -C "tradingagents-poller --test-alert" >/dev/null
}

legacy_baseline_contract_matches() {
  python3 - "$previous_status" "$previous_id" "$previous_image" \
    "$previous_digest" <<'PY'
import json
import sys

path, expected_id, expected_image, expected_digest = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)
machines = payload.get("Machines") or []
if len(machines) != 1 or not isinstance(machines[0], dict):
    raise SystemExit(1)
machine = machines[0]
config = machine.get("config") or {}
metadata = config.get("metadata") or {}
env = config.get("env") or {}
restart = config.get("restart") or {}
digest = (machine.get("image_ref") or {}).get("digest")
process_group = metadata.get("fly_process_group") or env.get("FLY_PROCESS_GROUP")
max_retries = restart.get("max_retries")
legacy_restart = (
    restart.get("policy") == "on-failure"
    and not isinstance(max_retries, bool)
    and isinstance(max_retries, int)
    and 1 <= max_retries <= 100
)
identity_matches = (
    machine.get("id") == expected_id
    and machine.get("state") == "started"
    and config.get("image") == expected_image
    and digest == expected_digest
)
pre_health_contract = (
    process_group == "app"
    and legacy_restart
    and "MEDIA_HEALTH_PORT" not in env
    and not config.get("checks")
    and not config.get("services")
)
raise SystemExit(0 if identity_matches and pre_health_contract else 1)
PY
}

legacy_baseline_runtime_responds() {
  local command_timeout=${1:-$rollback_timeout_seconds}
  local probe_command
  probe_command='python -c "import os, sys; '
  probe_command+="from tradingagents.research_protocol import build_identity; "
  probe_command+="from tradingagents.dataflows.media_store import open_store; "
  probe_command+="image_ok = os.environ.get('FLY_IMAGE_REF') == '$previous_image'; "
  probe_command+="value = build_identity(); build_ok = value.startswith('build_'); "
  probe_command+="store = open_store(auto_migrate=False); "
  probe_command+="heartbeat = store.get_meta('poller:last_success_utc'); "
  probe_command+="database_ok = store.dialect == 'postgresql' and not isinstance(heartbeat, bool) and isinstance(heartbeat, (int, float)) and heartbeat > 0; "
  probe_command+='store.close(); sys.exit(0 if image_ok and build_ok and database_ok else 1)"'
  run_bounded_command "$command_timeout" \
    fly ssh console -a "$app" --machine "$previous_id" --pty=false \
      -C "$probe_command"
}

legacy_restored_status_matches() {
  [[ $machine_id == "$previous_id" \
    && $machine_instance =~ ^[A-Za-z0-9_-]{8,128}$ \
    && $machine_instance != "$previous_instance" \
    && $machine_instance != "$target_instance" \
    && $machine_image == "$previous_image" \
    && $machine_digest == "$previous_digest" \
    && $machine_release == "$previous_release" \
    && $machine_release_version == "$previous_release_version" \
    && $machine_rollback_from_version == "$target_release_version" \
    && $machine_rollback_to_version == "$previous_release_version" \
    && $machine_config_fingerprint == "$previous_config_fingerprint" ]]
}

verify_rollback() {
  # Reset Bash's monotonic counter here so the configured deadline receives
  # its full interval instead of the remainder of a tick.
  SECONDS=0
  local deadline=$rollback_timeout_seconds
  local legacy_observed=false
  local legacy_instance= remaining sleep_for
  while (( SECONDS < deadline )); do
    remaining=$((deadline - SECONDS))
    if capture_status_bounded "$current_status" "$remaining" 2>/dev/null \
      && read_started_app_machine "$current_status" \
      && [[ $machine_digest == "$previous_digest" ]] \
      && [[ $machine_config_fingerprint == "$previous_config_fingerprint" ]] \
      && (( SECONDS < deadline )); then
      if [[ $legacy_bare_baseline == true ]]; then
        remaining=$((deadline - SECONDS))
        if ! legacy_restored_status_matches \
          || (( remaining < 1 )) \
          || ! legacy_baseline_runtime_responds "$remaining" >/dev/null 2>&1 \
          || (( SECONDS >= deadline )); then
          legacy_observed=false
          legacy_instance=
        elif [[ $legacy_observed == true \
          && $machine_instance == "$legacy_instance" ]]; then
          echo "previous collector image and configuration restored"
          return 0
        else
          legacy_observed=true
          legacy_instance=$machine_instance
        fi
      else
        echo "previous collector image and configuration restored"
        return 0
      fi
    else
      legacy_observed=false
      legacy_instance=
    fi
    remaining=$((deadline - SECONDS))
    (( remaining > 0 )) || break
    sleep_for=$poll_seconds
    (( sleep_for > remaining )) && sleep_for=$remaining
    sleep "$sleep_for"
  done
  echo "rollback command completed, but the previous image/configuration was not restored" >&2
  return 1
}

rollback_if_owned() {
  local fly_api_token
  local -a rollback_command
  [[ $rollback_attempted == false ]] || return 1
  rollback_attempted=true
  if [[ $superseded == true ]]; then
    echo "deployment was superseded; refusing to roll back a newer release" >&2
    return 1
  fi
  if ! verify_remote_deploy_lock; then
    superseded=true
    echo "collector remote deploy lock ownership was lost; refusing an unsafe rollback" >&2
    return 1
  fi
  if ! capture_status "$current_status" 2>/dev/null; then
    echo "cannot inspect the current Fly release; refusing an unsafe rollback" >&2
    return 1
  fi
  # The per-attempt image tag can authenticate a candidate even when fly deploy
  # returned nonzero after creating its Machine. After this binding, ownership
  # always requires the complete Machine/image/digest/release/config tuple.
  bind_target_from_status "$current_status" 2>/dev/null || true
  relation=$(status_relation "$current_status") || relation=unknown
  if [[ $relation == previous ]]; then
    preserve_remote_lock=true
    echo "the previous collector is visible, but the failed mutation may still complete; preserving the remote lock" >&2
    return 1
  fi
  if [[ $relation != owned ]]; then
    echo "deployment was superseded; refusing to roll back a newer release" >&2
    return 1
  fi
  if ! candidate_predecessor_is_baseline; then
    superseded=true
    echo "candidate predecessor is not the saved baseline; refusing an unsafe rollback" >&2
    return 1
  fi

  fly_api_token=${FLY_API_TOKEN:-}
  if [[ -z $fly_api_token ]] \
    && ! fly_api_token=$(fly auth token 2>/dev/null); then
    echo "cannot obtain Fly API authentication for a fenced rollback" >&2
    return 1
  fi
  rollback_command=(python3 \
    scripts/fenced_machine_rollback.py \
    --app "$app" \
    --machine-id "$target_id" \
    --expected-instance "$target_instance" \
    --expected-image "$target_image" \
    --expected-digest "$target_digest" \
    --expected-release "$target_release" \
    --expected-release-version "$target_release_version" \
    --expected-rollback-from-version "$target_rollback_from_version" \
    --expected-rollback-to-version "$target_rollback_to_version" \
    --expected-config-fingerprint "$target_config_fingerprint" \
    --baseline-machine-id "$previous_id" \
    --baseline-instance "$previous_instance" \
    --baseline-image "$previous_image" \
    --baseline-digest "$previous_digest" \
    --baseline-release "$previous_release" \
    --baseline-release-version "$previous_release_version" \
    --baseline-config-fingerprint "$previous_config_fingerprint")
  if [[ $legacy_bare_baseline == true ]]; then
    rollback_command+=(--allow-legacy-baseline-on-failure)
  fi
  rollback_command+=(--previous-status "$previous_status")
  echo "restoring the previous collector image/config under an exclusive Machine lease" >&2
  if ! FLY_API_TOKEN="$fly_api_token" \
    run_mutating_command "${rollback_command[@]}"; then
    fly_api_token=
    echo "automatic fenced rollback failed; stop the candidate and inspect Fly releases" >&2
    return 1
  fi
  fly_api_token=
  if verify_rollback; then
    remote_lock_release_permitted=true
    return 0
  fi
  preserve_remote_lock=true
  return 1
}

handle_exit() {
  local exit_code=$?
  local cleanup_failed=false
  trap - EXIT INT TERM
  set +e
  if (( exit_code != 0 )) && [[ $deploy_invoked == true ]] \
    && [[ $mutation_ambiguous != true ]] \
    && [[ $deployment_verified != true ]]; then
    rollback_if_owned
  fi
  if ! cleanup; then
    cleanup_failed=true
  fi
  if [[ $cleanup_failed == true && $exit_code -eq 0 ]]; then
    exit_code=74
  fi
  exit "$exit_code"
}

handle_signal() {
  local signal_name=$1
  local exit_code=$2
  local attempt
  if [[ $mutation_active == true && -n $mutation_pid ]]; then
    mutation_ambiguous=true
    preserve_remote_lock=true
    superseded=true
    kill -TERM "$mutation_pid" >/dev/null 2>&1 || true
    for attempt in 1 2 3 4 5; do
      if ! kill -0 "$mutation_pid" >/dev/null 2>&1; then
        wait "$mutation_pid" >/dev/null 2>&1 || true
        break
      fi
      sleep 1
    done
    if kill -0 "$mutation_pid" >/dev/null 2>&1; then
      kill -KILL "$mutation_pid" >/dev/null 2>&1 || true
      wait "$mutation_pid" >/dev/null 2>&1 || true
    fi
    echo "collector mutation was interrupted; the shared remote lock is preserved for manual Fly reconciliation" >&2
  fi
  echo "collector deploy interrupted by ${signal_name}" >&2
  exit "$exit_code"
}

trap handle_exit EXIT
trap 'handle_signal INT 130' INT
trap 'handle_signal TERM 143' TERM

if acquire_remote_deploy_lock; then
  echo "collector deploy owns the shared remote lock for ${app}"
else
  lock_status=$?
  exit "$lock_status"
fi

fly config validate -c fly.toml -a "$app"
capture_status "$previous_status_before"
if ! read_started_app_machine "$previous_status_before"; then
  echo "collector deploy requires exactly one started app Machine" >&2
  exit 69
fi
before_id=$machine_id
before_instance=$machine_instance
before_image=$machine_image
before_digest=$machine_digest
before_release=$machine_release
before_release_version=$machine_release_version
before_rollback_from_version=$machine_rollback_from_version
before_rollback_to_version=$machine_rollback_to_version
before_config_fingerprint=$machine_config_fingerprint

fly config save -a "$app" -c "$previous_config" --yes >/dev/null
capture_status "$previous_status"
if ! read_started_app_machine "$previous_status"; then
  echo "collector deploy requires exactly one stable started app Machine" >&2
  exit 69
fi
if [[ $machine_id != "$before_id" || $machine_instance != "$before_instance" \
  || $machine_image != "$before_image" \
  || $machine_digest != "$before_digest" || $machine_release != "$before_release" \
  || $machine_release_version != "$before_release_version" \
  || $machine_rollback_from_version != "$before_rollback_from_version" \
  || $machine_rollback_to_version != "$before_rollback_to_version" \
  || $machine_config_fingerprint != "$before_config_fingerprint" ]]; then
  echo "collector release changed while its rollback snapshot was captured" >&2
  exit 75
fi
previous_id=$machine_id
previous_instance=$machine_instance
previous_image=$machine_image
previous_digest=$machine_digest
previous_release=$machine_release
previous_release_version=$machine_release_version
previous_rollback_from_version=$machine_rollback_from_version
previous_rollback_to_version=$machine_rollback_to_version
previous_config_fingerprint=$machine_config_fingerprint

if machine_check_passes "$previous_id"; then
  baseline_health_passes=true
elif [[ $allow_unhealthy_baseline != true ]]; then
  echo "collector deploy requires a passing baseline collector_health check" >&2
  echo "use COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE=true only for one reviewed break-glass repair" >&2
  exit 69
else
  echo "WARNING: break-glass deployment from a baseline without a passing collector_health check; rollback can restore that baseline but cannot certify it healthy" >&2
fi

# A normal fenced rollback submits the saved tag pinned to its immutable digest.
# The sole bare-tag bridge additionally requires the authenticated pre-health
# config and a missing health signal. A future deployment-tag baseline therefore
# stays digest-pinned even if an operator accidentally reuses the break-glass flag.
if [[ $allow_unhealthy_baseline == true \
  && $baseline_health_passes == false \
  && $previous_image =~ ^registry\.fly\.io/${app}:deployment-[0-9A-HJKMNP-TV-Z]{26}$ ]] \
  && legacy_baseline_contract_matches; then
  legacy_bare_baseline=true
  if ! validate_runtime_image_identity "$previous_image"; then
    echo "collector legacy rollback image is incompatible with runtime build identity" >&2
    exit 65
  fi
  if ! legacy_baseline_runtime_responds "$rollback_timeout_seconds" \
    >/dev/null 2>&1; then
    echo "collector legacy rollback runtime probe failed before deployment" >&2
    exit 69
  fi
  echo "WARNING: one-time legacy rollback will use the exact saved deployment tag and verify its resolved digest" >&2
elif ! validate_runtime_image_identity "$previous_image" "$previous_digest"; then
  echo "collector rollback image is incompatible with runtime build identity" >&2
  exit 65
fi

# Close the review-to-deploy race against the authenticated remote, after the
# rollback snapshot but immediately before the first Fly mutation.
if [[ $allow_unmerged != true ]] && ! verify_remote_target; then
  echo "collector remote target changed or became unverifiable before deployment" >&2
  exit 75
fi

# The health probe and authenticated remote check both take time. Re-read Fly
# immediately before mutation so a concurrent release cannot hide inside that
# interval and be treated as the baseline captured above.
if ! capture_status "$current_status" 2>/dev/null; then
  superseded=true
  echo "collector release changed after baseline verification; refusing to deploy" >&2
  exit 75
fi
relation=$(status_relation "$current_status" 2>/dev/null) || relation=unknown
if [[ $relation != previous ]]; then
  superseded=true
  echo "collector release changed after baseline verification; refusing to deploy" >&2
  exit 75
fi
if ! verify_remote_deploy_lock; then
  superseded=true
  echo "collector remote deploy lock ownership was lost before mutation" >&2
  exit 75
fi

deploy_invoked=true
remote_lock_release_permitted=false
if ! run_mutating_command fly deploy \
  -a "$app" \
  -c fly.toml \
  --build-arg "GIT_REVISION=${revision}" \
  --image-label "git-${revision}"-"${deployment_nonce}" \
  --strategy immediate \
  --wait-timeout 10m \
  --yes; then
  echo "collector deployment command failed" >&2
  exit 1
fi

deadline=$((SECONDS + timeout_seconds))
while (( SECONDS < deadline )); do
  if ! verify_remote_deploy_lock; then
    superseded=true
    echo "collector remote deploy lock ownership was lost during verification" >&2
    exit 75
  fi
  if capture_status "$current_status" 2>/dev/null; then
    bind_target_from_status "$current_status" 2>/dev/null || true
    relation=$(status_relation "$current_status") || relation=unknown
    if [[ $relation == superseded ]]; then
      superseded=true
      echo "collector deployment was superseded before verification" >&2
      exit 75
    fi
    if [[ $relation == owned ]] \
      && bound_target_matches_status "$current_status" \
      && machine_check_passes "$target_id" \
        && target_revision_matches "$target_id"; then
      if ! candidate_predecessor_is_baseline; then
        superseded=true
        echo "candidate predecessor is not the saved baseline; another release interposed" >&2
        exit 75
      fi
      # Close the check/SSH race: a concurrent deploy may replace the target
      # after either observation. Success requires one final exact snapshot.
      if capture_status "$current_status" 2>/dev/null \
        && bound_target_matches_status "$current_status"; then
        if ! target_alert_delivers "$target_id"; then
          # The previous image would use the same Fly secret, so rolling code
          # back cannot repair notification delivery. Preserve the healthy,
          # revision-verified release and make the operator address the alert.
          deployment_verified=true
          remote_lock_release_permitted=true
          echo "collector is healthy, but the deployment alert was not delivered; not rolling back code" >&2
          exit 1
        fi
        # Alert delivery takes time; close the race once more before success.
        if ! capture_status "$current_status" 2>/dev/null \
          || ! bound_target_matches_status "$current_status"; then
          relation=$(status_relation "$current_status") || relation=unknown
          if [[ $relation == superseded ]]; then
            superseded=true
            echo "collector deployment was superseded after alert verification" >&2
            exit 75
          fi
          continue
        fi
        if ! verify_remote_deploy_lock; then
          superseded=true
          echo "collector remote deploy lock ownership was lost before success" >&2
          exit 75
        fi
        deployment_verified=true
        remote_lock_release_permitted=true
        echo "collector deployment is healthy at ${revision} on Machine ${target_id}"
        exit 0
      fi
      relation=$(status_relation "$current_status") || relation=unknown
      if [[ $relation == superseded ]]; then
        superseded=true
        echo "collector deployment was superseded during final verification" >&2
        exit 75
      fi
    fi
  fi
  remaining=$((deadline - SECONDS))
  (( remaining > 0 )) || break
  sleep_for=$poll_seconds
  (( sleep_for > remaining )) && sleep_for=$remaining
  sleep "$sleep_for"
done

echo "collector health and revision did not pass within ${timeout_seconds}s" >&2
exit 1
