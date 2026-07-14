from mangum import Mangum

from civilai_platform.app import create_app
from civilai_platform.store import get_store

_handler = Mangum(create_app(), lifespan="off")


def handler(event, context):
    if isinstance(event, dict) and event.get("civilai_async") == "complete_agent_run":
        from civilai_platform.services import agent_run as agent_run_svc

        get_store.cache_clear()
        run = agent_run_svc.complete_agent_run_from_event(get_store(), event)
        return {
            "ok": True,
            "run_id": run.run_id if run else None,
            "status": run.status.value if run else None,
        }
    return _handler(event, context)
