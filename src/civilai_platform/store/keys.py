def tenant_pk(tenant_id: str) -> str:
    return f"TENANT#{tenant_id}"


def user_pk(user_id: str) -> str:
    return f"USER#{user_id}"


def tenant_meta_sk() -> str:
    return "META"


def slug_pk(url_slug: str) -> str:
    return f"SLUG#{url_slug}"


def slug_meta_sk() -> str:
    return "META"


def llm_baseline_pk() -> str:
    return "APP#config"


def llm_baseline_sk() -> str:
    return "LLM_BASELINE"


def tenant_llm_config_sk() -> str:
    return "LLM_CONFIG"


def tenant_logo_s3_key(tenant_id: str, filename: str) -> str:
    safe = filename.replace("/", "_")
    return f"tenant/{tenant_id}/branding/logo/{safe}"


def membership_sk(user_id: str) -> str:
    return f"USER#{user_id}"


def client_sk(client_id: str) -> str:
    return f"CLIENT#{client_id}"


def project_sk(project_id: str) -> str:
    return f"PROJECT#{project_id}"


def state_sk(project_id: str) -> str:
    return f"STATE#{project_id}"


def project_activity_sk(project_id: str, event_id: str) -> str:
    return f"ACTIVITY#{project_id}#{event_id}"


def project_activity_prefix(project_id: str) -> str:
    return f"ACTIVITY#{project_id}#"


def profile_sk() -> str:
    return "PROFILE"


def gsi1_pk_user(user_id: str) -> str:
    return f"USER#{user_id}"


def gsi1_sk_tenant(tenant_id: str) -> str:
    return f"TENANT#{tenant_id}"


def gsi2_pk_tenant(tenant_id: str) -> str:
    return f"TENANT#{tenant_id}"


def gsi2_sk_audit(iso_ts: str, event_id: str) -> str:
    return f"AUDIT#{iso_ts}#{event_id}"


def agent_run_sk(run_id: str) -> str:
    return f"AGENT_RUN#{run_id}"


def agent_run_s3_prefix(tenant_id: str, project_id: str, run_id: str) -> str:
    return f"tenant/{tenant_id}/project/{project_id}/agent-runs/{run_id}/"


def llm_invoke_job_sk(job_id: str) -> str:
    return f"LLM_INVOKE#{job_id}"


ENTITY_TYPE = "entityType"
