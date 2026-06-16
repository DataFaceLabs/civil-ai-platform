# OpenTofu Infrastructure

OpenTofu is the planned infrastructure as code tool for Civil AI Platform.

This directory will contain environment definitions and reusable AWS modules.

Planned layout:

```text
infra/opentofu/
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

Before first apply, define:

- AWS account and region strategy.
- Remote state backend.
- State locking.
- Naming convention.
- Tagging convention.
- IAM permissions for plan/apply.
- Secret handling.
- Environment promotion process.
