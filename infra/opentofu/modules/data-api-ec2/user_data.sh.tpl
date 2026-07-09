#!/bin/bash
set -euxo pipefail

ENVIRONMENT="${environment}"
AWS_REGION="${aws_region}"
SERVING_URI="${serving_s3_uri}"
KEY_PARAM="${data_service_key_parameter}"
MAPBOX_PARAM="${mapbox_parameter}"
CORS="${cors_origins}"
REPO_URL="${github_repo_url}"
GIT_REF="${git_ref}"
TOKEN_PARAM="${github_token_parameter}"

dnf update -y
dnf install -y docker git jq
systemctl enable --now docker

mkdir -p /opt/civilai /etc/civil-ai-data /data
chmod 1777 /data

SERVICE_KEY="$(aws ssm get-parameter --region "$AWS_REGION" --name "$KEY_PARAM" --with-decryption --query Parameter.Value --output text)"
MAPBOX_LINE=""
if [ -n "$MAPBOX_PARAM" ]; then
  MAPBOX_TOKEN="$(aws ssm get-parameter --region "$AWS_REGION" --name "$MAPBOX_PARAM" --with-decryption --query Parameter.Value --output text)"
  MAPBOX_LINE="MAPBOX_ACCESS_TOKEN=$MAPBOX_TOKEN"
fi

cat >/etc/civil-ai-data/env <<EOF
CIVILAI_SERVING_DB_S3_URI=$SERVING_URI
CIVILAI_SECTION_FACTS_DUCKDB_PATH=/data/civil_ai_serving.duckdb
CIVILAI_SECTION_FACTS_BACKEND=duckdb
CIVILAI_DATA_SERVICE_KEY=$SERVICE_KEY
CIVILAI_CORS_ORIGINS=$CORS
CIVILAI_PII_REDACT=1
WEB_CONCURRENCY=4
PORT=8000
AWS_DEFAULT_REGION=$AWS_REGION
$MAPBOX_LINE
EOF
chmod 600 /etc/civil-ai-data/env

if [ ! -d /opt/civilai/civil-ai-data/.git ]; then
  if [ -n "$TOKEN_PARAM" ]; then
    GITHUB_TOKEN="$(aws ssm get-parameter --region "$AWS_REGION" --name "$TOKEN_PARAM" --with-decryption --query Parameter.Value --output text)"
    CLONE_URL="$(echo "$REPO_URL" | sed "s#https://#https://x-access-token:$${GITHUB_TOKEN}@#")"
    git clone --branch "$GIT_REF" --depth 1 "$CLONE_URL" /opt/civilai/civil-ai-data
  else
    echo "No github_token_parameter — clone civil-ai-data manually to /opt/civilai/civil-ai-data"
    exit 0
  fi
fi

cd /opt/civilai/civil-ai-data
docker build -t civil-ai-data .
docker rm -f civil-ai-data 2>/dev/null || true
docker run -d --name civil-ai-data --restart unless-stopped \
  -p 8000:8000 \
  -v /data:/data \
  -v /opt/civilai/civil-ai-data/docs:/app/docs:ro \
  --env-file /etc/civil-ai-data/env \
  civil-ai-data

echo "data-api bootstrap complete"
