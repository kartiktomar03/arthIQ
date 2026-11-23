import pytest

from backend.models import QueryFailure
from backend.sql_policy import validate_sql


CATALOG = {
    "products": {"id": "integer", "name": "varchar"},
    "orders": {"id": "integer", "status": "varchar"},
    "order_items": {"product_id": "integer", "order_id": "integer", "quantity": "integer", "unit_price": "numeric"},
}

TOP_PRODUCTS = """
SELECT p.name, SUM(i.quantity * i.unit_price) AS revenue
FROM products AS p
JOIN order_items AS i ON p.id = i.product_id
JOIN orders AS o ON i.order_id = o.id
WHERE o.status = 'completed'
GROUP BY p.name
ORDER BY revenue DESC, p.name
LIMIT 5
"""


@pytest.mark.parametrize("sql", [
    TOP_PRODUCTS,
    "SELECT COUNT(*) AS total FROM products",
    "SELECT name FROM products WHERE name LIKE 'UPDATE%'",
    "SELECT DISTINCT status FROM orders ORDER BY status",
])
def test_approves_supported_queries(sql):
    approved = validate_sql(sql, CATALOG)
    assert '"shop".' in approved.sql


@pytest.mark.parametrize("sql", [
    "DELETE FROM products",
    "SELECT id FROM products; SELECT id FROM products",
    "SELECT id INTO other FROM products",
    "SELECT id FROM products FOR UPDATE",
    "SELECT name FROM private.products",
    "SELECT relname FROM pg_catalog.pg_class",
    "SELECT p.list_price FROM products AS p",
    "SELECT secret FROM products",
    "SELECT id FROM products JOIN orders ON products.id = orders.id",
    "SELECT * FROM products",
    "SELECT name FROM products CROSS JOIN orders",
    "SELECT id FROM products WHERE id IN (SELECT id FROM orders)",
    "WITH q AS (SELECT id FROM products) SELECT id FROM q",
    "SELECT id FROM products UNION SELECT id FROM orders",
    "SELECT pg_catalog.pg_sleep(1) FROM products",
    "SELECT current_user FROM products",
    "SELECT id FROM products LIMIT ALL",
    "SELECT id FROM products LIMIT -1",
    "SELECT id FROM products OFFSET 999",
    "SELECT id FROM products TABLESAMPLE SYSTEM (1)",
])
def test_rejects_unsafe_unauthorized_or_unsupported_sql(sql):
    with pytest.raises(QueryFailure, match=".+") as error:
        validate_sql(sql, CATALOG)
    assert error.value.code == "sql_rejected"
