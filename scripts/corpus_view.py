#!/usr/bin/env python3
"""Local viewer for the agent feedback corpus (S3).

Browse the append-only event stream without Athena / S3 Select:

  # List recent events under a tenant (or project / section)
  AWS_PROFILE=civilai uv run python scripts/corpus_view.py list \\
      --tenant 4e4ec15b-2e6e-4a2e-8bd0-d5b4f40d1263

  # Filter to edits only
  AWS_PROFILE=civilai uv run python scripts/corpus_view.py list \\
      --tenant … --project … --section parcel --type edit

  # Pretty-print one object
  AWS_PROFILE=civilai uv run python scripts/corpus_view.py show \\
      tenant/…/project/…/section/parcel/….json

  # Replay a section's full trajectory (draft → edits → approve)
  AWS_PROFILE=civilai uv run python scripts/corpus_view.py replay \\
      --tenant … --project … --section parcel

Env:
  AWS_PROFILE   (default: civilai)
  CORPUS_BUCKET (default: civilai-agent-corpus-uat)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from typing import Any

import boto3

DEFAULT_BUCKET = os.environ.get("CORPUS_BUCKET", "civilai-agent-corpus-uat")
DEFAULT_PROFILE = os.environ.get("AWS_PROFILE", "civilai")
DEFAULT_REGION = os.environ.get("AWS_REGION", "us-east-1")
EVENT_TYPES = ("draft", "edit", "approve", "reopen")


def _session() -> boto3.Session:
    return boto3.Session(profile_name=DEFAULT_PROFILE, region_name=DEFAULT_REGION)


def _s3():
    return _session().client("s3")


def _prefix(*, tenant: str | None, project: str | None, section: str | None) -> str:
    if not tenant:
        return "tenant/"
    parts = [f"tenant/{tenant}"]
    if project:
        parts.append(f"project/{project}")
        if section:
            parts.append(f"section/{section}")
    elif section:
        raise SystemExit("--section requires --project")
    return "/".join(parts) + ("/" if not parts[-1].endswith("/") else "")


def _parse_key(key: str) -> dict[str, str]:
    """Parse tenant/.../section/.../{millis}__{type}__{id}.json into parts."""
    out: dict[str, str] = {"key": key}
    bits = key.strip("/").split("/")
    try:
        out["tenant_id"] = bits[bits.index("tenant") + 1]
        out["project_id"] = bits[bits.index("project") + 1]
        out["section_id"] = bits[bits.index("section") + 1]
    except (ValueError, IndexError):
        pass
    filename = bits[-1]
    if filename.endswith(".json"):
        stem = filename[: -len(".json")]
        parts = stem.split("__", 2)
        if len(parts) == 3:
            out["millis"], out["event_type"], out["event_id"] = parts
    return out


def list_keys(
    *,
    tenant: str | None,
    project: str | None,
    section: str | None,
    event_type: str | None,
    limit: int,
) -> list[str]:
    prefix = _prefix(tenant=tenant, project=project, section=section)
    keys: list[str] = []
    paginator = _s3().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=DEFAULT_BUCKET, Prefix=prefix):
        for obj in page.get("Contents") or []:
            key = obj["Key"]
            if event_type and f"__{event_type}__" not in key:
                continue
            keys.append(key)
    keys.sort()
    if limit > 0:
        keys = keys[-limit:]
    return keys


def get_event(key: str) -> dict[str, Any]:
    body = _s3().get_object(Bucket=DEFAULT_BUCKET, Key=key)["Body"].read()
    return json.loads(body)


def _clip(text: str | None, n: int = 96) -> str:
    if not text:
        return ""
    one = " ".join(str(text).split())
    return one if len(one) <= n else one[: n - 1] + "…"


def _summarize_row(key: str, rec: dict[str, Any] | None = None) -> str:
    meta = _parse_key(key)
    et = (rec or {}).get("event_type") or meta.get("event_type") or "?"
    section = (rec or {}).get("section_id") or meta.get("section_id") or "?"
    captured = (rec or {}).get("captured_at") or meta.get("millis") or ""
    if rec and et == "draft":
        ic = rec.get("input_context") or {}
        fc = ic.get("field_context") or {}
        ao = rec.get("agent_output") or {}
        detail = (
            f"fields={len(fc)}  "
            f"addr={_clip(fc.get('PROPERTY_ADDRESS'), 40)!r}  "
            f"out={len(ao.get('text') or '')}c  "
            f"entity={rec.get('entity_id')}"
        )
    elif rec:
        detail = f"text={_clip(rec.get('text'), 60)!r}  prev={rec.get('prev_status')}"
    else:
        detail = key
    return f"{captured}  {et:<7}  {section:<14}  {detail}"


def cmd_list(args: argparse.Namespace) -> int:
    keys = list_keys(
        tenant=args.tenant,
        project=args.project,
        section=args.section,
        event_type=args.type,
        limit=args.limit,
    )
    if not keys:
        print(f"(no events under s3://{DEFAULT_BUCKET}/{_prefix(tenant=args.tenant, project=args.project, section=args.section)})")
        return 0
    print(f"bucket={DEFAULT_BUCKET}  count={len(keys)}")
    for key in keys:
        if args.verbose:
            rec = get_event(key)
            print(_summarize_row(key, rec))
            print(f"  {key}")
        else:
            print(_summarize_row(key))
            if args.keys:
                print(f"  {key}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    key = args.key
    if key.startswith("s3://"):
        # s3://bucket/key → key
        without = key[len("s3://") :]
        parts = without.split("/", 1)
        if len(parts) != 2:
            raise SystemExit(f"bad s3 uri: {key}")
        key = parts[1]
    rec = get_event(key)
    if args.summary:
        print(_summarize_row(key, rec))
        if rec.get("event_type") == "draft":
            ic = rec.get("input_context") or {}
            fc = ic.get("field_context") or {}
            print(f"run_id={rec.get('run_id')}  model={rec.get('model')}")
            print(f"proposed_use={ic.get('proposed_use')!r}")
            print("request:")
            print(textwrap.indent(str(ic.get("request") or ""), "  "))
            print(f"field_context ({len(fc)} keys):")
            for k in sorted(fc):
                print(f"  {k}: {_clip(fc[k], 100)}")
            ao = rec.get("agent_output") or {}
            print("agent_output.text:")
            print(textwrap.indent(str(ao.get("text") or ""), "  "))
            print(f"trace_summary={json.dumps(ao.get('trace_summary') or {}, default=str)}")
        else:
            print(f"actor={rec.get('actor_user_id')} role={rec.get('actor_role')}")
            print("text:")
            print(textwrap.indent(str(rec.get("text") or ""), "  "))
        return 0
    print(json.dumps(rec, indent=2, default=str))
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    if not (args.tenant and args.project and args.section):
        raise SystemExit("replay requires --tenant --project --section")
    keys = list_keys(
        tenant=args.tenant,
        project=args.project,
        section=args.section,
        event_type=None,
        limit=0,
    )
    if not keys:
        print("(empty trajectory)")
        return 1
    print(f"trajectory  tenant={args.tenant}  project={args.project}  section={args.section}")
    print(f"events={len(keys)}  bucket={DEFAULT_BUCKET}\n")
    for i, key in enumerate(keys, 1):
        rec = get_event(key)
        et = rec.get("event_type")
        print(f"── {i}/{len(keys)}  {et}  {rec.get('captured_at')} ──")
        print(f"key: {key}")
        print(f"actor_user_id={rec.get('actor_user_id')}  actor_role={rec.get('actor_role')}  entity_id={rec.get('entity_id')}")
        if et == "draft":
            ic = rec.get("input_context") or {}
            fc = ic.get("field_context") or {}
            ao = rec.get("agent_output") or {}
            addr = fc.get("PROPERTY_ADDRESS")
            tcad = fc.get("TCAD_INFO")
            print(f"INITIATE  address={addr!r}")
            print(f"INITIATE  tcad_info={_clip(tcad, 120)!r}")
            print(f"INITIATE  field_context_keys={len(fc)}  sample={sorted(fc)[:8]}")
            print("SECTION PROMPT (request):")
            print(textwrap.indent(str(ic.get("request") or "")[:1500], "  "))
            if len(str(ic.get("request") or "")) > 1500:
                print("  …")
            chat_sys = ic.get("chat_system_prompt") or ""
            chat_instr = ic.get("chat_instructions") or []
            if chat_sys or chat_instr:
                print(f"LAB chat_system_prompt ({len(chat_sys)} chars): {_clip(chat_sys, 160)!r}")
                print(f"LAB chat_instructions ({len(chat_instr)}): {chat_instr[:5]}")
            print(f"AGENT OUTPUT ({len(ao.get('text') or '')} chars):")
            print(textwrap.indent(_clip(ao.get("text"), 500), "  "))
            print(f"trace={json.dumps(ao.get('trace_summary') or {}, default=str)}")
        else:
            print(f"prev_status={rec.get('prev_status')}")
            label = "USER EDIT" if et == "edit" else et.upper() if et else "EVENT"
            print(f"{label} ({len(rec.get('text') or '')} chars):")
            print(textwrap.indent(_clip(rec.get("text"), 500), "  "))
        print()
    # Final state = last event's body text (approve preferred).
    last = get_event(keys[-1])
    print("── FINAL ──")
    print(f"last_event_type={last.get('event_type')}  captured_at={last.get('captured_at')}")
    if last.get("event_type") == "draft":
        text = (last.get("agent_output") or {}).get("text")
    else:
        text = last.get("text")
    print(textwrap.indent(str(text or ""), "  "))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="corpus_view",
        description="Browse civilai-agent-corpus append-only events.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List events under a prefix")
    p_list.add_argument("--tenant")
    p_list.add_argument("--project")
    p_list.add_argument("--section")
    p_list.add_argument("--type", choices=EVENT_TYPES)
    p_list.add_argument("--limit", type=int, default=50, help="Most recent N (0=all)")
    p_list.add_argument("--keys", action="store_true", help="Also print full S3 keys")
    p_list.add_argument("--verbose", "-v", action="store_true", help="Fetch each object for richer rows")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="Print one event JSON (or --summary)")
    p_show.add_argument("key", help="S3 key or s3://bucket/key")
    p_show.add_argument("--summary", action="store_true")
    p_show.set_defaults(func=cmd_show)

    p_replay = sub.add_parser("replay", help="Replay a section trajectory in order")
    p_replay.add_argument("--tenant", required=True)
    p_replay.add_argument("--project", required=True)
    p_replay.add_argument("--section", required=True)
    p_replay.set_defaults(func=cmd_replay)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
