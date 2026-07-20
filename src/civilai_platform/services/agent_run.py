"""Agent run orchestration — invokes Strands agent and persists results."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from civilai_platform.models.entities import AgentRun, AgentRunStatus, new_id, utc_now
from civilai_platform.services import agent_corpus
from civilai_platform.services import artifacts as artifact_svc
from civilai_platform.services import llm_config as llm_config_svc
from civilai_platform.services.agent_prompt import resolve_section_agent_prompt
from civilai_platform.services.audit import record_audit
from civilai_platform.services.project_activity import record_project_activity
from civilai_platform.services.search_policy import resolve_chat_prompts, resolve_search_run_policy
from civilai_platform.store.base import PlatformStore
from civilai_platform.store.keys import agent_run_s3_prefix

logger = logging.getLogger(__name__)

_memory_agent_payloads: dict[str, bytes] = {}


@contextmanager
def _agent_data_api_base(base_url: str | None) -> Iterator[None]:
    """Route both deterministic-pipeline and tool-loop reads for one Lambda invocation."""
    if not base_url:
        yield
        return

    previous = os.environ.get("CIVILAI_DATA_API_BASE")
    os.environ["CIVILAI_DATA_API_BASE"] = base_url
    try:
        # The legacy tool loop caches its client globally; the deterministic pipeline
        # reads the environment afresh. Set both so either execution path is isolated.
        from civilai_agent.tools.data_client import DataApiClient
        from civilai_agent.tools.facts import set_data_client

        set_data_client(DataApiClient(base_url=base_url))
        yield
    finally:
        if previous is None:
            os.environ.pop("CIVILAI_DATA_API_BASE", None)
        else:
            os.environ["CIVILAI_DATA_API_BASE"] = previous
        from civilai_agent.tools.data_client import DataApiClient
        from civilai_agent.tools.facts import set_data_client

        set_data_client(DataApiClient(base_url=previous) if previous else DataApiClient())


def _truthy_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


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
    chat_instructions = (
        tuple(str(item) for item in instructions_raw) if isinstance(instructions_raw, list) else ()
    )

    context = WorkbenchContext(
        project_id=str(context_payload["project_id"]),
        entity_id=context_payload.get("entity_id"),
        active_section_id=context_payload.get("active_section_id"),
        proposed_use=context_payload.get("proposed_use"),
        user_role=str(context_payload.get("user_role", "analyst")),
        request=str(context_payload["request"]),
        client_request=str(context_payload.get("client_request") or ""),
        workflow=workflow,
        field_context=dict(context_payload.get("field_context") or {}),
        tenant_id=context_payload.get("tenant_id"),
        user_id=context_payload.get("user_id"),
        search_run_policy=search_run_policy,
        system_prompt=str(context_payload.get("system_prompt") or ""),
        model_id=context_payload.get("model_id"),
        temperature=context_payload.get("temperature"),
        guardrails=dict(context_payload.get("guardrails") or {}),
        prompt_config=dict(context_payload.get("prompt_config") or {}),
        thread_memory=str(context_payload.get("thread_memory") or ""),
        section_body_plain=str(context_payload.get("section_body_plain") or ""),
        tenant_name=context_payload.get("tenant_name"),
        project_name=context_payload.get("project_name"),
        property_address=context_payload.get("property_address"),
        chat_system_prompt=str(context_payload.get("chat_system_prompt") or ""),
        chat_instructions=chat_instructions,
    )
    with _agent_data_api_base(context_payload.get("_data_api_base")):
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


def _build_context_payload(
    store: PlatformStore,
    *,
    tenant_id: str,
    project_id: str,
    actor_user_id: str,
    request_text: str,
    entity_id: str | None,
    active_section_id: str | None,
    workflow: str | None,
    field_context: dict[str, str] | None,
    proposed_use: str | None,
    thread_memory: str,
    section_body_plain: str,
    mode: str,
    user_guidance: str | None,
    fields_unchanged: bool,
) -> dict[str, Any]:
    tenant_llm_response = llm_config_svc.get_tenant_llm_response(store, tenant_id)
    tenant_llm = tenant_llm_response.config
    tenant = store.get_tenant(tenant_id)
    project = store.get_project(tenant_id, project_id)
    resolved_entity_id = entity_id or _entity_id_from_state(store, tenant_id, project_id)
    resolved_field_context = dict(field_context or {})
    # Canonical spoken address = project.address (covers multi-situs same entity).
    canonical = (project.address or "").strip() if project else ""
    if canonical:
        resolved_field_context["PROPERTY_ADDRESS"] = canonical
    chat_system_prompt, chat_instructions = resolve_chat_prompts(tenant_llm)
    request = request_text
    system_prompt = ""
    model_id = None
    temperature = None
    guardrails: dict[str, Any] = {}
    prompt_config: dict[str, Any] = {}
    if workflow == "section_draft" and active_section_id:
        guidance = request_text if user_guidance is None else user_guidance
        resolved_prompt = resolve_section_agent_prompt(
            tenant_llm,
            config_version=tenant_llm_response.version,
            section_id=active_section_id,
            field_context=resolved_field_context,
            mode="refine" if mode == "refine" else "generate",
            user_guidance=guidance,
            thread_memory=thread_memory,
            section_body_plain=section_body_plain,
            fields_unchanged=fields_unchanged,
        )
        request = resolved_prompt.rendered_prompt
        system_prompt = resolved_prompt.system_prompt
        model_id = resolved_prompt.model_id
        temperature = resolved_prompt.temperature
        guardrails = resolved_prompt.guardrails
        search_run_policy = resolved_prompt.search_run_policy
        prompt_config = resolved_prompt.metadata()
    else:
        search_run_policy = resolve_search_run_policy(
            tenant_llm,
            active_section_id=active_section_id,
            field_context=resolved_field_context,
        )
    return {
        "project_id": project_id,
        "tenant_id": tenant_id,
        "user_id": actor_user_id,
        "request": request,
        "client_request": request_text,
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
        "system_prompt": system_prompt,
        "model_id": model_id,
        "temperature": temperature,
        "guardrails": guardrails,
        "prompt_config": prompt_config,
        "chat_system_prompt": chat_system_prompt,
        "chat_instructions": list(chat_instructions),
        "llm_config": tenant_llm,
    }


def _execute_agent_run(
    store: PlatformStore,
    run: AgentRun,
    context_payload: dict[str, Any],
    *,
    actor_role: str | None,
) -> AgentRun:
    dry_run = _truthy_env("CIVILAI_AGENT_DRY_RUN", "1")
    tenant_llm = context_payload.get("llm_config") or {}
    try:
        response = _invoke_strands_agent(context_payload, dry_run=dry_run)
        prefix = _write_run_artifacts(
            tenant_id=run.tenant_id,
            project_id=run.project_id,
            run_id=run.run_id,
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
        agent_corpus.capture_draft(
            tenant_id=run.tenant_id,
            project_id=run.project_id,
            section_id=run.active_section_id,
            entity_id=context_payload.get("entity_id"),
            actor_user_id=run.actor_user_id,
            actor_role=actor_role,
            run_id=run.run_id,
            field_context=dict(context_payload.get("field_context") or {}),
            request_text=run.request,
            proposed_use=context_payload.get("proposed_use"),
            output_text=response.get("message"),
            trace_summary=dict(response.get("trace_summary") or {}),
            model={
                "preset": (context_payload.get("prompt_config") or {}).get("model_preset")
                or (tenant_llm.get("modelPreset") if isinstance(tenant_llm, dict) else None),
                "model_id": context_payload.get("model_id"),
                "config_version": (context_payload.get("prompt_config") or {}).get(
                    "config_version"
                ),
            },
            chat_system_prompt=str(
                context_payload.get("system_prompt")
                or context_payload.get("chat_system_prompt")
                or ""
            ),
            chat_instructions=list(context_payload.get("chat_instructions") or []),
            prompt_config=dict(context_payload.get("prompt_config") or {}),
        )
        if run.workflow == "section_draft" and run.active_section_id:
            record_project_activity(
                store,
                tenant_id=run.tenant_id,
                project_id=run.project_id,
                actor_user_id=run.actor_user_id,
                event_id=run.run_id,
                event_type="section_draft_created",
                section_id=run.active_section_id,
                content="Section draft generated",
                detail={
                    "run_id": run.run_id,
                    "model_id": context_payload.get("model_id"),
                },
                created_at=completed,
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
        tenant_id=run.tenant_id,
        actor_user_id=run.actor_user_id,
        action="agent.run",
        resource_type="agent_run",
        resource_id=run.run_id,
        detail={"project_id": run.project_id, "status": run.status.value},
    )
    return run


def _enqueue_async_completion(
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    actor_role: str | None,
    context_payload: dict[str, Any],
) -> None:
    """Fire-and-forget self-invoke so API Gateway can return before Bedrock finishes."""
    import boto3

    function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if not function_name:
        raise RuntimeError("AWS_LAMBDA_FUNCTION_NAME unset; cannot enqueue async agent run")

    payload = {
        "civilai_async": "complete_agent_run",
        "tenant_id": tenant_id,
        "project_id": project_id,
        "run_id": run_id,
        "actor_role": actor_role,
        "context_payload": context_payload,
    }
    boto3.client("lambda").invoke(
        FunctionName=function_name,
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8"),
    )


def complete_agent_run_from_event(store: PlatformStore, event: dict[str, Any]) -> AgentRun | None:
    """Worker entrypoint for async Lambda self-invoke events."""
    tenant_id = str(event.get("tenant_id") or "")
    project_id = str(event.get("project_id") or "")
    run_id = str(event.get("run_id") or "")
    if not (tenant_id and project_id and run_id):
        logger.error("complete_agent_run event missing ids: %s", event)
        return None
    run = store.get_agent_run(tenant_id, project_id, run_id)
    if not run:
        logger.error("complete_agent_run missing run %s/%s/%s", tenant_id, project_id, run_id)
        return None
    if run.status in {AgentRunStatus.SUCCEEDED, AgentRunStatus.FAILED, AgentRunStatus.CANCELLED}:
        return run
    context_payload = dict(event.get("context_payload") or {})
    actor_role = event.get("actor_role")
    actor_role_str = str(actor_role) if actor_role is not None else None
    return _execute_agent_run(store, run, context_payload, actor_role=actor_role_str)


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
    mode: str = "generate",
    user_guidance: str | None = None,
    fields_unchanged: bool = False,
    actor_role: str | None = None,
    data_api_base: str | None = None,
) -> AgentRun:
    now = utc_now()
    run_id = new_id()
    prefix = agent_run_s3_prefix(tenant_id, project_id, run_id)
    context_payload = _build_context_payload(
        store,
        tenant_id=tenant_id,
        project_id=project_id,
        actor_user_id=actor_user_id,
        request_text=request_text,
        entity_id=entity_id,
        active_section_id=active_section_id,
        workflow=workflow,
        field_context=field_context,
        proposed_use=proposed_use,
        thread_memory=thread_memory,
        section_body_plain=section_body_plain,
        mode=mode,
        user_guidance=user_guidance,
        fields_unchanged=fields_unchanged,
    )
    if data_api_base:
        context_payload["_data_api_base"] = data_api_base
    run = AgentRun(
        run_id=run_id,
        tenant_id=tenant_id,
        project_id=project_id,
        actor_user_id=actor_user_id,
        status=AgentRunStatus.RUNNING,
        workflow=workflow,
        request=str(context_payload.get("request") or request_text),
        entity_id=context_payload.get("entity_id") or entity_id,
        active_section_id=active_section_id,
        s3_prefix=prefix,
        created_at=now,
        updated_at=now,
    )
    store.put_agent_run(run)

    # Async when explicitly enabled (UAT/prod behind API Gateway's ~29s cap).
    # Local tests stay synchronous so TestClient assertions keep working.
    if _truthy_env("CIVILAI_AGENT_ASYNC", "0"):
        try:
            _enqueue_async_completion(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                actor_role=actor_role,
                context_payload=context_payload,
            )
            return run
        except Exception:
            logger.exception("async enqueue failed; falling back to sync execution")

    return _execute_agent_run(store, run, context_payload, actor_role=actor_role)


def get_agent_run(
    store: PlatformStore,
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
) -> AgentRun | None:
    return store.get_agent_run(tenant_id, project_id, run_id)
