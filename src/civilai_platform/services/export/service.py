"""Export-job orchestration: assemble, render, lint, persist, and expose status."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from civilai_platform.models.entities import ExportJob, ExportJobStatus, new_id, utc_now
from civilai_platform.services import artifacts as artifact_svc
from civilai_platform.services.audit import record_audit
from civilai_platform.services.export.context import build_export_context
from civilai_platform.services.export.linter import lint_docx
from civilai_platform.services.export.render import render_docx
from civilai_platform.services.export.skins import get_skin
from civilai_platform.store.base import PlatformStore
from civilai_platform.store.keys import export_job_s3_prefix

logger = logging.getLogger(__name__)


def _truthy_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


def _execute_export(store: PlatformStore, job: ExportJob) -> ExportJob:
    try:
        skin = get_skin(job.skin_id)
        context = build_export_context(
            store,
            tenant_id=job.tenant_id,
            project_id=job.project_id,
            skin_id=skin.id,
            data_api_base=job.data_api_base,
            job_id=job.job_id,
        )
        rendered = render_docx(context, skin)
        findings = lint_docx(rendered, skin)
        key = f"{export_job_s3_prefix(job.tenant_id, job.project_id, job.job_id)}study.docx"
        artifact_svc.store_artifact_bytes(
            key,
            rendered,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        completed = utc_now()
        job = job.model_copy(
            update={
                "status": ExportJobStatus.SUCCEEDED,
                "skin_id": skin.id,
                "docx_s3_key": key,
                "findings": findings,
                "provenance": context.provenance,
                "updated_at": completed,
                "completed_at": completed,
            }
        )
    except Exception as exc:
        logger.exception("export job failed")
        failed = utc_now()
        job = job.model_copy(
            update={
                "status": ExportJobStatus.FAILED,
                "error": str(exc),
                "updated_at": failed,
                "completed_at": failed,
            }
        )

    store.put_export_job(job)
    record_audit(
        tenant_id=job.tenant_id,
        actor_user_id=job.actor_user_id,
        action="export.render",
        resource_type="export_job",
        resource_id=job.job_id,
        detail={
            "project_id": job.project_id,
            "status": job.status.value,
            "skin_id": job.skin_id,
        },
    )
    return job


def _enqueue_async_completion(job: ExportJob) -> None:
    import boto3

    function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if not function_name:
        raise RuntimeError("AWS_LAMBDA_FUNCTION_NAME unset; cannot enqueue async export")
    payload = {
        "civilai_async": "complete_export",
        "tenant_id": job.tenant_id,
        "project_id": job.project_id,
        "job_id": job.job_id,
    }
    boto3.client("lambda").invoke(
        FunctionName=function_name,
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8"),
    )


def start_export(
    store: PlatformStore,
    *,
    tenant_id: str,
    project_id: str,
    actor_user_id: str,
    skin_id: str | None,
    data_api_base: str | None,
) -> ExportJob:
    tenant = store.get_tenant(tenant_id)
    if not tenant:
        raise ValueError("tenant not found")
    skin = get_skin(skin_id or tenant.export_skin)
    now = utc_now()
    job = ExportJob(
        job_id=new_id(),
        tenant_id=tenant_id,
        project_id=project_id,
        actor_user_id=actor_user_id,
        status=ExportJobStatus.RUNNING,
        skin_id=skin.id,
        data_api_base=data_api_base,
        created_at=now,
        updated_at=now,
    )
    store.put_export_job(job)
    if _truthy_env("CIVILAI_EXPORT_ASYNC", "0"):
        try:
            _enqueue_async_completion(job)
            return job
        except Exception:
            logger.exception("async export enqueue failed; falling back to sync execution")
    return _execute_export(store, job)


def complete_export_from_event(store: PlatformStore, event: dict[str, Any]) -> ExportJob | None:
    tenant_id = str(event.get("tenant_id") or "")
    project_id = str(event.get("project_id") or "")
    job_id = str(event.get("job_id") or "")
    if not (tenant_id and project_id and job_id):
        logger.error("complete_export event missing ids: %s", event)
        return None
    job = store.get_export_job(tenant_id, project_id, job_id)
    if not job:
        logger.error("complete_export missing job %s/%s/%s", tenant_id, project_id, job_id)
        return None
    if job.status in {ExportJobStatus.SUCCEEDED, ExportJobStatus.FAILED}:
        return job
    return _execute_export(store, job)


def get_export(
    store: PlatformStore,
    *,
    tenant_id: str,
    project_id: str,
    job_id: str,
) -> ExportJob | None:
    return store.get_export_job(tenant_id, project_id, job_id)
