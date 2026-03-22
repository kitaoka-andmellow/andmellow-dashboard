#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <gcp-project-id> <region> [service-name]"
  exit 1
fi

if [[ -z "${GOOGLE_CLIENT_ID:-}" ]]; then
  echo "GOOGLE_CLIENT_ID env is required"
  exit 1
fi

if [[ -z "${SESSION_SECRET_NAME:-}" ]]; then
  echo "SESSION_SECRET_NAME env is required"
  exit 1
fi

PROJECT_ID="$1"
REGION="$2"
SERVICE_NAME="${3:-ecanalytics}"

gcloud config set project "$PROJECT_ID"

gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --port 8080 \
  --set-env-vars "HOST=0.0.0.0,DATA_ROOT=/app,AUTH_REQUIRED=1,ALLOWED_EMAIL_DOMAIN=andmellow.jp,GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID},SESSION_TTL_SECONDS=7200" \
  --set-secrets "SESSION_SECRET=${SESSION_SECRET_NAME}:latest"
