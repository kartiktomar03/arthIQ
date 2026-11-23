import pytest

from backend.datasources import OLIST
from backend.models import QueryFailure
from backend.olist import reader_pool
from backend.schema_context import SchemaSnapshot
from backend.schema_indexer import documents_for
from backend.sql_policy import validate_sql
from backend.main import create_app
from tests.test_api import StubDatabase, StubLLM, request

@pytest.mark.parametrize("dsn", [
    "postgresql://postgres@127.0.0.1/arthiq_olist",
    "postgresql://arthiq_olist_analytics@127.0.0.1/querypilot_ai",
    "postgresql://arthiq_olist_analytics@otherhost/arthiq_olist",
    "postgresql://arthiq_olist_analytics@127.0.0.1/arthiq_olist?user=postgres",
])
def test_olist_rejects_wrong_connection(dsn):
    with pytest.raises(QueryFailure):
        reader_pool(dsn)


def test_scoped_sql_and_metric_documents():
    catalog = {"orders":{"order_id":"text","order_status":"text"}, "order_items":{"order_id":"text","price":"numeric"}}
    assert '"olist"."orders"' in validate_sql("SELECT count(*) FROM orders",catalog,"olist").sql
    with pytest.raises(QueryFailure):
        validate_sql("SELECT count(*) FROM shop.orders",catalog,"olist")
    snapshot = SchemaSnapshot(catalog,schema="olist",glossary=OLIST.terms(),aliases=OLIST.aliases)
    text = " ".join(doc.text for doc in documents_for(snapshot))
    assert "olist.orders" in text and "BRL" in text and "unit_price" not in text


def test_unknown_and_unconfigured_never_use_demo(monkeypatch):
    monkeypatch.setenv("SCHEMA_MODE","full")
    monkeypatch.setenv("OLIST_ANALYTICS_DSN","")
    db=StubDatabase()
    llm=StubLLM("SELECT count(*) FROM orders")
    responses=request(create_app(db,llm),*(("POST","/api/query",{"json":{"question":"Count orders","datasource_id":key}})
                                         for key in ("other","olist")))
    assert [r.status_code for r in responses]==[422,503]
    assert not db.executed and not llm.calls


def test_six_questions_retrieve_scoped_schema():
    from backend.schema_context import ForeignKey
    from backend.schema_indexer import SchemaIndexer
    from backend.schema_retriever import SchemaRetriever
    from backend.vector_store import QdrantSchemaStore
    from evaluation.verify_olist import CASES
    from tests.test_rag import FakeEmbedder

    catalog = {"orders":{"order_id":"text","order_status":"text"},
               "customers":{"customer_id":"text","customer_unique_id":"text"},
               "sellers":{"seller_id":"text"},
               "order_items":{"order_id":"text","price":"numeric"}}
    join = ForeignKey("order_items","orders",(("order_id","order_id"),))
    snapshot = SchemaSnapshot(catalog,foreign_keys=(join,),schema="olist",glossary=OLIST.terms(),aliases=OLIST.aliases)
    store = QdrantSchemaStore(":memory:")
    try:
        retriever = SchemaRetriever(SchemaIndexer(FakeEmbedder(),store,"olist"),4,0.43)
        required = [{"orders"},{"orders"},{"customers"},{"order_items"},{"sellers"},{"orders","order_items"}]
        for (_, question, _), tables in zip(CASES,required,strict=True):
            result = retriever.retrieve(question,snapshot)
            assert set(result.context.catalog) == tables
            assert result.diagnostics.datasource_id == "olist"
            assert "shop." not in result.context.describe()
        assert join in result.context.relationships
    finally:
        store.close()
