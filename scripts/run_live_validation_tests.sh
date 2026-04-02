#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

SUITE=""
ARTIFACT_BASE_DIR="${ROOT_DIR}/artifacts/live-tests"
PYTEST_TIMEOUT_SEC="${PYTEST_TIMEOUT_SEC:-300}"
ALLOW_HOSTS="${LIVE_ALLOW_HOSTS:-www.alphavantage.co,alphavantage.co,query1.finance.yahoo.com,query2.finance.yahoo.com,finance.yahoo.com,fc.yahoo.com,www.finviz.com,finviz.com}"
ALLOW_DEMO_AV=0
declare -a OVERRIDE_MODULES=()

usage() {
  cat <<'EOF'
Usage: scripts/run_live_validation_tests.sh --suite core|alpha-vantage|full [--artifact-dir DIR] [--allow-hosts CSV] [--timeout-sec N] [--allow-demo-av] [--module PATH]

Suites:
  core           No API keys required. Runs core live scanner/market path checks.
  alpha-vantage  Requires ALPHA_VANTAGE_API_KEY.
  full           Runs core + alpha-vantage.

Options:
  --allow-demo-av   If ALPHA_VANTAGE_API_KEY is missing, use demo key for AV suites.
  --module PATH     Run only specific module(s). Repeatable.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --suite)
      SUITE="${2:-}"
      shift 2
      ;;
    --artifact-dir)
      ARTIFACT_BASE_DIR="${2:-}"
      shift 2
      ;;
    --allow-hosts)
      ALLOW_HOSTS="${2:-}"
      shift 2
      ;;
    --timeout-sec)
      PYTEST_TIMEOUT_SEC="${2:-}"
      shift 2
      ;;
    --allow-demo-av)
      ALLOW_DEMO_AV=1
      shift 1
      ;;
    --module)
      OVERRIDE_MODULES+=("${2:-}")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

case "${SUITE}" in
  core|alpha-vantage|full) ;;
  "")
    echo "Missing required --suite argument." >&2
    usage
    exit 2
    ;;
  *)
    echo "Invalid --suite value: ${SUITE}" >&2
    usage
    exit 2
    ;;
esac

require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Missing required command: ${cmd}" >&2
    exit 3
  fi
}

require_cmd pytest
require_cmd python3
require_cmd perl

if [[ "${SUITE}" == "alpha-vantage" || "${SUITE}" == "full" ]]; then
  if [[ -z "${ALPHA_VANTAGE_API_KEY:-}" ]]; then
    if [[ "${ALLOW_DEMO_AV}" -eq 1 ]]; then
      export ALPHA_VANTAGE_API_KEY="demo"
      echo "ALPHA_VANTAGE_API_KEY not set; using demo key due to --allow-demo-av." >&2
    else
      echo "ALPHA_VANTAGE_API_KEY is required for suite '${SUITE}'." >&2
      echo "Use --allow-demo-av to run with demo key intentionally." >&2
      exit 4
    fi
  fi
fi

# Finviz tests are part of core; fail fast if dependency is absent.
if ! python3 -c "import finvizfinance" >/dev/null 2>&1; then
  echo "Python package 'finvizfinance' is required for core live tests." >&2
  echo "Install with: pip install finvizfinance" >&2
  exit 5
fi

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARTIFACT_DIR="${ARTIFACT_BASE_DIR}/${TIMESTAMP}"
mkdir -p "${ARTIFACT_DIR}"

SUMMARY_FILE="${ARTIFACT_DIR}/summary.tsv"
printf "module\tstatus\trc\n" > "${SUMMARY_FILE}"

{
  echo "timestamp_utc=${TIMESTAMP}"
  echo "suite=${SUITE}"
  echo "git_rev=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "python=$(python3 --version | tr -d '\n')"
  echo "allow_hosts=${ALLOW_HOSTS}"
  echo "pytest_timeout_sec=${PYTEST_TIMEOUT_SEC}"
  echo "allow_demo_av=${ALLOW_DEMO_AV}"
  echo "alpha_vantage_key_set=$([[ -n "${ALPHA_VANTAGE_API_KEY:-}" ]] && echo yes || echo no)"
  echo "alpha_vantage_key_is_demo=$([[ "${ALPHA_VANTAGE_API_KEY:-}" == "demo" ]] && echo yes || echo no)"
  echo "finnhub_key_set=$([[ -n "${FINNHUB_API_KEY:-}" ]] && echo yes || echo no)"
} > "${ARTIFACT_DIR}/run_metadata.txt"

run_module() {
  local module_path="$1"
  local label="$2"
  local log_file="${ARTIFACT_DIR}/${label}.log"
  local junit_file="${ARTIFACT_DIR}/${label}.junit.xml"

  echo "==> Running ${module_path}"
  echo "    allow-hosts: ${ALLOW_HOSTS}"
  echo "    timeout-sec: ${PYTEST_TIMEOUT_SEC}"
  set +e
  # Use perl alarm so one hung live endpoint does not block the full suite.
  perl -e 'alarm shift; exec @ARGV' "${PYTEST_TIMEOUT_SEC}" \
    pytest -v "${module_path}" --allow-hosts="${ALLOW_HOSTS}" --junitxml="${junit_file}" \
    2>&1 | tee "${log_file}"
  local rc="${PIPESTATUS[0]}"
  set -e

  if [[ "${rc}" -eq 0 ]]; then
    printf "%s\tPASS\t%s\n" "${module_path}" "${rc}" >> "${SUMMARY_FILE}"
  else
    printf "%s\tFAIL\t%s\n" "${module_path}" "${rc}" >> "${SUMMARY_FILE}"
  fi
  return "${rc}"
}

declare -a TEST_MODULES=(
  "tests/integration/test_market_prices_live.py"
  "tests/integration/test_gatekeeper_live.py"
  "tests/integration/test_finviz_live.py"
)

if [[ "${SUITE}" == "alpha-vantage" || "${SUITE}" == "full" ]]; then
  TEST_MODULES+=(
    "tests/integration/test_alpha_vantage_live.py"
    "tests/integration/test_scanner_context_filtering_live.py"
  )
fi

if [[ "${#OVERRIDE_MODULES[@]}" -gt 0 ]]; then
  TEST_MODULES=("${OVERRIDE_MODULES[@]}")
fi

FAILED=0
for module in "${TEST_MODULES[@]}"; do
  label="$(basename "${module}" .py)"
  if ! run_module "${module}" "${label}"; then
    FAILED=1
  fi
done

if [[ "${FAILED}" -ne 0 ]]; then
  echo "Live validation suite FAILED. Artifacts: ${ARTIFACT_DIR}" >&2
  exit 10
fi

echo "Live validation suite PASSED. Artifacts: ${ARTIFACT_DIR}"
