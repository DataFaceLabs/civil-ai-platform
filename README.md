# Civil AI Platform

Civil AI Platform owns the application backend and infrastructure layer for Civil
AI.

It sits between the browser workbench, the data lakehouse, and the agent runtime.
The browser should call platform APIs; it should not directly access AWS data
services, S3 data lake buckets, DynamoDB tables, Athena, Bedrock, or AgentCore.

## Responsibilities

This repo owns:

- Infrastructure as code with OpenTofu.
- Amazon Cognito configuration for user authentication.
- API Gateway and Lambda platform APIs.
- DynamoDB tables for tenants, users, projects, sessions, permissions, and audit metadata.
- S3 app buckets for uploads, generated artifacts, exports, and agent run outputs.
- IAM roles and least-privilege policies for platform services.
- AgentCore orchestration APIs and tool authorization boundaries.
- Platform runbooks, API contracts, and deployment documentation.

This repo does not own:

- Browser UI implementation. That lives in `civil-ai-fe`.
- Data lakehouse ingestion, transformation, Athena DDL, or validation. That lives in `civil-ai-data`.
- Agent behavior design, prompt specs, or eval design. That lives in `civil-ai-agent`.
- Cross-repo architecture decisions. Those live in `civil-ai`.

## Target Architecture

The canonical cross-repo AWS architecture plan lives in
[`civil-ai/docs/architecture/aws-hardened-architecture-plan.md`](https://github.com/DataFaceLabs/civil-ai/blob/main/docs/architecture/aws-hardened-architecture-plan.md).
This repo implements the platform-owned pieces of that plan.

```text
civil-ai-fe
  |
  v
API Gateway + Cognito authorizer
  |
  v
Lambda platform services
  |
  +--> DynamoDB: app control plane
  +--> S3 app buckets: project artifacts
  +--> civil-ai-data: governed lakehouse contracts
  +--> Bedrock / AgentCore: agent runtime and tools
```

## Initial AWS Services

- Amplify Hosting integration outputs for the frontend.
- Cognito user pools and app clients.
- API Gateway HTTP API.
- Lambda functions.
- DynamoDB tables.
- S3 app and Athena result buckets.
- IAM roles and policies.
- CloudWatch logs, alarms, dashboards, and budgets.
- Optional WAF for UAT/customer-facing environments.

## Directory Layout

```text
docs/
  architecture/       platform architecture and ownership
  api/                platform API contracts
  runbooks/           deployment and operations runbooks
infra/
  opentofu/           OpenTofu configuration and modules
```

## Infrastructure As Code

OpenTofu is the planned IaC tool.

Initial layout:

```text
infra/opentofu/
  README.md
  environments/
    dev/
    uat/
    prod/
  modules/
    cognito/
    api-gateway/
    lambda/
    dynamodb/
    s3/
    iam/
    observability/
```

State backend, locking, environment naming, and deployment permissions must be
defined before the first infrastructure apply.

## API Principles

- Authenticate users with Cognito.
- Validate tokens at API Gateway.
- Authorize tenant/project/action access in Lambda.
- Keep project state in DynamoDB and large artifacts in S3.
- Expose stable product APIs to the frontend and agent.
- Hide raw lakehouse and Athena details behind platform/data contracts.
- Audit sensitive reads, shares, exports, approvals, and agent actions.

## Related Repos

- [`civil-ai`](https://github.com/DataFaceLabs/civil-ai): meta repo and canonical architecture.
- [`civil-ai-fe`](https://github.com/DataFaceLabs/civil-ai-fe): frontend workbench.
- [`civil-ai-data`](https://github.com/DataFaceLabs/civil-ai-data): data lakehouse and contracts.
- [`civil-ai-agent`](https://github.com/DataFaceLabs/civil-ai-agent): agent design and evals.
