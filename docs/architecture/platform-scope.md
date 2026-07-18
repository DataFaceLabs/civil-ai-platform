# Platform Scope

`civil-ai-platform` is the application control plane for Civil AI.

It owns the services that make the frontend usable for real customers: identity,
authorization, tenants, clients, projects, sessions, sharing, artifact storage, audit, and agent
orchestration.

The canonical cross-repo AWS architecture plan lives in the `civil-ai` meta repo:

```text
civil-ai/docs/architecture/aws-hardened-architecture-plan.md
```

This repository owns implementation of the platform services described there.

## In Scope

- Cognito user pools, app clients, groups, and federation setup.
- API Gateway routes and authorizers.
- Lambda application services.
- DynamoDB app tables.
- S3 app buckets and presigned artifact access.
- AgentCore orchestration and tool authorization.
- Platform API contracts.
- Infrastructure as code.
- Operational runbooks.

## Out Of Scope

- Frontend rendering and workbench UX.
- Lakehouse source extraction and transformation.
- Athena DDL and service view implementation.
- Agent prompt/eval design as product research artifacts.
- Cross-repo architecture decisions.

## First Milestone

The first platform milestone should prove:

1. Cognito login.
2. `GET /v1/me` profile load.
3. Project list/create/read/update.
4. DynamoDB-backed project session persistence.
5. S3-backed artifact upload/download through presigned URLs.
6. A placeholder agent-run API with status tracking.
7. Audit events for project and artifact actions.
