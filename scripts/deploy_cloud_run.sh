#!/usr/bin/env bash
# Build + deploy the Pro dashboard (deploy/Dockerfile.pro) to Cloud Run, for
# use behind Firebase Hosting (see firebase.json + docs/DEPLOYMENT.md).
#
# One-time GCP setup (APIs, Artifact Registry repo, GCS bucket, secrets) is
# NOT done by this script — see the "Cloud Run + Firebase Hosting" section
# of docs/DEPLOYMENT.md for that checklist. This script only builds the
# image and (re)deploys the Cloud Run service; safe to re-run.
#
# Required env vars:
#   PROJECT_ID        GCP project id (the one backing your Firebase project)
#   BUCKET            GCS bucket name backing the /data volume (persistence)
# Optional (defaults shown):
#   REGION=asia-south1
#   SERVICE=pro-dashboard
#   ARTIFACT_REPO=pro-dashboard
#   LLM_PROVIDER=deepseek
#   PRO_LOOP_DISABLED=0   # the hourly paper loop RUNS by default (accrual
#                         # clock, roadmap workstream T); set 1 to deploy
#                         # dashboard-only with on-demand runs
#
# Usage:
#   PROJECT_ID=my-project BUCKET=my-project-pro-data ./scripts/deploy_cloud_run.sh
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID to your GCP project id}"
: "${BUCKET:?Set BUCKET to the GCS bucket backing /data (see docs/DEPLOYMENT.md)}"
REGION="${REGION:-asia-south1}"
SERVICE="${SERVICE:-pro-dashboard}"
ARTIFACT_REPO="${ARTIFACT_REPO:-pro-dashboard}"
LLM_PROVIDER="${LLM_PROVIDER:-deepseek}"

for bin in gcloud git; do
  command -v "$bin" >/dev/null || { echo "missing required tool: $bin" >&2; exit 1; }
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TAG="$(git rev-parse --short HEAD)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/${SERVICE}:${TAG}"
# portable uppercase (macOS ships bash 3.2 — no ${VAR^^} support there)
LLM_PROVIDER_UPPER="$(printf '%s' "$LLM_PROVIDER" | tr '[:lower:]' '[:upper:]')"
LLM_KEY_ENV="${LLM_PROVIDER_UPPER}_API_KEY"

echo "==> Building + pushing ${IMAGE} via Cloud Build"
# `gcloud builds submit --tag` always runs `docker build -t $TAG .` with the
# default Dockerfile path — it can't take -f alongside --tag — so use the
# explicit build config instead (deploy/cloudbuild.yaml).
gcloud builds submit \
  --project "$PROJECT_ID" \
  --config deploy/cloudbuild.yaml \
  --substitutions "_IMAGE=${IMAGE}" \
  .

echo "==> Deploying ${SERVICE} to Cloud Run (${REGION})"
# --max-instances=1 enforces the app's single-writer invariant over the
# /data volume (memory.jsonl, run history, hash-chained audit log, arming
# state — see docs/DEPLOYMENT.md); --min-instances=1 keeps that singleton
# WARM: with scale-to-zero, every cold boot briefly served "monitor only"
# safety chrome before the paper service attached, so equity/status chips
# flickered between page loads (trader review P0.4 — a control surface
# whose LIVE state depends on which boot served you reads as broken).
# --execution-environment gen2 is required for the Cloud Storage volume mount.
# --update-env-vars/--update-secrets (not --set-*) MERGE with what's already
# on the service, so redeploys never wipe env applied out-of-band (e.g. the
# Google sign-in vars PRO_FIREBASE_PROJECT_ID/PRO_ALLOWED_EMAILS/
# PRO_FIREBASE_WEB_CONFIG — see docs/DEPLOYMENT.md).
gcloud run deploy "$SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --image "$IMAGE" \
  --execution-environment gen2 \
  --min-instances 1 \
  --max-instances 1 \
  --no-cpu-throttling \
  --add-volume "name=data,type=cloud-storage,bucket=${BUCKET}" \
  --add-volume-mount "volume=data,mount-path=/data" \
  --update-env-vars "TRADINGAGENTS_LLM_PROVIDER=${LLM_PROVIDER},PRO_LOOP_DISABLED=${PRO_LOOP_DISABLED:-0}" \
  --update-secrets "PRO_DASHBOARD_TOKEN=pro-dashboard-token:latest,${LLM_KEY_ENV}=${LLM_PROVIDER}-api-key:latest" \
  --allow-unauthenticated

echo "==> Done. Fetch the Cloud Run URL with:"
echo "    gcloud run services describe ${SERVICE} --project ${PROJECT_ID} --region ${REGION} --format='value(status.url)'"
echo "==> Then point firebase.json's hosting rewrite at serviceId=${SERVICE}, region=${REGION}, and run:"
echo "    firebase deploy --only hosting"
