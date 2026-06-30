import json
import os
import threading
import uuid
from pathlib import Path

from civilai_platform.models.entities import (
    AuditEvent,
    Client,
    Project,
    ProjectState,
    Tenant,
    TenantMembership,
    UserProfile,
)
from civilai_platform.store.memory import MemoryStore


def _pair_key(tenant_id: str, entity_id: str) -> str:
    return f"{tenant_id}:{entity_id}"


class FileStore(MemoryStore):
    """Disk-backed store for local dev — survives platform API restarts."""

    def __init__(self, root: str) -> None:
        super().__init__()
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._snapshot = self._root / "store.json"
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if not self._snapshot.exists():
            return
        raw = json.loads(self._snapshot.read_text(encoding="utf-8"))
        self._tenants = {
            k: Tenant.model_validate(v) for k, v in raw.get("tenants", {}).items()
        }
        self._profiles = {
            k: UserProfile.model_validate(v) for k, v in raw.get("profiles", {}).items()
        }
        self._memberships = {
            tuple(k.split(":", 1)): TenantMembership.model_validate(v)  # type: ignore[misc]
            for k, v in raw.get("memberships", {}).items()
        }
        self._clients = {
            tuple(k.split(":", 1)): Client.model_validate(v)  # type: ignore[misc]
            for k, v in raw.get("clients", {}).items()
        }
        self._projects = {
            tuple(k.split(":", 1)): Project.model_validate(v)  # type: ignore[misc]
            for k, v in raw.get("projects", {}).items()
        }
        self._states = {
            tuple(k.split(":", 1)): ProjectState.model_validate(v)  # type: ignore[misc]
            for k, v in raw.get("states", {}).items()
        }
        self._audit = [AuditEvent.model_validate(v) for v in raw.get("audit", [])]
        self._platform_admins = set(raw.get("platform_admins", []))

    def _save(self) -> None:
        with self._lock:
            payload = {
                "tenants": {k: v.model_dump(mode="json") for k, v in self._tenants.items()},
                "profiles": {k: v.model_dump(mode="json") for k, v in self._profiles.items()},
                "memberships": {
                    _pair_key(tid, uid): m.model_dump(mode="json")
                    for (tid, uid), m in self._memberships.items()
                },
                "clients": {
                    _pair_key(tid, cid): c.model_dump(mode="json")
                    for (tid, cid), c in self._clients.items()
                },
                "projects": {
                    _pair_key(tid, pid): p.model_dump(mode="json")
                    for (tid, pid), p in self._projects.items()
                },
                "states": {
                    _pair_key(tid, pid): s.model_dump(mode="json")
                    for (tid, pid), s in self._states.items()
                },
                "audit": [e.model_dump(mode="json") for e in self._audit],
                "platform_admins": sorted(self._platform_admins),
            }
            tmp = self._root / f"store.{os.getpid()}.{uuid.uuid4().hex}.tmp"
            try:
                tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                tmp.replace(self._snapshot)
            except OSError:
                raise
            finally:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)

    def put_tenant(self, tenant: Tenant) -> None:
        super().put_tenant(tenant)
        self._save()

    def delete_tenant(self, tenant_id: str) -> None:
        super().delete_tenant(tenant_id)
        self._save()

    def put_user_profile(self, profile: UserProfile) -> None:
        super().put_user_profile(profile)
        self._save()

    def put_membership(self, membership: TenantMembership) -> None:
        super().put_membership(membership)
        self._save()

    def delete_membership(self, tenant_id: str, user_id: str) -> None:
        super().delete_membership(tenant_id, user_id)
        self._save()

    def put_client(self, client: Client) -> None:
        super().put_client(client)
        self._save()

    def delete_client(self, tenant_id: str, client_id: str) -> None:
        super().delete_client(tenant_id, client_id)
        self._save()

    def put_project(self, project: Project) -> None:
        super().put_project(project)
        self._save()

    def delete_project(self, tenant_id: str, project_id: str) -> None:
        super().delete_project(tenant_id, project_id)
        self._save()

    def put_project_state(self, state: ProjectState) -> None:
        super().put_project_state(state)
        self._save()

    def put_audit_event(self, event: AuditEvent) -> None:
        super().put_audit_event(event)
        self._save()

    def set_platform_admin(self, user_id: str, is_admin: bool) -> None:
        super().set_platform_admin(user_id, is_admin)
        self._save()
