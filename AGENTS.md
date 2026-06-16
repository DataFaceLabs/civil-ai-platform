# Civil AI Platform Agent Instructions

This repo owns the Civil AI application backend/platform layer.

## Boundaries

- Put platform APIs, auth, authorization, app state, audit, and IaC here.
- Do not put frontend UI code here.
- Do not put data ingestion/lakehouse transformation code here.
- Do not put agent prompt/eval design here unless it is runtime integration code.

## Canonical References

- Cross-repo architecture: `../civil-ai/docs/architecture/`
- Frontend contracts and UI needs: `../civil-ai-fe/docs/`
- Data lakehouse contracts: `../civil-ai-data/docs/`
- Agent design and evals: `../civil-ai-agent/docs/`

## Security Rules

- Browser clients must never receive AWS credentials.
- API Gateway validates Cognito tokens.
- Lambda services perform tenant/project/action authorization.
- DynamoDB stores small control-plane records.
- S3 stores large uploaded/generated artifacts.
- Athena and data lake access must be mediated through approved backend contracts.
- AgentCore tools must use scoped platform APIs and must not bypass authorization.

## IaC Rules

- Use OpenTofu under `infra/opentofu/`.
- Keep modules small and environment-aware.
- Use least-privilege IAM.
- Add budgets and alarms with customer-facing environments.
- Review plans before apply.
