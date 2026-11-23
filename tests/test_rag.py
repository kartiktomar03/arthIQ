import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.embedding_service import EmbeddingUnavailable, MiniLMEmbedder
from backend.llm import GroqSQLGenerator
from backend.main import create_app
from backend.models import QueryFailure
from backend.relationship_graph import RelationshipGraph, UnresolvedJoin
from backend.schema_context import ForeignKey, SchemaSnapshot
from backend.schema_discovery import build_snapshot
from backend.schema_indexer import SchemaIndexer, documents_for
from backend.schema_retriever import SchemaRetriever, contains, terms
from backend.vector_store import QdrantSchemaStore, VectorHit, VectorUnavailable
from tests.test_api import StubDatabase, StubLLM, request
from tests.test_policy import TOP_PRODUCTS

CATALOG = {
    "customers": {"id": "integer", "name": "character varying", "region": "character varying"},
    "orders": {"id": "integer", "customer_id": "integer", "status": "character varying"},
    "order_items": {"order_id": "integer", "product_id": "integer", "quantity": "integer", "unit_price": "numeric"},
    "products": {"id": "integer", "name": "character varying", "category_id": "integer", "list_price": "numeric"},
    "categories": {"id": "integer", "name": "character varying"},
}
EDGES = (
    ForeignKey("orders", "customers", (("customer_id", "id"),)),
    ForeignKey("order_items", "orders", (("order_id", "id"),)),
    ForeignKey("order_items", "products", (("product_id", "id"),)),
    ForeignKey("products", "categories", (("category_id", "id"),)),
)
SNAPSHOT = SchemaSnapshot(CATALOG, {"order_items": ("order_id", "product_id")}, EDGES)


class FakeEmbedder:
    identity = "fixture-v1"

    def __init__(self):
        self.batches = []

    def encode(self, texts):
        self.batches.append(texts)
        return [[1.0, 0.0] for _ in texts]


@pytest.fixture
def rag():
    store = QdrantSchemaStore(":memory:")
    model = FakeEmbedder()
    indexer = SchemaIndexer(model, store, "fixture")
    retriever = SchemaRetriever(indexer, 4, 0.43)
    try:
        yield store, model, retriever
    finally:
        store.close()


def test_fingerprint_ignores_mapping_order_and_detects_metadata_changes():
    reverse = SchemaSnapshot(dict(reversed(tuple(CATALOG.items()))), SNAPSHOT.primary_keys, tuple(reversed(EDGES)))
    changed = SchemaSnapshot(CATALOG, SNAPSHOT.primary_keys, EDGES[:-1])
    assert reverse.fingerprint() == SNAPSHOT.fingerprint()
    assert changed.fingerprint() != SNAPSHOT.fingerprint()


def test_authorized_discovery_keeps_only_complete_visible_keys():
    def row(oid, kind, source, target, left, right, ordinal):
        return dict(oid=oid, contype=kind, source=source, target=target,
                    source_column=left, target_column=right, ordinality=ordinal)

    snapshot = build_snapshot(
        {"orders": {"id": "integer", "customer_id": "integer"},
         "customers": {"id": "integer"}},
        [
            row(1, "p", "orders", None, "id", None, 1),
            row(2, "f", "orders", "customers", "customer_id", "id", 1),
            row(3, "f", "orders", "customers", "customer_id", "id", 1),
            row(3, "f", "orders", "customers", "id", "private_key", 2),
            row(4, "f", "orders", "secret", "id", "id", 1),
        ],
    )
    assert snapshot.primary_keys == {"orders": ("id",)}
    assert snapshot.foreign_keys == (EDGES[0],)
    assert all("secret" not in doc.text and "private_key" not in doc.text for doc in documents_for(snapshot))


def test_discovery_preserves_composite_key_order():
    rows = [
        dict(oid=1, contype="p", source="order_items", target=None,
             source_column=column, target_column=None, ordinality=ordinal)
        for ordinal, column in [(2, "product_id"), (1, "order_id")]
    ]
    assert build_snapshot(CATALOG, rows).primary_keys == {"order_items": ("order_id", "product_id")}


def test_local_qdrant_persists_and_replaces_only_current_datasource(tmp_path):
    store = QdrantSchemaStore(tmp_path / "vectors")
    second = None
    try:
        model = FakeEmbedder()
        retriever = SchemaRetriever(SchemaIndexer(model, store, "fixture"), 4, 0.43)
        version, count = retriever.index(SNAPSHOT)
        assert count == len(documents_for(SNAPSHOT))
        assert len(model.batches) >= 2 and all(len(batch) <= 16 for batch in model.batches)
        assert store.search("fixture", version, [1.0, 0.0], 4)
        assert store.search("different", version, [1.0, 0.0], 4) == []
        store.close()

        second = QdrantSchemaStore(tmp_path / "vectors")
        model = FakeEmbedder()
        restarted = SchemaRetriever(SchemaIndexer(model, second, "fixture"), 4, 0.43)
        assert restarted.index(SNAPSHOT) == (version, count)
        assert model.batches == []
        assert restarted.index(SNAPSHOT, force=True) == (version, count)
        assert model.batches
        other = SchemaRetriever(SchemaIndexer(model, second, "different"), 4, 0.43)
        other.index(SNAPSHOT)
        new, new_count = restarted.index(SchemaSnapshot({"products": {"name": "character varying"}}))
        assert new != version and new_count == 2
        assert second.count("fixture", version) == 0
        assert second.count("different", version) == count
        restarted.index(SchemaSnapshot({}))
        assert second.count("fixture", new) == 0
    finally:
        store.close()
        if second:
            second.close()


def test_keyword_retrieval_keeps_revenue_context_narrow(rag):
    _, _, retriever = rag
    result = retriever.retrieve("Which customers generated the highest revenue?", SNAPSHOT)
    assert set(result.context.catalog) == {"customers", "orders", "order_items"}
    assert "completed orders only" in result.context.describe()
    assert len(result.context.relationships) == 2
    assert result.diagnostics.document_count == len(result.diagnostics.sources) > 0
    assert all(source.table in result.context.catalog for source in result.diagnostics.sources)
    assert contains(terms("Revenue by categories"), "category")
    assert not contains(terms("The reorder point"), "orders")


@pytest.mark.parametrize("metric", ["total spending", "amount spent", "sales value", "revenue", "total spend"])
def test_customer_ranking_uses_same_glossary_metric_and_fk_paths(rag, metric):
    _, _, retriever = rag
    result = retriever.retrieve(f"Show the top 3 customers by {metric} on completed orders.", SNAPSHOT)
    assert set(result.context.catalog) == {"customers", "orders", "order_items"}
    assert set(result.context.relationships) == set(EDGES[:2])
    assert [term.name for term in result.context.terms] == ["revenue"]
    assert "orders.status = 'completed'" in result.context.describe()


def test_revenue_requires_its_authorized_foreign_key(rag):
    _, _, retriever = rag
    without_order_link = SchemaSnapshot(CATALOG, foreign_keys=(EDGES[0], *EDGES[2:]))
    assert all(doc.source_type != "business_term" for doc in documents_for(without_order_link))
    with pytest.raises(QueryFailure, match="fields or join") as error:
        retriever.retrieve("Show product revenue", without_order_link)
    assert error.value.code == "schema_clarification"


def test_semantic_scores_rank_competing_exact_entities_and_are_used_without_keywords(rag, monkeypatch):
    store, _, retriever = rag
    monkeypatch.setattr(store, "search", lambda *_: [
        VectorHit("table:products", 0.8), VectorHit("table:customers", 0.45),
        VectorHit("table:invented", 1.0),
    ])
    result = retriever.retrieve("List the merchandise records", SNAPSHOT)
    assert result.selected == ("products",)
    assert retriever.retrieve("What can we offer?", SNAPSHOT).selected == ("products",)
    result = retriever.retrieve("List products and customers", SNAPSHOT)
    assert result.selected == ("products", "customers")


def test_multihop_expansion_and_actual_join_edges(rag):
    _, _, retriever = rag
    result = retriever.retrieve("Which products did the customer buy?", SNAPSHOT)
    assert set(result.selected) == {"products", "customers"}
    assert set(result.context.catalog) == {"customers", "orders", "order_items", "products"}
    assert set(result.context.relationships) == set(EDGES[:3])
    assert result.diagnostics.expanded


def test_graph_refuses_ambiguous_and_disconnected_paths():
    alternate = ForeignKey("order_items", "products", (("order_id", "id"),))
    graph = RelationshipGraph(SchemaSnapshot(CATALOG, foreign_keys=EDGES + (alternate,)))
    with pytest.raises(UnresolvedJoin, match="equally short"):
        graph.path("customers", "products")
    with pytest.raises(UnresolvedJoin, match="No authorized"):
        graph.path("products", "unlisted")


@pytest.mark.parametrize("query", ["How?", "Which customers are best?", "Show the top 3 customers with completed orders."])
def test_ambiguous_requests_return_clarification(rag, monkeypatch, query):
    store, _, retriever = rag
    monkeypatch.setattr(store, "search", lambda *_: [
        VectorHit("table:products", 0.5), VectorHit("table:orders", 0.5),
    ])
    with pytest.raises(QueryFailure) as error:
        retriever.retrieve(query, SNAPSHOT)
    assert error.value.code == "schema_clarification"
    assert error.value.retrieval.status == "failed"


def test_missing_model_and_vector_error_are_actionable(rag, monkeypatch):
    store, model, retriever = rag

    def model_failure(_):
        raise EmbeddingUnavailable("Model cache unavailable.")

    with monkeypatch.context() as temporary:
        temporary.setattr(model, "encode", model_failure)
        with pytest.raises(QueryFailure) as error:
            retriever.retrieve("List customers", SNAPSHOT)
        assert (error.value.status, error.value.code) == (503, "embedding_unavailable")
        assert error.value.retrieval.status == "failed"

    def fail(*_):
        raise OSError("internal path or credential")

    with monkeypatch.context() as temporary:
        temporary.setattr(store, "search", fail)
        with pytest.raises(QueryFailure) as error:
            retriever.retrieve("List customers", SNAPSHOT)
        assert (error.value.status, error.value.code) == (503, "vector_unavailable")
        assert "credential" not in str(error.value)
    monkeypatch.setattr(store, "count", fail)
    with pytest.raises(VectorUnavailable):
        retriever.index(SchemaSnapshot({"products": {"id": "integer"}}))


def test_minilm_lazily_loads_one_cpu_model(monkeypatch):
    calls = []

    class Model:
        def __init__(self, name, **options):
            calls.append((name, options))

        def encode(self, texts, **kwargs):
            assert kwargs == {"batch_size": 16, "normalize_embeddings": True}
            return SimpleNamespace(tolist=lambda: [[0.5, 0.5] for _ in texts])

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(set_num_threads=lambda count: calls.append(count)))
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=Model))
    embedder = MiniLMEmbedder(local_files_only=True)
    assert calls == []
    assert embedder.encode(["first"]) == embedder.encode(["second"])
    assert calls == [2, (embedder.identity, {"device": "cpu", "local_files_only": True, "trust_remote_code": False})]


def test_minilm_reports_missing_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(EmbeddingUnavailable, match="unavailable"):
        MiniLMEmbedder(local_files_only=True).encode(["schema"])


class Database(StubDatabase):
    async def schema_snapshot(self):
        return SNAPSHOT


def test_api_sends_retrieved_context_to_groq_and_keeps_sql_boundary(rag, monkeypatch):
    _, _, retriever = rag
    monkeypatch.setenv("SCHEMA_MODE", "rag")
    database = Database()
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"sql": sql})))])
        for sql in (TOP_PRODUCTS, "SELECT name FROM private.products", "SELECT name FROM customers")
    ]
    completion = AsyncMock(side_effect=responses)
    model = GroqSQLGenerator(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=completion))), "test")
    body = {"json": {"question": "Top 5 products by revenue"}}
    success, failure, out_of_context = request(
        create_app(database, model, retriever), ("POST", "/api/query", body),
        ("POST", "/api/query", body), ("POST", "/api/query", body),
    )
    prompt = completion.await_args_list[0].kwargs["messages"][0]["content"]
    assert "shop.products:" in prompt and "shop.customers:" not in prompt
    assert "Join order_items.product_id = products.id" in prompt
    assert success.status_code == 200, success.text
    assert success.json()["retrieval"]["status"] == "ok"
    assert failure.status_code == 422 and failure.json()["error"]["code"] == "sql_rejected"
    assert failure.json()["retrieval"]["status"] == "ok"
    assert out_of_context.status_code == 422 and out_of_context.json()["error"]["code"] == "sql_rejected"
    assert len(database.executed) == 1


def test_retrieval_failure_does_not_call_generator(rag, monkeypatch):
    _, _, retriever = rag
    monkeypatch.setenv("SCHEMA_MODE", "rag")
    database, model = Database(), StubLLM(TOP_PRODUCTS)
    response, = request(create_app(database, model, retriever),
                        ("POST", "/api/query", {"json": {"question": "Show best products"}}))
    assert response.status_code == 422
    assert response.json()["retrieval"]["status"] == "failed"
    assert not model.calls and not database.executed


def test_spending_question_reaches_mocked_groq_and_sql_policy(rag, monkeypatch):
    _, _, retriever = rag
    monkeypatch.setenv("SCHEMA_MODE", "rag")
    sql = """
        SELECT c.name, SUM(i.quantity * i.unit_price) AS spending
        FROM customers c JOIN orders o ON c.id = o.customer_id
        JOIN order_items i ON o.id = i.order_id
        WHERE o.status = 'completed'
        GROUP BY c.name ORDER BY spending DESC, c.name LIMIT 3
    """
    completion = AsyncMock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"sql": sql})))],
    ))
    model = GroqSQLGenerator(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=completion))), "test")
    database = Database()
    response, = request(create_app(database, model, retriever), (
        "POST", "/api/query", {"json": {"question": "Show the top 3 customers by total spending on completed orders."}},
    ))
    assert response.status_code == 200, response.text
    assert response.json()["retrieval"]["status"] == "ok"
    assert database.executed == [response.json()["sql"]]
    prompt = completion.await_args.kwargs["messages"][0]["content"]
    assert "Customer spending is this same completed-order amount" in prompt
    assert "Join orders.customer_id = customers.id" in prompt
    assert "Join order_items.order_id = orders.id" in prompt


def test_baseline_has_no_embedding_or_vector_calls(monkeypatch, rag):
    _, model, retriever = rag
    monkeypatch.setenv("SCHEMA_MODE", "full")
    database, llm = Database(), StubLLM(TOP_PRODUCTS)
    response, = request(create_app(database, llm, retriever),
                        ("POST", "/api/query", {"json": {"question": "Product revenue"}}))
    assert response.status_code == 200
    assert response.json()["retrieval"]["status"] == "skipped"
    assert "orders" in llm.calls[0][1]
    assert model.batches == []


def test_rag_prompt_for_single_table_does_not_disclose_other_fields(rag, monkeypatch):
    _, _, retriever = rag
    monkeypatch.setenv("SCHEMA_MODE", "rag")
    completion = AsyncMock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"sql":null}'))],
    ))
    model = GroqSQLGenerator(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=completion))), "test")
    request(create_app(Database(), model, retriever),
            ("POST", "/api/query", {"json": {"question": "List customer names"}}))
    prompt = completion.await_args.kwargs["messages"][0]["content"]
    assert "shop.customers:" in prompt
    assert "order_items" not in prompt and "unit_price" not in prompt
