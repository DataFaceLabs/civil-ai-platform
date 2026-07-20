from mangum import Mangum

from civilai_platform.app import create_app
from civilai_platform.store import get_store

_handler = Mangum(create_app(), lifespan="off")


def handler(event, context):
    if isinstance(event, dict) and event.get("civilai_async") == "complete_export":
        from civilai_platform.services.export import service as export_svc

        get_store.cache_clear()
        export_job = export_svc.complete_export_from_event(get_store(), event)
        return {
            "ok": True,
            "job_id": export_job.job_id if export_job else None,
            "status": export_job.status.value if export_job else None,
        }
    if isinstance(event, dict) and event.get("civilai_async") == "complete_agent_run":
        from civilai_platform.services import agent_run as agent_run_svc

        get_store.cache_clear()
        run = agent_run_svc.complete_agent_run_from_event(get_store(), event)
        return {
            "ok": True,
            "run_id": run.run_id if run else None,
            "status": run.status.value if run else None,
        }
    if isinstance(event, dict) and event.get("civilai_async") == "complete_llm_invoke":
        from civilai_platform.services import llm_invoke as llm_invoke_svc

        get_store.cache_clear()
        job = llm_invoke_svc.complete_llm_invoke_from_event(get_store(), event)
        return {
            "ok": True,
            "job_id": job.job_id if job else None,
            "status": job.status.value if job else None,
        }
    return _handler(event, context)
