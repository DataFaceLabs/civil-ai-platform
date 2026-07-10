"""Agent run orchestration — invokes Strands agent and persists results."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from civilai_platform.models.entities import AgentRun, AgentRunStatus, new_id, utc_now
from civilai_platform.services import artifacts as artifact_svc
from civilai_platform.services import llm_config as llm_config_svc
from civilai_platform.services.audit import record_audit
from civilai_platform.services.search_policy import resolve_chat_prompts, resolve_search_run_policy
from civilai_platform.store.base import PlatformStore
from civilai_platform.store.keys import agent_run_s3_prefix

logger = logging.getLogger(__name__)

_memory_agent_payloads: dict[str, bytes] = {}


def _entity_id_from_state(store: PlatformStore, tenant_id: str, project_id: str) -> str | None:
    state = store.get_project_state(tenant_id, project_id)
    if not state:
        return None
    site_payload = state.site_payload
    if isinstance(site_payload, dict):
        raw = site_payload.get("entity_id")
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return None


def _invoke_strands_agent(context_payload: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    try:
        from civilai_agent.models.context import AgentWorkflow, WorkbenchContext
        from civilai_agent.models.search_policy import SearchRunPolicy
        from civilai_agent.runner import run_agent
    except ImportError as exc:
        logger.warning("civilai-agent not installed: %s", exc)
        return {
            "message": "[stub] civilai-agent package not installed on platform runtime.",
            "artifacts": [],
            "trace_summary": {"tools_used": ["stub"]},
            "guardrail_warnings": [],
        }

    workflow_raw = context_payload.get("workflow")
    workflow = AgentWorkflow(workflow_raw) if workflow_raw else None
    policy_raw = context_payload.get("search_run_policy") or {}
    search_run_policy = (
        SearchRunPolicy.model_validate(policy_raw)
        if isinstance(policy_raw, dict)
        else SearchRunPolicy()
    )
    instructions_raw = context_payload.get("chat_instructions") or []
    chat_instructions = tuple(str(item) for item in instructions_raw) if isinstance(instructions_raw, list) else ()

    context = WorkbenchContext(
        project_id=str(context_payload["project_id"]),
        entity_id=context_payload.get("entity_id"),
        active_section_id=context_payload.get("active_section_id"),
        proposed_use=context_payload.get("proposed_use"),
        user_role=str(context_payload.get("user_role", "analyst")),
        request=str(context_payload["request"]),
        workflow=workflow,
        field_context=dict(context_payload.get("field_context") or {}),
        tenant_id=context_payload.get("tenant_id"),
        user_id=context_payload.get("user_id"),
        search_run_policy=search_run_policy,
        thread_memory=str(context_payload.get("thread_memory") or ""),
        section_body_plain=str(context_payload.get("section_body_plain") or ""),
        tenant_name=context_payload.get("tenant_name"),
        project_name=context_payload.get("project_name"),
        property_address=context_payload.get("property_address"),
        chat_system_prompt=str(context_payload.get("chat_system_prompt") or ""),
        chat_instructions=chat_instructions,
    )
    response = run_agent(context, dry_run=dry_run)
    return response.model_dump(mode="json")


def _write_run_artifacts(
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    request: dict[str, Any],
    response: dict[str, Any],
) -> str:
    prefix = agent_run_s3_prefix(tenant_id, project_id, run_id)
    request_key = f"{prefix}request.json"
    response_key = f"{prefix}response.json"
    trace_key = f"{prefix}trace.jsonl"

    request_bytes = json.dumps(request, indent=2).encode("utf-8")
    response_bytes = json.dumps(response, indent=2).encode("utf-8")
    trace_lines = []
    trace_summary = response.get("trace_summary") or {}
    for tool in trace_summary.get("tools_used") or []:
        trace_lines.append(json.dumps({"event": "tool", "tool": tool}))
    trace_bytes = "\n".join(trace_lines).encode("utf-8")

    artifact_svc.store_memory_artifact(request_key, request_bytes)
    artifact_svc.store_memory_artifact(response_key, response_bytes)
    artifact_svc.store_memory_artifact(trace_key, trace_bytes)
    _memory_agent_payloads[request_key] = request_bytes
    _memory_agent_payloads[response_key] = response_bytes
    _memory_agent_payloads[trace_key] = trace_bytes
    return prefix


def start_agent_run(
    store: PlatformStore,
    *,
    tenant_id: str,
    project_id: str,
    actor_user_id: str,
    request_text: str,
    entity_id: str | None = None,
    active_section_id: str | None = None,
    workflow: str | None = None,
    field_context: dict[str, str] | None = None,
    proposed_use: str | None = None,
    thread_memory: str = "",
    section_body_plain: str = "",
) -> AgentRun:
    now = utc_now()
    run_id = new_id()
    prefix = agent_run_s3_prefix(tenant_id, project_id, run_id)
    run = AgentRun(
        run_id=run_id,
        tenant_id=tenant_id,
        project_id=project_id,
        actor_user_id=actor_user_id,
        status=AgentRunStatus.RUNNING,
        workflow=workflow,
        request=request_text,
        entity_id=entity_id,
        active_section_id=active_section_id,
        s3_prefix=prefix,
        created_at=now,
        updated_at=now,
    )
    store.put_agent_run(run)

    tenant_llm = llm_config_svc.get_tenant_llm_response(store, tenant_id).config
    tenant = store.get_tenant(tenant_id)
    project = store.get_project(tenant_id, project_id)
    resolved_entity_id = entity_id or _entity_id_from_state(store, tenant_id, project_id)
    resolved_field_context = field_context or {}
    search_run_policy = resolve_search_run_policy(
        tenant_llm,
        active_section_id=active_section_id,
        field_context=resolved_field_context,
    )
    chat_system_prompt, chat_instructions = resolve_chat_prompts(tenant_llm)

    context_payload: dict[str, Any] = {
        "project_id": project_id,
        "tenant_id": tenant_id,
        "user_id": actor_user_id,
        "request": request_text,
        "entity_id": resolved_entity_id,
        "active_section_id": active_section_id,
        "workflow": workflow,
        "field_context": resolved_field_context,
        "proposed_use": proposed_use,
        "user_role": "analyst",
        "thread_memory": thread_memory,
        "section_body_plain": section_body_plain,
        "tenant_name": tenant.name if tenant else None,
        "project_name": project.name if project else None,
        "property_address": project.address if project else None,
        "search_run_policy": search_run_policy,
        "chat_system_prompt": chat_system_prompt,
        "chat_instructions": list(chat_instructions),
        "llm_config": tenant_llm,
    }

    dry_run = os.getenv("CIVILAI_AGENT_DRY_RUN", "1").strip().lower() in {"1", "true", "yes"}

    try:
        response = _invoke_strands_agent(context_payload, dry_run=dry_run)
        prefix = _write_run_artifacts(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            request=context_payload,
            response=response,
        )
        completed = utc_now()
        run = run.model_copy(
            update={
                "status": AgentRunStatus.SUCCEEDED,
                "message": response.get("message"),
                "artifacts": list(response.get("artifacts") or []),
                "trace_summary": dict(response.get("trace_summary") or {}),
                "guardrail_warnings": list(response.get("guardrail_warnings") or []),
                "s3_prefix": prefix,
                "updated_at": completed,
                "completed_at": completed,
            }
        )
    except Exception as exc:
        logger.exception("agent run failed")
        failed = utc_now()
        run = run.model_copy(
            update={
                "status": AgentRunStatus.FAILED,
                "error": str(exc),
                "updated_at": failed,
                "completed_at": failed,
            }
        )

    store.put_agent_run(run)
    record_audit(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="agent.run",
        resource_type="agent_run",
        resource_id=run_id,
        detail={"project_id": project_id, "status": run.status.value},
    )
    return run


def get_agent_run(
    store: PlatformStore,
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
) -> AgentRun | None:
    return store.get_agent_run(tenant_id, project_id, run_id)
