#!/usr/bin/env python3
"""UAT corpus trajectory smoke — initiate state → draft → edits → approve.

Verifies that S3 corpus events capture:

  1. Initiate state  = address + parcel/TCAD id + full data-pull blob (field_context)
  2. Sectionwise prompt = input_context.request for each drafted section
  3. Each SME edit     = edit events with the saved body
  4. Final result      = approve event with the approved body

Usage:
  E2E_STAGING_PASSWORD='…' AWS_PROFILE=civilai \\
    uv run python scripts/uat_corpus_smoke.py

Optional:
  E2E_STAGING_EMAIL   (default: bbrennan83@gmail.com)
  CORPUS_BUCKET       (default: civilai-agent-corpus-uat)
  SMOKE_ADDRESS       (default: 20401 Trappers Trail, Manor, TX)
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import boto3
import httpx

API_BASE = os.environ.get(
    "PLATFORM_API_BASE",
    "https://bavy1ysgn0.execute-api.us-east-1.amazonaws.com",
)
USER_POOL_ID = "us-east-1_SQyZR37Ha"
CLIENT_ID = "40o5pkhciavr1qp7h5vgvk8r7u"
CORPUS_BUCKET = os.environ.get("CORPUS_BUCKET", "civilai-agent-corpus-uat")
EMAIL = os.environ.get("E2E_STAGING_EMAIL", "bbrennan83@gmail.com")
PASSWORD = os.environ.get("E2E_STAGING_PASSWORD", "")
AWS_PROFILE = os.environ.get("AWS_PROFILE", "civilai")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
ADDRESS = os.environ.get("SMOKE_ADDRESS", "20401 Trappers Trail, Manor, TX")
PROPOSED_USE = "UAT corpus trajectory — 24-unit multifamily with ground-floor retail"

# Minimum size of a real site data-pull (browser drafts land ~50+ keys).
MIN_FIELD_CONTEXT_KEYS = 20
SECTIONS_TO_DRAFT = ("parcel", "zoning")


def _nonempty(value: object) -> str:
    return str(value or "").strip()


def _session() -> boto3.Session:
    return boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)


def _id_token() -> str:
    if not PASSWORD:
        raise SystemExit("E2E_STAGING_PASSWORD is required")
    cognito = _session().client("cognito-idp")
    resp = cognito.admin_initiate_auth(
        UserPoolId=USER_POOL_ID,
        ClientId=CLIENT_ID,
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": EMAIL, "PASSWORD": PASSWORD},
    )
    return resp["AuthenticationResult"]["IdToken"]


def _api(token: str, tenant_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if tenant_id:
        headers["X-Tenant-Id"] = tenant_id
    return headers


def _pick_tenant(me: dict[str, Any]) -> tuple[str, str]:
    memberships = me.get("memberships") or []
    if not memberships:
        raise SystemExit("no tenant memberships on /v1/me")
    # Prefer a real firm tenant; fall back to whatever we have.
    non_platform = [m for m in memberships if m.get("tenant_slug") not in (None, "", "platform")]
    m = non_platform[0] if non_platform else memberships[0]
    role = m.get("role") or m.get("tenant_role")
    print(f"  memberships={[{'slug': x.get('tenant_slug'), 'role': x.get('role') or x.get('tenant_role'), 'id': x.get('tenant_id')} for x in memberships]}")
    if role and str(role).lower() in {"viewer", "view"}:
        print(f"  ! chosen membership role={role!r} — project create needs Analyst+")
    return m["tenant_id"], m.get("tenant_slug") or m["tenant_id"]


def _list_corpus(prefix: str) -> list[str]:
    s3 = _session().client("s3")
    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=CORPUS_BUCKET, Prefix=prefix):
        for obj in page.get("Contents") or []:
            keys.append(obj["Key"])
    return sorted(keys)


def _get_event(key: str) -> dict[str, Any]:
    s3 = _session().client("s3")
    body = s3.get_object(Bucket=CORPUS_BUCKET, Key=key)["Body"].read()
    return json.loads(body)


def _flatten_site_payload(payload: dict[str, Any]) -> dict[str, str]:
    """Mirror FE collectPromptFieldContext: code → non-empty string value."""
    out: dict[str, str] = {}
    for family in (
        "parcel",
        "zoning",
        "environmental",
        "utilities",
        "access",
        "exhibits",
        "site_context",
    ):
        for view in payload.get(family) or []:
            if not isinstance(view, dict):
                continue
            code = view.get("code")
            if not code:
                continue
            value = view.get("value")
            if value is None:
                continue
            text = str(value).strip()
            if text:
                out[str(code)] = text
    return out


def _section_prompt(section: str, field_context: dict[str, str], guidance: str = "") -> str:
    """Mirror FE buildGeneratePreviewPrompt."""
    lines = [f"{k}: {v}" for k, v in sorted(field_context.items())]
    parts = [f"Generate feasibility language for the {section} section."]
    if lines:
        parts.append("Governed fields:\n" + "\n".join(lines))
    if guidance.strip():
        parts.append(f"Analyst guidance:\n{guidance.strip()}")
    return "\n\n".join(parts)


def _wait_run(
    client: httpx.Client,
    *,
    headers: dict[str, str],
    project_id: str,
    run_id: str,
    timeout_s: float = 300,
) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    latest: dict[str, Any] = {}
    while time.time() < deadline:
        poll = client.get(
            f"{API_BASE}/v1/projects/{project_id}/agent-runs/{run_id}",
            headers=headers,
        )
        poll.raise_for_status()
        latest = poll.json()
        if latest.get("status") in ("succeeded", "failed", "cancelled"):
            return latest
        time.sleep(3)
    raise TimeoutError(f"agent-run {run_id} did not finish in {timeout_s}s")


def _ensure_section(
    sections: list[dict[str, Any]], step_key: str, title: str | None = None
) -> dict[str, Any]:
    for s in sections:
        if s.get("step_key") == step_key or s.get("id") == step_key:
            return s
    sec = {
        "id": step_key,
        "step_key": step_key,
        "title": title or step_key.title(),
        "body": "",
        "status": "draft",
        "fields": {},
    }
    sections.append(sec)
    return sec


def _fail(msg: str) -> int:
    print(f"✗ {msg}")
    return 1


def main() -> int:
    print("=== UAT corpus trajectory smoke ===")
    token = _id_token()
    print("✓ Cognito auth")

    with httpx.Client(timeout=120.0) as client:
        me = client.get(f"{API_BASE}/v1/me", headers=_api(token)).json()
        tenant_id, tenant_slug = _pick_tenant(me)
        print(f"✓ tenant {tenant_slug} ({tenant_id})")
        headers = _api(token, tenant_id)

        # ── 1. Create project ─────────────────────────────────────────────
        project = client.post(
            f"{API_BASE}/v1/projects",
            headers=headers,
            json={
                "name": f"Corpus trajectory {int(time.time())}",
                "address": ADDRESS,
                "jurisdiction": "Travis County, TX",
            },
        )
        if project.status_code >= 400:
            return _fail(f"create project {project.status_code}: {project.text[:500]}")
        project_payload = project.json()
        project_id = project_payload.get("project_id") or project_payload.get("id")
        if not project_id:
            return _fail(f"create project missing id: {project_payload}")
        print(f"✓ project {project_id}")

        # ── 2. Resolve parcel + full data pull (initiate state) ───────────
        resolve = client.post(
            f"{API_BASE}/v1/data-proxy/entities/resolve",
            headers=headers,
            json={"address": ADDRESS},
        )
        resolve.raise_for_status()
        resolved = resolve.json()
        entity_id = (
            resolved.get("entity_id")
            or (resolved.get("candidates") or [{}])[0].get("entity_id")
        )
        if not entity_id:
            # Ambiguous path: try passthrough by-address next.
            print(f"  resolve payload keys={list(resolved.keys())}")
        else:
            print(f"✓ resolved entity_id={entity_id}")

        site_resp = client.post(
            f"{API_BASE}/v1/data-proxy/passthrough/fe/site/by-address",
            headers=headers,
            json={"address": ADDRESS},
        )
        if site_resp.status_code == 409:
            # Ambiguous — pick first candidate and pull by-entity / by-parcel.
            body = site_resp.json()
            candidates = body.get("candidates") or []
            if not candidates:
                return _fail("address ambiguous and no candidates")
            pick = candidates[0]
            entity_id = entity_id or pick.get("entity_id")
            print(f"  ambiguous address; picking entity_id={entity_id}")
            site_resp = client.get(
                f"{API_BASE}/v1/data-proxy/fe/site/by-entity/{entity_id}",
                headers=headers,
            )
        site_resp.raise_for_status()
        site_payload = site_resp.json()
        if entity_id:
            # agent_run falls back to site_payload.entity_id when request omits it
            site_payload = {**site_payload, "entity_id": entity_id}

        field_context = _flatten_site_payload(site_payload)
        # Seed a known PII key so redaction is asserted even if the lake omits it.
        field_context["owner_name"] = "Should Be Redacted"
        field_context.setdefault("PROPERTY_ADDRESS", ADDRESS)
        field_context.setdefault("PROPOSED_DEVELOPMENT", PROPOSED_USE)

        geom = site_payload.get("geometry") or {}
        geom_props = (geom.get("properties") if isinstance(geom, dict) else None) or {}
        parcel_id = geom_props.get("source_parcel_id") or geom_props.get("parcel_id")
        tcad_info = field_context.get("TCAD_INFO", "")

        print(f"✓ data pull  field_context_keys={len(field_context)}")
        print(f"  address={field_context.get('PROPERTY_ADDRESS')!r}")
        print(f"  parcel_id={parcel_id!r}")
        print(f"  tcad_info={tcad_info[:100]!r}")
        if len(field_context) < MIN_FIELD_CONTEXT_KEYS:
            return _fail(
                f"data pull too thin ({len(field_context)} keys < {MIN_FIELD_CONTEXT_KEYS})"
            )

        # Persist site onto project state so entity_id is discoverable.
        state = client.get(
            f"{API_BASE}/v1/projects/{project_id}/state", headers=headers
        ).json()
        sections = list(state.get("sections") or [])
        for step in ("client", "parcel", "zoning", "environmental", "utilities", "access", "exhibits"):
            _ensure_section(sections, step)
        patch = client.patch(
            f"{API_BASE}/v1/projects/{project_id}/state",
            headers=headers,
            json={
                "sections": sections,
                "site_payload": site_payload,
                "proposed_use": PROPOSED_USE,
            },
        )
        patch.raise_for_status()
        print("✓ project state seeded with site_payload")

        # ── 3. Sectionwise agent drafts ───────────────────────────────────
        draft_by_section: dict[str, dict[str, Any]] = {}
        for section in SECTIONS_TO_DRAFT:
            request = _section_prompt(section, field_context)
            run_resp = client.post(
                f"{API_BASE}/v1/projects/{project_id}/agent-runs",
                headers=headers,
                json={
                    "request": request,
                    "active_section_id": section,
                    "workflow": "section_draft",
                    "entity_id": entity_id,
                    "field_context": field_context,
                    "proposed_use": PROPOSED_USE,
                },
            )
            run_resp.raise_for_status()
            run = run_resp.json()
            run_id = run["run_id"]
            print(f"✓ agent-run started section={section} run_id={run_id}")
            final = _wait_run(
                client, headers=headers, project_id=project_id, run_id=run_id
            )
            print(f"  finished status={final.get('status')}")
            if final.get("status") != "succeeded":
                print(json.dumps(final, indent=2, default=str))
                return _fail(f"agent-run failed for {section}")
            draft_by_section[section] = final

        time.sleep(2)

        # ── 4. Assert draft corpus events (initiate + prompts + output) ───
        for section in SECTIONS_TO_DRAFT:
            prefix = f"tenant/{tenant_id}/project/{project_id}/section/{section}/"
            keys = _list_corpus(prefix)
            draft_keys = [k for k in keys if "__draft__" in k]
            if not draft_keys:
                return _fail(f"no draft event under {prefix}")
            draft = _get_event(draft_keys[-1])
            ic = draft.get("input_context") or {}
            fc = ic.get("field_context") or {}
            ao = draft.get("agent_output") or {}
            request = ic.get("request") or ""

            print(f"\n── draft/{section} ──")
            print(f"  key={draft_keys[-1]}")
            print(f"  entity_id={draft.get('entity_id')}")
            print(f"  field_context_keys={len(fc)}")
            print(f"  request_preview={request[:120]!r}…")
            print(f"  output_chars={len(ao.get('text') or '')}")

            if draft.get("event_type") != "draft":
                return _fail(f"{section}: bad event_type")
            if draft.get("schema_version") != 1:
                return _fail(f"{section}: bad schema_version")
            addr = fc.get("PROPERTY_ADDRESS") or ""
            if "trappers" not in addr.lower():
                return _fail(f"{section}: PROPERTY_ADDRESS missing/wrong: {addr!r}")
            if not (fc.get("TCAD_INFO") or parcel_id):
                return _fail(f"{section}: neither TCAD_INFO nor parcel_id present")
            if parcel_id and "870361" not in str(parcel_id) and "870361" not in str(fc.get("TCAD_INFO") or ""):
                # Soft signal only when we know this fixture's prop id.
                print(f"  ! parcel_id unexpected: {parcel_id!r}")
            if len(fc) < MIN_FIELD_CONTEXT_KEYS:
                return _fail(f"{section}: thin field_context ({len(fc)})")
            if fc.get("owner_name") != "[redacted]":
                return _fail(f"{section}: owner_name not redacted ({fc.get('owner_name')!r})")
            section_label = section.replace("_", " ").title()
            if (
                f'drafting the "{section_label}"' not in request
                and f"Draft concise feasibility-study language for the {section} section"
                not in request
            ):
                return _fail(f"{section}: Prompt Lab section prompt missing from request")
            prompt_config = ic.get("prompt_config") or {}
            if not isinstance(prompt_config, dict) or not prompt_config:
                return _fail(f"{section}: prompt_config missing from input_context")
            if prompt_config.get("section_id") != section:
                return _fail(
                    f"{section}: prompt_config.section_id={prompt_config.get('section_id')!r}"
                )
            if not _nonempty(prompt_config.get("rendered_prompt")):
                return _fail(f"{section}: prompt_config.rendered_prompt empty")
            if not _nonempty(prompt_config.get("model_id")):
                return _fail(f"{section}: prompt_config.model_id empty")
            if prompt_config.get("config_version") is None:
                return _fail(f"{section}: prompt_config.config_version missing")
            if not (ao.get("text") or "").strip():
                return _fail(f"{section}: empty agent_output.text")
            if "chat_system_prompt" not in ic:
                return _fail(f"{section}: chat_system_prompt missing from input_context")
            if "chat_instructions" not in ic:
                return _fail(f"{section}: chat_instructions missing from input_context")
            print(
                f"  lab_prompt_chars={len(ic.get('chat_system_prompt') or '')}  "
                f"lab_instructions={len(ic.get('chat_instructions') or [])}  "
                f"prompt_config_version={prompt_config.get('config_version')}  "
                f"model_preset={prompt_config.get('model_preset')!r}"
            )
            if entity_id and draft.get("entity_id") not in (entity_id, None):
                # Prefer exact match; None is a known FE gap we still flag.
                print(f"  ! entity_id mismatch draft={draft.get('entity_id')} expected={entity_id}")
            if entity_id and draft.get("entity_id") != entity_id:
                return _fail(
                    f"{section}: entity_id not captured on draft "
                    f"(got {draft.get('entity_id')!r}, expected {entity_id!r})"
                )
            print(f"✓ {section}: initiate state + section prompt + lab prompts + agent output captured")

        # ── 5. SME edits (two) + approve on parcel ────────────────────────
        state = client.get(
            f"{API_BASE}/v1/projects/{project_id}/state", headers=headers
        ).json()
        sections = list(state.get("sections") or [])
        parcel = _ensure_section(sections, "parcel", "Parcel")
        draft_text = (
            (draft_by_section["parcel"].get("message") or "")
            or ((draft_by_section["parcel"].get("artifacts") or [{}])[0].get("body") or "")
            or "<p>draft</p>"
        )
        # Prefer corpus draft body if message empty / stubby.
        parcel_prefix = f"tenant/{tenant_id}/project/{project_id}/section/parcel/"
        corpus_draft = _get_event(
            [k for k in _list_corpus(parcel_prefix) if "__draft__" in k][-1]
        )
        draft_text = (corpus_draft.get("agent_output") or {}).get("text") or draft_text

        edit1 = draft_text + "\n<p>SME edit #1 — clarify acreage.</p>"
        parcel["body"] = edit1
        parcel["status"] = "in_review"
        client.patch(
            f"{API_BASE}/v1/projects/{project_id}/state",
            headers=headers,
            json={"sections": sections},
        ).raise_for_status()
        print("✓ SME edit #1")

        state = client.get(
            f"{API_BASE}/v1/projects/{project_id}/state", headers=headers
        ).json()
        sections = list(state.get("sections") or [])
        parcel = _ensure_section(sections, "parcel", "Parcel")
        edit2 = edit1 + "\n<p>SME edit #2 — add TCAD valuation note.</p>"
        parcel["body"] = edit2
        parcel["status"] = "in_review"
        client.patch(
            f"{API_BASE}/v1/projects/{project_id}/state",
            headers=headers,
            json={"sections": sections},
        ).raise_for_status()
        print("✓ SME edit #2")

        state = client.get(
            f"{API_BASE}/v1/projects/{project_id}/state", headers=headers
        ).json()
        sections = list(state.get("sections") or [])
        parcel = _ensure_section(sections, "parcel", "Parcel")
        final_body = edit2 + "\n<p>FINAL approved parcel language.</p>"
        parcel["body"] = final_body
        parcel["status"] = "approved"
        client.patch(
            f"{API_BASE}/v1/projects/{project_id}/state",
            headers=headers,
            json={"sections": sections},
        ).raise_for_status()
        print("✓ approve parcel")

        time.sleep(2)

        # ── 6. Assert edit + approve events ───────────────────────────────
        keys = _list_corpus(parcel_prefix)
        edit_keys = [k for k in keys if "__edit__" in k]
        approve_keys = [k for k in keys if "__approve__" in k]
        print(f"\n── parcel trajectory keys ({len(keys)}) ──")
        for k in keys:
            print(f"  {k.split('/')[-1]}")

        if len(edit_keys) < 2:
            return _fail(f"expected ≥2 edit events, got {len(edit_keys)}")
        if len(approve_keys) < 1:
            return _fail("no approve event")

        e1 = _get_event(edit_keys[0])
        e2 = _get_event(edit_keys[1])
        ap = _get_event(approve_keys[-1])
        if "SME edit #1" not in (e1.get("text") or ""):
            return _fail("edit #1 text marker missing")
        if "SME edit #2" not in (e2.get("text") or ""):
            return _fail("edit #2 text marker missing")
        if ap.get("event_type") != "approve":
            return _fail("approve event_type wrong")
        if "FINAL approved parcel language" not in (ap.get("text") or ""):
            return _fail("approve text missing final marker")
        if (ap.get("prev_status") or "") == "approved":
            return _fail("approve prev_status should not already be approved")
        if entity_id:
            for label, rec in (("edit#1", e1), ("edit#2", e2), ("approve", ap)):
                if rec.get("entity_id") != entity_id:
                    return _fail(
                        f"{label} entity_id={rec.get('entity_id')!r}, expected {entity_id!r}"
                    )
        print("✓ edits + approve captured with expected markers + entity_id")

    print("\n=== PASS: initiate + section prompts + edits + final approve ===")
    print(f"replay with:")
    print(
        f"  AWS_PROFILE={AWS_PROFILE} uv run python scripts/corpus_view.py replay "
        f"--tenant {tenant_id} --project {project_id} --section parcel"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
