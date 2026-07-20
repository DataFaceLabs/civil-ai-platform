# Day-2: stand up the dev data-API container without replacing the instance

`user_data` is boot-only and is ignored by tofu (`lifecycle.ignore_changes`).
Standing up (or refreshing) the second container on a live box is an SSM
operation, never an instance replacement — so `civil1.ai` (port 8000) is
untouched.

Prerequisites:

1. `civil-ai-data` on the box includes `S3DuckDBSectionFactRuntime`
   ([data #392](https://github.com/DataFaceLabs/civil-ai-data/pull/392)).
2. IAM allows `s3:GetObject` on `civilai-data/{dev,prod}/serving/*`
   (tofu apply of this module, or an inline policy update).
3. SG allows inbound TCP 8001 from the platform CIDR (tofu apply of this module).

## Bring up / refresh the container

```bash
INSTANCE_ID=i-0658b3db749e9e5cb   # civilai-uat-data-api
AWS_PROFILE=civilai

aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --parameters commands='[
    "set -euo pipefail",
    "cd /opt/civilai/civil-ai-data",
    "git fetch origin && git checkout develop && git pull --ff-only",
    "docker build -t civil-ai-data .",
    "SERVICE_KEY=$(grep ^CIVILAI_DATA_SERVICE_KEY= /etc/civil-ai-data/env | cut -d= -f2-)",
    "CORS=$(grep ^CIVILAI_CORS_ORIGINS= /etc/civil-ai-data/env | cut -d= -f2-)",
    "MAPBOX_LINE=$(grep ^MAPBOX_ACCESS_TOKEN= /etc/civil-ai-data/env || true)",
    "cat >/etc/civil-ai-data/env-dev <<EOF\nCIVILAI_SECTION_FACTS_BACKEND=duckdb_s3\nCIVILAI_SECTION_FACTS_DUCKDB_S3_URI=s3://civilai-data/dev/serving/current.json\nCIVILAI_SECTION_FACTS_DUCKDB_MEMORY_LIMIT=512MiB\nCIVILAI_DATA_SERVICE_KEY=$SERVICE_KEY\nCIVILAI_EXPERIMENTAL_LLM=1\nCIVILAI_CORS_ORIGINS=$CORS\nCIVILAI_PII_REDACT=1\nWEB_CONCURRENCY=2\nPORT=8001\nAWS_DEFAULT_REGION=us-east-1\n$MAPBOX_LINE\nEOF",
    "chmod 600 /etc/civil-ai-data/env-dev",
    "docker rm -f civil-ai-data-dev 2>/dev/null || true",
    "docker run -d --name civil-ai-data-dev --restart unless-stopped -p 8001:8001 -v /opt/civilai/civil-ai-data/docs:/app/docs:ro --env-file /etc/civil-ai-data/env-dev civil-ai-data",
    "sleep 5",
    "curl -sf http://localhost:8001/healthz",
    "curl -sf http://localhost:8000/healthz"
  ]'
```

The final two curls prove both planes answer — and that the prod one was
never restarted.
