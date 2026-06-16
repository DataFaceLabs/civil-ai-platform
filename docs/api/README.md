# Platform API Contracts

This directory will hold platform API contracts for the Civil AI frontend and
agent runtime.

Initial API surface:

- `GET /v1/me`
- `GET /v1/projects`
- `POST /v1/projects`
- `GET /v1/projects/{projectId}`
- `PATCH /v1/projects/{projectId}`
- `GET /v1/projects/{projectId}/sessions`
- `POST /v1/projects/{projectId}/artifacts`
- `POST /v1/projects/{projectId}/share`
- `GET /v1/projects/{projectId}/data/site`
- `POST /v1/projects/{projectId}/agent-runs`
- `GET /v1/projects/{projectId}/agent-runs/{runId}`
- `POST /v1/projects/{projectId}/approvals`

Contracts should define request/response shapes, auth scopes, authorization
rules, audit events, and expected error states.
