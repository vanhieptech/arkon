"""Unit tests for agent_kb_service (Wave A filters and snippets)."""

from types import SimpleNamespace

import pytest

from app.services import agent_kb_service as svc


def _page(*, slug: str, title: str, summary: str = "", content_md: str = ""):
    return SimpleNamespace(
        slug=slug,
        title=title,
        summary=summary,
        content_md=content_md,
        knowledge_type_slugs=["architecture"],
        page_type="concept",
    )


def test_expand_search_query_channel():
    assert "policy" in svc.expand_search_query("T24 rollout", "policy").lower()
    assert svc.expand_search_query("foo", None) == "foo"
    assert svc.expand_search_query("  bar  ", "") == "bar"


def test_infer_systems_from_slug():
    systems = svc.infer_systems_from_slug("system/payment/integration")
    assert "payment" in systems


def test_infer_doc_type_from_title():
    page = _page(slug="x", title="Policy :: Payment rollout")
    assert svc.infer_doc_type(page) == "Policy"


def test_build_snippet_prefers_long_summary():
    page = _page(slug="a", title="A", summary="x" * 150)
    assert len(svc.build_snippet(page, "query")) == 150


def test_build_snippet_falls_back_to_content():
    page = _page(
        slug="integration/payment-t24",
        title="Edge",
        summary="short",
        content_md="## Overview\n\nPayment connects to T24 core for settlement.\n\n## More\n\nOther.",
    )
    snippet = svc.build_snippet(page, "T24 payment")
    assert "T24" in snippet or "Payment" in snippet


def test_hit_passes_filters_systems():
    page = _page(slug="system/t24/overview", title="T24", summary="")
    filters = svc.SearchFilters(systems=("t24",))
    assert svc.hit_passes_filters(page, 0.9, filters)
    filters_miss = svc.SearchFilters(systems=("dwh",))
    assert not svc.hit_passes_filters(page, 0.9, filters_miss)


def test_hit_passes_filters_doc_type():
    page = _page(slug="p", title="Policy :: Gate", summary="")
    assert svc.hit_passes_filters(
        page, 0.5, svc.SearchFilters(doc_type="Policy")
    )
    assert not svc.hit_passes_filters(
        page, 0.5, svc.SearchFilters(doc_type="FSD")
    )


def test_wiki_hit_dict_shape():
    page = _page(slug="system/payment", title="Payment hub", summary="Hub text")
    hit = svc.wiki_hit_dict(page, 0.82, query="payment")
    assert hit["source_ref"] == "arkon:wiki:system/payment"
    assert hit["rank"] == 82
    assert "snippet" in hit
    assert hit["metadata"]["slug"] == "system/payment"


def test_fetch_top_k_overfetch_when_filtered():
    assert svc._fetch_top_k(5, svc.SearchFilters(systems=("t24",))) == 30
    assert svc._fetch_top_k(20, svc.SearchFilters()) == 20
    assert svc._fetch_top_k(5, svc.SearchFilters(), hybrid=True) == 30


def test_rrf_merge_fuses_overlapping_slugs():
    p1 = _page(slug="system/t24", title="T24")
    p2 = _page(slug="system/payment", title="Payment")
    merged = svc.rrf_merge([(p1, 0.9), (p2, 0.7)], [(p2, 0.8), (p1, 0.6)])
    slugs = [str(getattr(p, "slug")) for p, _ in merged]
    assert slugs == ["system/t24", "system/payment"] or slugs == ["system/payment", "system/t24"]
    assert len(merged) == 2


def test_relaxed_filters_keeps_channel():
    f = svc.SearchFilters(systems=("t24",), doc_type="Policy", channel="arch")
    relaxed = svc.relaxed_filters(f)
    assert relaxed.systems == ()
    assert relaxed.doc_type is None
    assert relaxed.channel == "arch"


def test_apply_post_filters_strict_vs_relaxed():
    t24 = _page(slug="system/t24/overview", title="T24", summary="")
    payment = _page(slug="system/payment/hub", title="Payment", summary="")
    raw = [(t24, 0.9), (payment, 0.8)]
    strict = svc.SearchFilters(systems=("dwh",))
    assert svc.apply_post_filters(raw, strict, 5) == []
    relaxed = svc.relaxed_filters(strict)
    out = svc.apply_post_filters(raw, relaxed, 5)
    assert len(out) == 2


@pytest.mark.asyncio
async def test_search_wiki_hits_empty_when_embed_missing(monkeypatch):
    class FakeSession:
        pass

    async def no_embed(_db, _q):
        return None

    async def spec_id(_db):
        return None

    monkeypatch.setattr(svc, "embed_search_query", no_embed)
    monkeypatch.setattr(svc, "active_embedding_spec_id", spec_id)

    identity = SimpleNamespace(
        is_admin=True,
        allowed_knowledge_types=[],
        department_ids=[],
        project_ids=[],
    )
    out = await svc.search_wiki_hits(
        FakeSession(), identity, "T24", debug=True
    )
    assert out["hits"] == []
    assert out["debug"]["empty_reason"] == "embedding_not_configured"


@pytest.mark.asyncio
async def test_search_wiki_hits_filter_relaxed(monkeypatch):
    t24 = _page(slug="system/t24/overview", title="T24", summary="")
    payment = _page(slug="system/payment", title="Pay", summary="")

    async def fake_embed(_db, _q):
        return [0.1, 0.2]

    async def fake_spec(_db):
        return "spec-1"

    async def fake_semantic(_db, _id, _emb, top_k):
        return [(t24, 0.9), (payment, 0.8)]

    async def fake_keyword(*_a, **_k):
        return []

    monkeypatch.setattr(svc, "embed_search_query", fake_embed)
    monkeypatch.setattr(svc, "active_embedding_spec_id", fake_spec)
    monkeypatch.setattr(svc, "semantic_search_pages", fake_semantic)
    monkeypatch.setattr(svc, "keyword_search_pages", fake_keyword)

    identity = SimpleNamespace(
        is_admin=True,
        allowed_knowledge_types=[],
        department_ids=[],
        project_ids=[],
    )
    out = await svc.search_wiki_hits(
        object(),
        identity,
        "T24",
        systems="dwh",
        debug=True,
    )
    assert len(out["hits"]) == 2
    assert out["debug"]["filter_relaxed"] is True


@pytest.mark.asyncio
async def test_search_wiki_hits_hybrid_sets_legs(monkeypatch):
    page = _page(slug="system/t24", title="T24", summary="")

    async def fake_embed(_db, _q):
        return [0.1]

    async def fake_spec(_db):
        return "spec-1"

    async def fake_semantic(_db, _id, _emb, top_k):
        return [(page, 0.9)]

    async def fake_keyword(_db, _id, _q, top_k):
        return [(page, 0.5)]

    monkeypatch.setattr(svc, "embed_search_query", fake_embed)
    monkeypatch.setattr(svc, "active_embedding_spec_id", fake_spec)
    monkeypatch.setattr(svc, "semantic_search_pages", fake_semantic)
    monkeypatch.setattr(svc, "keyword_search_pages", fake_keyword)

    identity = SimpleNamespace(
        is_admin=True,
        allowed_knowledge_types=[],
        department_ids=[],
        project_ids=[],
    )
    out = await svc.search_wiki_hits(
        object(),
        identity,
        "T24 rollback",
        hybrid=True,
        debug=True,
    )
    assert out["debug"]["hybrid"] is True
    assert out["debug"]["legs"]["vector"] == 1
    assert out["debug"]["legs"]["keyword"] == 1
    assert len(out["hits"]) >= 1
