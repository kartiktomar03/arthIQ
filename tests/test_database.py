import asyncio
import os
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import httpx
import pytest

from backend.database import AnalyticsDatabase
from backend.main import create_app
from backend.models import QueryFailure
from backend.sql_policy import validate_sql
from tests.test_api import StubLLM
from tests.test_policy import CATALOG, TOP_PRODUCTS


class Cursor:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.fetched = 0

    async def fetch(self, size):
        from itertools import islice

        rows = list(islice(self.rows, size))
        self.fetched += len(rows)
        return rows


@pytest.mark.parametrize("size,truncated", [(2, False), (3, True), (30, True)])
def test_cursor_fetches_at_most_one_extra_row(size, truncated):
    db = AnalyticsDatabase(None, 100, 2, 1024)
    cursor = Cursor([(Decimal("12.30"),)] * size)
    assert asyncio.run(db._collect(cursor, ["revenue"])) == ([["12.30"], ["12.30"]], truncated)
    assert cursor.fetched == min(size, 3)


def test_byte_cap():
    db = AnalyticsDatabase(None, 100, 20, 25)
    cursor = Cursor([("small",), ("much-too-large-to-fit",)])
    assert asyncio.run(db._collect(cursor, ["name"])) == ([["small"]], True)


@pytest.mark.parametrize("role", ["querypilot_analytics", "querypilot_migrator"])
def test_executor_enforces_role_transaction_and_timeouts(role):
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=role)
    conn.execute = AsyncMock()
    statement = MagicMock()
    statement.get_attributes.return_value = [SimpleNamespace(name="name")]
    statement.cursor = AsyncMock(return_value=Cursor([("Daypack",)]))
    conn.prepare = AsyncMock(return_value=statement)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    db = AnalyticsDatabase(pool, 750, 2, 1024)
    approved = validate_sql("SELECT name FROM products", CATALOG)

    if role == "querypilot_analytics":
        assert asyncio.run(db.execute(approved)).rows == [["Daypack"]]
        conn.prepare.assert_awaited_once_with(approved.sql)
    else:
        with pytest.raises(QueryFailure) as error:
            asyncio.run(db.execute(approved))
        assert error.value.code == "database_role"
        conn.prepare.assert_not_awaited()

    conn.transaction.assert_called_once_with(readonly=True)
    settings = conn.execute.await_args_list
    assert settings[0].args == ("SET LOCAL search_path = pg_catalog",)
    assert "statement_timeout" in settings[1].args[0] and "lock_timeout" in settings[1].args[0]
    assert settings[1].args[1:] == ("750ms", "500ms")


def test_postgres_seed_and_read_only_role(monkeypatch):
    dsn = os.environ.get("QP_TEST_ANALYTICS_DSN")
    if not dsn:
        pytest.skip("Set QP_TEST_ANALYTICS_DSN to the seeded disposable PostgreSQL database.")
    monkeypatch.setenv("ANALYTICS_DSN", dsn)
    monkeypatch.setenv("MAX_ROWS", "200")
    monkeypatch.setenv("SCHEMA_MODE", "full")

    async def check():
        async with asyncpg.create_pool(dsn, min_size=1, max_size=1) as pool:
            db = AnalyticsDatabase(pool, 3000, 200, 262144)
            catalog = await db.catalog()
            assert set(catalog) == {"categories", "customers", "products", "orders", "order_items"}
            snapshot = await db.schema_snapshot()
            assert snapshot.catalog == catalog
            assert snapshot.primary_keys["order_items"] == ("order_id", "product_id")
            assert {key.describe() for key in snapshot.foreign_keys} == {
                "products.category_id = categories.id", "orders.customer_id = customers.id",
                "order_items.order_id = orders.id", "order_items.product_id = products.id",
            }
            app = create_app(generator=StubLLM(TOP_PRODUCTS))
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/query", json={"question": "Which are the top 5 products by total revenue?"}
                    )
            assert response.status_code == 200, response.text
            assert response.json()["rows"] == [
                ["Daypack", "175.00"], ["Monitor Stand", "175.00"],
                ["Desk Lamp", "140.00"], ["Pour-over Kit", "135.00"], ["Insulated Mug", "112.00"],
            ]
            assert response.json()["execution"]["row_count"] == 5
            limited = AnalyticsDatabase(pool, 3000, 2, 262144)
            result = await limited.execute(validate_sql("SELECT name FROM products ORDER BY name", catalog))
            assert len(result.rows) == 2 and result.execution.truncated
            async with pool.acquire() as conn:
                assert await conn.fetchval("SHOW default_transaction_read_only") == "on"
                assert not await conn.fetchval(
                    "SELECT has_table_privilege(current_user, 'shop.products', 'UPDATE')"
                )
                assert not await conn.fetchval(
                    "SELECT has_database_privilege(current_user, current_database(), 'TEMP')"
                )

    asyncio.run(check())
