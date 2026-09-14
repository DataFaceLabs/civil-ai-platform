> **Brought under version control 2026-09-07** from the workspace root, which is not a
> git repository. Distinct from [`../civil1-ai-dns-dynadot.md`](../civil1-ai-dns-dynadot.md):
> that document covers apex→www forwarding with path preservation; this one is the
> step-by-step Dynadot setup for pointing civil1.ai at the Amplify/CloudFront UAT app.
> They overlap in subject, not in purpose — read both before changing DNS.

# Dynadot DNS setup for civil1.ai → AWS Amplify (UAT)

Domain: **civil1.ai**  
Amplify app: **civilai-fe-uat**  
CloudFront target: **d2516rpjl7se8i.cloudfront.net**

---

## Before you start

1. Log in to Dynadot → **My Domains** → **civil1.ai** → **DNS Settings**
2. DNS type: **Dynadot DNS**
3. **Delete** the current Domain Record if it is **Forward 301 → https://www.civil1.ai**

---

## Record 1 — Domain Record (apex / @)

| Field | Value |
|-------|-------|
| Record Type | **ANAME** |
| Target | `d2516rpjl7se8i.cloudfront.net` |

*(Not Forward — must be ANAME.)*

---

## Record 2 — Subdomain: www

| Field | Value |
|-------|-------|
| Subdomain | `www` |
| Record Type | **CNAME** |
| Target | `d2516rpjl7se8i.cloudfront.net` |

---

## Record 3 — Subdomain: SSL validation (required)

| Field | Value |
|-------|-------|
| Subdomain | `_ac78bbce2871e36d2e0ca4ca83c393aa` |
| Record Type | **CNAME** |
| Target | `_2abf3f88c80641bb1d8bdcf340568fc1.jkddzztszm.acm-validations.aws` |

---

## Save

- TTL: **5 minutes** is fine
- Click **Save Settings**
- Wait **5–30 minutes** (sometimes up to a few hours)

---

## How to know it worked

In **AWS Amplify → civilai-fe-uat → Hosting → Domain management → civil1.ai**:

- SSL configuration → green check
- Domain activation → green check

Then test:

- https://www.civil1.ai
- https://civil1.ai (should redirect to www)

---

## After DNS is live (separate step — not Dynadot)

Cognito login URLs must be updated to include `https://www.civil1.ai` — Ben will handle in platform/terraform.
