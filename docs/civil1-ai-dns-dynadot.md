# civil1.ai DNS (Dynadot) — apex forwards to www, preserving paths

## Problem

`www.civil1.ai` points at Amplify/CloudFront and works over HTTPS.

Apex `civil1.ai` is managed by Dynadot forwarding. Without wildcard forwarding, that host:

- 301s to `https://www.civil1.ai` **and drops the path** (`/login` → `/`)

Users who type `civil1.ai/...` therefore get a broken entry path. Chrome may also show confusing security UI depending on cache / mixed content.

## Fix (Dynadot DNS) — saved 2026-07-14

Registrar: **Dynadot** (`ns1.dyna-ns.net` / `ns2.dyna-ns.net`).

In Dynadot DNS settings:

| Section | Record | Value |
|---------|--------|-------|
| Domain Record | `Forward` / `301` | `https://www.civil1.ai/` |
| Advanced option | `Enable wildcard Forwarding` | checked |
| Advanced option | `Enable Domain Variable` | unchecked |
| Subdomain `www` | `CNAME` | `d22adnc428zp0v.cloudfront.net` |
| ACM validation subdomain | `CNAME` | `_2abf3f88c80641bb1d8bdcf340568fc1.jkddzztszm.acm-validations.aws` |

### Amplify

Amplify should only serve `www.civil1.ai`:

- domain association: `www` → branch `develop`
- custom redirects: none required for apex; Dynadot performs apex forwarding

Cognito already allows callbacks/logouts for both `https://civil1.ai/...` and `https://www.civil1.ai/...`.

## Verify

```bash
dig +short www.civil1.ai CNAME

curl -sI https://civil1.ai/login | rg -i '^(HTTP/|location:)'
# HTTP/2 301
# location: https://www.civil1.ai/login

curl -sI http://civil1.ai/fstudio/platform/workspace | rg -i '^(HTTP/|location:)'
# HTTP/1.1 301 Moved Permanently
# location: https://www.civil1.ai/fstudio/platform/workspace

curl -sI https://www.civil1.ai/login | head -3
# HTTP/2 200
```

In Chrome (normal + Incognito), `civil1.ai/...` should redirect to the corresponding `https://www.civil1.ai/...` path and show a normal lock.
