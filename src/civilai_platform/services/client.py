from civilai_platform.models.api import ClientCreate, ClientResponse, ClientUpdate
from civilai_platform.models.entities import Client, ClientContact, FieldValue, new_id, utc_now
from civilai_platform.services.audit import record_audit
from civilai_platform.store.base import PlatformStore


def _company_key(name: str, address: str) -> tuple[str, str]:
    return (name.strip().lower(), address.strip().lower())


def find_client_by_name_address(
    store: PlatformStore,
    tenant_id: str,
    name: str,
    address: str,
) -> Client | None:
    key = _company_key(name, address)
    if not key[0]:
        return None
    for client in store.list_clients(tenant_id):
        if _company_key(client.name, client.address) == key:
            return client
    return None


def _merge_contacts(
    existing: list[ClientContact],
    incoming: list[ClientContact],
) -> list[ClientContact]:
    by_email: dict[str, ClientContact] = {}
    for contact in existing:
        email = contact.email.strip().lower()
        if email:
            by_email[email] = contact
    for contact in incoming:
        email = contact.email.strip().lower()
        if email:
            by_email[email] = contact
    return list(by_email.values())


def create_client(
    store: PlatformStore,
    *,
    tenant_id: str,
    actor_user_id: str,
    data: ClientCreate,
) -> ClientResponse:
    existing = find_client_by_name_address(store, tenant_id, data.name, data.address)
    if existing:
        return update_client(
            store,
            tenant_id=tenant_id,
            client_id=existing.client_id,
            actor_user_id=actor_user_id,
            data=ClientUpdate(
                name=data.name,
                address=data.address,
                location=data.location or existing.location,
                contacts=_merge_contacts(existing.contacts, data.contacts),
                notes=existing.notes + data.notes,
            ),
        )

    now = utc_now()
    client = Client(
        client_id=new_id(),
        tenant_id=tenant_id,
        name=data.name,
        address=data.address,
        location=data.location,
        contacts=data.contacts,
        notes=data.notes,
        created_by_user_id=actor_user_id,
        created_at=now,
        updated_at=now,
    )
    store.put_client(client)
    record_audit(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="client.create",
        resource_type="client",
        resource_id=client.client_id,
    )
    return ClientResponse.from_entity(client)


def update_client(
    store: PlatformStore,
    *,
    tenant_id: str,
    client_id: str,
    actor_user_id: str,
    data: ClientUpdate,
) -> ClientResponse:
    client = store.get_client(tenant_id, client_id)
    if not client:
        raise ValueError("Client not found")
    updates = data.model_dump(exclude_unset=True)
    updated = client.model_copy(update={**updates, "updated_at": utc_now()})
    store.put_client(updated)
    record_audit(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="client.update",
        resource_type="client",
        resource_id=client_id,
    )
    return ClientResponse.from_entity(updated)


def delete_client(
    store: PlatformStore,
    *,
    tenant_id: str,
    client_id: str,
    actor_user_id: str,
) -> None:
    if not store.get_client(tenant_id, client_id):
        raise ValueError("Client not found")
    store.delete_client(tenant_id, client_id)
    record_audit(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="client.delete",
        resource_type="client",
        resource_id=client_id,
    )


def list_clients(store: PlatformStore, tenant_id: str) -> list[ClientResponse]:
    return [ClientResponse.from_entity(c) for c in store.list_clients(tenant_id)]


def sync_client_fields_to_sections(
    client: Client,
    sections: list,
) -> list:
    """Copy company identity into workflow client step fields."""
    updated = []
    for section in sections:
        if section.step_key != "client":
            updated.append(section)
            continue
        fields = dict(section.fields)
        fields["CLIENT_COMPANY"] = FieldValue(
            value=client.name, status=fields.get("CLIENT_COMPANY", FieldValue()).status
        )
        fields["CLIENT_ADDRESS"] = FieldValue(
            value=client.address, status=fields.get("CLIENT_ADDRESS", FieldValue()).status
        )
        fields["CLIENT_LOCATION"] = FieldValue(
            value=client.location, status=fields.get("CLIENT_LOCATION", FieldValue()).status
        )
        updated.append(section.model_copy(update={"fields": fields}))
    return updated
