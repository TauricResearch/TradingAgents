#!/usr/bin/env bash
# Deploy one reviewed collector commit as a transaction. The prior image and
# deployed Fly configuration are captured together before any remote mutation.

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

allow_unmerged=${COLLECTOR_DEPLOY_ALLOW_UNMERGED:-false}
case $allow_unmerged in
  1|true|TRUE|yes|YES|on|ON) allow_unmerged=true ;;
  0|false|FALSE|no|NO|off|OFF) allow_unmerged=false ;;
  *)
    echo "COLLECTOR_DEPLOY_ALLOW_UNMERGED must be an explicit boolean" >&2
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

read_remote_target_revision() {
  local output sha observed_ref extra
  if ! output=$(git ls-remote --exit-code --refs "$target_remote" \
    "refs/heads/${target_branch}" 2>/dev/null); then
    return 1
  fi
  # One exact branch must produce one exact SHA/ref record. Never forward remote
  # output: transport errors can contain credential-bearing remote URLs.
  [[ -n $output && $output != *$'\n'* ]] || return 1
  IFS=$'\t' read -r sha observed_ref extra <<< "$output"
  [[ $sha =~ ^[0-9a-f]{40}$ \
    && $observed_ref == "refs/heads/${target_branch}" \
    && $output == "${sha}"$'\t'"${observed_ref}" \
    && -z ${extra:-} ]] || return 1
  printf '%s\n' "$sha"
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
cleanup() {
  [[ -z $temp_dir ]] || rm -rf "$temp_dir"
  rm -rf "$lock_dir"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

temp_dir=$(mktemp -d "${TMPDIR:-/tmp}/tradingagents-deploy.XXXXXX")
previous_config="$temp_dir/fly.previous.toml"
previous_status_before="$temp_dir/status.previous-before.json"
previous_status="$temp_dir/status.previous.json"
current_status="$temp_dir/status.current.json"

deploy_invoked=false
deployment_verified=false
rollback_attempted=false
superseded=false
previous_id=
previous_image=
previous_digest=
previous_release=
previous_config_fingerprint=
target_id=
target_image="registry.fly.io/${app}:git-${revision}"
target_digest=
target_release=

capture_status() {
  local output_file=$1
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
semantic_config = {
    key: value
    for key, value in config.items()
    if key not in {"image", "metadata"}
}
fingerprint = hashlib.sha256(
    json.dumps(semantic_config, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
image_ref = machine.get("image_ref") or {}
fields = (
    machine.get("id") or "",
    config.get("image") or "",
    image_ref.get("digest") or "",
    (config.get("metadata") or {}).get("fly_release_id") or "",
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
  IFS=$'\t' read -r machine_id machine_image machine_digest machine_release \
    machine_config_fingerprint <<< "$summary"
}

status_relation() {
  local status_file=$1
  python3 - "$status_file" "$previous_digest" "$previous_config_fingerprint" \
    "$target_image" "$target_digest" "$target_release" <<'PY'
import hashlib
import json
import sys

path, previous_digest, previous_fingerprint, target_image, target_digest, target_release = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)

machines = []
for machine in payload.get("Machines") or []:
    config = machine.get("config") or {}
    metadata = config.get("metadata") or {}
    env = config.get("env") or {}
    if (metadata.get("fly_process_group") or env.get("FLY_PROCESS_GROUP")) == "app":
        machines.append(machine)

started = [machine for machine in machines if machine.get("state") == "started"]
if len(started) == 1:
    machine = started[0]
    config = machine.get("config") or {}
    semantic_config = {
        key: value for key, value in config.items()
        if key not in {"image", "metadata"}
    }
    fingerprint = hashlib.sha256(
        json.dumps(semantic_config, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    digest = (machine.get("image_ref") or {}).get("digest") or ""
    if digest == previous_digest and fingerprint == previous_fingerprint:
        print("previous")
        raise SystemExit

if not machines:
    print("owned")
    raise SystemExit

def is_target(machine):
    config = machine.get("config") or {}
    digest = (machine.get("image_ref") or {}).get("digest") or ""
    release = (config.get("metadata") or {}).get("fly_release_id") or ""
    return (
        config.get("image") == target_image
        or bool(target_digest and digest == target_digest)
        or bool(target_release and release == target_release)
    )

if any(is_target(machine) for machine in machines):
    print("owned")
elif all(
    ((machine.get("image_ref") or {}).get("digest") or "") == previous_digest
    for machine in machines
):
    # The image is old but a failed deploy may already have changed its config.
    print("owned")
else:
    print("superseded")
PY
}

target_check_passes() {
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

verify_rollback() {
  local deadline=$((SECONDS + rollback_timeout_seconds))
  while (( SECONDS < deadline )); do
    if capture_status "$current_status" 2>/dev/null \
      && read_started_app_machine "$current_status" \
      && [[ $machine_digest == "$previous_digest" ]] \
      && [[ $machine_config_fingerprint == "$previous_config_fingerprint" ]]; then
      echo "previous collector image and configuration restored"
      return 0
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
  [[ $rollback_attempted == false ]] || return 1
  rollback_attempted=true
  if [[ $superseded == true ]]; then
    echo "deployment was superseded; refusing to roll back a newer release" >&2
    return 1
  fi
  if ! capture_status "$current_status" 2>/dev/null; then
    echo "cannot inspect the current Fly release; refusing an unsafe rollback" >&2
    return 1
  fi
  relation=$(status_relation "$current_status") || relation=unknown
  if [[ $relation == previous ]]; then
    echo "previous collector image and configuration remain active" >&2
    return 0
  fi
  if [[ $relation != owned ]]; then
    echo "deployment was superseded; refusing to roll back a newer release" >&2
    return 1
  fi

  echo "restoring the previous collector image and deployed configuration" >&2
  if ! fly config validate -c "$previous_config" -a "$app" >/dev/null; then
    echo "saved previous Fly configuration no longer validates" >&2
    return 1
  fi
  if ! fly deploy \
    -a "$app" \
    -c "$previous_config" \
    --image "$previous_image" \
    --skip-release-command \
    --strategy immediate \
    --wait-timeout 10m \
    --yes; then
    echo "automatic rollback failed; scale the app to zero and inspect Fly releases" >&2
    return 1
  fi
  verify_rollback
}

handle_exit() {
  local exit_code=$?
  trap - EXIT INT TERM
  set +e
  if (( exit_code != 0 )) && [[ $deploy_invoked == true ]] \
    && [[ $deployment_verified != true ]]; then
    rollback_if_owned
  fi
  cleanup
  exit "$exit_code"
}

handle_signal() {
  local signal_name=$1
  local exit_code=$2
  echo "collector deploy interrupted by ${signal_name}" >&2
  exit "$exit_code"
}

trap handle_exit EXIT
trap 'handle_signal INT 130' INT
trap 'handle_signal TERM 143' TERM

fly config validate -c fly.toml -a "$app"
capture_status "$previous_status_before"
if ! read_started_app_machine "$previous_status_before"; then
  echo "collector deploy requires exactly one started app Machine" >&2
  exit 69
fi
before_id=$machine_id
before_image=$machine_image
before_digest=$machine_digest
before_release=$machine_release
before_config_fingerprint=$machine_config_fingerprint

fly config save -a "$app" -c "$previous_config" --yes >/dev/null
capture_status "$previous_status"
if ! read_started_app_machine "$previous_status"; then
  echo "collector deploy requires exactly one stable started app Machine" >&2
  exit 69
fi
if [[ $machine_id != "$before_id" || $machine_image != "$before_image" \
  || $machine_digest != "$before_digest" || $machine_release != "$before_release" \
  || $machine_config_fingerprint != "$before_config_fingerprint" ]]; then
  echo "collector release changed while its rollback snapshot was captured" >&2
  exit 75
fi
previous_id=$machine_id
previous_image=$machine_image
previous_digest=$machine_digest
previous_release=$machine_release
previous_config_fingerprint=$machine_config_fingerprint

# Close the review-to-deploy race against the authenticated remote, after the
# rollback snapshot but immediately before the first Fly mutation.
if [[ $allow_unmerged != true ]] && ! verify_remote_target; then
  echo "collector remote target changed or became unverifiable before deployment" >&2
  exit 75
fi

deploy_invoked=true
if ! fly deploy \
  -a "$app" \
  -c fly.toml \
  --build-arg "GIT_REVISION=${revision}" \
  --image-label "git-${revision}" \
  --strategy immediate \
  --wait-timeout 10m \
  --yes; then
  echo "collector deployment command failed" >&2
  exit 1
fi

deadline=$((SECONDS + timeout_seconds))
while (( SECONDS < deadline )); do
  if capture_status "$current_status" 2>/dev/null; then
    relation=$(status_relation "$current_status") || relation=unknown
    if [[ $relation == superseded ]]; then
      superseded=true
      echo "collector deployment was superseded before verification" >&2
      exit 75
    fi
    if read_started_app_machine "$current_status" \
      && [[ $machine_image == "$target_image" ]]; then
      if [[ -z $target_release ]]; then
        target_id=$machine_id
        target_digest=$machine_digest
        target_release=$machine_release
      fi
      if [[ $machine_id == "$target_id" \
        && $machine_digest == "$target_digest" \
        && $machine_release == "$target_release" ]] \
        && target_check_passes "$target_id" \
        && target_revision_matches "$target_id"; then
        # Close the check/SSH race: a concurrent deploy may replace the target
        # after either observation. Success requires one final exact snapshot.
        if capture_status "$current_status" 2>/dev/null \
          && read_started_app_machine "$current_status" \
          && [[ $machine_id == "$target_id" \
            && $machine_image == "$target_image" \
            && $machine_digest == "$target_digest" \
            && $machine_release == "$target_release" ]]; then
          if ! target_alert_delivers "$target_id"; then
            # The previous image would use the same Fly secret, so rolling code
            # back cannot repair notification delivery. Preserve the healthy,
            # revision-verified release and make the operator address the alert.
            deployment_verified=true
            echo "collector is healthy, but the deployment alert was not delivered; not rolling back code" >&2
            exit 1
          fi
          # Alert delivery takes time; close the race once more before success.
          if ! capture_status "$current_status" 2>/dev/null \
            || ! read_started_app_machine "$current_status" \
            || [[ $machine_id != "$target_id" \
              || $machine_image != "$target_image" \
              || $machine_digest != "$target_digest" \
              || $machine_release != "$target_release" ]]; then
            relation=$(status_relation "$current_status") || relation=unknown
            if [[ $relation == superseded ]]; then
              superseded=true
              echo "collector deployment was superseded after alert verification" >&2
              exit 75
            fi
            continue
          fi
          deployment_verified=true
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
  fi
  remaining=$((deadline - SECONDS))
  (( remaining > 0 )) || break
  sleep_for=$poll_seconds
  (( sleep_for > remaining )) && sleep_for=$remaining
  sleep "$sleep_for"
done

echo "collector health and revision did not pass within ${timeout_seconds}s" >&2
exit 1
