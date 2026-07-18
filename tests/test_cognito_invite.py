"""Tests for Cognito invite password generation and membership activation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from civilai_platform.models.api import UserCreate
from civilai_platform.models.entities import (
    MembershipStatus,
    Role,
    Tenant,
    TenantMembership,
    TenantStatus,
    UserProfile,
    new_id,
    utc_now,
)
from civilai_platform.services import tenant as tenant_svc
from civilai_platform.services import user as user_svc
from civilai_platform.services.cognito import CognitoProvisioner, generate_temporary_password
from civilai_platform.store.memory import MemoryStore


def test_generate_temporary_password_meets_policy() -> None:
    for _ in range(20):
        password = generate_temporary_password()
        assert len(password) >= 10
        assert any(c.isupper() for c in password)
        assert any(c.islower() for c in password)
        assert any(c.isdigit() for c in password)


def test_provision_user_returns_unique_temp_password() -> None:
    provisioner = CognitoProvisioner()
    provisioner._pool_id = "us-east-1_test"
    client = MagicMock()
    client.admin_create_user.return_value = {
        "User": {
            "Username": "user@example.com",
            "Attributes": [{"Name": "sub", "Value": "sub-123"}],
        }
    }
    provisioner._client = client

    sub, temp = provisioner.provision_user(
        email="user@example.com",
        first_name="Ada",
        last_name="Lovelace",
        invite=True,
    )
    assert sub == "sub-123"
    assert temp is not None
    assert temp != "ChangeMe-123!"
    assert len(temp) >= 10
    kwargs = client.admin_create_user.call_args.kwargs
    assert kwargs["TemporaryPassword"] == temp
    assert kwargs["DesiredDeliveryMediums"] == ["EMAIL"]
    assert "MessageAction" not in kwargs


class _UsernameExists(Exception):
    """Stand-in for botocore UsernameExistsException."""


def test_provision_user_reinvites_when_username_exists() -> None:
    provisioner = CognitoProvisioner()
    provisioner._pool_id = "us-east-1_test"
    client = MagicMock()
    client.exceptions.UserNotFoundException = type("UserNotFoundException", (Exception,), {})
    client.admin_create_user.side_effect = [
        _UsernameExists("UsernameExistsException"),
        None,  # RESEND best-effort
    ]
    client.admin_get_user.return_value = {
        "Username": "rs@austincivil.com",
        "UserAttributes": [{"Name": "sub", "Value": "sub-rick"}],
    }
    provisioner._client = client

    sub, temp = provisioner.provision_user(
        email="rs@austincivil.com",
        first_name="Rick",
        last_name="Shurtz",
        invite=True,
    )
    assert sub == "sub-rick"
    assert temp is not None
    client.admin_enable_user.assert_called_once()
    client.admin_set_user_password.assert_called_once()
    assert client.admin_set_user_password.call_args.kwargs["Permanent"] is False
    assert client.admin_set_user_password.call_args.kwargs["Password"] == temp


def test_create_user_reinvites_orphaned_profile_after_delete() -> None:
    """Delete leaves profile + disabled Cognito; re-invite must restore membership."""
    store = MemoryStore()
    now = utc_now()
    tenant_id = new_id()
    user_id = "4428a4b8-f071-706d-a7bc-6c4a22a033bf"
    store.put_tenant(
        Tenant(
            tenant_id=tenant_id,
            name="Austin Civil",
            url_slug="austincivil",
            status=TenantStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    store.put_user_profile(
        UserProfile(
            user_id=user_id,
            email="rs@austincivil.com",
            first_name="Rick",
            last_name="Shurtz",
            created_at=now,
            updated_at=now,
        )
    )
    # No membership — simulates post-delete orphaned profile.

    with patch("civilai_platform.services.user.get_cognito_provisioner") as mock_get:
        provisioner = MagicMock()
        provisioner.get_user_sub.return_value = user_id
        provisioner.reinvite_existing_user.return_value = (user_id, "ReinvitePass1")
        mock_get.return_value = provisioner
        created = user_svc.create_user(
            store,
            tenant_id=tenant_id,
            actor_user_id="actor",
            data=UserCreate(
                email="rs@austincivil.com",
                first_name="Rick",
                last_name="Shurtz",
                role=Role.ADMIN,
                invite=True,
            ),
        )

    assert created.user_id == user_id
    assert created.temporary_password == "ReinvitePass1"
    assert created.status == MembershipStatus.INVITED
    assert store.get_membership(tenant_id, user_id) is not None
    provisioner.reinvite_existing_user.assert_called_once()


def test_get_me_activates_invited_membership() -> None:
    store = MemoryStore()
    now = utc_now()
    tenant_id = new_id()
    user_id = new_id()
    store.put_tenant(
        Tenant(
            tenant_id=tenant_id,
            name="Acme",
            url_slug="acme",
            status=TenantStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    store.put_user_profile(
        UserProfile(
            user_id=user_id,
            email="ada@example.com",
            first_name="Ada",
            last_name="Lovelace",
            created_at=now,
            updated_at=now,
        )
    )
    store.put_membership(
        TenantMembership(
            tenant_id=tenant_id,
            user_id=user_id,
            role=Role.ANALYST,
            status=MembershipStatus.INVITED,
            joined_at=now,
        )
    )

    me = tenant_svc.get_me(store, user_id)
    assert len(me.memberships) == 1
    assert me.memberships[0].status == MembershipStatus.ACTIVE
    assert store.get_membership(tenant_id, user_id).status == MembershipStatus.ACTIVE


def test_create_user_returns_temporary_password_when_cognito_provisions() -> None:
    store = MemoryStore()
    now = utc_now()
    tenant_id = new_id()
    store.put_tenant(
        Tenant(
            tenant_id=tenant_id,
            name="Acme",
            url_slug="acme",
            status=TenantStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    with patch("civilai_platform.services.user.get_cognito_provisioner") as mock_get:
        provisioner = MagicMock()
        provisioner.provision_user.return_value = ("sub-xyz", "TempPass99aa")
        mock_get.return_value = provisioner
        created = user_svc.create_user(
            store,
            tenant_id=tenant_id,
            actor_user_id="actor",
            data=UserCreate(
                email="new@example.com",
                first_name="New",
                last_name="User",
                invite=True,
            ),
        )
    assert created.temporary_password == "TempPass99aa"
    assert created.status == MembershipStatus.INVITED
