# Civil AI Platform Agent Instructions

This repo owns the Civil AI application backend/platform layer.

## Boundaries

- Put platform APIs, auth, authorization, app state, audit, and IaC here.
- Do not put frontend UI code here.
- Do not put data ingestion/lakehouse transformation code here.
- Do not put agent prompt/eval design here unless it is runtime integration code.

## Branching + PRs

Same convention as every repo in this workspace: branch off `develop`
(`feature/*`/`chore/*`/`fix/*`), PR into `develop`; `develop` → `main` only for major
milestones or a real bug fix, never on every merge. Never commit directly to `develop` or
`main`. CI enforces the PR base-branch policy (feature/fix/chore → `develop` only; `main`
only from `release/*`/`hotfix/*`).

Since the 2026-07-18 release migration, this is not just a git convention — `main` is what
`www.civil1.ai` actually serves (Amplify build wired to it), and `develop` is the team's
Basic Auth-gated continuous test space
(`https://develop.d3joxyeudajkza.amplifyapp.com`). See `RELEASE-MIGRATION-PLAN.md` in the
Project-Landmark workspace root for the full mechanics and current phase status. One
caveat specific to this repo: the platform Lambda and EC2 data API have no separate dev
environment yet (that runbook's Phase 6) — `civil-ai/scripts/deploy-uat.sh`'s
`platform`/`data-api` targets deploy straight to the shared, customer-facing backend
regardless of git branch. Treat any backend deploy as production.

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
