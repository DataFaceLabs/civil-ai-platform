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

## Do not `git checkout` in the shared clone

`/opt/civilai/civil-ai-data` is **bind-mounted into the prod container**:

```
civil-ai-data (:8000)     -v /opt/civilai/civil-ai-data/docs:/app/docs:ro
civil-ai-data-dev (:8001) -v /opt/civilai/civil-ai-data/docs:/app/docs:ro
                          -v .../data/reference/tap_cards:/app/data/reference/tap_cards:ro
```

`docs/` is not documentation at runtime — it carries **config the app reads**
(`docs/design/field_tiers.yaml`, `docs/design/fe_field_mapping.yaml`,
`docs/reference/source_templates.yaml`, `docs/catalog/data_catalog.yaml`).

So `git checkout develop` in that clone silently gives the **prod** container
develop's config while prod's *code* stays on the `main`-built image — a
config/code mismatch on the customer path, with no restart and no signal. An
earlier revision of this runbook did exactly that.

Use a **git worktree** instead. The shared clone never moves, and the dev
container gets code *and* config from the same commit.

Note the `tap_cards` bind: it was added after this runbook was written
([data #418](https://github.com/DataFaceLabs/civil-ai-data/pull/418)) and is
required for tap-card sources. Always mirror the live container's binds —
check `docker inspect civil-ai-data-dev --format '{{json .HostConfig.Binds}}'`
before replacing it.

## Bring up / refresh the container

```bash
INSTANCE_ID=i-0658b3db749e9e5cb   # civilai-uat-data-api
AWS_PROFILE=civilai

# 1. Worktree at the target commit (shared clone untouched)
aws ssm send-command --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --parameters commands='[
    "set -eu",
    "cd /opt/civilai/civil-ai-data",
    "git fetch origin --quiet",
    "rm -rf /opt/civilai/civil-ai-data-develop && git worktree prune",
    "git worktree add --detach /opt/civilai/civil-ai-data-develop origin/develop",
    "cd /opt/civilai/civil-ai-data-develop && git log --oneline -1",
    "cd /opt/civilai/civil-ai-data && git rev-parse --abbrev-ref HEAD"
  ]'

# 2. Build (tag by sha -- never overwrite the tag prod runs)
#    Allow ~5 min; pass --timeout-seconds 3600.
aws ssm send-command --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript --timeout-seconds 3600 \
  --parameters commands='[
    "set -e",
    "cd /opt/civilai/civil-ai-data-develop",
    "SHA=$(git rev-parse --short HEAD)",
    "docker build -t civil-ai-data:develop-$SHA .",
    "echo BUILT=civil-ai-data:develop-$SHA"
  ]'

# 3. Recreate the dev container against the worktree (env-dev is reused if present;
#    create it per the block below on first bring-up). Substitute the built tag.
aws ssm send-command --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --parameters commands='[
    "set -e",
    "W=/opt/civilai/civil-ai-data-develop",
    "docker rm -f civil-ai-data-dev 2>/dev/null || true",
    "docker run -d --name civil-ai-data-dev --restart unless-stopped -p 8001:8001 -v $W/docs:/app/docs:ro -v $W/data/reference/tap_cards:/app/data/reference/tap_cards:ro --env-file /etc/civil-ai-data/env-dev civil-ai-data:develop-<SHA>",
    "sleep 12",
    "curl -sf http://localhost:8001/healthz",
    "curl -sf http://localhost:8000/healthz"
  ]'
```

First bring-up only — create `/etc/civil-ai-data/env-dev`:

```bash
aws ssm send-command --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --parameters commands='[
    "SERVICE_KEY=$(grep ^CIVILAI_DATA_SERVICE_KEY= /etc/civil-ai-data/env | cut -d= -f2-)",
    "CORS=$(grep ^CIVILAI_CORS_ORIGINS= /etc/civil-ai-data/env | cut -d= -f2-)",
    "MAPBOX_LINE=$(grep ^MAPBOX_ACCESS_TOKEN= /etc/civil-ai-data/env || true)",
    "cat >/etc/civil-ai-data/env-dev <<EOF\nCIVILAI_SECTION_FACTS_BACKEND=duckdb_s3\nCIVILAI_SECTION_FACTS_DUCKDB_S3_URI=s3://civilai-data/dev/serving/current.json\nCIVILAI_SECTION_FACTS_DUCKDB_MEMORY_LIMIT=512MiB\nCIVILAI_DATA_SERVICE_KEY=$SERVICE_KEY\nCIVILAI_EXPERIMENTAL_LLM=1\nCIVILAI_CORS_ORIGINS=$CORS\nCIVILAI_PII_REDACT=1\nWEB_CONCURRENCY=2\nPORT=8001\nAWS_DEFAULT_REGION=us-east-1\n$MAPBOX_LINE\nEOF",
    "chmod 600 /etc/civil-ai-data/env-dev"
  ]'
```

### SSM quoting

Multi-line heredocs inside the `commands=[...]` JSON get mangled — a `\n`-escaped
heredoc silently truncated a script during the 2026-07-29 refresh. Prefer
one-liners; where a Python snippet is unavoidable, use `python3 -c` reading from a
file rather than a heredoc.

### Latency expectation (measured 2026-07-29, server-side)

`POST /v1/fe/site/by-address`, full 10-section payload:

| plane | runtime | latency |
|---|---|---|
| prod `:8000` | local DuckDB file | **0.69 – 0.91 s** |
| dev `:8001` | S3 httpfs (deliberate) | 18 – 21 s |

The ~25x gap is the M0.5 asymmetric design, not a regression. If `:8001` is *fast*,
suspect it is reading a local file and no longer exercising the dev data plane.

The final two curls prove both planes answer — and that the prod one was
never restarted.
