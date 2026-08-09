# Amplify Trust Console app (H3-HEALTH / H3-QAUI Stage 3)

Second Amplify **WEB_COMPUTE** app pointing at the same `civil-ai-fe` repo, on a
non-custom `*.amplifyapp.com` URL. Product `civilai-fe` / `www.civil1.ai` stays
untouched as the customer surface.

## Hard isolation (product vs Trust)

| Surface | Product Amplify (`civilai-fe` → civil1.ai) | Trust Amplify (`civilai-trust-console`) |
|---|---|---|
| `VITE_CIVILAI_TRUST_CONSOLE` | **unset** | `true` |
| `/trust` routes | `notFound()` — no stub, no teaser | Fleet home |
| Workbench nav | **no** Trust Console link | N/A (separate app entry) |
| Default `/` | login / tenant workspace | redirect → `/trust/` |

Do **not** wire Trust Console into the customer workbench. Same repo is fine;
same Amplify app / civil1.ai hostname is not.

## Locked decisions

- Reuse Explorer (`civil-ai-fe`); **no** new monitor repo, **no** static HTML fleet
- Cognito: share the existing UAT pool; add `trust-reviewer` group (this PR) + a
  dedicated Hosted UI app client with trust-app callback URLs (next infra apply)
- FE gate: `VITE_CIVILAI_TRUST_CONSOLE=true` only on this Amplify app — product
  builds leave it unset so `/trust` is not exposed on civil1.ai
- Data: browser → platform data-proxy `internal/trust/*` → data API service key →
  S3 `_snapshot_health.json` / `_coverage_matrix.json`

## Module layout

| Path | Role |
|---|---|
| `modules/cognito` | `aws_cognito_user_group.trust_reviewer` (shipped this PR) |
| `modules/amplify-trust-console/` | Second app + branch + trust env vars (module sketch; **not** wired into `environments/uat` yet) |

## Wire-up checklist (next apply — do not surprise-apply)

1. Add Cognito app client `civilai-trust-fe-{env}` with callback/logout =
   `https://develop.<trust-app-default-domain>/auth/callback` (and logout URL).
2. Instantiate `module "amplify_trust"` from `modules/amplify-trust-console` with
   `create_amplify_trust_app = true` (new UAT var, default **false** until first
   dry-run plan is reviewed).
3. Invite SMEs into `trust-reviewer`; gate Trust Console routes on group membership
   (FE + optional platform authorizer later).
4. Confirm product Amplify env does **not** set `VITE_CIVILAI_TRUST_CONSOLE`.

## Why not a branch on civilai-fe?

Close second option in the hardening plan. Rejected as default because app-level
env inheritance and the customer `develop`→`main` train make it easier to leak
trust routes onto civil1.ai. Separate app keeps the shareable SME URL isolated.
