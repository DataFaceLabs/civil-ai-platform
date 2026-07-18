"""FileStore persistence: derived indexes must survive a reload from disk."""

from __future__ import annotations

from pathlib import Path

from civilai_platform.models.api import TenantCreate
from civilai_platform.services import tenant as tenant_svc
from civilai_platform.store.file import FileStore


def test_slug_index_rebuilt_after_reload(tmp_path: Path) -> None:
    # A fresh FileStore process (server restart) must resolve a tenant by slug, not just
    # by id. Regression for the workspace-load 404: get_tenant_by_slug returned None after
    # reload because _load rehydrated _tenants but not the derived _slug_index.
    root = str(tmp_path / "store")
    writer = FileStore(root)
    tenant = tenant_svc.create_tenant(
        writer, TenantCreate(name="E2E Firm", address="", location="", phone="", fax="")
    )

    reader = FileStore(root)  # simulates a separate server process loading the snapshot
    by_slug = reader.get_tenant_by_slug(tenant.url_slug)
    assert by_slug is not None
    assert by_slug.tenant_id == tenant.tenant_id
    assert reader.get_tenant(tenant.tenant_id) is not None
    assert tenant.url_slug in reader.list_tenant_slugs()
