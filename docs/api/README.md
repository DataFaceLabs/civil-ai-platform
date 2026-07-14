# Platform API

Control-plane API for Civil AI workbench: tenants, users, projects, LLM configuration, and agent runs.

## Base URL

- Local: `http://localhost:8001`
- OpenAPI: `GET /openapi.json` (regenerate: `make openapi`)

## Authentication

- **Production:** Cognito JWT (`Authorization: Bearer …`)
- **Local dev:** `CIVILAI_DEV_AUTH=true` with `X-Dev-User-Id` and optional `X-Tenant-Id`

## Tenant URLs

Tenants are addressed in the FE at `/fstudio/{url_slug}/…`. Public branding (no auth):

- `GET /v1/public/tenants/{slug}` — name + logo URL for login

## Admin APIs (platform admin only)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/v1/admin/tenants` | List tenants |
| POST | `/v1/admin/tenants` | Create tenant + invite initial admin |
| POST | `/v1/admin/tenants/{id}/invite-admin` | Invite tenant admin |
| GET/PATCH | `/v1/admin/llm-baseline` | App LLM baseline template |
| GET/POST/DELETE | `/v1/admin/platform-admins/{user_id}` | Grant/revoke civil1.ai admin |

## Tenant admin APIs

| Method | Path | Purpose |
| --- | --- | --- |
| GET/PATCH | `/v1/tenant/llm-config` | Tenant LLM copy |
| POST | `/v1/tenant/llm/invoke` | Section LLM invoke (loads tenant config server-side) |
| POST | `/v1/tenant/logo` | Presigned logo upload |
| POST | `/v1/users` | Invite user by email (`invite: true` default) |

## Migration scripts

```bash
# Backfill url_slug for legacy tenants
uv run python scripts/backfill_tenant_slugs.py [--dry-run]

# Ensure LLM baseline row exists
uv run python scripts/seed_llm_baseline.py
```

## Infrastructure

OpenTofu modules live under `infra/opentofu/` (Cognito, API Gateway/Lambda IAM, Bedrock policy). Configure remote state in `environments/*/backend.tf` before first apply.

FE hosting: Amplify rewrite `/fstudio/*` → SPA index (`civil-ai-fe/public/_redirects`).
