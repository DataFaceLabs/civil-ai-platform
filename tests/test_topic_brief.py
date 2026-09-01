"""Tests for Topic Hydrate brief compute (Slice 2)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from civilai_platform.app import create_app
from civilai_platform.models.topic_brief import TopicFieldExtract, ZoningBriefRequest
from civilai_platform.services import guardrails as guardrails_svc
from civilai_platform.services.guardrails_merge import FieldGuardRail
from civilai_platform.services.topic_brief import apply_citation_gate, build_zoning_briefs
from civilai_platform.store import get_store
from civilai_platform.store.memory import MemoryStore
from tests.conftest import bootstrap_client_user

_TEST_SEED_DIR = Path(__file__).resolve().parent / "fixtures" / "facts_guardrails" / "zoning"


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIVILAI_DEV_AUTH", "true")
    monkeypatch.setenv("CIVILAI_STORE_BACKEND", "memory")
    get_store.cache_clear()


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def store() -> MemoryStore:
    return get_store()  # type: ignore[return-value]


def _headers(user_id: str, tenant_id: str | None = None) -> dict[str, str]:
    h = {"X-Dev-User-Id": user_id}
    if tenant_id:
        h["X-Tenant-Id"] = tenant_id
    return h


def test_citation_gate_drops_uncited_and_blocked_fields() -> None:
    fields = [
        TopicFieldExtract(
            fe_code="MAX_BUILDING_HEIGHT",
            value="55 ft",
            section_id="SEC1",
            quote="maximum height 55 feet",
        ),
        TopicFieldExtract(
            fe_code="GREEN_FACTOR_MIN",
            value="0.5",
            section_id=None,
            quote=None,
        ),
        TopicFieldExtract(
            fe_code="IMPERVIOUS_COVER_LIMIT",
            value="70%",
            section_id="SEC2",
            quote="70 percent",
        ),
    ]
    rules = {
        "MAX_BUILDING_HEIGHT": FieldGuardRail(
            llm_extract_allowed=True,
            citation_required=True,
        ),
        "GREEN_FACTOR_MIN": FieldGuardRail(
            llm_extract_allowed=True,
            citation_required=True,
        ),
        "IMPERVIOUS_COVER_LIMIT": FieldGuardRail(
            llm_extract_allowed=False,
            citation_required=True,
            not_applicable=True,
        ),
    }
    gated = apply_citation_gate(fields, rules)
    assert [f.fe_code for f in gated] == ["MAX_BUILDING_HEIGHT"]


class _FakeDataClient:
    def __init__(self) -> None:
        self.retrieve_calls = 0
        self.llm_calls = 0

    def retrieve_regtext(self, body: dict) -> dict:
        self.retrieve_calls += 1
        return {
            "corpus_status": "ready",
            "topics": {
                "height_far": {
                    "topic_id": "height_far",
                    "status": "complete",
                    "sections": [
                        {
                            "section_id": "SEC_HEIGHT",
                            "title": "Height standards",
                            "citation": "SMC 23.47A.012",
                            "excerpt": "Maximum height 55 feet for NC districts.",
                        }
                    ],
                }
            },
        }

    def invoke_llm(self, body: dict) -> dict:
        self.llm_calls += 1
        return {
            "text": json.dumps(
                {
                    "summary": "Height comes from the map designation.",
                    "fields": [
                        {
                            "fe_code": "GREEN_FACTOR_MIN",
                            "value": "0.5",
                            "section_id": "SEC_HEIGHT",
                            "quote": "minimum Green Factor score of 0.5",
                        },
                        {
                            "fe_code": "GREEN_FACTOR_MIN",
                            "value": "0.7",
                            "section_id": None,
                            "quote": None,
                        },
                    ],
                    "citations": [
                        {
                            "section_id": "SEC_HEIGHT",
                            "citation": "SMC 23.47A.012",
                            "quote": "Maximum height 55 feet",
                        }
                    ],
                }
            )
        }


@patch.object(guardrails_svc, "jurisdiction_catalog_ready", return_value=True)
def test_build_briefs_applies_citation_gate(
    _mock_catalog: object,
    store: MemoryStore,
) -> None:
    guardrails_svc.seed_zoning_guardrails_from_yaml(
        store, seed_dir=_TEST_SEED_DIR, refresh=True
    )
    fake = _FakeDataClient()
    response = build_zoning_briefs(
        store,
        ZoningBriefRequest(
            jurisdiction_key="seattle",
            zoning_code="NC2-55 (M)",
            state_abbr="WA",
            county_fips="53033",
            topic_ids=["height_far"],
        ),
        data_client=fake,  # type: ignore[arg-type]
    )
    assert response.topic_hydrate_enabled is True
    assert fake.retrieve_calls == 1
    assert fake.llm_calls == 1
    assert len(response.briefs) == 1
    brief = response.briefs[0]
    assert brief.topic_id == "height_far"
    assert brief.fields
    assert brief.fields[0].fe_code == "GREEN_FACTOR_MIN"
    assert brief.fields[0].value == "0.5"


@patch.object(guardrails_svc, "jurisdiction_catalog_ready", return_value=False)
def test_build_briefs_disabled_when_catalog_not_ready(
    _mock_catalog: object,
    store: MemoryStore,
) -> None:
    guardrails_svc.seed_zoning_guardrails_from_yaml(
        store, seed_dir=_TEST_SEED_DIR, refresh=True
    )
    fake = _FakeDataClient()
    response = build_zoning_briefs(
        store,
        ZoningBriefRequest(
            jurisdiction_key="seattle",
            zoning_code="LR1 (M)",
            state_abbr="WA",
            county_fips="53033",
            topic_ids=["height_far"],
        ),
        data_client=fake,  # type: ignore[arg-type]
    )
    assert response.topic_hydrate_enabled is False
    assert fake.retrieve_calls == 0
    assert fake.llm_calls == 0
    assert response.briefs[0].status == "disabled"


@patch("civilai_platform.api.routes.zoning.DataProxyClient")
@patch.object(guardrails_svc, "jurisdiction_catalog_ready", return_value=True)
def test_zoning_brief_route(
    _mock_catalog: object,
    mock_client_cls: object,
    client: TestClient,
    store: MemoryStore,
) -> None:
    from tests.seed import seed_tenant_member

    guardrails_svc.seed_zoning_guardrails_from_yaml(
        store, seed_dir=_TEST_SEED_DIR, refresh=True
    )
    tenant_id, _ = seed_tenant_member(
        store,
        user_id="brief-user",
        email="brief@example.com",
    )
    bootstrap_client_user(client, "brief-user", email="brief@example.com")
    fake = _FakeDataClient()
    mock_client_cls.return_value = fake

    with patch(
        "civilai_platform.api.routes.zoning.topic_brief_svc.build_zoning_briefs",
        wraps=build_zoning_briefs,
    ):
        res = client.post(
            "/v1/zoning/brief",
            headers=_headers("brief-user", tenant_id),
            json={
                "jurisdiction_key": "seattle",
                "zoning_code": "NC2-55 (M)",
                "state_abbr": "WA",
                "county_fips": "53033",
                "topic_ids": ["height_far"],
            },
        )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["topic_hydrate_enabled"] is True
    assert payload["briefs"][0]["topic_id"] == "height_far"
