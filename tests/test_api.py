import asyncio

import httpx
import pytest

from backend.main import create_app
from backend.models import ExecutionMetadata, QueryResponse, SQLProposal
from tests.test_policy import CATALOG, TOP_PRODUCTS


@pytest.fixture(autouse=True)
def full_schema_mode(monkeypatch):
    monkeypatch.setenv("SCHEMA_MODE", "full")


class StubDatabase:
    def __init__(self):
        self.executed = []

    async def catalog(self):
        return CATALOG

    async def execute(self, query):
        self.executed.append(query.sql)
        return QueryResponse(
            sql=query.sql, columns=["name", "revenue"], rows=[["Daypack", "175.00"]],
            execution=ExecutionMetadata(duration_ms=1, row_count=1, truncated=False),
        )


class StubLLM:
    def __init__(self, sql):
        self.sql = sql
        self.calls = []

    async def generate(self, question, catalog):
        self.calls.append((question, catalog))
        return SQLProposal(sql=self.sql)


def request(app, *requests):
    async def run():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                return [await client.request(method, path, **options) for method, path, options in requests]

    return asyncio.run(run())


def test_query_returns_approved_sql_and_structured_result():
    database = StubDatabase()
    model = StubLLM(TOP_PRODUCTS)
    question = "Which are the top 5 products by total revenue?"
    response, = request(create_app(database, model), ("POST", "/api/query", {"json": {"question": question}}))
    assert response.status_code == 200, response.text
    assert model.calls == [(question, CATALOG)]
    result = response.json()
    assert result["columns"] == ["name", "revenue"]
    assert result["rows"] == [["Daypack", "175.00"]]
    assert result["execution"]["row_count"] == 1
    assert database.executed == [result["sql"]]


def test_rejected_sql_never_executes():
    database = StubDatabase()
    response, = request(
        create_app(database, StubLLM("DELETE FROM products")),
        ("POST", "/api/query", {"json": {"question": "Count the products"}}),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sql_rejected"
    assert database.executed == []


def test_unanswerable_and_empty_requests():
    database = StubDatabase()
    model = StubLLM(None)
    health, empty, response = request(
        create_app(database, model),
        ("GET", "/api/health", {}),
        ("POST", "/api/query", {"json": {"question": " "}}),
        ("POST", "/api/query", {"json": {"question": "Weather forecast?"}}),
    )
    assert health.json() == {"status": "ok"}
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "invalid_question"
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unanswerable"
    assert len(model.calls) == 1
    assert database.executed == []
