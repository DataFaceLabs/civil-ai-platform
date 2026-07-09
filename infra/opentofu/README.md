# Civil AI — OpenTofu (Infrastructure as Code)

OpenTofu manages **all** UAT AWS resources for the product stack:

| Module | Resources |
|--------|-----------|
| `bootstrap/` | Remote state S3 + DynamoDB lock (once per account) |
| `modules/data-api-ec2` | **EC2** `t4g.medium`, EIP, SG, IAM, Docker bootstrap via user_data |
| `modules/cognito` | User pool, app client, hosted UI domain |
| `modules/dynamodb` | `civilai-app-{env}` single-table store |
| `modules/s3` | `civilai-app-{env}` artifacts bucket (platform exports) |
| `modules/secrets` | SSM: `data-service-key`, Mapbox token |
| `modules/api-gateway` | Lambda IAM + **HTTP API** + Cognito JWT authorizer |
| `modules/bedrock` | Invoke policy for Lambda |
| `modules/amplify-hosting` | Amplify app + `develop` branch + FE env vars |
| `modules/observability` | Lambda log group + error alarm |
| `modules/agentcore` | Agent runtime IAM attachments |

**Existing data lake** (`s3://civilai-data`) is referenced via data source — not recreated.

## Prerequisites

- [OpenTofu](https://opentofu.org/) >= 1.6
- AWS CLI profile with admin access (account `379604374458`, `us-east-1`)
- GitHub PAT for Amplify (and optional EC2 clone of private repos)

## Apply order

### 1. Bootstrap remote state (once)

```bash
cd infra/opentofu/bootstrap
tofu init && tofu apply
```

### 2. UAT environment

```bash
cd ../environments/uat
cp terraform.tfvars.example terraform.tfvars
# Edit: allowed_ssh_cidr_blocks, mapbox_access_token, github_access_token, cognito URLs

# Platform Lambda zip (when create_platform_http_api=true)
cd ../../.. && bash scripts/package-lambda.sh && cd infra/opentofu/environments/uat

tofu init
tofu plan
tofu apply
```

### 3. Post-apply

```bash
tofu output data_api_public_ip
curl -s "http://$(tofu output -raw data_api_public_ip):8000/healthz" | jq .
# expect snapshot_date: 2026-07-02 (after ~2 min S3 download)

tofu output -raw data_service_key   # share with James for platform .env.local
```

Wire James:

```bash
CIVILAI_DATA_API_BASE=http://<EIP>:8000   # or https://data-uat... after nginx
CIVILAI_DATA_SERVICE_KEY=<from tofu output>
```

## Module audit (pre-UAT gaps addressed)

| Area | Before | Now |
|------|--------|-----|
| EC2 data API | Manual console | `modules/data-api-ec2` |
| API Gateway | IAM stub only | HTTP API + Lambda + Cognito JWT |
| Cognito | Hardcoded callbacks | Parameterized per env |
| S3 / DynamoDB | Modules exist, unwired in UAT | Wired in `environments/uat` |
| Amplify | Not in IaC | `modules/amplify-hosting` |
| Secrets | Ad hoc | SSM via `modules/secrets` |
| Remote state | Commented placeholders | `bootstrap/` + `backend.tf` |

## Still manual / phase 2

- **nginx + TLS** on EC2 (`data-uat.<domain>`) — add `modules/data-api-nginx` or certbot runbook
- **Route53** DNS → EIP
- **Lambda code updates** — re-run `package-lambda.sh` + `tofu apply` (or CI pipeline)
- **FE SSR on Amplify** — build spec may need nitro/SSR tuning; verify first Amplify build
- **WAF** — per architecture plan, post-UAT

## Default VPC note

EC2 launches in the **account default VPC** (no custom VPC/NAT — matches lean budget roadmap).
Lambda stays **outside VPC** and calls the data API over the public EIP + TLS.

## Destroy

```bash
cd environments/uat
tofu destroy
```

Do not destroy `bootstrap/` unless retiring the account's remote state.
