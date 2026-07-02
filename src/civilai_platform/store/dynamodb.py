import json
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

from civilai_platform.models.entities import (
    AgentRun,
    AuditEvent,
    Client,
    Project,
    ProjectState,
    Tenant,
    TenantMembership,
    UserProfile,
)
from civilai_platform.settings import get_settings
from civilai_platform.store.base import PlatformStore
from civilai_platform.store.keys import (
    ENTITY_TYPE,
    agent_run_sk,
    client_sk,
    gsi1_pk_user,
    gsi1_sk_tenant,
    gsi2_pk_tenant,
    gsi2_sk_audit,
    membership_sk,
    profile_sk,
    project_sk,
    state_sk,
    tenant_meta_sk,
    tenant_pk,
    user_pk,
)


def _serialize(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    return obj


def _deserialize_datetime(val: str) -> datetime:
    return datetime.fromisoformat(val.replace("Z", "+00:00"))


class DynamoDBStore(PlatformStore):
    def __init__(self, table_name: str | None = None) -> None:
        settings = get_settings()
        self._table_name = table_name or settings.dynamodb_table
        resource_kwargs: dict[str, str] = {"region_name": settings.aws_region}
        if settings.dynamodb_endpoint_url:
            resource_kwargs["endpoint_url"] = settings.dynamodb_endpoint_url
            resource_kwargs["aws_access_key_id"] = "local"
            resource_kwargs["aws_secret_access_key"] = "local"
            self._ddb = boto3.resource("dynamodb", **resource_kwargs)
        else:
            session = boto3.Session(
                profile_name=settings.aws_profile,
                region_name=settings.aws_region,
            )
            self._ddb = session.resource("dynamodb")
        self._table = self._ddb.Table(self._table_name)

    def _put(self, pk: str, sk: str, entity_type: str, payload: dict[str, Any], gsi: dict | None = None) -> None:
        item: dict[str, Any] = {
            "PK": pk,
            "SK": sk,
            ENTITY_TYPE: entity_type,
            "payload": json.dumps(_serialize(payload)),
        }
        if gsi:
            item.update(gsi)
        self._table.put_item(Item=item)

    def _get(self, pk: str, sk: str) -> dict[str, Any] | None:
        try:
            resp = self._table.get_item(Key={"PK": pk, "SK": sk})
        except ClientError:
            return None
        return resp.get("Item")

    def _delete(self, pk: str, sk: str) -> None:
        self._table.delete_item(Key={"PK": pk, "SK": sk})

    def put_tenant(self, tenant: Tenant) -> None:
        self._put(tenant_pk(tenant.tenant_id), tenant_meta_sk(), "Tenant", tenant.model_dump())

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        item = self._get(tenant_pk(tenant_id), tenant_meta_sk())
        if not item:
            return None
        return Tenant.model_validate(json.loads(item["payload"]))

    def list_tenants(self) -> list[Tenant]:
        # Scan for META rows — acceptable for platform admin only at low scale
        resp = self._table.scan(
            FilterExpression="SK = :sk AND #et = :et",
            ExpressionAttributeNames={"#et": ENTITY_TYPE},
            ExpressionAttributeValues={":sk": tenant_meta_sk(), ":et": "Tenant"},
        )
        return [Tenant.model_validate(json.loads(i["payload"])) for i in resp.get("Items", [])]

    def delete_tenant(self, tenant_id: str) -> None:
        self._delete(tenant_pk(tenant_id), tenant_meta_sk())

    def put_user_profile(self, profile: UserProfile) -> None:
        self._put(user_pk(profile.user_id), profile_sk(), "UserProfile", profile.model_dump())

    def get_user_profile(self, user_id: str) -> UserProfile | None:
        item = self._get(user_pk(user_id), profile_sk())
        if not item:
            return None
        return UserProfile.model_validate(json.loads(item["payload"]))

    def put_membership(self, membership: TenantMembership) -> None:
        gsi = {
            "GSI1PK": gsi1_pk_user(membership.user_id),
            "GSI1SK": gsi1_sk_tenant(membership.tenant_id),
        }
        self._put(
            tenant_pk(membership.tenant_id),
            membership_sk(membership.user_id),
            "TenantMembership",
            membership.model_dump(),
            gsi,
        )

    def get_membership(self, tenant_id: str, user_id: str) -> TenantMembership | None:
        item = self._get(tenant_pk(tenant_id), membership_sk(user_id))
        if not item:
            return None
        return TenantMembership.model_validate(json.loads(item["payload"]))

    def list_memberships_for_tenant(self, tenant_id: str) -> list[TenantMembership]:
        resp = self._table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
            ExpressionAttributeValues={":pk": tenant_pk(tenant_id), ":prefix": "USER#"},
        )
        return [
            TenantMembership.model_validate(json.loads(i["payload"]))
            for i in resp.get("Items", [])
            if i.get(ENTITY_TYPE) == "TenantMembership"
        ]

    def list_memberships_for_user(self, user_id: str) -> list[TenantMembership]:
        resp = self._table.query(
            IndexName="GSI1",
            KeyConditionExpression="GSI1PK = :pk",
            ExpressionAttributeValues={":pk": gsi1_pk_user(user_id)},
        )
        return [TenantMembership.model_validate(json.loads(i["payload"])) for i in resp.get("Items", [])]

    def delete_membership(self, tenant_id: str, user_id: str) -> None:
        self._delete(tenant_pk(tenant_id), membership_sk(user_id))

    def put_client(self, client: Client) -> None:
        self._put(
            tenant_pk(client.tenant_id),
            client_sk(client.client_id),
            "Client",
            client.model_dump(),
        )

    def get_client(self, tenant_id: str, client_id: str) -> Client | None:
        item = self._get(tenant_pk(tenant_id), client_sk(client_id))
        if not item:
            return None
        return Client.model_validate(json.loads(item["payload"]))

    def list_clients(self, tenant_id: str) -> list[Client]:
        resp = self._table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
            ExpressionAttributeValues={":pk": tenant_pk(tenant_id), ":prefix": "CLIENT#"},
        )
        return [Client.model_validate(json.loads(i["payload"])) for i in resp.get("Items", [])]

    def delete_client(self, tenant_id: str, client_id: str) -> None:
        self._delete(tenant_pk(tenant_id), client_sk(client_id))

    def put_project(self, project: Project) -> None:
        self._put(
            tenant_pk(project.tenant_id),
            project_sk(project.project_id),
            "Project",
            project.model_dump(),
        )

    def get_project(self, tenant_id: str, project_id: str) -> Project | None:
        item = self._get(tenant_pk(tenant_id), project_sk(project_id))
        if not item:
            return None
        return Project.model_validate(json.loads(item["payload"]))

    def list_projects(self, tenant_id: str) -> list[Project]:
        resp = self._table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
            ExpressionAttributeValues={":pk": tenant_pk(tenant_id), ":prefix": "PROJECT#"},
        )
        return [Project.model_validate(json.loads(i["payload"])) for i in resp.get("Items", [])]

    def delete_project(self, tenant_id: str, project_id: str) -> None:
        self._delete(tenant_pk(tenant_id), project_sk(project_id))
        self._delete(tenant_pk(tenant_id), state_sk(project_id))

    def put_project_state(self, state: ProjectState) -> None:
        self._put(
            tenant_pk(state.tenant_id),
            state_sk(state.project_id),
            "ProjectState",
            state.model_dump(),
        )

    def get_project_state(self, tenant_id: str, project_id: str) -> ProjectState | None:
        item = self._get(tenant_pk(tenant_id), state_sk(project_id))
        if not item:
            return None
        return ProjectState.model_validate(json.loads(item["payload"]))

    def put_audit_event(self, event: AuditEvent) -> None:
        iso = event.created_at.isoformat()
        gsi = {
            "GSI2PK": gsi2_pk_tenant(event.tenant_id),
            "GSI2SK": gsi2_sk_audit(iso, event.event_id),
        }
        self._put(
            tenant_pk(event.tenant_id),
            f"AUDIT#{event.event_id}",
            "AuditEvent",
            event.model_dump(),
            gsi,
        )

    def list_audit_events(
        self, tenant_id: str, since: datetime | None = None, limit: int = 100
    ) -> list[AuditEvent]:
        resp = self._table.query(
            IndexName="GSI2",
            KeyConditionExpression="GSI2PK = :pk AND begins_with(GSI2SK, :prefix)",
            ExpressionAttributeValues={":pk": gsi2_pk_tenant(tenant_id), ":prefix": "AUDIT#"},
            ScanIndexForward=False,
            Limit=limit,
        )
        events = [AuditEvent.model_validate(json.loads(i["payload"])) for i in resp.get("Items", [])]
        if since:
            events = [e for e in events if e.created_at >= since]
        return events

    def is_platform_admin(self, user_id: str) -> bool:
        item = self._get(user_pk(user_id), "PLATFORM_ADMIN")
        return item is not None

    def set_platform_admin(self, user_id: str, is_admin: bool) -> None:
        if is_admin:
            self._put(user_pk(user_id), "PLATFORM_ADMIN", "PlatformAdmin", {"user_id": user_id})
        else:
            self._delete(user_pk(user_id), "PLATFORM_ADMIN")

    def put_agent_run(self, run: AgentRun) -> None:
        self._put(
            tenant_pk(run.tenant_id),
            agent_run_sk(run.run_id),
            "AgentRun",
            run.model_dump(),
        )

    def get_agent_run(self, tenant_id: str, project_id: str, run_id: str) -> AgentRun | None:
        item = self._get(tenant_pk(tenant_id), agent_run_sk(run_id))
        if not item:
            return None
        run = AgentRun.model_validate(json.loads(item["payload"]))
        if run.project_id != project_id:
            return None
        return run

    def list_agent_runs(self, tenant_id: str, project_id: str, limit: int = 50) -> list[AgentRun]:
        resp = self._table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
            ExpressionAttributeValues={
                ":pk": tenant_pk(tenant_id),
                ":prefix": "AGENT_RUN#",
            },
            ScanIndexForward=False,
            Limit=limit,
        )
        runs = [AgentRun.model_validate(json.loads(i["payload"])) for i in resp.get("Items", [])]
        return [r for r in runs if r.project_id == project_id]
