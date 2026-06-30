# Platform API Contracts

This directory holds platform API contracts for the Civil AI frontend and
agent runtime. **Distinct from** `civil-ai-data` OpenAPI — see namespace split below.

## Terminology

| Term | Meaning |
|------|---------|
| **Tenant** | Org using Civil AI (e.g. ATX Civil) |
| **Client** | Study subject a tenant runs feasibility work for |
| **Project** | Workbench feasibility study (metadata + workflow state) |

`civil-ai-data` uses **ParcelSnapshot** (`/v1/parcel-snapshots`) for snapshot-pinned
entity collections — not the same as platform **Project**.

## API namespace split

| Service | Workbench / control plane | Data / site facts |
|---------|---------------------------|-------------------|
| Repo | `civil-ai-platform` | `civil-ai-data` |
| Project (study) | `GET/POST /v1/projects`, `PATCH /v1/projects/{id}/state` | — |
| Client (study subject) | `GET/POST/PATCH/DELETE /v1/clients` | — |
| Site payload | — | `POST /v1/fe/site/by-address`, `POST /v1/fe/site/by-parcel` |
| Snapshot pinning | — | `GET/POST /v1/parcel-snapshots`, `POST /v1/parcel-snapshots/{id}/export` |

## Initial API surface

**Identity and tenant**
- `GET /v1/me`
- `GET/PATCH /v1/tenant`
- `GET/POST/PATCH/DELETE /v1/users`
- `POST/GET /v1/admin/tenants`

**Clients (tenant-scoped study subjects)**
- `GET /v1/clients`
- `POST /v1/clients`
- `GET /v1/clients/{clientId}`
- `PATCH /v1/clients/{clientId}`
- `DELETE /v1/clients/{clientId}`

**Projects (workbench feasibility studies)**
- `GET /v1/projects`
- `POST /v1/projects`
- `GET /v1/projects/{projectId}`
- `PATCH /v1/projects/{projectId}`
- `DELETE /v1/projects/{projectId}`
- `GET /v1/projects/{projectId}/state`
- `PATCH /v1/projects/{projectId}/state`
- `GET /v1/projects/{projectId}/sessions`
- `POST /v1/projects/{projectId}/artifacts`
- `POST /v1/projects/{projectId}/share`
- `GET /v1/projects/{projectId}/data/site`
- `POST /v1/projects/{projectId}/agent-runs`
- `GET /v1/projects/{projectId}/agent-runs/{runId}`
- `POST /v1/projects/{projectId}/approvals`

Contracts should define request/response shapes, auth scopes, authorization
rules, audit events, and expected error states. Use `clientId` on project
metadata when a study is linked to a canonical Client record.
