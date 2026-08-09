# Amplify Trust Console app (H3-HEALTH / H3-QAUI Stage 3)

Second Amplify **WEB_COMPUTE** app pointing at the same `civil-ai-fe` repo, on a
non-custom `*.amplifyapp.com` URL. Product `civilai-fe` / `www.civil1.ai` stays
untouched as the customer surface.

## Hard isolation (product vs Trust)

| Surface | Product Amplify (`civilai-fe` → civil1.ai) | Trust Amplify (`{env}-civilai-trust-console`) |
|---|---|---|
| `VITE_CIVILAI_TRUST_CONSOLE` | **unset** | `true` |
| `/trust` routes | `notFound()` — no stub, no teaser | Fleet home |
| Workbench nav | **no** Trust Console link | N/A (separate app entry) |
| Default `/` | login / tenant workspace | redirect → `/trust/` |
| Amplify app id | `d3joxyeudajkza` (do not destroy/replace) | separate app id |

Do **not** wire Trust Console into the customer workbench. Same repo is fine;
same Amplify app / civil1.ai hostname is not.

## Locked decisions

- Reuse Explorer (`civil-ai-fe`); **no** new monitor repo, **no** static HTML fleet
- Cognito: share the existing UAT pool; `trust-reviewer` group + dedicated Hosted UI
  app client `civilai-trust-fe-{env}` with trust-app callback/logout URLs
- FE gate: `VITE_CIVILAI_TRUST_CONSOLE=true` only on this Amplify app — product
  builds leave it unset so `/trust` is not exposed on civil1.ai
- Data: browser → platform data-proxy `internal/trust/*` → data API service key →
  S3 `_snapshot_health.json` / `_coverage_matrix.json`

## Module layout

| Path | Role |
|---|---|
| `modules/cognito` | `aws_cognito_user_group.trust_reviewer` |
| `modules/amplify-trust-console/` | Second app + branch + trust env vars + dedicated Cognito client |
| `environments/uat` | `module.amplify_trust` gated by `create_amplify_trust_app` (default **false**) |

## Apply checklist

1. Set `create_amplify_trust_app = true` in local `terraform.tfvars` (gitignored).
2. `tofu plan` — expect **create** of trust Amplify app/branch/IAM + Cognito group
   + trust Hosted UI client. Confirm product `module.amplify` / `d3joxyeudajkza` is
   **not** destroyed or replaced (H0-AMPLIFY).
3. `tofu apply` only after plan review.
4. Invite SMEs into `trust-reviewer`; gate Trust Console routes on group membership
   (FE + optional platform authorizer later).
5. Confirm product Amplify env does **not** set `VITE_CIVILAI_TRUST_CONSOLE`.
6. After the trust default domain is known, add
   `https://develop.<trust-default-domain>` to `cors_origins` if Explorer S3/PMTiles
   needs it (platform API CORS is already `*`).

## Why not a branch on civilai-fe?

Close second option in the hardening plan. Rejected as default because app-level
env inheritance and the customer `develop`→`main` train make it easier to leak
trust routes onto civil1.ai. Separate app keeps the shareable SME URL isolated.
